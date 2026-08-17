
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Dict, List, Optional

from .models import GPSRecord, HistoryPoint, InventoryRecord, ScanMethod

NOW = datetime(2026, 8, 16, 14, 0, 0)  


class SourceUnavailableError(Exception):
    """Raised when a source has no data for the requested asset."""


class GPSSource:
    """Stub client for a GPS tracking API."""

    def __init__(self, records: Dict[str, GPSRecord]):
        self._records = records

    def query(self, asset_id: str) -> GPSRecord:
        if asset_id not in self._records:
            raise SourceUnavailableError(f"GPS: no fix on file for {asset_id}")
        return self._records[asset_id]


class InventorySource:
    """Stub client for a warehouse inventory database."""

    def __init__(self, records: Dict[str, InventoryRecord]):
        self._records = records

    def query(self, asset_id: str) -> InventoryRecord:
        if asset_id not in self._records:
            raise SourceUnavailableError(f"Inventory: no record on file for {asset_id}")
        return self._records[asset_id]


class HistoryStore:
    """
    Stub client for previously-reconciled location history, used by the agent
    for plausibility / velocity checks (Rule R4). In production this would be
    the agent's own prior output, persisted.
    """

    def __init__(self, histories: Dict[str, List[HistoryPoint]]):
        self._histories = histories

    def recent(self, asset_id: str, limit: int = 5) -> List[HistoryPoint]:
        points = self._histories.get(asset_id, [])
        return sorted(points, key=lambda p: p.timestamp, reverse=True)[:limit]



GPS_RECORDS: Dict[str, GPSRecord] = {
    # Scenario 1: recency mismatch 
  
    "AST-1001": GPSRecord(
        asset_id="AST-1001",
        timestamp=NOW - timedelta(hours=3, minutes=10),
        latitude=40.7128, longitude=-74.0060,   # WH-A
        accuracy_radius_m=12, satellites=9,
        raw_note="Last fix before tag went out of signal range in transit.",
    ),
    #  Scenario 2: signal quality difference 
    
    "AST-1002": GPSRecord(
        asset_id="AST-1002",
        timestamp=NOW - timedelta(minutes=4),
        latitude=40.7290, longitude=-73.9880,   
        accuracy_radius_m=180, satellites=3,
        raw_note="Poor fix, low satellite count, near building.",
    ),
    #  Scenario 3: logical inconsistency 

    "AST-1003": GPSRecord(
        asset_id="AST-1003",
        timestamp=NOW - timedelta(minutes=6),
        latitude=40.7130, longitude=-74.0058,   
        accuracy_radius_m=8, satellites=10,
        raw_note="Stable fix, consistent with recent history.",
    ),
    #  Scenario 4: physical implausibility (GPS multipath/spoofing) 
    
    "AST-1004": GPSRecord(
        asset_id="AST-1004",
        timestamp=NOW - timedelta(minutes=2),
        latitude=41.9000, longitude=-73.5000,   
        accuracy_radius_m=15, satellites=8,
        raw_note="Single fix, no corroborating trend.",
    ),
    #  Scenario 5: logical inconsistency, but UNCORROBORATED 
  
    "AST-1005": GPSRecord(
        asset_id="AST-1005",
        timestamp=NOW - timedelta(minutes=5),   
        latitude=40.6890, longitude=-74.0447,   
        accuracy_radius_m=20, satellites=7,
        raw_note="Single fix after the manifest scan; tag has not reported again since.",
    ),
}

INVENTORY_RECORDS: Dict[str, InventoryRecord] = {
    "AST-1001": InventoryRecord(
        asset_id="AST-1001",
        timestamp=NOW - timedelta(minutes=12),
        location_code="WH-B-04",
        scan_method=ScanMethod.RFID_GATE,
        event_type="SCAN_IN",
        operator_id=None,
        manifest_id=None,
        raw_note="Automatic gate read on entry to WH-B receiving dock.",
    ),
    "AST-1002": InventoryRecord(
        asset_id="AST-1002",
        timestamp=NOW - timedelta(minutes=6),
        location_code="WH-C-19",
        scan_method=ScanMethod.RFID_GATE,
        event_type="CYCLE_COUNT",
        operator_id=None,
        manifest_id=None,
        raw_note="Automated cycle-count sweep, gate antenna 3.",
    ),
    "AST-1003": InventoryRecord(
        asset_id="AST-1003",
        timestamp=NOW - timedelta(minutes=20),
        location_code="SHIPPED_OUT",
        scan_method=ScanMethod.BARCODE,
        event_type="SHIPPED_OUT",
        operator_id="OP-2291",
        manifest_id="MAN-88831",
        raw_note="Barcode scanned onto outbound manifest MAN-88831.",
    ),
    "AST-1004": InventoryRecord(
        asset_id="AST-1004",
        timestamp=NOW - timedelta(hours=1, minutes=45),
        location_code="WH-B-11",
        scan_method=ScanMethod.BARCODE,
        event_type="SCAN_IN",
        operator_id="OP-1140",
        manifest_id=None,
        raw_note="Routine shelf scan during morning count.",
    ),
    "AST-1005": InventoryRecord(
        asset_id="AST-1005",
        timestamp=NOW - timedelta(minutes=10),
        location_code="SHIPPED_OUT",
        scan_method=ScanMethod.BARCODE,
        event_type="SHIPPED_OUT",
        operator_id="OP-3387",
        manifest_id="MAN-77410",
        raw_note="Barcode scanned onto outbound manifest MAN-77410.",
    ),
}

HISTORY_POINTS: Dict[str, List[HistoryPoint]] = {
    "AST-1001": [
        HistoryPoint(NOW - timedelta(hours=8), 40.7128, -74.0060, "WH-A-08"),
        HistoryPoint(NOW - timedelta(hours=5), 40.7128, -74.0060, "WH-A-08"),
    ],
    "AST-1002": [
        HistoryPoint(NOW - timedelta(hours=6), 40.7306, -73.9866, "WH-C-19"),
    ],
    "AST-1003": [
      
        HistoryPoint(NOW - timedelta(hours=2), 40.7127, -74.0061, "WH-A-14"),
        HistoryPoint(NOW - timedelta(minutes=15), 40.7129, -74.0059, "WH-A-14"),
        HistoryPoint(NOW - timedelta(minutes=10), 40.7130, -74.0058, "WH-A-14"),
    ],
    "AST-1004": [
        HistoryPoint(NOW - timedelta(hours=3), 40.6892, -74.0445, "WH-B-11"),
        HistoryPoint(NOW - timedelta(minutes=40), 40.6893, -74.0446, "WH-B-11"),
    ],
    "AST-1005": [
       
        HistoryPoint(NOW - timedelta(hours=4), 40.6891, -74.0446, "WH-B-11"),
    ],
}


def build_default_sources() -> tuple[GPSSource, InventorySource, HistoryStore]:
    return (
        GPSSource(GPS_RECORDS),
        InventorySource(INVENTORY_RECORDS),
        HistoryStore(HISTORY_POINTS),
    )