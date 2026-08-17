
from __future__ import annotations

import sys

from asset_reconciliation import ReconciliationAgent, build_default_sources
from asset_reconciliation.report import to_human_readable, to_json
from asset_reconciliation.sources import NOW

SCENARIO_NOTES = {
    "AST-1001": "Scenario 1: RECENCY MISMATCH -- stale GPS fix vs. a fresh warehouse gate scan.",
    "AST-1002": "Scenario 2: SIGNAL QUALITY DIFFERENCE -- near-simultaneous readings, one is a poor GPS fix.",
    "AST-1003": "Scenario 3: LOGICAL INCONSISTENCY (corroborated) -- inventory claims 'shipped out', GPS shows continued, corroborated presence.",
    "AST-1004": "Scenario 4: PHYSICAL IMPLAUSIBILITY -- GPS reading implies an impossible jump; treated as noise.",
    "AST-1005": "Scenario 5: LOGICAL INCONSISTENCY (uncorroborated) -- same conflict type as #3, opposite winner, because the GPS evidence this time is a single unconfirmed ping.",
}


def main() -> None:
    as_json = "--json" in sys.argv

    gps_source, inventory_source, history_store = build_default_sources()
    agent = ReconciliationAgent(gps_source, inventory_source, history_store, now=NOW)

    results = []
    for asset_id in ["AST-1001", "AST-1002", "AST-1003", "AST-1004", "AST-1005"]:
        results.append(agent.reconcile(asset_id))

    if as_json:
        import json
        from asset_reconciliation.report import to_audit_dict
        print(json.dumps([to_audit_dict(r) for r in results], indent=2))
        return

    print(f"Asset Location Reconciliation Agent -- run at {NOW.isoformat()}\n")
    for result in results:
        print(SCENARIO_NOTES.get(result.asset_id, ""))
        print(to_human_readable(result))

    print("=" * 78)
    print("SUMMARY")
    print("=" * 78)
    for r in results:
        print(
            f"  {r.asset_id}: {r.decision.winner.value:<9} won via {r.decision.rule_id} "
            f"({r.decision.rule_name}) -> {r.final_location_code}  "
            f"[confidence {r.decision.confidence:.2f}]"
        )


if __name__ == "__main__":
    main()
