"""News retrieval service."""

import logging
import re
from datetime import datetime, timedelta
from typing import List, Tuple

from haversine import haversine
from pydantic import BaseModel

from app.config import settings
from app.db.init import get_database
from app.models.article import Article
from app.models.intent import ParsedIntent
from app.models.location import Location
from app.models.schemas import Meta
from app.services.geocoder import geocode
from app.utils import radius_km_for_location
from app.services.llm import get_llm_adapter
from app.services.llm.adapter import LLMAdapter

logger = logging.getLogger(__name__)


INTENT_PRIORITY = {
    "nearby": 1,
    "search": 2,
    "category": 3,
    "source": 4,
    "score": 5,
}


class NewsResult(BaseModel):
    """Domain result: articles + meta. Controller maps to API response."""

    articles: List[Article]
    meta: Meta


class NewsService:
    """News fetch service."""

    def __init__(self, llm_adapter: LLMAdapter | None = None):
        self._llm = llm_adapter or get_llm_adapter()
        self._collection = get_database()[Article.Settings.name]

    async def handle_unified_query(
        self,
        query: str,
        limit: int | None = None,
        offset: int = 0,
    ) -> NewsResult:

        limit = limit or settings.default_limit
        offset = max(offset, 0)

        parsed_intent = await self._llm.parse_query(query)
        parsed_intent._query = query
        logger.info("Parsed intent: %s", parsed_intent)

        return await self.fetch_by_intent(parsed_intent, limit, offset)

    async def fetch_by_intent(
        self,
        intent: ParsedIntent,
        limit: int,
        offset: int,
    ) -> NewsResult:

        intents = self._resolve_pipeline(intent.intent)
        logger.info("Intents: %s", intents)
        geocoded = await self._resolve_geolocation(intent, intents)
        logger.info("Geocoded: %s", geocoded)

        articles, total = await self._fetch_candidates(
            intent=intent,
            intents=intents,
            geocoded=geocoded,
        )

        articles = self._apply_intent_specific_ranking(
            articles,
            intent=intent,
            intents=intents,
            geocoded=geocoded,
            query=intent.keywords or "",
        )

        paginated = articles[offset : offset + limit]

        return NewsResult(
            articles=paginated,
            meta=Meta(
                total=total,
                limit=limit,
                offset=offset,
                has_more=offset + limit < total,
                query=getattr(intent, "_query", None)
                or intent.keywords
                or intent.category
                or "",
                intent=",".join(intent.intent or []),
            ),
        )

    def _resolve_pipeline(self, intents: list[str]) -> list[str]:
        if not intents:
            return ["search"]
        return sorted(intents, key=lambda x: INTENT_PRIORITY.get(x, 100))

    async def _resolve_geolocation(self, intent, intents):
        if "nearby" not in intents:
            return None
        loc = None
        if intent.latitude and intent.longitude:
            loc = Location(lat=intent.latitude, lon=intent.longitude)
        elif intent.location_name:
            loc = await geocode(intent.location_name)
            if loc and intent.radius_km is None:
                intent.radius_km = radius_km_for_location(loc)
        else:
            return None

        return loc

    async def _fetch_candidates(
        self,
        intent: ParsedIntent,
        intents: list[str],
        geocoded=None,
    ) -> Tuple[List[Article], int]:

        match = {
            "publication_date": {
                "$gte": datetime.now() - timedelta(days=settings.news_buffer_days)
            }
        }
        pipeline = []

        if "category" in intents and intent.category:
            match["category"] = intent.category.lower()

        if "source" in intents and intent.source:
            match["source_name"] = {
                "$regex": f"^{re.escape(intent.source)}$",
                "$options": "i",
            }

        if "score" in intents and intent.threshold is not None:
            match["relevance_score"] = {"$gte": intent.threshold}

        base_query = intent.keywords
        has_text_search = bool(base_query and base_query.strip())

        has_nearby = "nearby" in intents and geocoded is not None

        # $geoWithin when both text search + nearby, since mongo doesn't support $geoNear and $text together as top level match
        if has_text_search and has_nearby:
            radius_km = intent.radius_km or settings.default_radius_km

            match["location"] = {
                "$geoWithin": {
                    "$centerSphere": [
                        [geocoded.lon, geocoded.lat],
                        radius_km / 6371.0,
                    ]
                }
            }

            match["$text"] = {"$search": base_query}

            pipeline.append({"$match": match})

            pipeline.append({"$addFields": {"_textScore": {"$meta": "textScore"}}})

            pipeline.append({"$sort": {"_textScore": -1}})

        # $geoNear returns distance-sorted results
        elif has_nearby:
            radius_km = intent.radius_km or settings.default_radius_km

            pipeline.append(
                {
                    "$geoNear": {
                        "near": {
                            "type": "Point",
                            "coordinates": [geocoded.lon, geocoded.lat],
                        },
                        "distanceField": "_distance",
                        "maxDistance": radius_km * 1000,
                        "spherical": True,
                        "query": match,
                    }
                }
            )

        elif has_text_search:
            match["$text"] = {"$search": base_query}

            pipeline.append({"$match": match})

            pipeline.append({"$addFields": {"_textScore": {"$meta": "textScore"}}})
            pipeline.append({"$sort": {"_textScore": -1}})

        else:
            pipeline.append({"$match": match if match else {}})
            if "score" in intents:
                pipeline.append({"$sort": {"relevance_score": -1}})
            else:
                pipeline.append({"$sort": {"publication_date": -1}})

        pipeline.append({"$limit": 100})

        docs = await self._collection.aggregate(pipeline).to_list(length=100)

        articles = []

        for d in docs:
            mongo_score = d.get("_textScore", 0.0)
            distance = d.get("_distance", None)

            article = Article.model_validate(d)
            article._mongo_text_score = mongo_score
            article._geo_distance = distance

            articles.append(article)

        return articles, len(articles)

    def _apply_intent_specific_ranking(
        self,
        articles: List[Article],
        intent: ParsedIntent,
        intents: list[str],
        geocoded=None,
        query: str = "",
    ) -> List[Article]:
        if not articles:
            return articles

        if "nearby" in intents and geocoded:

            def _distance_key(a: Article) -> float:
                dist = getattr(a, "_geo_distance", None)
                if dist is not None:
                    return dist
                if a.location and len(a.location.coordinates) >= 2:
                    lon, lat = a.location.coordinates[0], a.location.coordinates[1]
                    return (
                        haversine(
                            (geocoded.lat, geocoded.lon),
                            (lat, lon),
                        )
                        * 1000
                    )
                return float("inf")

            articles = sorted(articles, key=_distance_key)
            logger.debug(
                "Ranked %d articles by distance (closest first)", len(articles)
            )
            return articles

        if "search" in intents:
            return self._apply_weighted_ranking(
                articles
            )

        if "score" in intents:
            articles = sorted(
                articles,
                key=lambda a: -(a.relevance_score or 0.0),
            )
            logger.debug(
                "Ranked %d articles by relevance_score (highest first)", len(articles)
            )
            return articles

        def _date_key(a: Article):
            dt = self._parse_publication_date(a.publication_date)
            return dt

        articles = sorted(articles, key=_date_key, reverse=True)
        logger.debug(
            "Ranked %d articles by publication_date (most recent first)", len(articles)
        )
        return articles

    def _parse_publication_date(self, pub_date: datetime | None) -> datetime:
        """Return publication date for sorting. Returns datetime.min for missing."""
        if not pub_date:
            return datetime.min
        return pub_date

    def _apply_weighted_ranking(
        self,
        articles: List[Article]
    ) -> List[Article]:
        """Search ranking: Mongo text score + relevance_score."""
        ranked = []
        for a in articles:
            mongo_score = min(getattr(a, "_mongo_text_score", 0.0) / 10.0, 1.0)
            relevance = a.relevance_score or 0.0
            final_score = 0.70 * mongo_score + 0.30 * relevance
            ranked.append((final_score, a))
        ranked.sort(key=lambda x: x[0], reverse=True)
        return [a for _, a in ranked]

    async def fetch_articles_by_ids(self, ids: List[str]) -> List[Article]:
        if not ids:
            return []
        docs = await self._collection.find(
            {"$or": [{"id": {"$in": ids}}, {"_id": {"$in": ids}}]}
        ).to_list(length=len(ids))
        id_to_doc = {str(d.get("id") or d.get("_id", "")): d for d in docs}
        articles: List[Article] = []
        for aid in ids:
            doc = id_to_doc.get(aid)
            if not doc:
                continue
            if "id" not in doc:
                doc = {**doc, "id": str(doc.get("_id", ""))}
            articles.append(Article.model_validate(doc))
        return articles
