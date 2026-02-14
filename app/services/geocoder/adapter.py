"""Abstract geocoder service interface."""

from abc import ABC, abstractmethod

from app.models.location import Location


class GeocoderService(ABC):
    """Abstract interface for geocoding providers.

    Implementations convert location names to Location (lat, lon).
    Extend with new providers (Google, Mapbox, etc.) by implementing this interface.
    """

    @abstractmethod
    async def geocode(self, location_name: str) -> Location | None:
        """
        Convert a location name to coordinates.

        Args:
            location_name: Place name (e.g. "Palo Alto", "New York").

        Returns:
            Location with lat/lon or None if the location cannot be geocoded.
        """
        ...
