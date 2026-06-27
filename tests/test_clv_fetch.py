"""Tests for clv_fetch — match settled player props to their BettingPros consensus close.

The matching core is exercised offline through injected fetchers (no live HTTP): fake
offer ladders + a fake event resolver stand in for BettingPros. Verifies the de-viggable
two-way is found at the ENTRY line even when the displayed main line is split, and that
every never-fabricate path (missing market, missing player, line not on both sides,
unmapped stat, unsettled/non-prop pick) leaves the pick out of the closes map → Unmeasured.
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


cf = _load("clv_fetch", "clv_fetch.py")
tracker = _load("tracker", "tracker.py")


def _norm(s):
    return tracker._normalize_name(s)


# A split-line outs-recorded ladder (under main 14.5 / over main 15.5) that nonetheless
# prices BOTH sides at 14.5 AND 15.5 — the real BettingPros shape (verified 2026-06-27).
LADDERS = [{
    "player": "Patrick Corbin", "team": "TOR",
    "sides": {
        "under": {14.5: -115, 15.5: 120},
        "over": {14.5: -125, 15.5: 145},
    },
}]


class TestTwoWayAtLine(unittest.TestCase):
    def test_finds_both_sides_at_entry_line_despite_split_main(self):
        c = cf.two_way_at_line(LADDERS, _norm("Patrick Corbin"), 14.5, normalize_name=_norm)
        self.assertEqual(c, {"under": "-115", "over": "-125"})

    def test_formats_positive_odds_with_plus(self):
        c = cf.two_way_at_line(LADDERS, _norm("Patrick Corbin"), 15.5, normalize_name=_norm)
        self.assertEqual(c, {"under": "+120", "over": "+145"})

    def test_none_when_line_not_priced_both_sides(self):
        lad = [{"player": "X Y", "sides": {"under": {4.5: -110}, "over": {5.5: -110}}}]
        self.assertIsNone(cf.two_way_at_line(lad, _norm("X Y"), 4.5, normalize_name=_norm))

    def test_none_when_player_absent(self):
        self.assertIsNone(cf.two_way_at_line(LADDERS, _norm("Nobody Here"), 14.5, normalize_name=_norm))


class TestMarketForSpec(unittest.TestCase):
    def test_maps_pitcher_outs_and_ks(self):
        self.assertEqual(cf.market_for_spec({"stat_group": "pitching", "stat_key": "outs"}), 405)
        self.assertEqual(cf.market_for_spec({"stat_group": "pitching", "stat_key": "strikeOuts"}), 285)

    def test_unmapped_stat_returns_none(self):
        self.assertIsNone(cf.market_for_spec({"stat_group": "pitching", "stat_key": "wins"}))

    def test_combined_stat_tuple_returns_none(self):
        self.assertIsNone(cf.market_for_spec({"stat_group": "batting", "stat_key": ("hits", "runs")}))


def _pick(**kw):
    p = {"id": "p1", "sport": "MLB", "result": "win", "closing_line": None, "clv": None,
         "bet": "Patrick Corbin Under 14.5 Outs Recorded vs Rangers (TEX @ TOR)",
         "line": "+144 @ Novig", "line_num": 14.5, "date": "2026-06-26"}
    p.update(kw)
    return p


class TestBuildCloses(unittest.TestCase):
    def _build(self, picks, **over):
        kw = dict(
            resolve_event=lambda d, pl: 98219,
            fetch_ladders=lambda ev, mk: LADDERS,
            extract_prop=tracker.extract_prop,
            normalize_name=_norm,
            stat_map=tracker.PROP_STAT_MAP,
            classify_bet=tracker.classify_bet,
        )
        kw.update(over)
        return cf.build_closes(picks, **kw)

    def test_builds_close_info_for_settled_prop(self):
        closes = self._build([_pick()])
        self.assertEqual(closes["p1"], {"close": {"under": "-115", "over": "-125"},
                                        "side": "under", "market": "prop"})

    def test_skips_open_pick(self):
        self.assertEqual(self._build([_pick(result=None)]), {})

    def test_skips_already_measured_unless_force(self):
        self.assertEqual(self._build([_pick(closing_line="-110")]), {})
        forced = self._build([_pick(closing_line="-110")], force=True)
        self.assertIn("p1", forced)

    def test_skips_when_event_not_resolved(self):
        self.assertEqual(self._build([_pick()], resolve_event=lambda d, pl: None), {})

    def test_skips_when_market_dropped(self):
        self.assertEqual(self._build([_pick()], fetch_ladders=lambda ev, mk: []), {})

    def test_caches_ladder_per_event_market(self):
        calls = []
        self._build([_pick(id="a"), _pick(id="b")],
                    fetch_ladders=lambda ev, mk: calls.append((ev, mk)) or LADDERS)
        self.assertEqual(len(calls), 1, "ladder should be fetched once per (event, market)")

    def test_realized_clv_is_negative_devigged_not_raw(self):
        # End-to-end through clv_backfill: Corbin entry +144 vs consensus close -115/-125
        # de-vigs to a strongly POSITIVE realized CLV (he beat the close); the point is it
        # routes through the de-vig core, not raw odds subtraction.
        cb = _load("clv_backfill", "clv_backfill.py")
        closes = self._build([_pick()])
        p = _pick()
        self.assertTrue(cb.backfill_pick(p, closes["p1"]))
        self.assertEqual(p["closing_line"], "-115")
        self.assertGreater(p["clv"], 5.0)


if __name__ == "__main__":
    unittest.main()
