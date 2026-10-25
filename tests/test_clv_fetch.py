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


# ── #107: NBA and NFL player props ────────────────────────────────────────────────

class TestMarketForSpecBySport(unittest.TestCase):
    def _m(self, sport, bet):
        spec = tracker.extract_prop(bet, 1.5, tracker._stat_map_for_sport(sport))
        self.assertIsNotNone(spec, bet)
        return cf.market_for_spec(spec, sport=sport)

    def test_nba_markets(self):
        self.assertEqual(self._m("NBA", "Peyton Watson Under 13.5 Points"), 156)
        self.assertEqual(self._m("NBA", "Rudy Gobert Over 11.5 Rebounds"), 157)
        self.assertEqual(self._m("NBA", "Trae Young Over 10.5 Assists"), 151)
        self.assertEqual(self._m("NBA", "Steph Curry Over 4.5 threes"), 162)
        self.assertEqual(self._m("NBA", "Alex Caruso Over 1.5 steals"), 160)
        self.assertEqual(self._m("NBA", "Victor Wembanyama Over 3.5 blocks"), 152)
        self.assertEqual(self._m("NBA", "Victor Wembanyama Under 40.5 Points+Rebounds+Assists"), 338)
        self.assertEqual(self._m("NBA", "Victor Wembanyama Under 40.5 PRA"), 338)

    def test_nfl_markets_discovered_from_v3_markets(self):
        # /v3/markets?sport=NFL, 2026-10-24: 103 pass yds, 105 rec yds, 107 rush yds,
        # 104 receptions, 333 pass attempts, 100 completions, 106 rush attempts, 406 rush+rec.
        self.assertEqual(self._m("NFL", "Aaron Rodgers (PIT) Under 216.5 passing yards vs ATL"), 103)
        self.assertEqual(self._m("NFL", "Travis Kelce (KC) Over 38.5 receiving yards vs DEN"), 105)
        self.assertEqual(self._m("NFL", "Chase Brown (CIN) Over 75.5 rushing yards vs HOU"), 107)
        self.assertEqual(self._m("NFL", "Travis Kelce Over 5.5 receptions"), 104)
        self.assertEqual(self._m("NFL", "Patrick Mahomes (KC) Under 32.5 pass attempts vs DEN"), 333)
        self.assertEqual(self._m("NFL", "Jordan Love Over 21.5 completions"), 100)
        self.assertEqual(self._m("NFL", "Kenneth Walker III Over 15.5 rushing attempts"), 106)
        self.assertEqual(self._m("NFL", "Kyle Monangai Over 50.5 rushing + receiving yards"), 406)

    def test_market_ids_are_never_borrowed_across_sports(self):
        nba_points = {"stat_group": "scoring", "stat_key": "points"}
        self.assertIsNone(cf.market_for_spec(nba_points))                 # MLB default
        self.assertIsNone(cf.market_for_spec(nba_points, sport="NFL"))
        outs = {"stat_group": "pitching", "stat_key": "outs"}
        self.assertIsNone(cf.market_for_spec(outs, sport="NBA"))
        self.assertEqual(cf.market_for_spec(outs, sport="MLB"), 405)

    def test_every_mapped_market_is_reachable_from_the_sports_stat_map(self):
        # "Map only stats that extract_prop can parse for that sport": a market keyed by a
        # (group, key) that no stat keyword produces is dead weight that hides a typo.
        for sport in ("NBA", "NFL"):
            produced = set(tracker._stat_map_for_sport(sport).values())
            for key in cf.STAT_MARKET[sport]:
                with self.subTest(sport=sport, key=key):
                    self.assertIn(key, produced)

    def test_nba_combos_extract_prop_cannot_parse_are_unmapped(self):
        # P+A (335), P+R (336), R+A (337) have markets, but extract_prop returns None for
        # them, so they must stay unmeasured (memory: nba-combo-prop-bet-phrasing).
        self.assertNotIn(335, cf.STAT_MARKET["NBA"].values())
        self.assertNotIn(336, cf.STAT_MARKET["NBA"].values())
        self.assertNotIn(337, cf.STAT_MARKET["NBA"].values())


class TestStrictExtractProp(unittest.TestCase):
    """NBA/NFL picks carry line_num values that are not the bet's line (odds stored as
    line_num, 235.0 for a 224.5 bet). extract_prop trusts line_num, so a close would be
    matched at the WRONG line. The strict wrapper refuses anything it cannot verify."""

    strict = staticmethod(cf.strict_extract_prop(tracker.extract_prop))

    def _s(self, bet, ln, sport):
        return self.strict(bet, ln, tracker._stat_map_for_sport(sport))

    def test_accepts_a_pick_whose_line_num_matches_its_text(self):
        s = self._s("Peyton Watson Under 13.5 Points (BKN @ CLE)", 13.5, "NBA")
        self.assertEqual((s["player"], s["side"], s["threshold"]), ("peyton watson", "under", 13.5))

    def test_rejects_line_num_that_disagrees_with_the_bet_text(self):
        self.assertIsNone(self._s("Aaron Rodgers Under 224.5 passing yards (IND @ PIT)", 235.0, "NFL"))

    def test_rejects_odds_stored_as_line_num(self):
        self.assertIsNone(self._s("Ace Bailey Over 11.5 Points (NOR @ UTA)", -108.0, "NBA"))

    def test_rejects_bet_with_no_number_after_the_side(self):
        self.assertIsNone(self._s("Peyton Watson Under Points", 13.5, "NBA"))

    def test_rejects_two_stats_joined_by_and(self):
        # "points and rebounds" silently grades as rebounds (memory note); a close for
        # the rebounds market would be the wrong market.
        self.assertIsNone(self._s("Naz Reid Over 23.5 points and rebounds", 23.5, "NBA"))

    def test_rejects_combo_extract_prop_cannot_parse(self):
        self.assertIsNone(self._s("Domantas Sabonis Over 21.5 Points + Assists (SAC @ LAC)", 21.5, "NBA"))

    def test_accepts_parseable_pra_combo(self):
        s = self._s("Victor Wembanyama Under 40.5 Points+Rebounds+Assists (HOU @ SAS)", 40.5, "NBA")
        self.assertEqual(s["stat_key"], ("points", "rebounds", "assists"))

    def test_n_plus_form_needs_no_line_num(self):
        s = self._s("Jalen Brunson 25+ Points", None, "NBA")
        self.assertEqual((s["side"], s["threshold"]), ("over", 24.5))

    def test_n_plus_elsewhere_in_the_text_does_not_skip_the_line_check(self):
        # Review of #112: extract_prop reads "3+" first and returns OVER 2.5 for an
        # Under 224.5 bet. A stray N+ must never bypass the Over/Under line check.
        self.assertIsNone(self._s("Bo Nix (3+ games) Under 224.5 passing yards", 224.5, "NFL"))

    def test_missing_or_empty_stat_map_returns_none_instead_of_raising(self):
        # build_closes / capture call extract_prop(bet, line_num) with 2 args when the
        # stat map is empty; that must leave the pick Unmeasured, not crash the pass.
        self.assertIsNone(self.strict("Peyton Watson Under 13.5 Points", 13.5))
        self.assertIsNone(self.strict("Peyton Watson Under 13.5 Points", 13.5, {}))

    def test_stat_word_inside_the_player_name_is_not_a_second_stat(self):
        s = self._s("Cooper Rush Over 200.5 passing yards", 200.5, "NFL")
        self.assertEqual((s["player"], s["stat_key"]), ("cooper rush", "passingYards"))

    def test_second_stat_is_still_refused_when_the_name_shares_a_stat_word(self):
        self.assertIsNone(self._s("Cooper Rush Over 200.5 passing yards and rush yards", 200.5, "NFL"))


class FakeBP:
    """Stands in for the bettingpros module: records which sport every call used."""

    def __init__(self, props=None, events=None, ladders=None):
        self.props = props or {}        # sport -> [normalized prop]
        self.events = events or {}      # sport -> [normalized event]
        self.ladders = ladders or {}    # (sport, event_id, market_id) -> ladder list
        self.calls = []

    def fetch_props(self, sport, date=None):
        self.calls.append(("props", sport, date))
        return self.props.get(sport, [])

    def fetch_events(self, sport, date):
        self.calls.append(("events", sport, date))
        return self.events.get(sport, [])

    def fetch_offer_ladder(self, event_id, market_id, *, sport="MLB"):
        self.calls.append(("ladder", sport, event_id, market_id))
        return self.ladders.get((sport, event_id, market_id), [])


def _bp_prop(name, event_id):
    return {"event_id": event_id, "player": {"name": name}}


def _settled(pid, sport, bet, line_num, line="-110", date="2026-10-25"):
    return {"id": pid, "sport": sport, "bet": bet, "line_num": line_num, "line": line,
            "date": date, "result": "win", "closing_line": None, "clv": None,
            "bet_type": "prop"}


class TestBuildClosesLiveNbaNfl(unittest.TestCase):
    def _bp(self):
        return FakeBP(
            props={"NBA": [_bp_prop("Rui Hachimura", 27926), _bp_prop("Austin Reaves", 27926)],
                   "NFL": [_bp_prop("Aaron Rodgers", 21915), _bp_prop("Josh Allen", 22000),
                           _bp_prop("Josh Allen", 22001)]},
            ladders={
                ("NBA", 27926, 156): [{"player": "Rui Hachimura",
                                       "sides": {"over": {16.5: -119}, "under": {16.5: -107}}}],
                ("NFL", 21915, 103): [{"player": "Aaron Rodgers",
                                       "sides": {"over": {229.5: -113}, "under": {229.5: -113}}}],
            })

    def test_nba_and_nfl_props_get_a_consensus_close_from_their_own_sport(self):
        bp = self._bp()
        picks = [_settled("nba1", "NBA", "Rui Hachimura Under 16.5 Points (LAL @ OKC)", 16.5),
                 _settled("nfl1", "NFL", "Aaron Rodgers (PIT) Over 229.5 passing yards vs NO", 229.5)]
        closes = cf.build_closes_live(picks, tracker=tracker, bp=bp)
        self.assertEqual(closes["nba1"], {"close": {"under": "-107", "over": "-119"},
                                          "side": "under", "market": "prop"})
        self.assertEqual(closes["nfl1"], {"close": {"under": "-113", "over": "-113"},
                                          "side": "over", "market": "prop"})
        self.assertIn(("ladder", "NBA", 27926, 156), bp.calls)
        self.assertIn(("ladder", "NFL", 21915, 103), bp.calls)
        self.assertIn(("props", "NBA", "2026-10-25"), bp.calls)

    def test_player_listed_in_two_events_is_never_guessed(self):
        bp = self._bp()
        picks = [_settled("nfl2", "NFL", "Josh Allen Over 250.5 passing yards", 250.5)]
        self.assertEqual(cf.build_closes_live(picks, tracker=tracker, bp=bp), {})
        self.assertFalse([c for c in bp.calls if c[0] == "ladder"])

    def test_wrong_line_num_is_unmeasured_not_matched(self):
        bp = self._bp()
        picks = [_settled("nfl3", "NFL", "Aaron Rodgers Under 224.5 passing yards", 229.5)]
        self.assertEqual(cf.build_closes_live(picks, tracker=tracker, bp=bp), {})

    def test_line_not_priced_both_sides_is_unmeasured(self):
        bp = self._bp()
        picks = [_settled("nba2", "NBA", "Rui Hachimura Under 17.5 Points", 17.5)]
        self.assertEqual(cf.build_closes_live(picks, tracker=tracker, bp=bp), {})

    def test_empty_stat_map_does_not_abort_the_pass(self):
        # An empty map makes build_closes call extract_prop with 2 args. That used to
        # raise TypeError and abort the whole pass (MLB included); now it is a skip.
        bp = self._bp()
        picks = [_settled("nba1", "NBA", "Rui Hachimura Under 16.5 Points", 16.5)]
        closes = cf.build_closes(
            picks, sport="NBA", stat_map={}, resolve_event=lambda d, pl: 27926,
            fetch_ladders=lambda ev, mk: [], normalize_name=_norm,
            extract_prop=cf.strict_extract_prop(tracker.extract_prop))
        self.assertEqual(closes, {})

    def test_unsupported_sport_is_ignored(self):
        bp = self._bp()
        picks = [_settled("nhl1", "NHL", "Connor McDavid Over 0.5 goals", 0.5)]
        self.assertEqual(cf.build_closes_live(picks, tracker=tracker, bp=bp), {})
        self.assertFalse([c for c in bp.calls if c[1] == "NHL"])

    def test_mlb_still_resolves_through_probable_pitchers_with_sport_mlb(self):
        bp = FakeBP(
            events={"MLB": [{"id": 98219, "pitchers": {"home": {"name": "Patrick Corbin"},
                                                       "visitor": None}}]},
            ladders={("MLB", 98219, 405): LADDERS})
        picks = [_pick()]
        closes = cf.build_closes_live(picks, tracker=tracker, bp=bp)
        self.assertEqual(closes["p1"], {"close": {"under": "-115", "over": "-125"},
                                        "side": "under", "market": "prop"})
        self.assertNotIn(("props", "MLB", "2026-06-26"), bp.calls)   # pitcher index sufficed


if __name__ == "__main__":
    unittest.main()
