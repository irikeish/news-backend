"""Cache helper – Valkey/Redis only."""

import json
import logging
from typing import Any, Awaitable, Callable

_logger = logging.getLogger(__name__)

_valkey_client: Any = None
_key_prefix = "cache:"


def set_valkey_client(client: Any) -> None:
    """Set the async Redis/Valkey client. Call from lifespan when available."""
    global _valkey_client
    _valkey_client = client


def _key(k: str) -> str:
    return _key_prefix + k


async def get(key: str) -> str | None:
    """Get cached value by key. Returns None on miss, error, or when Valkey unavailable."""
    if not _valkey_client:
        return None
    try:
        raw = await _valkey_client.get(_key(key))
        return raw if isinstance(raw, str) else (raw.decode() if raw else None)
    except Exception as e:
        _logger.warning("Cache get failed: %s", e)
        return None


async def set(key: str, value: str, ttl: int = 3600) -> None:
    """Store value with TTL (seconds). No-op when Valkey unavailable."""
    if not _valkey_client:
        return
    try:
        await _valkey_client.setex(_key(key), ttl, value)
    except Exception as e:
        _logger.warning("Cache set failed: %s", e)


async def delete(key: str) -> None:
    """Delete key from cache. No-op when Valkey unavailable."""
    if not _valkey_client:
        return
    try:
        await _valkey_client.delete(_key(key))
    except Exception as e:
        _logger.warning("Cache delete failed: %s", e)


async def get_or_load(
    key: str,
    loader: Callable[[], Awaitable[Any]],
    ttl: int = 300,
    as_json: bool = True,
) -> Any:
    """
    Get value from cache.
    If missing, load using async loader, store with TTL, return value.

    - loader must be async function
    - Automatically JSON serializes/deserializes if as_json=True
    """

    cached = await get(key)

    if cached:
        if as_json:
            try:
                return json.loads(cached)
            except Exception:
                _logger.warning("Cache JSON decode failed for key=%s", key)
        else:
            return cached

    value = await loader()

    try:
        to_store = json.dumps(value) if as_json else value
        await set(key, to_store, ttl=ttl)
    except Exception as e:
        _logger.warning("Cache store failed for key=%s: %s", key, e)

    return value
