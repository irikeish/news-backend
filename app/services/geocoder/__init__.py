"""Nominatim (OpenStreetMap) geocoder provider."""

import asyncio
import logging
import time

import httpx

from app.config import settings
from app.models.location import Location
from app.services.geocoder.adapter import GeocoderService

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
_logger = logging.getLogger(__name__)

# Rate limit: Nominatim expects <=1 req/sec
_nominatim_lock = asyncio.Lock()
_last_nominatim_request: float = 0


class NominatimGeocoderService(GeocoderService):
    """Geocoding via Nominatim (OpenStreetMap). Free, no API key required."""

    def __init__(
        self,
        *,
        user_agent: str | None = None,
        base_url: str = NOMINATIM_URL,
    ):
        self._user_agent = user_agent or settings.nominatim_user_agent
        self._base_url = base_url

    async def geocode(self, location_name: str) -> Location | None:
        """Geocode location name via Nominatim API."""
        if not location_name or not location_name.strip():
            return None

        await self._rate_limit()

        headers = {"User-Agent": self._user_agent}
        params = {
            "q": location_name.strip(),
            "format": "json",
            "limit": 1,
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    self._base_url,
                    params=params,
                    headers=headers,
                )
                response.raise_for_status()
                data = response.json()
        except Exception as e:
            _logger.warning("Nominatim geocoding failed for %r: %s", location_name, e)
            return None

        if not data or not isinstance(data, list):
            return None

        item = data[0]
        if not isinstance(item, dict):
            return None

        lat = item.get("lat")
        lon = item.get("lon")
        if lat is None or lon is None:
            return None

        try:
            lat_f = float(lat)
            lon_f = float(lon)
        except (TypeError, ValueError):
            return None

        address_type = (
            item.get("addresstype")
            if isinstance(item.get("addresstype"), str)
            else None
        )
        class_name = item.get("class") if isinstance(item.get("class"), str) else None
        bbox: list[float] | None = None
        raw_bbox = item.get("boundingbox")
        if isinstance(raw_bbox, (list, tuple)) and len(raw_bbox) >= 4:
            try:
                bbox = [float(x) for x in raw_bbox[:4]]
            except (TypeError, ValueError):
                pass

        return Location(
            lat=lat_f,
            lon=lon_f,
            address_type=address_type,
            class_name=class_name,
            bounding_box=bbox,
        )

    async def _rate_limit(self) -> None:
        """Enforce Nominatim 1 req/sec policy."""
        global _last_nominatim_request

        async with _nominatim_lock:
            now = time.monotonic()
            elapsed = now - _last_nominatim_request
            if elapsed < 1.0:
                await asyncio.sleep(1.0 - elapsed)
            _last_nominatim_request = time.monotonic()


geocode = NominatimGeocoderService().geocode
