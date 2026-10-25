"""Tests for clv_backfill — realized-CLV computation + idempotent backfill (#51).

Realized CLV uses the de-vigged Pinnacle close (via value_engine), the same definition
as V3's projected CLV, so the two are comparable. Unmeasured picks (no close fetched)
must stay null — never a 0.0 placeholder (preserves tracker.is_measured_clv, #46).
"""

import importlib.util
import sys
import unittest
from pathlib import Path

_BT = Path(__file__).parent.parent / ".agents" / "skills" / "bet-tracker"


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, _BT / rel)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


cb = _load("clv_backfill", "clv_backfill.py")


def _pick(**kw):
    p = {"id": "t1", "model": "v3-value", "bet": "SF ML", "line": "+120",
         "bet_type": "moneyline", "units": 1, "result": "win",
         "closing_line": None, "clv": None}
    p.update(kw)
    return p


class TestRealizedClv(unittest.TestCase):
    def test_devigged_realized_clv_matches_projected_definition(self):
        # Close ARI -120 / SF +110, moneyline -> power de-vig (ADR 0011) fair SF .4650;
        # entry SF +120 (.4545) -> +2.30%. (Multiplicative, before ADR 0011, gave .4661 / +2.55%.)
        clv = cb.realized_clv({"ARI": "-120", "SF": "+110"}, "SF", "+120", "moneyline")
        self.assertAlmostEqual(clv, 2.30, delta=0.05)

    def test_negative_when_entry_worse_than_close(self):
        clv = cb.realized_clv({"LAD": "-150", "COL": "+135"}, "LAD", "-160", "moneyline")
        self.assertLess(clv, 0)

    def test_handles_book_suffix_in_entry_line(self):
        # real picks store line as '+120 @ FanDuel' / '-105 (DK)' — must parse the odds out
        for entry in ("+120 @ FanDuel", "120 @ FanDuel", "+120 (DK)"):
            clv = cb.realized_clv({"ARI": "-120", "SF": "+110"}, "SF", entry, "moneyline")
            self.assertAlmostEqual(clv, 2.30, delta=0.05, msg=f"entry={entry!r}")

    def test_none_when_side_missing_or_not_two_way(self):
        self.assertIsNone(cb.realized_clv({"ARI": "-120", "SF": "+110"}, "NYY", "+120", "moneyline"))
        self.assertIsNone(cb.realized_clv({"ARI": "-120"}, "ARI", "-120", "moneyline"))
        self.assertIsNone(cb.realized_clv(None, "SF", "+120", "moneyline"))

    def test_unknown_market_kind_leaves_the_pick_unmeasured(self):
        # value_engine.market_kind raises on a label it doesn't know (ADR 0011). The
        # backfill must leave that pick null, not abort the run or guess a method.
        self.assertIsNone(cb.realized_clv({"over": "-110", "under": "-110"}, "over", "+100", "points"))
        # backfill_pick still records the one-sided percentage-point CLV, but no de-vig.
        p = _pick()
        cb.backfill_pick(p, {"close": {"ARI": "-120", "SF": "+110"}, "side": "SF",
                             "market": "first half"})
        self.assertIsNone(p.get("clv_devig"))
        self.assertIsNotNone(p.get("clv_pct_pts"))


class TestBackfillPick(unittest.TestCase):
    def _close(self):
        return {"close": {"ARI": "-120", "SF": "+110"}, "side": "SF", "market": "moneyline"}

    def test_fills_missing_closing_line_and_clv(self):
        p = _pick()
        self.assertTrue(cb.backfill_pick(p, self._close()))
        self.assertEqual(p["closing_line"], "+110")      # Pinnacle's close on the bet side
        self.assertAlmostEqual(p["clv"], 2.30, delta=0.05)

    def test_idempotent_no_op_when_already_measured(self):
        p = _pick(closing_line="+108", clv=1.2)
        self.assertFalse(cb.backfill_pick(p, self._close()))
        self.assertEqual(p["closing_line"], "+108")      # untouched
        self.assertEqual(p["clv"], 1.2)

    def test_force_overwrites(self):
        p = _pick(closing_line="+108", clv=1.2)
        self.assertTrue(cb.backfill_pick(p, self._close(), force=True))
        self.assertEqual(p["closing_line"], "+110")

    def test_no_close_leaves_null_not_zero(self):
        p = _pick()
        self.assertFalse(cb.backfill_pick(p, None))
        self.assertIsNone(p["clv"])          # Unmeasured stays null, never 0.0
        self.assertIsNone(p["closing_line"])


class TestBackfillBatch(unittest.TestCase):
    def test_updates_only_picks_with_a_fetched_close(self):
        picks = [_pick(id="a"), _pick(id="b", closing_line="+100", clv=0.5), _pick(id="c")]
        closes = {"a": {"close": {"ARI": "-120", "SF": "+110"}, "side": "SF", "market": "moneyline"}}
        n = cb.backfill_picks(picks, closes)
        self.assertEqual(n, 1)                            # only 'a' (b already measured, c has no close)
        self.assertIsNotNone(picks[0]["clv"])
        self.assertEqual(picks[1]["clv"], 0.5)            # untouched
        self.assertIsNone(picks[2]["clv"])                # no close -> stays null


class TestCapturedNbaSnapshotBackfill(unittest.TestCase):
    """#107: a close captured for an NBA prop is backfilled like an MLB one."""

    def test_captured_nba_prop_close_becomes_measured_devig_clv(self):
        snap = {"close": {"under": "-107", "over": "-119"}, "side": "under", "market": "prop",
                "captured_at": "2026-10-25T15:50:00-07:00", "minutes_before_start": 10.0,
                "vintage": "close", "source": "bettingpros_consensus"}
        p = _pick(id="nba1", bet="Rui Hachimura Under 16.5 Points (LAL @ OKC)",
                  line="-110 @ FanDuel", bet_type="prop")
        self.assertTrue(cb.backfill_pick(p, snap))
        # Worked by hand: under 107/207 = .51691, over 119/219 = .54338, sum 1.06029,
        # fair under .48752; entry -110 = .52381 -> .48752/.52381 - 1 = -6.93%.
        self.assertAlmostEqual(p["clv_devig"], -6.93, delta=0.02)
        self.assertAlmostEqual(p["clv_pct_pts"], -0.69, delta=0.02)
        self.assertEqual(p["closing_line"], "-107")


if __name__ == "__main__":
    unittest.main()
