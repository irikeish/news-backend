"""News retrieval API entry point."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from redis.asyncio import Redis

from app.api.v1.news import router as news_router
from app.db.init import init_db
from app.exceptions import (
    EXCEPTION_TO_CODE,
    EXCEPTION_TO_STATUS,
    NewsAppError,
)
from app.cache import set_valkey_client as set_cache_valkey_client
from app.config import settings
from app.models.schemas import ErrorDetail, ErrorResponse, RootResponse

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

_logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize DB on startup, close on shutdown."""
    await init_db()

    valkey_client = None
    _logger.info(
        "cache_backend=%s valkey_url=%s", settings.cache_backend, settings.valkey_url
    )
    if settings.cache_backend == "valkey":
        try:
            valkey_client = Redis.from_url(
                settings.valkey_url,
                decode_responses=True,
            )
            await valkey_client.ping()
            set_cache_valkey_client(valkey_client)
            _logger.info("Valkey connected for cache")
        except Exception as e:
            _logger.warning("Valkey unavailable, cache disabled: %s", e, exc_info=True)
            set_cache_valkey_client(None)

    yield

    if valkey_client:
        await valkey_client.aclose()


app = FastAPI(lifespan=lifespan, title="News API", version="0.1.0")


@app.exception_handler(NewsAppError)
async def news_app_exception_handler(request, exc: NewsAppError):
    """Map NewsAppError and subclasses to HTTP ErrorResponse."""
    status = EXCEPTION_TO_STATUS.get(type(exc), 500)
    code = EXCEPTION_TO_CODE.get(type(exc), "INTERNAL")
    payload = ErrorResponse(
        success=False,
        error=ErrorDetail(
            code=code,
            message=str(exc),
            details=exc.details if hasattr(exc, "details") and exc.details else None,
        ),
    )
    return JSONResponse(status_code=status, content=payload.model_dump())


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc: RequestValidationError):
    """Map FastAPI validation errors to ErrorResponse format."""
    errors = exc.errors()
    details = [f"{e.get('loc', ())}: {e.get('msg', '')}" for e in errors]
    payload = ErrorResponse(
        success=False,
        error=ErrorDetail(
            code="VALIDATION_ERROR",
            message="Invalid or missing parameters",
            details=details,
        ),
    )
    return JSONResponse(status_code=400, content=payload.model_dump())


@app.exception_handler(Exception)
async def generic_exception_handler(request, exc: Exception):
    """Map unhandled exceptions to ErrorResponse format."""
    _logger.exception("Unhandled exception: %s", exc)
    payload = ErrorResponse(
        success=False,
        error=ErrorDetail(
            code="INTERNAL",
            message="Internal server error",
            details=None,
        ),
    )
    return JSONResponse(status_code=500, content=payload.model_dump())


@app.get("/", response_model=RootResponse)
def root():
    """Health check."""
    return RootResponse(message="News API", docs="/docs")


app.include_router(news_router, prefix="/api/v1")
