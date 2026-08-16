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

class ReconciliationAgent:
    def __init__(self, gps: GPSSource, inventory: InventorySource, history: HistoryStore, now: datetime):
        self.gps = gps
        self.inventory = inventory
        self.history = history
        self.now = now
        self.rule_engine = RuleEngine()

    def reconcile(self, asset_id: str) -> AssetReconciliationResult:
                    plan: List[PlanStep] = []
                    step_no = 1
            
                    plan.append(PlanStep(step_no, "QUERY_GPS", f"Request latest GPS fix for {asset_id}."))
                    step_no += 1
                    gps_record: Optional[GPSRecord] = None
                    try:
                        gps_record = self.gps.query(asset_id)
                    except SourceUnavailableError as e:
                        plan.append(PlanStep(step_no, "GPS_UNAVAILABLE", str(e)))
                        step_no += 1
            
                    plan.append(PlanStep(step_no, "QUERY_INVENTORY", f"Request latest inventory record for {asset_id}."))
                    step_no += 1
                    inv_record: Optional[InventoryRecord] = None
                    try:
                        inv_record = self.inventory.query(asset_id)
                    except SourceUnavailableError as e:
                        plan.append(PlanStep(step_no, "INVENTORY_UNAVAILABLE", str(e)))
                        step_no += 1
            
                    plan.append(PlanStep(step_no, "QUERY_HISTORY", f"Pull recent confirmed history for {asset_id} for plausibility checks."))
                    step_no += 1
                    history: List[HistoryPoint] = self.history.recent(asset_id)
            
                    if gps_record is not None and inv_record is None:
                        plan.append(PlanStep(step_no, "SINGLE_SOURCE", "Only GPS available; using it directly, reduced confidence."))
                        decision = Decision(
                            winner=SourceName.GPS, rule_id="R0", rule_name="Single-source fallback",
                            rationale="Inventory has no record for this asset; GPS is the only available source.",
                            confidence=0.5, conflicts=[],
                        )
                        return self._finalize(asset_id, plan, gps_record, inv_record, decision)
            
                    if inv_record is not None and gps_record is None:
                        plan.append(PlanStep(step_no, "SINGLE_SOURCE", "Only inventory available; using it directly, reduced confidence."))
                        decision = Decision(
                            winner=SourceName.INVENTORY, rule_id="R0", rule_name="Single-source fallback",
                            rationale="GPS has no fix for this asset; inventory is the only available source.",
                            confidence=0.5, conflicts=[],
                        )
                        return self._finalize(asset_id, plan, gps_record, inv_record, decision)
            
                    if gps_record is None and inv_record is None:
                        raise SourceUnavailableError(f"Neither source has data for {asset_id}; cannot reconcile.")
            
                    plan.append(PlanStep(
                        step_no, "COMPARE",
                        f"GPS reports coordinates near "
                        f"{geofence_containing(gps_record.latitude, gps_record.longitude).name if geofence_containing(gps_record.latitude, gps_record.longitude) else 'no known warehouse'} "
                        f"@ {gps_record.timestamp.isoformat()}; "
                        f"Inventory reports '{inv_record.location_code}' via {inv_record.event_type} @ {inv_record.timestamp.isoformat()}.",
                    ))
                    step_no += 1
            
                    plan.append(PlanStep(step_no, "APPLY_RULES", "Evaluate rule chain R4 -> R1 -> R2 -> R3 -> R5 in order; first applicable rule decides."))
                    step_no += 1
                    decision = self.rule_engine.decide(gps_record, inv_record, history, self.now)
            
                    plan.append(PlanStep(
                        step_no, "DECIDE",
                        f"Rule {decision.rule_id} ({decision.rule_name}) selected {decision.winner.value} "
                        f"with confidence {decision.confidence:.2f}.",
                    ))
            
                    return self._finalize(asset_id, plan, gps_record, inv_record, decision)
            
    def _finalize(
                    self,
                    asset_id: str,
                    plan: List[PlanStep],
                    gps_record: Optional[GPSRecord],
                    inv_record: Optional[InventoryRecord],
                    decision: Decision,
                ) -> AssetReconciliationResult:
                    if decision.winner == SourceName.GPS and gps_record is not None:
                        wh = geofence_containing(gps_record.latitude, gps_record.longitude)
                        final_code = wh.code if wh else "UNMAPPED_COORDINATES"
                        final_coords = (gps_record.latitude, gps_record.longitude)
                        ts = gps_record.timestamp
                    else:
                        final_code = inv_record.location_code if inv_record else "UNKNOWN"
                        wh = warehouse_for_code(inv_record.location_code) if inv_record else None
                        final_coords = (wh.latitude, wh.longitude) if wh else None
                        ts = inv_record.timestamp if inv_record else self.now
            
                    return AssetReconciliationResult(
                        asset_id=asset_id,
                        plan=plan,
                        gps_record=gps_record,
                        inventory_record=inv_record,
                        decision=decision,
                        final_location_code=final_code,
                        final_coordinates=final_coords,
                        timestamp_used=ts,
                    )
            
    