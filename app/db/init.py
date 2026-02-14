"""Beanie database initialization."""

from beanie import init_beanie
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import PyMongoError

from app.config import settings
from app.exceptions import DatabaseUnavailableError
from app.models.article import Article
from app.models.user_event import UserEvent

_database = None


async def init_db() -> None:
    """Initialize Beanie with Motor and register document models."""
    global _database
    try:
        client = AsyncIOMotorClient(settings.resolved_mongodb_url)
        _database = client[settings.mongodb_db]
        await init_beanie(database=_database, document_models=[Article, UserEvent])
    except PyMongoError as e:
        raise DatabaseUnavailableError(f"Database connection failed: {e}") from e


def get_database():
    """Return the Motor database (call after init_db)."""
    if _database is None:
        raise DatabaseUnavailableError("Database not initialized")
    return _database
