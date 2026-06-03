"""Tests for CLV calibration stats (#46).

The model is judged by closing-line value, not short-run ROI: CLV+ rate, average CLV,
and CLV per Primary Edge Type. The load-bearing rule (CONTEXT.md): **Unmeasured CLV**
picks — null clv, or a placeholder +0.00% with no Pinnacle close fetched — are EXCLUDED
from every CLV statistic, never treated as zero. A genuine measured 0.00% (close was
fetched, price tied the close) IS measured: it counts in the denominator but did not
beat the close.
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


def _pick(clv, closing_line="-105", edge="clv_value", model="v3-value", result="win"):
    return {"model": model, "result": result, "units": 1.0, "units_won_lost": 0.9,
            "score": 7.0, "sport": "MLB", "bet": "ARI vs SF", "line": "-110",
            "date": "2026-06-01", "primary_edge": edge, "primary_edge_type": edge,
            "clv": clv, "closing_line": closing_line}


class TestIsMeasuredClv(unittest.TestCase):
    def test_null_clv_is_unmeasured(self):
        self.assertFalse(tracker.is_measured_clv(_pick(None, closing_line=None)))

    def test_placeholder_zero_without_close_is_unmeasured(self):
        # +0.00% with no Pinnacle close fetched == placeholder Unmeasured
        self.assertFalse(tracker.is_measured_clv(_pick(0.0, closing_line=None)))

    def test_genuine_zero_with_close_is_measured(self):
        # close WAS fetched and the price tied it -> a real 0.00% CLV, measured
        self.assertTrue(tracker.is_measured_clv(_pick(0.0, closing_line="-110")))

    def test_nonzero_with_close_is_measured(self):
        self.assertTrue(tracker.is_measured_clv(_pick(2.5, closing_line="-105")))


class TestClvStats(unittest.TestCase):
    def test_unmeasured_excluded_not_treated_as_zero(self):
        # 1 measured +4%, 3 unmeasured (null). Excluding -> avg +4%, CLV+ 100%.
        # Treating unmeasured as zero would wrongly give avg +1% and CLV+ 25%.
        picks = [_pick(4.0)] + [_pick(None, closing_line=None) for _ in range(3)]
        s = tracker.clv_stats(picks)
        self.assertEqual(s["measured"], 1)
        self.assertEqual(s["unmeasured"], 3)
        self.assertAlmostEqual(s["avg_clv"], 4.0, places=4)
        self.assertAlmostEqual(s["clv_plus_rate"], 100.0, places=4)

    def test_clv_plus_rate_counts_only_beats(self):
        # +2, +0.5, 0.00 (tied), -1  -> 2 of 4 beat the close = 50% CLV+
        picks = [_pick(2.0), _pick(0.5), _pick(0.0, closing_line="-110"), _pick(-1.0)]
        s = tracker.clv_stats(picks)
        self.assertEqual(s["measured"], 4)
        self.assertAlmostEqual(s["clv_plus_rate"], 50.0, places=4)
        self.assertAlmostEqual(s["avg_clv"], (2.0 + 0.5 + 0.0 - 1.0) / 4, places=4)

    def test_per_edge_type_breakdown(self):
        picks = [_pick(3.0, edge="clv_value"), _pick(1.0, edge="clv_value"),
                 _pick(-2.0, edge="cross_book_gap"),
                 _pick(None, closing_line=None, edge="clv_value")]  # excluded
        s = tracker.clv_stats(picks)
        by = s["by_edge_type"]
        self.assertEqual(by["clv_value"]["n"], 2)
        self.assertAlmostEqual(by["clv_value"]["avg_clv"], 2.0, places=4)
        self.assertAlmostEqual(by["clv_value"]["plus_rate"], 100.0, places=4)
        self.assertEqual(by["cross_book_gap"]["n"], 1)
        self.assertAlmostEqual(by["cross_book_gap"]["plus_rate"], 0.0, places=4)

    def test_all_unmeasured_returns_none_rates(self):
        picks = [_pick(None, closing_line=None) for _ in range(3)]
        s = tracker.clv_stats(picks)
        self.assertEqual(s["measured"], 0)
        self.assertIsNone(s["avg_clv"])
        self.assertIsNone(s["clv_plus_rate"])


class TestClvRendersInDashboard(unittest.TestCase):
    def test_clv_section_appears_with_measured_picks(self):
        picks = [_pick(2.5), _pick(-1.0), _pick(None, closing_line=None)]
        buf = io.StringIO()
        with patch.object(tracker, "load_picks", return_value=picks):
            with contextlib.redirect_stdout(buf):
                tracker.cmd_stats(None)
        out = buf.getvalue().upper()
        self.assertIn("CLV", out)
        # the per-model cards must still render (didn't displace #45's output)
        self.assertIn("V3-VALUE", out)


class TestPerModelClv(unittest.TestCase):
    def test_dashboard_summaries_include_per_model_clv(self):
        picks = [
            _pick(2.0, model="v1-trends"),                       # measured, beats close
            _pick(-1.0, model="v1-trends"),                      # measured, doesn't beat
            _pick(None, closing_line=None, model="v2-sharp"),    # unmeasured
        ]
        rows = {r["id"]: r for r in tracker.dashboard_summaries(picks)}
        v1 = rows["v1-trends"]
        self.assertEqual(v1["clv_measured"], 2)
        self.assertAlmostEqual(v1["clv_plus_rate"], 50.0, places=4)
        self.assertAlmostEqual(v1["avg_clv"], 0.5, places=4)
        v2 = rows["v2-sharp"]
        self.assertEqual(v2["clv_measured"], 0)
        self.assertIsNone(v2["clv_plus_rate"])  # never fabricate a rate from zero samples

    def test_per_model_clv_renders_on_cards(self):
        picks = [_pick(2.0, model="v1-trends"),
                 _pick(None, closing_line=None, model="v2-sharp")]
        buf = io.StringIO()
        with patch.object(tracker, "load_picks", return_value=picks):
            with contextlib.redirect_stdout(buf):
                tracker.cmd_stats(None)
        out = buf.getvalue()
        self.assertIn("CLV+:", out)                  # measured model shows a rate
        self.assertIn("no measured picks yet", out)  # unmeasured model says so, not 0%


if __name__ == "__main__":
    unittest.main()
