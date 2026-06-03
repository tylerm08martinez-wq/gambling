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
        # Pinnacle close ARI -120 / SF +110 -> fair SF .4661; entry SF +120 (.4545) -> +2.55%
        clv = cb.realized_clv({"ARI": "-120", "SF": "+110"}, "SF", "+120", "moneyline")
        self.assertAlmostEqual(clv, 2.55, delta=0.05)

    def test_negative_when_entry_worse_than_close(self):
        clv = cb.realized_clv({"LAD": "-150", "COL": "+135"}, "LAD", "-160", "moneyline")
        self.assertLess(clv, 0)

    def test_handles_book_suffix_in_entry_line(self):
        # real picks store line as '+120 @ FanDuel' / '-105 (DK)' — must parse the odds out
        for entry in ("+120 @ FanDuel", "120 @ FanDuel", "+120 (DK)"):
            clv = cb.realized_clv({"ARI": "-120", "SF": "+110"}, "SF", entry, "moneyline")
            self.assertAlmostEqual(clv, 2.55, delta=0.05, msg=f"entry={entry!r}")

    def test_none_when_side_missing_or_not_two_way(self):
        self.assertIsNone(cb.realized_clv({"ARI": "-120", "SF": "+110"}, "NYY", "+120", "moneyline"))
        self.assertIsNone(cb.realized_clv({"ARI": "-120"}, "ARI", "-120", "moneyline"))
        self.assertIsNone(cb.realized_clv(None, "SF", "+120", "moneyline"))


class TestBackfillPick(unittest.TestCase):
    def _close(self):
        return {"close": {"ARI": "-120", "SF": "+110"}, "side": "SF", "market": "moneyline"}

    def test_fills_missing_closing_line_and_clv(self):
        p = _pick()
        self.assertTrue(cb.backfill_pick(p, self._close()))
        self.assertEqual(p["closing_line"], "+110")      # Pinnacle's close on the bet side
        self.assertAlmostEqual(p["clv"], 2.55, delta=0.05)

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


if __name__ == "__main__":
    unittest.main()
