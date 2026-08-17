
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

from .geofences import distance_to_warehouse_m, geofence_containing, haversine_distance_m, warehouse_for_code
from .models import GPSRecord, HistoryPoint, InventoryRecord, SourceName


RECENCY_TOLERANCE = 30 * 60          
STALE_GAP_THRESHOLD = 2 * 60 * 60    
FRESHNESS_DECAY_SECONDS = 6 * 60 * 60  
MAX_PLAUSIBLE_SPEED_KMH = 120.0      
MIN_TIME_FOR_SPEED_CHECK_S = 30      

SCAN_METHOD_BASE_QUALITY = {
    "BARCODE": 0.80,
    "RFID_GATE": 0.90,
    "MANUAL_ENTRY": 0.45,
}


@dataclass
class ConflictFlag:
    kind: str            
    detail: str


@dataclass
class Decision:
    winner: SourceName
    rule_id: str
    rule_name: str
    rationale: str
    confidence: float
    gps_discarded: bool = False        
    conflicts: List[ConflictFlag] = field(default_factory=list)



def gps_quality_score(gps: GPSRecord) -> float:
    """0..1 quality score from accuracy radius and satellite count, blended evenly."""
    accuracy_component = max(0.0, 1.0 - gps.accuracy_radius_m / 500.0)
    sat_component = min(1.0, gps.satellites / 12.0)
    return round(0.5 * accuracy_component + 0.5 * sat_component, 3)


def inventory_quality_score(inv: InventoryRecord) -> float:
    """0..1 quality score from scan method, boosted for hard events with a manifest."""
    base = SCAN_METHOD_BASE_QUALITY.get(inv.scan_method.value, 0.5)
    if inv.is_hard_departure_event and inv.manifest_id:
        base = min(1.0, base + 0.08)
    return round(base, 3)


def freshness_score(timestamp: datetime, now: datetime) -> float:
    age_s = max(0.0, (now - timestamp).total_seconds())
    return math.exp(-age_s / FRESHNESS_DECAY_SECONDS)


def combined_confidence(quality: float, freshness: float) -> float:
    """Overall confidence blends signal quality and how fresh the reading is."""
    return round(0.6 * quality + 0.4 * freshness, 3)


# Individuals roles

def rule_r4_physical_implausibility(
    gps: GPSRecord, inv: InventoryRecord, history: List[HistoryPoint], now: datetime
) -> Optional[Decision]:
    """
    Reject a GPS fix if it implies a velocity no ground asset could achieve
    given the last known corroborated position. A single wild reading with
    no corroborating trend is treated as sensor noise (multipath / bounce /
    spoofing), not as evidence of movement.
    """
    if not history:
        return None

    last = max(history, key=lambda p: p.timestamp)
    dt_s = (gps.timestamp - last.timestamp).total_seconds()
    if dt_s < MIN_TIME_FOR_SPEED_CHECK_S:
        return None  # too close in time to compute a meaningful speed

    dist_m = haversine_distance_m(last.latitude, last.longitude, gps.latitude, gps.longitude)
    implied_speed_kmh = (dist_m / 1000.0) / (dt_s / 3600.0)

    if implied_speed_kmh <= MAX_PLAUSIBLE_SPEED_KMH:
        return None

    flag = ConflictFlag(
        kind="physical_implausibility",
        detail=(
            f"GPS fix implies {implied_speed_kmh:,.0f} km/h relative to last confirmed "
            f"position {dt_s/60:.1f} min earlier -- exceeds the {MAX_PLAUSIBLE_SPEED_KMH:.0f} km/h "
            f"ceiling for a ground asset. Treated as sensor noise, not movement."
        ),
    )
    inv_q = inventory_quality_score(inv)
    inv_f = freshness_score(inv.timestamp, now)
    return Decision(
        winner=SourceName.INVENTORY,
        rule_id="R4",
        rule_name="Physical-implausibility rejection",
        rationale=(
            f"GPS reading discarded as implausible ({flag.detail}). Falling back to inventory "
            f"as the only remaining source, independent of its own recency."
        ),
        confidence=combined_confidence(inv_q, inv_f),
        gps_discarded=True,
        conflicts=[flag],
    )


def rule_r1_logical_inconsistency(
    gps: GPSRecord, inv: InventoryRecord, history: List[HistoryPoint], now: datetime
) -> Optional[Decision]:
    """
    Catch cases where the inventory record asserts a state ("shipped out",
    "scanned out") that directly contradicts what GPS is currently showing
    (still inside the same geofence it was in before the claimed departure).

    Resolution: count how many *post-event* GPS/history points corroborate
    continued presence. Two or more independent corroborating points beat a
    single scan event (scans are one-time and error-prone; a sustained GPS
    trend is not). A single GPS point alone is not enough to override a
    hard, attributable scan event with a manifest ID.
    """
    if not inv.is_hard_departure_event:
        return None

    departed_warehouse = warehouse_for_code(inv.location_code) if inv.location_code != "SHIPPED_OUT" else None
    gps_warehouse = geofence_containing(gps.latitude, gps.longitude)

    
    prior_points = [p for p in history if p.timestamp <= inv.timestamp]
    if not prior_points:
        return None
    prior_wh = warehouse_for_code(max(prior_points, key=lambda p: p.timestamp).location_code)

    if gps_warehouse is None or prior_wh is None or gps_warehouse.code != prior_wh.code:
        return None  

    post_event_points = [p for p in history if p.timestamp > inv.timestamp]
    corroborating = [
        p for p in post_event_points
        if warehouse_for_code(p.location_code) is not None and warehouse_for_code(p.location_code).code == gps_warehouse.code
    ]
    
    gps_is_post_event = gps.timestamp > inv.timestamp
    corroboration_count = len(corroborating) + (1 if gps_is_post_event else 0)

    if corroboration_count == 0:
        
        return None


    flag = ConflictFlag(
        kind="logical_inconsistency",
        detail=(
            f"Inventory logged a hard departure event ('{inv.event_type}', manifest="
            f"{inv.manifest_id or 'none'}) at {inv.timestamp.isoformat()}, but GPS shows the "
            f"asset still inside {gps_warehouse.name} ({gps_warehouse.code}) at "
            f"{gps.timestamp.isoformat()}, {corroboration_count} corroborating point(s) after "
            f"the claimed departure."
        ),
    )

    gps_q = gps_quality_score(gps)
    gps_f = freshness_score(gps.timestamp, now)
    inv_q = inventory_quality_score(inv)
    inv_f = freshness_score(inv.timestamp, now)

    if corroboration_count >= 2:
        return Decision(
            winner=SourceName.GPS,
            rule_id="R1",
            rule_name="Logical-inconsistency resolution (corroboration favors GPS)",
            rationale=(
                f"{flag.detail} Multiple independent post-event GPS points corroborate continued "
                f"presence, which outweighs a single scan event -- most likely the wrong item was "
                f"scanned onto the manifest. GPS wins."
            ),
            confidence=combined_confidence(gps_q, gps_f),
            conflicts=[flag],
        )
    else:
        return Decision(
            winner=SourceName.INVENTORY,
            rule_id="R1",
            rule_name="Logical-inconsistency resolution (hard event favors inventory)",
            rationale=(
                f"{flag.detail} Only a single, uncorroborated GPS point contradicts the event. "
                f"A hard, attributable scan event with a manifest ID is treated as stronger "
                f"evidence than one uncorroborated GPS fix. Inventory wins, pending the next "
                f"GPS ping for confirmation."
            ),
            confidence=combined_confidence(inv_q, inv_f),
            conflicts=[flag],
        )


def rule_r2_recency(gps: GPSRecord, inv: InventoryRecord, now: datetime) -> Optional[Decision]:
    gap_s = abs((gps.timestamp - inv.timestamp).total_seconds())
    if gap_s <= STALE_GAP_THRESHOLD:
        return None

    gps_q, inv_q = gps_quality_score(gps), inventory_quality_score(inv)
    gps_f, inv_f = freshness_score(gps.timestamp, now), freshness_score(inv.timestamp, now)

    fresher_source = SourceName.GPS if gps.timestamp > inv.timestamp else SourceName.INVENTORY
    quality, freshness = (gps_q, gps_f) if fresher_source == SourceName.GPS else (inv_q, inv_f)
    stale_hours = gap_s / 3600.0

    flag = ConflictFlag(
        kind="recency_mismatch",
        detail=f"GPS timestamp and inventory timestamp differ by {stale_hours:.1f} hours, "
               f"exceeding the {STALE_GAP_THRESHOLD/3600:.0f}h staleness threshold.",
    )
    return Decision(
        winner=fresher_source,
        rule_id="R2",
        rule_name="Recency rule",
        rationale=(
            f"{flag.detail} The {fresher_source.value} record is the more recent observation "
            f"({(gps.timestamp if fresher_source == SourceName.GPS else inv.timestamp).isoformat()}) "
            f"and no logical or physical objection applies, so it is trusted."
        ),
        confidence=combined_confidence(quality, freshness),
        conflicts=[flag],
    )


def rule_r3_signal_quality(gps: GPSRecord, inv: InventoryRecord, now: datetime) -> Decision:
    """Fallback comparator for near-simultaneous readings: whichever has better signal quality wins."""
    gps_q, inv_q = gps_quality_score(gps), inventory_quality_score(inv)
    gps_f, inv_f = freshness_score(gps.timestamp, now), freshness_score(inv.timestamp, now)

    flag = ConflictFlag(
        kind="signal_quality_difference",
        detail=(
            f"Readings are within {RECENCY_TOLERANCE/60:.0f} min of each other "
            f"(GPS quality={gps_q:.2f} [{gps.satellites} sats, {gps.accuracy_radius_m:.0f}m radius], "
            f"Inventory quality={inv_q:.2f} [{inv.scan_method.value}])."
        ),
    )

    if abs(gps_q - inv_q) < 0.03:
        # Genuinely tied on quality -- hand off to the tie-break rule rather
        # than fabricate a preference.
        return rule_r5_tie_break(gps, inv, now, prior_flags=[flag])

    winner = SourceName.GPS if gps_q > inv_q else SourceName.INVENTORY
    quality, freshness = (gps_q, gps_f) if winner == SourceName.GPS else (inv_q, inv_f)
    return Decision(
        winner=winner,
        rule_id="R3",
        rule_name="Signal-quality rule",
        rationale=(
            f"{flag.detail} Timestamps are too close for recency to be a meaningful tiebreaker, "
            f"so the higher-quality signal ({winner.value}) is trusted."
        ),
        confidence=combined_confidence(quality, freshness),
        conflicts=[flag],
    )


def rule_r5_tie_break(
    gps: GPSRecord, inv: InventoryRecord, now: datetime, prior_flags: Optional[List[ConflictFlag]] = None
) -> Decision:
    gps_q, inv_q = gps_quality_score(gps), inventory_quality_score(inv)
    gps_f, inv_f = freshness_score(gps.timestamp, now), freshness_score(inv.timestamp, now)
    gps_conf, inv_conf = combined_confidence(gps_q, gps_f), combined_confidence(inv_q, inv_f)

    winner = SourceName.GPS if gps_conf >= inv_conf else SourceName.INVENTORY
    winning_conf = max(gps_conf, inv_conf)

    return Decision(
        winner=winner,
        rule_id="R5",
        rule_name="Weighted-confidence tie-break",
        rationale=(
            f"No other rule produced a clear winner. Falling back to overall weighted confidence "
            f"(quality*0.6 + freshness*0.4): GPS={gps_conf:.3f} vs Inventory={inv_conf:.3f}. "
            f"{winner.value} wins by weighted confidence."
        ),
        confidence=winning_conf,
        conflicts=(prior_flags or []),
    )


# ---------------------------------------------------------------------------
# Rule engine entry point
# ---------------------------------------------------------------------------


class RuleEngine:
    """Evaluates the ordered rule chain and always returns exactly one Decision."""

    def decide(
        self,
        gps: GPSRecord,
        inv: InventoryRecord,
        history: List[HistoryPoint],
        now: datetime,
    ) -> Decision:
        all_conflicts: List[ConflictFlag] = []

        # Always record a recency-mismatch / signal-quality observation for
        # the audit trail even when it isn't the deciding factor, so the
        # report is honest about *everything* that disagreed, not just the
        # thing that ultimately mattered.
        gap_s = abs((gps.timestamp - inv.timestamp).total_seconds())
        if gap_s > RECENCY_TOLERANCE:
            all_conflicts.append(ConflictFlag(
                kind="recency_mismatch",
                detail=f"Timestamps differ by {gap_s/3600:.2f}h.",
            ))
        gps_q, inv_q = gps_quality_score(gps), inventory_quality_score(inv)
        if abs(gps_q - inv_q) >= 0.15:
            all_conflicts.append(ConflictFlag(
                kind="signal_quality_difference",
                detail=f"GPS quality={gps_q:.2f} vs Inventory quality={inv_q:.2f}.",
            ))

        for rule_fn, needs_history in (
            (rule_r4_physical_implausibility, True),
            (rule_r1_logical_inconsistency, True),
        ):
            decision = rule_fn(gps, inv, history, now) if needs_history else rule_fn(gps, inv, now)
            if decision is not None:
                decision.conflicts = _merge_flags(all_conflicts, decision.conflicts)
                return decision

        decision = rule_r2_recency(gps, inv, now)
        if decision is not None:
            decision.conflicts = _merge_flags(all_conflicts, decision.conflicts)
            return decision

        decision = rule_r3_signal_quality(gps, inv, now)
        decision.conflicts = _merge_flags(all_conflicts, decision.conflicts)
        return decision


def _merge_flags(base: List[ConflictFlag], extra: List[ConflictFlag]) -> List[ConflictFlag]:
    seen = set()
    merged = []
    for f in base + extra:
        key = (f.kind, f.detail)
        if key not in seen:
            seen.add(key)
            merged.append(f)
    return merged
