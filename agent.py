from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

from .geofences import geofence_containing, warehouse_for_code
from .models import GPSRecord, HistoryPoint, InventoryRecord, SourceName
from .rules import Decision, RuleEngine
from .sources import GPSSource, HistoryStore, InventorySource, SourceUnavailableError


@dataclass
class PlanStep:
    step_number: int
    action: str
    detail: str


@dataclass
class AssetReconciliationResult:
    asset_id: str
    plan: List[PlanStep]
    gps_record: Optional[GPSRecord]
    inventory_record: Optional[InventoryRecord]
    decision: Decision
    final_location_code: str
    final_coordinates: Optional[tuple]
    timestamp_used: datetime


