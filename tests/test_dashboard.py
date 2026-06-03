"""Tests for the model-agnostic dashboard (#45).

The dashboard must show V1, V2, and V3 (and any future model) driven by a model
*registry*, not hardcoded two-model branches — so adding a model is a data change,
never a new conditional. v3-value picks must be counted and labeled correctly, never
silently dropped or mislabeled as V2.
"""

import contextlib
import importlib.util
import io
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

_spec = importlib.util.spec_from_file_location(
    "tracker",
    Path(__file__).parent.parent / ".agents" / "skills" / "bet-tracker" / "tracker.py",
)
tracker = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tracker)
sys.modules["tracker"] = tracker


def _pick(model, result="win", units=1.0, won=0.9, score=7.0, sport="MLB",
          bet="ARI vs SF", line="-110", date="2026-06-01", edge="clv_value", clv=None):
    won_lost = won if result in ("win", "loss") else (0.0 if result in ("push", "void") else None)
    return {
        "model": model, "result": result, "units": units, "units_won_lost": won_lost,
        "score": score, "sport": sport, "bet": bet, "line": line, "date": date,
        "primary_edge": edge, "primary_edge_type": edge, "clv": clv, "closing_line": None,
    }


class TestModelRegistry(unittest.TestCase):
    def test_registry_includes_all_three_models(self):
        ids = [m["id"] for m in tracker.MODELS]
        self.assertEqual(ids, ["v1-trends", "v2-sharp", "v3-value"])

    def test_model_label_maps_each_registered_model(self):
        self.assertEqual(tracker.model_label("v1-trends"), "V1")
        self.assertEqual(tracker.model_label("v2-sharp"), "V2")
        self.assertEqual(tracker.model_label("v3-value"), "V3")

    def test_unknown_model_is_not_mislabeled_as_v2(self):
        # the old code did `"V1" if v1 else "V2"`, mislabeling v3/any new model as V2
        self.assertNotEqual(tracker.model_label("v4-future"), "V2")
        self.assertEqual(tracker.model_label("v4-future"), "v4-future")


class TestDashboardSummaries(unittest.TestCase):
    def test_one_summary_row_per_registered_model(self):
        picks = [_pick("v1-trends"), _pick("v2-sharp"), _pick("v3-value")]
        rows = tracker.dashboard_summaries(picks)
        self.assertEqual([r["id"] for r in rows], ["v1-trends", "v2-sharp", "v3-value"])

    def test_v3_picks_are_counted_in_their_own_row(self):
        picks = [_pick("v3-value", result="win", units=1, won=0.91),
                 _pick("v3-value", result="loss", units=2, won=-2.0),
                 _pick("v1-trends")]
        rows = {r["id"]: r for r in tracker.dashboard_summaries(picks)}
        v3 = rows["v3-value"]
        self.assertEqual(v3["total"], 2)
        self.assertEqual(v3["settled"], 2)
        self.assertAlmostEqual(v3["units_net"], -1.09, places=2)
        # v3 picks must not leak into another model's row
        self.assertEqual(rows["v1-trends"]["total"], 1)

    def test_new_model_surfaces_without_code_change(self):
        # Extend the registry with a brand-new model id; it must appear with correct
        # stats purely from the data — no new branch in dashboard_summaries.
        extended = tracker.MODELS + [{"id": "v4-quant", "name": "V4-Quant",
                                      "label": "V4-QUANT", "short": "V4", "emoji": "🧮"}]
        picks = [_pick("v4-quant", result="win", units=1, won=1.5), _pick("v1-trends")]
        rows = {r["id"]: r for r in tracker.dashboard_summaries(picks, models=extended)}
        self.assertIn("v4-quant", rows)
        self.assertEqual(rows["v4-quant"]["total"], 1)
        self.assertAlmostEqual(rows["v4-quant"]["units_net"], 1.5, places=2)


class TestCmdStatsRender(unittest.TestCase):
    def _render(self, picks):
        buf = io.StringIO()
        with patch.object(tracker, "load_picks", return_value=picks):
            with contextlib.redirect_stdout(buf):
                tracker.cmd_stats(None)
        return buf.getvalue()

    def test_renders_all_three_model_cards_and_combined(self):
        picks = [_pick("v1-trends"), _pick("v2-sharp"), _pick("v3-value")]
        out = self._render(picks)
        for needle in ("V1-TRENDS", "V2-SHARP", "V3-VALUE", "COMBINED"):
            self.assertIn(needle, out)

    def test_v3_recent_pick_labeled_v3_not_v2(self):
        picks = [_pick("v3-value", bet="LAD vs COL", date="2026-06-02")]
        out = self._render(picks)
        self.assertIn("· V3 ·", out)        # recent-pick row uses the V3 short label
        self.assertNotIn("· V2 ·", out)     # the lone v3 pick must not render as V2


if __name__ == "__main__":
    unittest.main()
