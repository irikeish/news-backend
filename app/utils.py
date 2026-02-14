from app.models.location import Location
from app.config import settings

RADIUS_KM_BY_SCOPE: dict[str, float] = {
    "city": 50.0,
    "state": 300.0,
    "country": 1000.0,
}
DEFAULT_RADIUS_KM = settings.default_radius_km


def radius_km_for_location(location: Location) -> float:
    """Return appropriate radius in km based on Location scope."""
    at = (location.address_type or "").lower().strip()
    if at in RADIUS_KM_BY_SCOPE:
        return RADIUS_KM_BY_SCOPE[at]

    return DEFAULT_RADIUS_KM
