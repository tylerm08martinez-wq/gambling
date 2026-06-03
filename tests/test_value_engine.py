"""Table-driven tests for value_engine — the V3-Value de-vig / CLV engine (#44).

`value_engine` is the pure, deterministic core extracted out of the
sports-betting-value SKILL.md prompt (no more in-prompt arithmetic). These cases
reuse the *hand-verified numbers* from the skill's autoeval answer key:

    experiments: skills/sports-betting-value/autoeval/fixtures.py

Cross-repo import isn't available in gambling CI, so the four board snapshots are
vendored here verbatim — same inputs, same expected actions. Keep them in sync
with the autoeval fixtures: both encode the same worked-by-hand de-vig/CLV math
(every number below is derived in the fixtures' `rationale`).
"""

import importlib.util
import sys
import unittest
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "value_engine",
    Path(__file__).parent.parent / ".agents" / "skills" / "bet-tracker" / "value_engine.py",
)
value_engine = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(value_engine)
sys.modules["value_engine"] = value_engine
ve = value_engine


# --- the 4 autoeval board snapshots, vendored from experiments ---------------------
# (id/kind/input/expected mirror skills/sports-betting-value/autoeval/fixtures.py)
FIXTURES = [
    {
        "id": "game_line_clear_ev",  # price beats de-vig Pinnacle by >2% -> LOG
        "input": {
            "market": "moneyline", "game": "ARI @ SF", "time_to_start_min": 90,
            "pinnacle": {"ARI": "-120", "SF": "+110"},
            "best_book_prices": {"SF": "+120 (DK)", "ARI": "-118 (FD)"},
        },
        "expected": {"action": "log", "edge_type": "clv_value", "side": "SF",
                     "book": "DK", "units": 1, "clv_pct": 2.55},
    },
    {
        "id": "prop_below_gate",  # +2.2% prop clears the 2% game gate but not the 3% prop gate -> REJECT
        "input": {
            "market": "player_prop", "prop": "Zack Wheeler strikeouts O/U 6.5",
            "time_to_start_min": 200,
            "pinnacle": {"Over": "-130", "Under": "+115"},
            "best_book_prices": {"Over": "-116 (DK)"},
        },
        "expected": {"action": "reject", "edge_type": "clv_value", "clv_pct": 2.16},
    },
    {
        "id": "steam_no_clv",  # real 4-book steam but every price is worse than fair -> NO BET
        "input": {
            "market": "moneyline", "game": "LAD @ COL", "time_to_start_min": 60,
            "pinnacle": {"LAD": "-150", "COL": "+135"},
            "best_book_prices": {"LAD": "-148 (MGM)", "COL": "+130 (DK)"},
            "steam": "LAD -130(open) -> -148 at 4 books same direction",
        },
        "expected": {"action": "no_bet"},
    },
    {
        "id": "no_value_slate",  # nothing on the slate beats fair -> SIT OUT
        "input": {
            "time_to_start_min": 240,
            "markets": [
                {"game": "BOS @ MIA", "market": "total 210.5",
                 "pinnacle": {"Over": "-108", "Under": "-112"},
                 "best_book_prices": {"Over": "-110 (DK)", "Under": "-110 (FD)"}},
                {"game": "DEN @ MIN", "market": "moneyline",
                 "pinnacle": {"DEN": "-200", "MIN": "+175"},
                 "best_book_prices": {"DEN": "-198 (DK)", "MIN": "+172 (MGM)"}},
            ],
        },
        "expected": {"action": "sit_out"},
    },
]


class TestFixtureDecisions(unittest.TestCase):
    """End-to-end: evaluate_board(snapshot) must reach each fixture's verdict."""

    def _by_id(self, fid):
        return next(f for f in FIXTURES if f["id"] == fid)

    def test_game_line_clear_ev_logs(self):
        f = self._by_id("game_line_clear_ev")
        r = ve.evaluate_board(f["input"])
        exp = f["expected"]
        self.assertEqual(r["action"], "log")
        pick = r["picks"][0]
        self.assertEqual(pick["edge_type"], exp["edge_type"])
        self.assertEqual(pick["side"], exp["side"])
        self.assertEqual(pick["book"], exp["book"])
        self.assertEqual(pick["units"], exp["units"])
        self.assertAlmostEqual(pick["clv"] * 100, exp["clv_pct"], delta=0.3)

    def test_prop_below_gate_rejects(self):
        f = self._by_id("prop_below_gate")
        r = ve.evaluate_board(f["input"])
        self.assertEqual(r["action"], "reject")
        self.assertEqual(r["picks"], [])
        cand = r["rejected"][0]
        self.assertEqual(cand["edge_type"], "clv_value")
        # The whole point: it WOULD clear the 2% game gate but props need 3%.
        self.assertAlmostEqual(cand["clv"] * 100, f["expected"]["clv_pct"], delta=0.3)
        self.assertTrue(ve.clears_gate(cand["clv"], "moneyline"))
        self.assertFalse(ve.clears_gate(cand["clv"], "player_prop"))

    def test_steam_without_clv_is_no_bet(self):
        f = self._by_id("steam_no_clv")
        r = ve.evaluate_board(f["input"])
        self.assertEqual(r["action"], "no_bet")
        self.assertEqual(r["picks"], [])
        # Best CLV on either side is negative — chasing the post-steam price captures none.
        self.assertLessEqual(r["considered"][0]["best_clv"], 0)

    def test_no_value_slate_sits_out(self):
        f = self._by_id("no_value_slate")
        r = ve.evaluate_board(f["input"])
        self.assertEqual(r["action"], "sit_out")
        self.assertEqual(r["picks"], [])


class TestImpliedProb(unittest.TestCase):
    def test_favorite_and_underdog(self):
        self.assertAlmostEqual(ve.american_to_prob(-110), 0.5238, places=4)
        self.assertAlmostEqual(ve.american_to_prob(146), 0.4065, places=4)
        self.assertAlmostEqual(ve.american_to_prob("-120"), 0.5455, places=4)
        self.assertAlmostEqual(ve.american_to_prob("+110"), 0.4762, places=4)


class TestDevig(unittest.TestCase):
    def test_multiplicative_reference_example(self):
        # REFERENCE.md §2: Over -115 / Under -105 -> fair .5108 / .4892
        fa, fb = ve.multiplicative_devig(ve.american_to_prob(-115), ve.american_to_prob(-105))
        self.assertAlmostEqual(fa, 0.5108, places=4)
        self.assertAlmostEqual(fb, 0.4892, places=4)

    def test_multiplicative_fixture_moneyline(self):
        # fixture game_line_clear_ev: Pinnacle ARI -120 / SF +110 -> fair SF .4661
        fa, fb = ve.multiplicative_devig(ve.american_to_prob(-120), ve.american_to_prob(110))
        self.assertAlmostEqual(fa, 0.5339, places=4)  # ARI
        self.assertAlmostEqual(fb, 0.4661, places=4)  # SF

    def test_power_solves_invariant_and_agrees_near_5050(self):
        pa, pb = ve.american_to_prob(-108), ve.american_to_prob(-112)
        fa, fb = ve.power_devig(pa, pb)
        self.assertAlmostEqual(fa + fb, 1.0, places=6)  # de-vigged probs sum to 1
        ma, mb = ve.multiplicative_devig(pa, pb)
        self.assertAlmostEqual(fa, ma, delta=0.001)     # methods agree near 50/50
        self.assertLess(fa, 0.5)                         # -108 favorite side > 50% raw -> over priced; fair Over < .5

    def test_power_handles_wide_lopsided_market(self):
        # ~19% hold, lopsided -> root k > the nominal 1.5 bound; fair probs must still
        # sum to 1 (regression: a clamped k silently returned non-normalized probs).
        pa, pb = ve.american_to_prob(-900), ve.american_to_prob(250)
        fa, fb = ve.power_devig(pa, pb)
        self.assertAlmostEqual(fa + fb, 1.0, places=6)
        self.assertGreater(fa, fb)  # the -900 favorite stays the favorite

    def test_fair_prob_routes_method_by_market(self):
        # game lines that are spreads/totals use the power method; ML/props multiplicative
        self.assertEqual(ve.devig_method("total 210.5"), "power")
        self.assertEqual(ve.devig_method("spread -3.5"), "power")
        self.assertEqual(ve.devig_method("moneyline"), "multiplicative")
        self.assertEqual(ve.devig_method("player_prop"), "multiplicative")


class TestProjectedCLV(unittest.TestCase):
    def test_clv_is_fair_over_pbest_minus_one(self):
        # fixture: fair SF .4661, DK +120 implied .4545 -> +2.55%
        clv = ve.projected_clv(0.4661, ve.american_to_prob(120))
        self.assertAlmostEqual(clv, 0.0255, delta=0.0005)

    def test_clv_negative_when_price_worse_than_fair(self):
        # fixture steam_no_clv: fair LAD .5851, best -148 implied .5968 -> negative
        clv = ve.projected_clv(0.5851, ve.american_to_prob(-148))
        self.assertLess(clv, 0)


class TestGate(unittest.TestCase):
    def test_game_line_gate_is_2pct_prop_gate_is_3pct(self):
        self.assertTrue(ve.clears_gate(0.025, "moneyline"))   # +2.5% game line logs
        self.assertTrue(ve.clears_gate(0.020, "total 210.5"))
        self.assertFalse(ve.clears_gate(0.022, "player_prop"))  # +2.2% prop rejects
        self.assertTrue(ve.clears_gate(0.022, "moneyline"))     # same edge clears game gate
        self.assertFalse(ve.clears_gate(0.0, "moneyline"))


class TestUnits(unittest.TestCase):
    def test_tiny_stake_is_zero_units(self):
        # clv ~0.4% -> half-Kelly < 0.5% bankroll -> pass
        self.assertEqual(ve.units_from_clv(0.502, ve.american_to_prob(-100), 0.004,
                                           "moneyline", confirmation=False), 0)

    def test_standard_edge_is_one_unit(self):
        # fixture game_line_clear_ev: fair .4661 / best +120 -> 1u
        self.assertEqual(ve.units_from_clv(0.4661, ve.american_to_prob(120), 0.0255,
                                           "moneyline", confirmation=False), 1)

    def test_strong_edge_with_confirmation_is_two_units(self):
        # fair .60 / best +82(~.55) -> ~9% CLV, big half-Kelly, confirmed -> 2u
        self.assertEqual(ve.units_from_clv(0.60, 0.55, 0.091, "moneyline",
                                           confirmation=True), 2)

    def test_hard_cap_two_units(self):
        # an enormous (probably stale) edge still caps at 2u, never 3u+
        self.assertEqual(ve.units_from_clv(0.80, 0.50, 0.60, "moneyline",
                                           confirmation=True), 2)

    def test_two_units_reachable_end_to_end_and_gated_on_confirmation(self):
        # Pinnacle A -160/B +140 -> fair A .596; best A -115 (.535) -> +11.5% CLV.
        # With a confirmation flag the board must size to 2u; without it, 1u.
        board = {"market": "moneyline", "confirmation": True,
                 "pinnacle": {"A": "-160", "B": "+140"},
                 "best_book_prices": {"A": "-115 (DK)"}}
        confirmed = ve.evaluate_board(board)
        self.assertEqual(confirmed["action"], "log")
        self.assertEqual(confirmed["picks"][0]["units"], 2)
        unconfirmed = ve.evaluate_board({**board, "confirmation": False})
        self.assertEqual(unconfirmed["picks"][0]["units"], 1)


class TestSteamClassifier(unittest.TestCase):
    def test_three_plus_books_toward_pinnacle_is_usable_steam(self):
        s = ve.classify_steam(
            opening=-130, current_by_book={"DK": -148, "FD": -146, "MGM": -149, "CZR": -147},
            pinnacle_now=-150)
        self.assertTrue(s["is_steam"])
        self.assertTrue(s["is_mega"])        # 4+ books
        self.assertTrue(s["toward_pinnacle"])
        self.assertTrue(s["usable"])

    def test_move_past_pinnacle_is_not_usable(self):
        # books blew past the current Pinnacle number -> retail overreaction, skip
        s = ve.classify_steam(
            opening=-130, current_by_book={"DK": -158, "FD": -160, "MGM": -159},
            pinnacle_now=-150)
        self.assertTrue(s["is_steam"])
        self.assertFalse(s["toward_pinnacle"])
        self.assertFalse(s["usable"])

    def test_below_three_book_floor_is_not_steam(self):
        # only 2 books off the opening -> below the 3-book floor, not steam, not usable
        s = ve.classify_steam(
            opening=-130, current_by_book={"DK": -148, "FD": -146}, pinnacle_now=-150)
        self.assertFalse(s["is_steam"])
        self.assertFalse(s["usable"])
        # (the engine ignores steam entirely when picking — see test_steam_without_clv_is_no_bet)


if __name__ == "__main__":
    unittest.main()
