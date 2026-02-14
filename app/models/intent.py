"""Parsed intent from LLM query parsing."""

from typing import Literal

from pydantic import BaseModel
from app.config import settings

IntentKind = Literal["category", "source", "search", "score", "nearby"]


class ParsedIntent(BaseModel):
    """Structured query intent."""

    intent: list[IntentKind] = []
    category: str | None = None
    source: str | None = None
    keywords: str | None = None
    threshold: float | None = None
    location_name: str | None = None
    radius_km: float | None = settings.default_radius_km
    longitude: float | None = None
    latitude: float | None = None
