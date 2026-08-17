"""Formats an AssetReconciliationResult as a human-readable report or JSON audit record."""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any, Dict

from .agent import AssetReconciliationResult
from .models import SourceName


def to_audit_dict(result: AssetReconciliationResult) -> Dict[str, Any]:
    d = result.decision
    gps = result.gps_record
    inv = result.inventory_record

    other_source_data = None
    if d.winner == SourceName.GPS and inv is not None:
        other_source_data = {
            "source": "INVENTORY",
            "location_code": inv.location_code,
            "timestamp": inv.timestamp.isoformat(),
            "event_type": inv.event_type,
            "scan_method": inv.scan_method.value,
        }
    elif d.winner == SourceName.INVENTORY and gps is not None:
        other_source_data = {
            "source": "GPS",
            "latitude": gps.latitude,
            "longitude": gps.longitude,
            "timestamp": gps.timestamp.isoformat(),
            "accuracy_radius_m": gps.accuracy_radius_m,
            "satellites": gps.satellites,
        }

    return {
        "asset_id": result.asset_id,
        "final_state": {
            "location_code": result.final_location_code,
            "coordinates": result.final_coordinates,
            "timestamp": result.timestamp_used.isoformat(),
            "winning_source": d.winner.value,
            "confidence": d.confidence,
            "gps_reading_discarded": d.gps_discarded,
        },
        "resolving_rule": {
            "id": d.rule_id,
            "name": d.rule_name,
            "rationale": d.rationale,
        },
        "conflicts_detected": [{"type": c.kind, "detail": c.detail} for c in d.conflicts],
        "losing_source_data": other_source_data,
        "plan": [{"step": p.step_number, "action": p.action, "detail": p.detail} for p in result.plan],
    }


def to_json(result: AssetReconciliationResult, indent: int = 2) -> str:
    return json.dumps(to_audit_dict(result), indent=indent)


def to_human_readable(result: AssetReconciliationResult) -> str:
    d = result.decision
    lines = []
    lines.append("=" * 78)
    lines.append(f"ASSET {result.asset_id}")
    lines.append("=" * 78)

    lines.append("\nPLAN")
    for step in result.plan:
        lines.append(f"  [{step.step_number}] {step.action}: {step.detail}")

    lines.append("\nRAW SOURCE DATA")
    if result.gps_record:
        g = result.gps_record
        lines.append(
            f"  GPS       @ {g.timestamp.isoformat()}  lat={g.latitude:.4f} lon={g.longitude:.4f} "
            f"accuracy=±{g.accuracy_radius_m:.0f}m sats={g.satellites}"
        )
    else:
        lines.append("  GPS       -- no data")
    if result.inventory_record:
        i = result.inventory_record
        lines.append(
            f"  INVENTORY @ {i.timestamp.isoformat()}  location={i.location_code} "
            f"event={i.event_type} method={i.scan_method.value} manifest={i.manifest_id or '-'}"
        )
    else:
        lines.append("  INVENTORY -- no data")

    if d.conflicts:
        lines.append("\nCONFLICTS DETECTED")
        for c in d.conflicts:
            lines.append(f"  - [{c.kind}] {c.detail}")
    else:
        lines.append("\nCONFLICTS DETECTED\n  - none")

    lines.append(f"\nRESOLVING RULE: {d.rule_id} -- {d.rule_name}")
    lines.append(f"  {d.rationale}")

    lines.append("\nFINAL RECONCILED STATE")
    lines.append(f"  Winning source : {d.winner.value}"
                 + ("  (GPS reading discarded as invalid)" if d.gps_discarded else ""))
    lines.append(f"  Location       : {result.final_location_code}")
    if result.final_coordinates:
        lines.append(f"  Coordinates    : {result.final_coordinates[0]:.4f}, {result.final_coordinates[1]:.4f}")
    lines.append(f"  As of          : {result.timestamp_used.isoformat()}")
    lines.append(f"  Confidence     : {d.confidence:.2f}")
    lines.append("")
    return "\n".join(lines)
