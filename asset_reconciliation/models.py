
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class SourceName(str, Enum):
    GPS = "GPS"
    INVENTORY = "INVENTORY"


class ScanMethod(str, Enum):
    """How an inventory record was captured. Not all scans are equally trustworthy."""

    BARCODE = "BARCODE"          
    RFID_GATE = "RFID_GATE"     
    MANUAL_ENTRY = "MANUAL_ENTRY" 

@dataclass(frozen=True)
class GPSRecord:
    asset_id: str
    timestamp: datetime
    latitude: float
    longitude: float
    accuracy_radius_m: float   
    satellites: int            
    raw_note: str = ""


@dataclass(frozen=True)
class InventoryRecord:
    asset_id: str
    timestamp: datetime
    location_code: str         
    scan_method: ScanMethod
    event_type: str            
    operator_id: Optional[str] = None
    manifest_id: Optional[str] = None   
    raw_note: str = ""

    @property
    def is_hard_departure_event(self) -> bool:
        """Events that assert the asset physically left the building."""
        return self.event_type in ("SHIPPED_OUT", "SCAN_OUT")


@dataclass(frozen=True)
class HistoryPoint:
    """A previously-confirmed (already-reconciled) location, used for plausibility checks."""

    timestamp: datetime
    latitude: float
    longitude: float
    location_code: str
