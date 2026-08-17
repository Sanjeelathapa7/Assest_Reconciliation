"""
Unit tests for the rule engine, independent of the demo fixtures.

These construct minimal records directly so each rule is tested in
isolation, plus a couple of end-to-end tests through the agent using the
shared demo fixtures as a regression check.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import unittest
from datetime import datetime, timedelta

from asset_reconciliation.models import GPSRecord, HistoryPoint, InventoryRecord, ScanMethod, SourceName
from asset_reconciliation.rules import RuleEngine, gps_quality_score, inventory_quality_score, freshness_score


NOW = datetime(2026, 1, 1, 12, 0, 0)


class TestQualityScores(unittest.TestCase):
    def test_gps_quality_scales_with_accuracy_and_sats(self):
        good = GPSRecord("A", NOW, 0, 0, accuracy_radius_m=5, satellites=12)
        bad = GPSRecord("A", NOW, 0, 0, accuracy_radius_m=400, satellites=2)
        self.assertGreater(gps_quality_score(good), gps_quality_score(bad))

    def test_inventory_hard_event_with_manifest_scores_higher(self):
        plain = InventoryRecord("A", NOW, "WH-A-1", ScanMethod.BARCODE, "SCAN_IN")
        hard = InventoryRecord("A", NOW, "SHIPPED_OUT", ScanMethod.BARCODE, "SHIPPED_OUT", manifest_id="M-1")
        self.assertGreater(inventory_quality_score(hard), inventory_quality_score(plain))

    def test_freshness_decays_with_age(self):
        fresh = freshness_score(NOW - timedelta(minutes=1), NOW)
        stale = freshness_score(NOW - timedelta(hours=10), NOW)
        self.assertGreater(fresh, stale)
        self.assertLessEqual(fresh, 1.0)
        self.assertGreaterEqual(stale, 0.0)


class TestRecencyRule(unittest.TestCase):
    def test_recency_wins_beyond_threshold(self):
        gps = GPSRecord("A", NOW - timedelta(hours=5), 40.7128, -74.0060, accuracy_radius_m=10, satellites=9)
        inv = InventoryRecord("A", NOW - timedelta(minutes=5), "WH-A-1", ScanMethod.RFID_GATE, "SCAN_IN")
        decision = RuleEngine().decide(gps, inv, history=[], now=NOW)
        self.assertEqual(decision.rule_id, "R2")
        self.assertEqual(decision.winner, SourceName.INVENTORY)

    def test_recency_does_not_apply_within_threshold(self):
        gps = GPSRecord("A", NOW - timedelta(minutes=5), 40.7128, -74.0060, accuracy_radius_m=10, satellites=9)
        inv = InventoryRecord("A", NOW - timedelta(minutes=6), "WH-A-1", ScanMethod.RFID_GATE, "SCAN_IN")
        decision = RuleEngine().decide(gps, inv, history=[], now=NOW)
        self.assertNotEqual(decision.rule_id, "R2")


class TestSignalQualityRule(unittest.TestCase):
    def test_quality_wins_when_timestamps_close(self):
        gps = GPSRecord("A", NOW - timedelta(minutes=2), 40.7128, -74.0060, accuracy_radius_m=300, satellites=3)
        inv = InventoryRecord("A", NOW - timedelta(minutes=1), "WH-A-1", ScanMethod.RFID_GATE, "SCAN_IN")
        decision = RuleEngine().decide(gps, inv, history=[], now=NOW)
        self.assertEqual(decision.rule_id, "R3")
        self.assertEqual(decision.winner, SourceName.INVENTORY)

    def test_gps_can_win_on_quality_too(self):
        gps = GPSRecord("A", NOW - timedelta(minutes=1), 40.7128, -74.0060, accuracy_radius_m=3, satellites=12)
        inv = InventoryRecord("A", NOW - timedelta(minutes=2), "WH-A-1", ScanMethod.MANUAL_ENTRY, "SCAN_IN")
        decision = RuleEngine().decide(gps, inv, history=[], now=NOW)
        self.assertEqual(decision.rule_id, "R3")
        self.assertEqual(decision.winner, SourceName.GPS)


class TestLogicalInconsistencyRule(unittest.TestCase):
    def _shipped_out_setup(self, num_corroborating_after: int):
        prior = HistoryPoint(NOW - timedelta(hours=2), 40.7128, -74.0060, "WH-A-1")
        history = [prior]
        event_time = NOW - timedelta(minutes=20)
        for i in range(num_corroborating_after):
            history.append(HistoryPoint(NOW - timedelta(minutes=15 - i), 40.7128, -74.0060, "WH-A-1"))
        gps = GPSRecord("A", NOW - timedelta(minutes=2), 40.7128, -74.0060, accuracy_radius_m=10, satellites=9)
        inv = InventoryRecord(
            "A", event_time, "SHIPPED_OUT", ScanMethod.BARCODE, "SHIPPED_OUT", manifest_id="M-1"
        )
        return gps, inv, history

    def test_corroborated_contradiction_favors_gps(self):
        gps, inv, history = self._shipped_out_setup(num_corroborating_after=2)
        decision = RuleEngine().decide(gps, inv, history, now=NOW)
        self.assertEqual(decision.rule_id, "R1")
        self.assertEqual(decision.winner, SourceName.GPS)

    def test_uncorroborated_contradiction_favors_inventory(self):
        gps, inv, history = self._shipped_out_setup(num_corroborating_after=0)
        decision = RuleEngine().decide(gps, inv, history, now=NOW)
        self.assertEqual(decision.rule_id, "R1")
        self.assertEqual(decision.winner, SourceName.INVENTORY)

    def test_pre_event_gps_reading_is_not_counted_as_corroboration(self):
        """
        Regression test for a real bug found during review: a GPS reading
        that predates the inventory's departure event must NOT be counted
        as evidence against that event, even if one genuine post-event
        history point exists. Before the fix, the current GPS reading was
        unconditionally counted as "+1" corroboration regardless of
        whether it actually came after the event, which could let GPS
        incorrectly win off of only one real corroborating point.
        """
        prior = HistoryPoint(NOW - timedelta(hours=2), 40.7128, -74.0060, "WH-A-1")
        event_time = NOW - timedelta(minutes=20)
        one_genuine_post_event_point = HistoryPoint(NOW - timedelta(minutes=15), 40.7128, -74.0060, "WH-A-1")
        history = [prior, one_genuine_post_event_point]

        # GPS reading is BEFORE the departure event -- it should not count.
        stale_pre_event_gps = GPSRecord(
            "A", NOW - timedelta(minutes=25), 40.7128, -74.0060, accuracy_radius_m=10, satellites=9
        )
        inv = InventoryRecord(
            "A", event_time, "SHIPPED_OUT", ScanMethod.BARCODE, "SHIPPED_OUT", manifest_id="M-1"
        )
        decision = RuleEngine().decide(stale_pre_event_gps, inv, history, now=NOW)
        # Only one genuine post-event corroborating point exists, which is
        # below the >=2 threshold for GPS to win -- inventory should win.
        self.assertEqual(decision.rule_id, "R1")
        self.assertEqual(decision.winner, SourceName.INVENTORY)

    def test_non_departure_event_does_not_trigger_rule(self):
        gps = GPSRecord("A", NOW - timedelta(minutes=2), 40.7128, -74.0060, accuracy_radius_m=10, satellites=9)
        inv = InventoryRecord("A", NOW - timedelta(minutes=3), "WH-A-1", ScanMethod.BARCODE, "CYCLE_COUNT")
        decision = RuleEngine().decide(gps, inv, history=[], now=NOW)
        self.assertNotEqual(decision.rule_id, "R1")


class TestPhysicalImplausibilityRule(unittest.TestCase):
    def test_impossible_jump_is_rejected(self):
        history = [HistoryPoint(NOW - timedelta(minutes=30), 40.7128, -74.0060, "WH-A-1")]
        gps = GPSRecord("A", NOW - timedelta(minutes=1), 41.9000, -73.5000, accuracy_radius_m=10, satellites=9)
        inv = InventoryRecord("A", NOW - timedelta(hours=1), "WH-A-1", ScanMethod.BARCODE, "SCAN_IN")
        decision = RuleEngine().decide(gps, inv, history, now=NOW)
        self.assertEqual(decision.rule_id, "R4")
        self.assertEqual(decision.winner, SourceName.INVENTORY)
        self.assertTrue(decision.gps_discarded)

    def test_plausible_movement_is_not_rejected(self):
        history = [HistoryPoint(NOW - timedelta(minutes=30), 40.7128, -74.0060, "WH-A-1")]
        # ~2km away in 30 minutes -> 4 km/h, trivially plausible
        gps = GPSRecord("A", NOW - timedelta(minutes=1), 40.7290, -73.9990, accuracy_radius_m=10, satellites=9)
        inv = InventoryRecord("A", NOW - timedelta(hours=1), "WH-A-1", ScanMethod.BARCODE, "SCAN_IN")
        decision = RuleEngine().decide(gps, inv, history, now=NOW)
        self.assertNotEqual(decision.rule_id, "R4")

    def test_no_history_skips_check_gracefully(self):
        gps = GPSRecord("A", NOW - timedelta(minutes=1), 41.9000, -73.5000, accuracy_radius_m=10, satellites=9)
        inv = InventoryRecord("A", NOW - timedelta(hours=1), "WH-A-1", ScanMethod.BARCODE, "SCAN_IN")
        decision = RuleEngine().decide(gps, inv, history=[], now=NOW)
        self.assertNotEqual(decision.rule_id, "R4")  # nothing to compare against, rule can't fire


class TestAgentEndToEnd(unittest.TestCase):
    def test_all_demo_scenarios_resolve_as_expected(self):
        from asset_reconciliation import ReconciliationAgent, build_default_sources
        from asset_reconciliation.sources import NOW as DEMO_NOW

        gps_source, inv_source, history_store = build_default_sources()
        agent = ReconciliationAgent(gps_source, inv_source, history_store, now=DEMO_NOW)

        expected = {
            "AST-1001": ("R2", SourceName.INVENTORY),
            "AST-1002": ("R3", SourceName.INVENTORY),
            "AST-1003": ("R1", SourceName.GPS),
            "AST-1004": ("R4", SourceName.INVENTORY),
            "AST-1005": ("R1", SourceName.INVENTORY),
        }
        for asset_id, (rule_id, winner) in expected.items():
            result = agent.reconcile(asset_id)
            self.assertEqual(result.decision.rule_id, rule_id, f"{asset_id} rule mismatch")
            self.assertEqual(result.decision.winner, winner, f"{asset_id} winner mismatch")
            self.assertGreater(result.decision.confidence, 0.0)
            self.assertLessEqual(result.decision.confidence, 1.0)

    def test_single_source_fallback(self):
        from asset_reconciliation import ReconciliationAgent
        from asset_reconciliation.sources import GPSSource, InventorySource, HistoryStore
        from asset_reconciliation.models import GPSRecord

        gps_only = GPSSource({"X": GPSRecord("X", NOW, 40.7128, -74.0060, accuracy_radius_m=10, satellites=9)})
        empty_inv = InventorySource({})
        empty_hist = HistoryStore({})
        agent = ReconciliationAgent(gps_only, empty_inv, empty_hist, now=NOW)
        result = agent.reconcile("X")
        self.assertEqual(result.decision.rule_id, "R0")
        self.assertEqual(result.decision.winner, SourceName.GPS)


if __name__ == "__main__":
    unittest.main()
