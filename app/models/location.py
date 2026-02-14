"""Location model for geocoding results."""

from typing import List, Optional
from pydantic import BaseModel


class Location(BaseModel):
    lat: float
    lon: float
    address_type: Optional[str] = None
    class_name: Optional[str] = None
    bounding_box: Optional[List[float]] = None
