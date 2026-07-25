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


def _pick(clv, closing_line="-105", edge="clv_value", model="v3-value", result="win",
          pct_pts="same"):
    """Build a pick. `clv` is the DE-VIGGED value (the headline metric).

    Headline CLV stats read `clv_devig`; `clv_pct_pts` is the wider-coverage
    vig-inclusive fallback, reported over its own denominator. The two used to share
    one `clv` field and were averaged together, which made avg_clv neither metric.
    `clv` remains as a legacy mirror of whichever is preferred+available.
    """
    return {"model": model, "result": result, "units": 1.0, "units_won_lost": 0.9,
            "score": 7.0, "sport": "MLB", "bet": "ARI vs SF", "line": "-110",
            "date": "2026-06-01", "primary_edge": edge, "primary_edge_type": edge,
            "clv": clv, "clv_devig": clv,
            "clv_pct_pts": clv if pct_pts == "same" else pct_pts,
            "closing_line": closing_line}


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

    def test_unparseable_close_is_unmeasured(self):
        # Six real picks carried a hand-written clv of 0.0 beside free text like
        # 'Mets ML +110'. Truthiness alone accepted those as Measured — 18% of the
        # denominator — so a close must now PARSE as American odds.
        for junk in ("Mets ML +110", "PHI ML -126 @ FanDuel", "Spurs +6.5 -110",
                     "Over 4.5 hits at DK", ""):
            with self.subTest(close=junk):
                self.assertFalse(tracker.is_measured_clv(_pick(0.0, closing_line=junk)))

    def test_parseable_close_with_book_suffix_is_measured(self):
        self.assertTrue(tracker.is_measured_clv(_pick(1.0, closing_line="-115 @ DK")))


class TestMetricsNeverBlended(unittest.TestCase):
    """The bug this schema exists to prevent: cmd_resolve wrote percentage points and
    cmd_backfill_clv wrote a de-vigged ratio into the SAME field, and clv_stats averaged
    them. The ratio form is systematically larger, so whichever writer ran more often
    dominated avg_clv — a number that was neither metric."""

    def test_avg_clv_uses_devig_only(self):
        picks = [_pick(1.0, pct_pts=50.0), _pick(3.0, pct_pts=50.0)]
        s = tracker.clv_stats(picks)
        self.assertEqual(s["metric"], "devig")
        self.assertAlmostEqual(s["avg_clv"], 2.0, places=4)      # not 26.5

    def test_pct_pts_reported_over_its_own_denominator(self):
        # one pick has only percentage-point CLV; it must not enter the devig mean
        devig_only = _pick(4.0)
        pct_only = _pick(None, pct_pts=10.0)
        s = tracker.clv_stats([devig_only, pct_only])
        self.assertEqual(s["measured"], 1)                        # devig denominator
        self.assertAlmostEqual(s["avg_clv"], 4.0, places=4)
        self.assertEqual(s["measured_pct_pts"], 2)                # pct denominator
        self.assertAlmostEqual(s["avg_clv_pct_pts"], 7.0, places=4)

    def test_clv_value_prefers_devig_then_falls_back(self):
        self.assertEqual(tracker.clv_value({"clv_devig": 1.5, "clv_pct_pts": 9.9}), 1.5)
        self.assertEqual(tracker.clv_value({"clv_devig": None, "clv_pct_pts": 9.9}), 9.9)
        self.assertIsNone(tracker.clv_value({"clv_devig": None, "clv_pct_pts": None}))


class TestCalcClvDevig(unittest.TestCase):
    def test_devig_strips_the_hold(self):
        # -110/-110 close: raw probs 0.5238 each, overround 1.0476, fair 0.50.
        # Entry at -110 (0.5238) is therefore BEHIND the fair close.
        self.assertLess(tracker.calc_clv_devig("-110", {"over": -110, "under": -110}, "over"), 0)

    def test_devig_positive_when_entry_beats_fair(self):
        self.assertGreater(tracker.calc_clv_devig("+130", {"over": -110, "under": -110}, "over"), 0)

    def test_devig_needs_two_way_close(self):
        self.assertIsNone(tracker.calc_clv_devig("-110", {"over": -110}, "over"))
        self.assertIsNone(tracker.calc_clv_devig("-110", {}, "over"))

    def test_devig_none_when_side_absent(self):
        self.assertIsNone(tracker.calc_clv_devig("-110", {"over": -110, "under": -110}, "yes"))

    def test_devig_none_on_unparseable_odds(self):
        self.assertIsNone(tracker.calc_clv_devig("-110", {"over": "n/a", "under": -110}, "over"))


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
