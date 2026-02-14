"""Generate simulated user events for trending testing."""

import logging
import random
from datetime import datetime, timedelta, timezone

from app.db.init import get_database, init_db
from app.models.article import Article, Point
from app.models.user_event import UserEvent

logger = logging.getLogger(__name__)

INDIA_LAT_RANGE = (8.0, 35.0)
INDIA_LON_RANGE = (68.0, 97.0)
JITTER_DEG = 0.05
JITTER_DEG_CENTERED = 0.02


async def generate_events(
    count: int = 10000,
    users: int = 500,
    center_lat: float | None = None,
    center_lon: float | None = None,
) -> int:
    await init_db()
    db = get_database()
    articles_cursor = db[Article.Settings.name].find(
        {"location": {"$exists": True}, "location.type": "Point"},
        {"id": 1, "location": 1},
    )
    articles = await articles_cursor.to_list(length=None)
    if not articles:
        logger.error("No articles with location in DB; run 'load' first")
        return 0

    def _coords(doc):
        loc = doc.get("location")
        if not loc or loc.get("type") != "Point":
            return None
        coords = loc.get("coordinates")
        if not coords or len(coords) < 2:
            return None
        return coords[1], coords[0]  # lat, lon (GeoJSON is [lon, lat])

    article_pool = []
    for a in articles:
        c = _coords(a)
        if c:
            lat, lon = c
            article_pool.append((str(a.get("id") or a.get("_id", "")), lat, lon))
    if not article_pool:
        logger.error("No articles with valid lat/lon; run 'load' with geographic data")
        return 0

    now = datetime.now(timezone.utc)
    since = now - timedelta(hours=48)
    events: list[UserEvent] = []

    use_center = center_lat is not None and center_lon is not None
    jitter = JITTER_DEG_CENTERED if use_center else JITTER_DEG

    for _ in range(count):
        aid, art_lat, art_lon = random.choice(article_pool)
        if use_center:
            base_lat, base_lon = center_lat, center_lon
        else:
            base_lat, base_lon = art_lat, art_lon
        jitter_lat = random.uniform(-jitter, jitter)
        jitter_lon = random.uniform(-jitter, jitter)
        lon_coord = max(
            INDIA_LON_RANGE[0], min(INDIA_LON_RANGE[1], base_lon + jitter_lon)
        )
        lat_coord = max(
            INDIA_LAT_RANGE[0], min(INDIA_LAT_RANGE[1], base_lat + jitter_lat)
        )

        user_id = f"user_{random.randint(1, users)}"
        event_type: str = random.choices(["view", "click"], weights=[80, 20])[0]
        ts = since + timedelta(seconds=random.uniform(0, 48 * 3600))
        location = Point(type="Point", coordinates=[lon_coord, lat_coord])
        events.append(
            UserEvent(
                article_id=aid,
                user_id=user_id,
                event_type=event_type,
                timestamp=ts,
                location=location,
            )
        )

    result = await UserEvent.insert_many(events)
    logger.info("Inserted %d events into user_events", len(result.inserted_ids))
    return len(result.inserted_ids)
