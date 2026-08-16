
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Warehouse:
    code: str            
    
    name: str
    latitude: float
    longitude: float
    radius_m: float       


WAREHOUSES = [
    Warehouse(code="WH-A", name="North Distribution Center", latitude=40.7128, longitude=-74.0060, radius_m=300),
    Warehouse(code="WH-B", name="South Fulfillment Hub", latitude=40.6892, longitude=-74.0445, radius_m=250),
    Warehouse(code="WH-C", name="East Staging Yard", latitude=40.7306, longitude=-73.9866, radius_m=400),
]

_WAREHOUSE_BY_CODE = {w.code: w for w in WAREHOUSES}


def haversine_distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two points in meters."""
    R = 6371000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def warehouse_for_code(code: str) -> Optional[Warehouse]:
    """Look up a warehouse by its inventory location-code prefix (e.g. 'WH-A-12' -> WH-A)."""
    prefix = code.split("-")[0] + "-" + code.split("-")[1] if code.count("-") >= 2 else code
    return _WAREHOUSE_BY_CODE.get(prefix)


def geofence_containing(latitude: float, longitude: float) -> Optional[Warehouse]:
    """Return the warehouse whose geofence contains this point, if any."""
    for w in WAREHOUSES:
        if haversine_distance_m(latitude, longitude, w.latitude, w.longitude) <= w.radius_m:
            return w
    return None

def distance_to_warehouse_m(latitude: float, longitude: float, warehouse_code: str) -> Optional[float]:
    w = _WAREHOUSE_BY_CODE.get(warehouse_code)
    if w is None:
        return None
    return haversine_distance_m(latitude, longitude, w.latitude, w.longitude)
