"""News API endpoints."""

import logging
from fastapi import APIRouter, Depends

from app.models.article import Article
from app.models.intent import ParsedIntent
from app.models.schemas import (
    ApiResponse,
    ArticleResponse,
    ArticleTrendingResponse,
    NewsCategoryRequest,
    NewsNearbyRequest,
    NewsResponseData,
    NewsSearchRequest,
    NewsTrendingRequest,
    NewsTrendingResponse,
    NewsUnifiedRequest,
    NewsSourceRequest,
    NewsScoreRequest,
)
from app.services.news import NewsService
from app.services.trending import TrendingService


def _article_to_response(a: Article) -> ArticleResponse:
    """Map domain Article to API ArticleResponse."""
    lat = lon = None
    if a.location and len(a.location.coordinates) >= 2:
        lon, lat = a.location.coordinates[0], a.location.coordinates[1]
    return ArticleResponse(
        id=a.id,
        title=a.title,
        description=a.description,
        url=a.url,
        publication_date=a.publication_date,
        source_name=a.source_name,
        category=a.category,
        relevance_score=a.relevance_score,
        llm_summary=a.llm_summary,
        latitude=lat,
        longitude=lon,
    )


def _to_news_response(result) -> NewsResponseData:
    """Map NewsResult to API NewsResponseData."""
    return NewsResponseData(
        articles=[_article_to_response(a) for a in result.articles],
        meta=result.meta,
    )


def _to_trending_response(result) -> NewsTrendingResponse:
    """Map TrendingResult to API NewsTrendingResponse."""
    return NewsTrendingResponse(
        articles=[
            ArticleTrendingResponse(
                **_article_to_response(item.article).model_dump(),
                trending_score=item.trending_score,
            )
            for item in result.items
        ],
        meta=result.meta,
    )


router = APIRouter(prefix="/news", tags=["news"])

logger = logging.getLogger(__name__)


def get_news_service() -> NewsService:
    return NewsService()


def get_trending_service() -> TrendingService:
    return TrendingService()


def _intent_category(params: NewsCategoryRequest) -> ParsedIntent:
    return ParsedIntent(
        intent=["category"],
        category=params.category,
    )


def _intent_search(params: NewsSearchRequest) -> ParsedIntent:
    return ParsedIntent(
        intent=["search"],
        keywords=params.query,
    )


def _intent_source(params: NewsSourceRequest) -> ParsedIntent:
    return ParsedIntent(
        intent=["source"],
        source=params.source,
    )


def _intent_score(params: NewsScoreRequest) -> ParsedIntent:
    return ParsedIntent(
        intent=["score"],
        threshold=params.threshold,
    )


def _intent_nearby(params: NewsNearbyRequest) -> ParsedIntent:
    return ParsedIntent(
        intent=["nearby"],
        latitude=params.lat,
        longitude=params.lon,
        radius_km=params.radius_km,
    )


@router.get(
    "",
    response_model=ApiResponse[NewsResponseData],
)
async def get_news_unified(
    params: NewsUnifiedRequest = Depends(),
    service: NewsService = Depends(get_news_service),
):
    """Unified endpoint: LLM parses query and routes internally."""
    result = await service.handle_unified_query(
        query=params.query,
        limit=params.limit,
        offset=params.offset,
    )
    return ApiResponse(data=_to_news_response(result))


@router.get(
    "/category",
    response_model=ApiResponse[NewsResponseData],
)
async def get_news_category(
    params: NewsCategoryRequest = Depends(),
    service: NewsService = Depends(get_news_service),
):
    intent = _intent_category(params)
    result = await service.fetch_by_intent(
        intent=intent,
        limit=params.limit,
        offset=params.offset,
    )
    if not result.articles:
        logger.warning("No articles found for category %r", params.category)
    return ApiResponse(data=_to_news_response(result))


@router.get(
    "/search",
    response_model=ApiResponse[NewsResponseData],
)
async def get_news_search(
    params: NewsSearchRequest = Depends(),
    service: NewsService = Depends(get_news_service),
):
    intent = _intent_search(params)
    result = await service.fetch_by_intent(
        intent=intent,
        limit=params.limit,
        offset=params.offset,
    )
    if not result.articles:
        logger.warning("No articles found for search %r", params.query)
    return ApiResponse(data=_to_news_response(result))


@router.get(
    "/source",
    response_model=ApiResponse[NewsResponseData],
)
async def get_news_source(
    params: NewsSourceRequest = Depends(),
    service: NewsService = Depends(get_news_service),
):
    intent = _intent_source(params)
    result = await service.fetch_by_intent(
        intent=intent,
        limit=params.limit,
        offset=params.offset,
    )
    if not result.articles:
        logger.warning("No articles found for source %r", params.source)
    return ApiResponse(data=_to_news_response(result))


@router.get(
    "/score",
    response_model=ApiResponse[NewsResponseData],
)
async def get_news_score(
    params: NewsScoreRequest = Depends(),
    service: NewsService = Depends(get_news_service),
):
    intent = _intent_score(params)
    result = await service.fetch_by_intent(
        intent=intent,
        limit=params.limit,
        offset=params.offset,
    )
    if not result.articles:
        logger.warning("No articles found above threshold %s", params.threshold)
    return ApiResponse(data=_to_news_response(result))


@router.get(
    "/nearby",
    response_model=ApiResponse[NewsResponseData],
)
async def get_news_nearby(
    params: NewsNearbyRequest = Depends(),
    service: NewsService = Depends(get_news_service),
):
    intent = _intent_nearby(params)
    result = await service.fetch_by_intent(
        intent=intent,
        limit=params.limit,
        offset=params.offset,
    )
    if not result.articles:
        logger.warning(
            "No articles found nearby lat=%s lon=%s",
            params.lat,
            params.lon,
        )
    return ApiResponse(data=_to_news_response(result))


@router.get(
    "/trending",
    response_model=ApiResponse[NewsTrendingResponse],
)
async def get_news_trending(
    params: NewsTrendingRequest = Depends(),
    service: TrendingService = Depends(get_trending_service),
):
    result = await service.get_trending(
        lat=params.lat,
        lon=params.lon,
        radius_km=params.radius_km,
        limit=params.limit,
        offset=params.offset,
    )
    if not result.items:
        logger.debug("No trending articles for lat=%s lon=%s", params.lat, params.lon)
    return ApiResponse(data=_to_trending_response(result))
