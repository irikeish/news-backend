"""Trending news service"""

import json
import logging
from datetime import datetime, timedelta, timezone

from pydantic import BaseModel
from pymongo.errors import PyMongoError

from app.cache import get, set
from app.config import settings
from app.db.init import get_database
from app.models.article import Article
from app.models.schemas import TrendingMeta
from app.models.user_event import UserEvent
from app.services.geocoder import reverse_geocode
from app.services.news import NewsService

logger = logging.getLogger(__name__)


class TrendingItem(BaseModel):
    """Article with its trending score."""

    article: Article
    trending_score: float


class TrendingResult(BaseModel):
    """Domain result: articles with scores + meta."""

    items: list[TrendingItem]
    meta: TrendingMeta


TRENDING_CACHE_TTL = 300
RADIUS_BUCKETS = [10, 50, 200, 500]
TRENDING_TOP_N = 100
WEIGHT_CLICK = 3
WEIGHT_VIEW = 1
RECENCY_HOURS = 48
DECAY_HALFLIFE_HOURS = 12


class TrendingService:
    def __init__(self, news_service: NewsService | None = None):
        self._news = news_service or NewsService()
        self._collection = get_database()[UserEvent.Settings.name]

    @staticmethod
    def _snap_radius(radius_km: float) -> int:
        """Snap radius to nearest bucket to reduce cache key variations."""
        for bucket in RADIUS_BUCKETS:
            if radius_km <= bucket:
                return bucket
        return RADIUS_BUCKETS[-1]

    async def _build_cache_key(
        self, lat: float, lon: float, radius_km: float
    ) -> str:
        """Build cache key using reverse geocoding with grid fallback."""
        bucket = self._snap_radius(radius_km)

        location = await reverse_geocode(lat, lon)
        if location:
            return f"trending:{location}:{bucket}"

        # group coordinates within 11 KM
        grid_coord = f"{round(lat, 1)}:{round(lon, 1)}"
        return f"trending:geo:{grid_coord}:{bucket}"

    async def get_trending(
        self,
        lat: float,
        lon: float,
        radius_km: float = settings.default_radius_km,
        limit: int = 5,
        offset: int = 0,
    ) -> TrendingResult:
        cache_key = await self._build_cache_key(lat, lon, radius_km)
        logger.debug("Trending cache lookup key=%s", cache_key)
        cached = await get(cache_key)
        if cached:
            try:
                ranked = json.loads(cached)
                logger.info("Trending cache hit for key=%s", cache_key)
                return await self._build_response_from_ranked(
                    ranked=ranked,
                    lat=lat,
                    lon=lon,
                    radius_km=radius_km,
                    limit=limit,
                    offset=offset,
                    cached=True,
                )
            except (json.JSONDecodeError, TypeError, KeyError) as e:
                logger.warning("Trending cache decode failed key=%s: %s", cache_key, e)

        logger.debug(
            "Trending cache miss, running aggregation lat=%.2f lon=%.2f", lat, lon
        )
        ranked = await self._compute_ranked(lat, lon, radius_km)
        if not ranked:
            return TrendingResult(
                items=[],
                meta=TrendingMeta(
                    lat=lat,
                    lon=lon,
                    radius=radius_km,
                    cached=False,
                    total=0,
                    limit=limit,
                    offset=offset,
                    has_more=False,
                ),
            )
        try:
            await set(
                cache_key,
                json.dumps(ranked, default=str),
                ttl=TRENDING_CACHE_TTL,
            )
        except Exception as e:
            logger.warning("Trending cache set failed key=%s: %s", cache_key, e)

        return await self._build_response_from_ranked(
            ranked=ranked,
            lat=lat,
            lon=lon,
            radius_km=radius_km,
            limit=limit,
            offset=offset,
            cached=False,
        )

    async def _compute_ranked(
        self, lat: float, lon: float, radius_km: float
    ) -> list[dict]:
        now = datetime.now(timezone.utc)
        since = now - timedelta(hours=RECENCY_HOURS)
        max_dist_m = radius_km * 1000

        try:
            pipeline = [
                {
                    "$geoNear": {
                        "near": {"type": "Point", "coordinates": [lon, lat]},
                        "distanceField": "_distance",
                        "maxDistance": max_dist_m,
                        "spherical": True,
                    }
                },
                {"$match": {"timestamp": {"$gte": since}}},
                {
                    "$addFields": {
                        "interaction_weight": {
                            "$cond": {
                                "if": {"$eq": ["$event_type", "click"]},
                                "then": WEIGHT_CLICK,
                                "else": WEIGHT_VIEW,
                            }
                        }
                    }
                },
                {
                    "$group": {
                        "_id": {"article_id": "$article_id", "user_id": "$user_id"},
                        "interaction_weight": {"$max": "$interaction_weight"},
                        "timestamp": {"$max": "$timestamp"},
                        "_distance": {"$min": "$_distance"},
                    }
                },
                {
                    "$addFields": {
                        "hours_since": {
                            "$divide": [
                                {"$subtract": ["$$NOW", "$timestamp"]},
                                3600000,
                            ]
                        }
                    }
                },
                {"$addFields": {"distance_km": {"$divide": ["$_distance", 1000]}}},
                {
                    "$addFields": {
                        "decay": {
                            "$exp": {
                                "$multiply": [
                                    -1,
                                    {"$divide": ["$hours_since", DECAY_HALFLIFE_HOURS]},
                                ]
                            }
                        }
                    }
                },
                {
                    "$addFields": {
                        "geo_weight": {
                            "$divide": [1, {"$add": [1, "$distance_km"]}],
                        }
                    }
                },
                {
                    "$addFields": {
                        "user_score": {
                            "$multiply": [
                                "$interaction_weight",
                                "$decay",
                                "$geo_weight",
                            ]
                        }
                    }
                },
                {
                    "$group": {
                        "_id": "$_id.article_id",
                        "trending_score": {"$sum": "$user_score"},
                        "unique_users": {"$sum": 1},
                    }
                },
                {"$sort": {"trending_score": -1}},
                {"$limit": TRENDING_TOP_N},
            ]

            cursor = self._collection.aggregate(pipeline)
            results = await cursor.to_list(length=TRENDING_TOP_N)
            ranked = [
                {
                    "article_id": r["_id"],
                    "trending_score": round(r["trending_score"], 2),
                }
                for r in results
            ]
            logger.debug(
                "Trending aggregation returned %d article_ids for lat=%.2f lon=%.2f",
                len(ranked),
                lat,
                lon,
            )
            return ranked
        except PyMongoError as e:
            logger.error("Trending aggregation failed: %s", e, exc_info=True)
            return []

    async def _build_response_from_ranked(
        self,
        ranked: list[dict],
        lat: float,
        lon: float,
        radius_km: float,
        limit: int,
        offset: int,
        cached: bool,
    ) -> TrendingResult:
        total = len(ranked)
        page = ranked[offset : offset + limit]
        article_ids = [p["article_id"] for p in page]
        scores_by_id = {p["article_id"]: p["trending_score"] for p in page}

        if not article_ids:
            return TrendingResult(
                items=[],
                meta=TrendingMeta(
                    lat=lat,
                    lon=lon,
                    radius=radius_km,
                    cached=cached,
                    total=total,
                    limit=limit,
                    offset=offset,
                    has_more=False,
                ),
            )

        articles = await self._news.fetch_articles_by_ids(article_ids)
        id_to_article = {a.id: a for a in articles}

        items: list[TrendingItem] = []
        for aid in article_ids:
            art = id_to_article.get(aid)
            if not art:
                continue
            score = scores_by_id.get(aid, 0.0)
            items.append(TrendingItem(article=art, trending_score=score))

        logger.info(
            "Trending returned %d articles for lat=%.2f lon=%.2f offset=%d (cached=%s)",
            len(items),
            lat,
            lon,
            offset,
            cached,
        )
        return TrendingResult(
            items=items,
            meta=TrendingMeta(
                lat=lat,
                lon=lon,
                radius=radius_km,
                cached=cached,
                total=total,
                limit=limit,
                offset=offset,
                has_more=offset + len(items) < total,
            ),
        )
