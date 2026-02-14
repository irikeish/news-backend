"""Beanie Article document model."""

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
    publication_date: str
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
            "category",
            "source_name",
            "relevance_score",
            [("publication_date", pymongo.DESCENDING)],
            IndexModel([("location", pymongo.GEOSPHERE)]),
            IndexModel(
                [("title", pymongo.TEXT), ("description", pymongo.TEXT)],
                name="title_description_text",
            ),
        ]
