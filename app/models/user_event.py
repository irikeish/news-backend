"""User event document for trending aggregation."""

from datetime import datetime
from typing import Literal

import pymongo
from beanie import Document
from pymongo import IndexModel

from app.models.article import Point


class UserEvent(Document):
    article_id: str
    user_id: str
    event_type: Literal["view", "click"]
    timestamp: datetime
    location: Point

    class Settings:
        name = "user_events"
        use_state_management = False
        use_revision = False
        indexes = [
            IndexModel([("location", pymongo.GEOSPHERE)]),
            IndexModel([("article_id", 1)]),
            IndexModel([("user_id", 1)]),
            IndexModel([("timestamp", pymongo.DESCENDING)]),
            IndexModel([("article_id", 1), ("user_id", 1)]),
        ]
