"""Beanie Article document model."""

from datetime import date, datetime
from typing import Literal, Optional

import pymongo
from beanie import Document
from bson import ObjectId
from pydantic import BaseModel, Field, field_validator
from pymongo import IndexModel


class Point(BaseModel):
    """GeoJSON Point for 2dsphere index."""

    type: Literal["Point"] = "Point"
    coordinates: list[float]


class Article(Document):
    """News article document."""

    id: str = Field(..., description="UUID from source")
    title: str

    @field_validator("id", mode="before")
    @classmethod
    def coerce_id_to_str(cls, v: object) -> str:
        if isinstance(v, ObjectId):
            return str(v)
        return str(v) if v is not None else ""

    description: str
    url: str
    publication_date: datetime

    @field_validator("publication_date", mode="before")
    @classmethod
    def coerce_to_datetime(cls, v: object) -> datetime:
        if isinstance(v, datetime):
            return v
        if isinstance(v, date):
            return datetime(v.year, v.month, v.day)
        if isinstance(v, str):
            return datetime.fromisoformat(v.replace("Z", "+00:00"))
        raise ValueError(f"Cannot parse publication_date: {v}")
    source_name: str
    category: list[str]
    relevance_score: float
    llm_summary: Optional[str] = None
    location: Optional[Point] = None

    class Settings:
        name = "articles"
        use_state_management = True
        use_revision = False
        indexes = [
            [("publication_date", pymongo.DESCENDING)],
            [("category", pymongo.ASCENDING), ("publication_date", pymongo.DESCENDING)],
            [("relevance_score", pymongo.DESCENDING), ("publication_date", pymongo.DESCENDING)],
            IndexModel([("location", pymongo.GEOSPHERE), ("publication_date", pymongo.DESCENDING)]),
            IndexModel(
                [("title", pymongo.TEXT), ("description", pymongo.TEXT)],
                name="title_description_text",
            ),
        ]
