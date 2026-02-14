"""News data ingestion service."""

import json
import logging
from pathlib import Path

from pydantic import ValidationError as PydanticValidationError
from pymongo import ReplaceOne, UpdateOne

from app.db.init import get_database, init_db
from app.models.article import Article, Point
from app.services.llm import get_llm_adapter

logger = logging.getLogger(__name__)

BULK_WRITE_BATCH_SIZE = 1000
SUMMARY_BATCH_SIZE = 5


def normalize_article(item: dict) -> dict:
    """
    Normalize article dict for Article model.
    """
    data = dict(item)
    if "id" not in data:
        data["id"] = str(data.get("_id", ""))
    if "category" in data:
        cats = data["category"]
        if isinstance(cats, str):
            data["category"] = [cats.lower()]
        else:
            data["category"] = [
                c.lower() if isinstance(c, str) else str(c) for c in cats
            ]
    lat = data.get("latitude")
    lon = data.get("longitude")
    if lat is not None and lon is not None:
        data["location"] = Point(type="Point", coordinates=[float(lon), float(lat)])

    data.pop("latitude", None)
    data.pop("longitude", None)

    return data


async def load_news(
    path: Path, *, summarize: bool = False, n_summarize: int = 10
) -> int:
    """Load news from JSON file into MongoDB. Upserts by id to avoid duplicates."""
    await init_db()
    try:
        text = path.read_text()
        raw = json.loads(text)
    except (OSError, json.JSONDecodeError) as e:
        raise RuntimeError(f"Failed to read or parse {path}: {e}") from e

    if not isinstance(raw, list):
        raw = [raw]
    articles = []
    for item in raw:
        try:
            norm = normalize_article(item)
            articles.append(Article(**norm))
        except (ValueError, TypeError, KeyError, PydanticValidationError) as e:
            logger.warning("Skip invalid item: %s", e)
            continue
    if not articles:
        return 0
    collection = get_database()["articles"]
    for i in range(0, len(articles), BULK_WRITE_BATCH_SIZE):
        batch = articles[i : i + BULK_WRITE_BATCH_SIZE]
        requests = [
            ReplaceOne({"_id": art.id}, art.model_dump(by_alias=True), upsert=True)
            for art in batch
        ]
        await collection.bulk_write(requests)
        logger.info("Upserted articles %s-%s", i, i + len(batch))

    if summarize:
        llm = get_llm_adapter()
        max_summarize = min(n_summarize, len(articles))
        for i in range(0, max_summarize, SUMMARY_BATCH_SIZE):
            batch = articles[i : i + SUMMARY_BATCH_SIZE]
            logger.info("Summarizing articles %s-%s", i, i + len(batch))
            try:
                summaries = await llm.summarize_articles(batch)
                requests = [
                    UpdateOne({"_id": art.id}, {"$set": {"llm_summary": summaries[j]}})
                    for j, art in enumerate(batch)
                    if j < len(summaries) and summaries[j]
                ]
                await collection.bulk_write(requests)
                logger.info("Summarized articles %s-%s", i, i + len(batch))
            except Exception:
                logger.exception(
                    "Batch summarization failed for articles %s-%s", i, i + len(batch)
                )

    return len(articles)
