"""Request and response Pydantic schemas."""

from datetime import datetime
from typing import Generic, Literal, TypeVar, Optional

from pydantic import BaseModel, Field

T = TypeVar("T")


class RootResponse(BaseModel):
    """Health check response."""

    message: str
    docs: str


class BaseNewsRequest(BaseModel):
    limit: int = Field(5, ge=1, le=20)
    offset: int = Field(0, ge=0)


class NewsUnifiedRequest(BaseNewsRequest):
    """Request for unified news endpoint"""

    query: str = Field(..., min_length=1)


class NewsCategoryRequest(BaseNewsRequest):
    """Request for category-based news."""

    category: str = Field(..., min_length=1)


class NewsSearchRequest(BaseNewsRequest):
    """Request for text search news."""

    query: str = Field(..., min_length=1)


class NewsNearbyRequest(BaseNewsRequest):
    """Request for location-based nearby news."""

    lat: float = Field(..., ge=-90, le=90)
    lon: float = Field(..., ge=-180, le=180)
    radius_km: float = Field(10, ge=0.1, le=500)


class NewsTrendingRequest(BaseNewsRequest):
    lat: float = Field(..., ge=-90, le=90)
    lon: float = Field(..., ge=-180, le=180)
    radius_km: float = Field(10, ge=0.1, le=500)


class NewsSourceRequest(BaseNewsRequest):
    source: str


class NewsScoreRequest(BaseNewsRequest):
    threshold: float = Field(
        ...,
        ge=0,
        le=1,
        description="Relevance score threshold (0–1). Use decimal format e.g. 0.8",
        examples=[0.8],
    )


class IngestResponseData(BaseModel):
    """Ingest endpoint response payload."""

    loaded: int


class ArticleResponse(BaseModel):
    """Single article in API response."""

    id: str
    title: str
    description: str
    url: str
    publication_date: datetime
    source_name: str
    category: list[str]
    relevance_score: float
    llm_summary: str | None = None
    latitude: float | None = None
    longitude: float | None = None


class ArticleTrendingResponse(ArticleResponse):
    trending_score: float


class TrendingMeta(BaseModel):
    lat: float
    lon: float
    radius: float
    cached: bool
    total: int
    limit: int
    offset: int
    has_more: bool


class NewsTrendingResponse(BaseModel):
    articles: list[ArticleTrendingResponse]
    meta: TrendingMeta


class Meta(BaseModel):
    """Response metadata."""

    total: int
    limit: int
    offset: int
    has_more: bool
    query: Optional[str]
    intent: Optional[str]


class NewsResponseData(BaseModel):
    """News endpoint payload."""

    articles: list[ArticleResponse]
    meta: Meta


class ApiResponse(BaseModel, Generic[T]):
    """Generic success envelope."""

    success: Literal[True] = True
    data: T


class ErrorDetail(BaseModel):
    """Error detail in error response."""

    code: str
    message: str
    details: list[str] | None = None


class ErrorResponse(BaseModel):
    """Error response envelope."""

    success: Literal[False] = False
    error: ErrorDetail
