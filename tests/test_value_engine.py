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
import json
import sys
import unittest
from datetime import datetime, timedelta, timezone
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
        # ADR 0011: power for every game line (moneyline, spread, total); props stay
        # multiplicative. (Moneylines were multiplicative before ADR 0011.)
        self.assertEqual(ve.devig_method("total 210.5"), "power")
        self.assertEqual(ve.devig_method("spread -3.5"), "power")
        self.assertEqual(ve.devig_method("moneyline"), "power")
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


# ==================================================================================
# ADR 0011 — explicit market kind, kind-based de-vig and gate, Exchange Benchmark (#106)
# ==================================================================================
class TestMarketKind(unittest.TestCase):
    def test_every_label_existing_callers_pass_maps_to_a_kind(self):
        # Labels in use today: clv_fetch / close_capture pass "prop"; clv_backfill passes
        # the pick's bet_type (tracker.classify_bet tokens) or the "moneyline" default;
        # the V3 SKILL boards pass "moneyline" / "player_prop" / "total 210.5".
        expected = {
            "moneyline": "moneyline", "ml": "moneyline",
            "spread": "spread", "rl": "spread", "pl": "spread", "spread -3.5": "spread",
            "run line": "spread", "puck line": "spread",
            "total": "total", "total 210.5": "total",
            "prop": "prop", "player_prop": "prop", "Player Prop": "prop",
        }
        for label, kind in expected.items():
            self.assertEqual(ve.market_kind(label), kind, msg=label)

    def test_kinds_map_to_themselves(self):
        self.assertEqual(ve.MARKET_KINDS, {"moneyline", "spread", "total", "prop"})
        for kind in ve.MARKET_KINDS:
            self.assertEqual(ve.market_kind(kind), kind)

    def test_unknown_label_raises_instead_of_guessing(self):
        # The old gate searched the label for "prop", so "points" / "PRA" got the 2%
        # game-line gate. A stat name is not a market kind: it must be passed explicitly.
        for label in ("points", "PRA", "", None, "propane", "first half", "total bases"):
            with self.assertRaises(ValueError, msg=repr(label)):
                ve.market_kind(label)


class TestDevigByKind(unittest.TestCase):
    def test_power_for_every_game_kind_multiplicative_for_props(self):
        for kind in ("moneyline", "spread", "total"):
            self.assertEqual(ve.devig_method(kind), "power", msg=kind)
        self.assertEqual(ve.devig_method("prop"), "multiplicative")

    def test_unknown_kind_raises(self):
        with self.assertRaises(ValueError):
            ve.devig_method("points")
        with self.assertRaises(ValueError):
            ve.fair_two_way(-110, -110, "PRA")

    def test_moneyline_fair_price_is_power_devig(self):
        # ARI -120 / SF +110. Power: k solves .5455^k + .4762^k = 1 -> fair SF .4650
        # (multiplicative gave .4661, inflating the dog). Hand-checked by bisection.
        fa, fb = ve.fair_two_way("-120", "+110", "moneyline")
        self.assertAlmostEqual(fa, 0.5350, places=4)
        self.assertAlmostEqual(fb, 0.4650, places=4)

    def test_prop_fair_price_is_unchanged_multiplicative(self):
        # REFERENCE.md §2: Over -115 / Under -105 -> fair .5108 / .4892
        fa, fb = ve.fair_two_way(-115, -105, "prop")
        self.assertAlmostEqual(fa, 0.5108, places=4)
        self.assertAlmostEqual(fb, 0.4892, places=4)

    def test_heavy_favourite_longshot_not_inflated(self):
        # Benchmark around -1200/+800 (here -1200/+900, 2.3% hold) vs retail +809.
        # Power puts the dog at ~.083 (< +809's .1099), so CLV is clearly negative;
        # multiplicative's ~.098 is the inflated longshot ADR 0011 removed.
        fav, dog = ve.fair_two_way(-1200, 900, "moneyline")
        self.assertAlmostEqual(dog, 0.0829, places=3)
        _, mult_dog = ve.multiplicative_devig(ve.american_to_prob(-1200), ve.american_to_prob(900))
        self.assertLess(dog, mult_dog)
        self.assertLess(ve.projected_clv(dog, ve.american_to_prob(809)), -0.2)


class TestGateByKind(unittest.TestCase):
    def test_three_percent_for_props_two_for_game_kinds(self):
        self.assertEqual(ve.gate_threshold("prop"), 0.03)
        for kind in ("moneyline", "spread", "total"):
            self.assertEqual(ve.gate_threshold(kind), 0.02, msg=kind)

    def test_stat_named_labels_no_longer_get_the_game_line_gate(self):
        # Regression: "points" and "PRA" used to get 2% because they lack the word "prop".
        for label in ("points", "PRA", "rebounds"):
            with self.assertRaises(ValueError, msg=label):
                ve.gate_threshold(label)
            with self.assertRaises(ValueError, msg=label):
                ve.clears_gate(0.025, label)


class TestDevigInputValidation(unittest.TestCase):
    def test_american_odds_are_rejected_not_turned_into_complex_numbers(self):
        for fn in (ve.power_devig, ve.multiplicative_devig):
            with self.assertRaises(ValueError, msg=fn.__name__):
                fn(-110, -110)
            with self.assertRaises(ValueError, msg=fn.__name__):
                fn(0.52, 150)

    def test_probabilities_must_be_strictly_inside_zero_one(self):
        for fn in (ve.power_devig, ve.multiplicative_devig):
            for bad in ((0.0, 0.5), (0.5, 1.0), (1.2, 0.3), (None, 0.5), (True, 0.5)):
                with self.assertRaises(ValueError, msg=f"{fn.__name__}{bad}"):
                    fn(*bad)


# --- Exchange Benchmark --------------------------------------------------------------
NOW = datetime(2026, 10, 25, 2, 12, 0, tzinfo=timezone.utc)   # scans run on an aware clock


def q(book_id, line, odds_a, odds_b, minutes_old=5):
    """A quote as scan_market / exchange_benchmark consume it."""
    updated = (NOW - timedelta(minutes=minutes_old)).strftime("%Y-%m-%d %H:%M:%S")
    return {"book_id": book_id, "line": line, "odds_a": odds_a, "odds_b": odds_b,
            "updated": updated}


class TestExchangeBenchmarkConstants(unittest.TestCase):
    def test_adr_0011_venues_and_limits(self):
        self.assertEqual(ve.BENCHMARK_BOOKS, {60, 68, 73, 75, 38})
        self.assertEqual(ve.RETAIL_BOOKS, {10, 12, 13, 14, 18, 19, 24, 33, 39, 45, 49})
        self.assertEqual(ve.OPERATOR, {73: "polymarket", 75: "polymarket"})
        self.assertEqual(ve.MAX_BENCHMARK_HOLD, 0.03)
        self.assertEqual(ve.MAX_QUOTE_AGE_MIN, 60)
        self.assertEqual(ve.MIN_OPERATORS, 2)
        # Skins and exchanges are never candidates.
        self.assertFalse(ve.RETAIL_BOOKS & ve.BENCHMARK_BOOKS)
        self.assertFalse({15, 27} & ve.RETAIL_BOOKS)


class TestExchangeBenchmark(unittest.TestCase):
    def test_two_operators_give_the_median_devigged_price(self):
        # Novig -105/-105 -> .5000; Kalshi +100/-110 -> power fair_a .4884 (hand-solved).
        b = ve.exchange_benchmark([q(60, 7.5, -105, -105), q(68, 7.5, 100, -110)],
                                  7.5, "total", NOW)
        self.assertEqual(len(b["operators"]), 2)
        self.assertEqual(len(b["quotes_used"]), 2)
        fa60 = 0.5
        fa68 = ve.power_devig(ve.american_to_prob(100), ve.american_to_prob(-110))[0]
        self.assertAlmostEqual(fa68, 0.4884, places=3)
        self.assertAlmostEqual(b["fair_a"], (fa60 + fa68) / 2, places=9)
        self.assertAlmostEqual(b["fair_a"] + b["fair_b"], 1.0, places=9)

    def test_polymarket_twins_are_one_operator_so_no_benchmark(self):
        quotes = [q(73, 7.5, -105, -105), q(75, 7.5, -104, -106)]
        self.assertIsNone(ve.exchange_benchmark(quotes, 7.5, "total", NOW))

    def test_freshest_quote_per_operator_is_kept(self):
        quotes = [q(73, 7.5, 120, -130, minutes_old=30), q(75, 7.5, -105, -105, minutes_old=2),
                  q(60, 7.5, -105, -105)]
        b = ve.exchange_benchmark(quotes, 7.5, "total", NOW)
        self.assertEqual(len(b["operators"]), 2)
        self.assertIn(75, [x["book_id"] for x in b["quotes_used"]])
        self.assertNotIn(73, [x["book_id"] for x in b["quotes_used"]])
        self.assertAlmostEqual(b["fair_a"], 0.5, places=9)

    def test_stale_quote_is_excluded(self):
        # 61 minutes old is out; exactly 60 is still in.
        stale = [q(60, 7.5, -105, -105), q(68, 7.5, -105, -105, minutes_old=61)]
        self.assertIsNone(ve.exchange_benchmark(stale, 7.5, "total", NOW))
        edge = [q(60, 7.5, -105, -105), q(68, 7.5, -105, -105, minutes_old=60)]
        self.assertIsNotNone(ve.exchange_benchmark(edge, 7.5, "total", NOW))

    def test_wide_quote_is_excluded(self):
        # +100/-115 holds 3.49% (> 3%); -105/-105 holds 2.44%.
        wide = [q(60, 7.5, -105, -105), q(68, 7.5, 100, -115)]
        self.assertIsNone(ve.exchange_benchmark(wide, 7.5, "total", NOW))

    def test_only_quotes_at_exactly_the_line_count(self):
        quotes = [q(60, 3.0, -105, -105), q(68, 2.5, -105, -105)]
        self.assertIsNone(ve.exchange_benchmark(quotes, 3.0, "spread", NOW))
        self.assertIsNone(ve.exchange_benchmark(quotes, 2.5, "spread", NOW))

    def test_one_sided_and_retail_quotes_are_ignored(self):
        quotes = [q(60, 7.5, -105, None), q(12, 7.5, -105, -105), q(10, 7.5, -105, -105),
                  q(68, 7.5, -105, -105)]
        self.assertIsNone(ve.exchange_benchmark(quotes, 7.5, "total", NOW))

    def test_undated_quote_is_excluded_never_assumed_fresh(self):
        quotes = [q(60, 7.5, -105, -105), dict(q(68, 7.5, -105, -105), updated=None)]
        self.assertIsNone(ve.exchange_benchmark(quotes, 7.5, "total", NOW))


class TestScanMarket(unittest.TestCase):
    BENCH_EVEN = [q(60, 7.5, -105, -105), q(68, 7.5, -105, -105)]   # fair .5000 / .5000

    def _row(self, rows, book_id, side):
        return next(r for r in rows if r["book_id"] == book_id and r["side"] == side)

    def test_one_row_per_retail_side_with_log_reject_no_bet(self):
        quotes = self.BENCH_EVEN + [q(12, 7.5, 110, -130), q(10, 7.5, 103, -125)]
        rows = ve.scan_market(quotes, "total", NOW)
        self.assertEqual(len(rows), 4)
        dk_over = self._row(rows, 12, "a")       # +110 = .4762 vs fair .5 -> +5.0%
        self.assertAlmostEqual(dk_over["clv"], 0.05, places=4)
        self.assertEqual(dk_over["action"], "log")
        self.assertEqual(dk_over["edge_type"], "clv_value")
        self.assertEqual(dk_over["units"], 1)
        fd_over = self._row(rows, 10, "a")       # +103 = .4926 -> +1.5%, under the 2% gate
        self.assertAlmostEqual(fd_over["clv"], 0.015, places=4)
        self.assertEqual(fd_over["action"], "reject")
        for book in (12, 10):                    # the -130 / -125 sides are worse than fair
            self.assertEqual(self._row(rows, book, "b")["action"], "no_bet")
        self.assertEqual(dk_over["operators"], [60, 68])

    def test_prop_kind_uses_the_three_percent_gate(self):
        quotes = self.BENCH_EVEN + [q(12, 7.5, 104, -140)]    # +104 = .4902 -> +2.0%
        self.assertEqual(self._row(ve.scan_market(quotes, "total", NOW), 12, "a")["action"], "log")
        self.assertEqual(self._row(ve.scan_market(quotes, "prop", NOW), 12, "a")["action"], "reject")

    def test_benchmark_and_non_retail_books_are_never_candidates(self):
        # 60/68 are the benchmark; 36 (Underdog), 15 and 27 (skins), 0 (consensus) aren't retail.
        quotes = self.BENCH_EVEN + [q(36, 7.5, 150, -200), q(15, 7.5, 150, -200),
                                    q(27, 7.5, 150, -200), q(0, 7.5, 150, -200)]
        self.assertEqual(ve.scan_market(quotes, "total", NOW), [])

    def test_line_mismatch_produces_no_row(self):
        # Retail +2.5 against a benchmark at +3 only: never compared across numbers.
        quotes = [q(60, 3.0, -105, -105), q(68, 3.0, -104, -106), q(12, 2.5, 150, -200)]
        self.assertEqual(ve.scan_market(quotes, "spread", NOW), [])

    def test_each_line_is_benchmarked_on_its_own(self):
        quotes = [q(60, 3.0, -105, -105), q(68, 3.0, -105, -105), q(12, 3.0, 110, -130),
                  q(60, 2.5, -120, 110), q(12, 2.5, 110, -130)]   # 2.5 has one operator
        rows = ve.scan_market(quotes, "spread", NOW)
        self.assertEqual({(r["side"], r["line"]) for r in rows}, {("a", 3.0), ("b", -3.0)})
        self.assertEqual(len(rows), 2)

    def test_line_without_benchmark_gives_no_row(self):
        quotes = [q(73, 7.5, -105, -105), q(75, 7.5, -105, -105), q(12, 7.5, 150, -200)]
        self.assertEqual(ve.scan_market(quotes, "total", NOW), [])

    def test_heavy_favourite_moneyline_longshot_is_negative_clv(self):
        # Benchmark around -1200/+800 (Novig -1200/+900, Kalshi -1100/+800, both <= 3% hold);
        # retail +809 on the dog. Power de-vig puts the dog near .087, below +809's .1099.
        quotes = [q(60, None, -1200, 900), q(68, None, -1100, 800), q(12, None, -1500, 809)]
        rows = ve.scan_market(quotes, "moneyline", NOW)
        dog = self._row(rows, 12, "b")
        self.assertLess(dog["clv"], -0.15)
        self.assertEqual(dog["action"], "no_bet")

    def test_moneyline_ignores_the_feeds_line_number(self):
        # BettingPros stamps moneylines with line 1 (bet365 with 0): no number to match.
        quotes = [q(60, 1, -105, -105), q(68, 1, -105, -105), q(24, 0, 110, -130)]
        rows = ve.scan_market(quotes, "moneyline", NOW)
        self.assertEqual(self._row(rows, 24, "a")["action"], "log")

    def test_unknown_kind_raises(self):
        with self.assertRaises(ValueError):
            ve.scan_market(self.BENCH_EVEN, "points", NOW)


# --- real-data cases: the live board pulled 2026-10-24 (tests/fixtures) ---------------
_LIVE = json.loads((Path(__file__).parent / "fixtures" / "exchange_benchmark_offers.json").read_text())
LIVE_NOW = datetime(2026, 10, 25, 2, 12, 0, tzinfo=timezone.utc)   # when poll1 was pulled


class TestQuotesFromOffer(unittest.TestCase):
    def test_moneyline_offer_becomes_one_two_way_quote_per_book(self):
        out = ve.quotes_from_offer(_LIVE["colts_vikings_moneyline"], "moneyline")
        self.assertEqual(out["labels"], ("Colts", "Vikings"))
        by_book = {x["book_id"]: x for x in out["quotes"]}
        self.assertEqual((by_book[12]["odds_a"], by_book[12]["odds_b"]), (260, -325))
        self.assertEqual((by_book[60]["odds_a"], by_book[60]["odds_b"]), (257, -264))
        self.assertEqual(by_book[68]["updated"], "2026-10-25 02:01:13")
        self.assertEqual(len(out["quotes"]), 18)   # consensus (0) + 17 books

    def test_prop_ladder_pairs_over_and_under_at_the_same_number(self):
        out = ve.quotes_from_offer(_LIVE["gainwell_receiving_yards"], "prop")
        self.assertEqual(out["labels"], ("Over", "Under"))
        mgm = [x for x in out["quotes"] if x["book_id"] == 19]
        self.assertEqual([(x["line"], x["odds_a"], x["odds_b"]) for x in mgm], [(14.5, 110, -150)])
        # Fanatics (14) is flagged is_off on the feed, so it is not a quote at all.
        self.assertNotIn(14, {x["book_id"] for x in out["quotes"]})

    def test_spread_pairs_a_number_with_its_negation(self):
        offer = {"selections": [
            {"label": "Vikings", "books": [{"id": 12, "lines": [
                {"line": -6.5, "cost": -108, "updated": "2026-10-25 02:05:00"},
                {"line": -7.5, "cost": 105, "updated": "2026-10-25 02:05:00"}]}]},
            {"label": "Colts", "books": [{"id": 12, "lines": [
                {"line": 6.5, "cost": -112, "updated": "2026-10-25 02:04:00"},
                {"line": 5.5, "cost": 130, "updated": "2026-10-25 02:05:00"}]}]}]}
        out = ve.quotes_from_offer(offer, "spread")
        self.assertEqual(out["quotes"], [{"book_id": 12, "line": -6.5, "odds_a": -108,
                                          "odds_b": -112, "updated": "2026-10-25 02:04:00"}])


class TestLiveBoardCases(unittest.TestCase):
    def test_colts_moneyline_draftkings_260_against_the_exchange_benchmark(self):
        # DraftKings Colts +260 (.2778). Benchmark at 02:12 UTC: Novig 257/-264,
        # ProphetX 255/-260, Polymarket 245/-257, Kalshi 245/-257 -> four operators,
        # all fresh and under 1% hold. Power fair Colts: .2769 / .2793 / .2840 / .2840,
        # median .2817 -> +1.4%: positive but under the 2% gate.
        quotes = ve.quotes_from_offer(_LIVE["colts_vikings_moneyline"], "moneyline")["quotes"]
        bench = ve.exchange_benchmark(quotes, 1, "moneyline", LIVE_NOW)
        self.assertEqual(bench["operators"], [38, 60, 68, "polymarket"])
        self.assertAlmostEqual(bench["fair_a"], 0.2817, places=4)
        dk = next(r for r in ve.scan_market(quotes, "moneyline", LIVE_NOW)
                  if r["book_id"] == 12 and r["side"] == "a")
        self.assertAlmostEqual(dk["clv"], 0.014, delta=0.001)
        self.assertEqual(dk["action"], "reject")

    def test_colts_without_prophetx_reproduces_the_issue_106_figure(self):
        # Issue #106 expects 3 operators and about +2.2%, which clears the 2% gate. That
        # figure came from the 2026-10-24 review script, whose venue list had no
        # ProphetX (38). Dropping 38 reproduces it exactly: median .2840 -> +2.24%.
        # It clears the 2% gate, but at +260 the ½-Kelly stake is 0.43% of bankroll,
        # under the existing 0.5% floor (units_from_clv), so the row is still `reject`.
        quotes = [x for x in ve.quotes_from_offer(_LIVE["colts_vikings_moneyline"],
                                                  "moneyline")["quotes"] if x["book_id"] != 38]
        bench = ve.exchange_benchmark(quotes, 1, "moneyline", LIVE_NOW)
        self.assertEqual(len(bench["operators"]), 3)
        dk = next(r for r in ve.scan_market(quotes, "moneyline", LIVE_NOW)
                  if r["book_id"] == 12 and r["side"] == "a")
        self.assertAlmostEqual(dk["clv"], 0.0224, delta=0.0005)
        self.assertTrue(ve.clears_gate(dk["clv"], "moneyline"))
        self.assertEqual(dk["units"], 0)
        self.assertEqual(dk["action"], "reject")
        self.assertIn("1u minimum", dk["reason"])

    def test_gainwell_under_14_5_has_one_benchmark_operator_so_no_row(self):
        # BetMGM Under 14.5 -150. At 14.5 the only benchmark venue is Novig, and its
        # Under is a -99900 placeholder. One operator -> no benchmark -> no row.
        quotes = ve.quotes_from_offer(_LIVE["gainwell_receiving_yards"], "prop")["quotes"]
        self.assertIsNone(ve.exchange_benchmark(quotes, 14.5, "prop", LIVE_NOW))
        rows = ve.scan_market(quotes, "prop", LIVE_NOW)
        self.assertFalse([r for r in rows if r["book_id"] == 19])
        self.assertEqual(rows, [])   # no line on this ladder has two operators


# --- review fixes on PR #111 -----------------------------------------------------------
class TestPlaceholderAndUnderroundQuotes(unittest.TestCase):
    def test_feed_placeholder_odds_are_recognised(self):
        # Novig's Gainwell Under 14.5 on the live board is -99900: a suspended side.
        quotes = ve.quotes_from_offer(_LIVE["gainwell_receiving_yards"], "prop")["quotes"]
        novig = next(x for x in quotes if x["book_id"] == 60 and x["line"] == 14.5)
        self.assertEqual(novig["odds_b"], -99900)
        self.assertTrue(ve.is_placeholder_odds(-99900))
        self.assertTrue(ve.is_placeholder_odds(99900))
        self.assertTrue(ve.is_placeholder_odds(10000))
        self.assertFalse(ve.is_placeholder_odds(9999))
        self.assertFalse(ve.is_placeholder_odds(-1200))
        self.assertFalse(ve.benchmark_eligible(novig, 14.5, "prop", LIVE_NOW))

    def test_placeholder_benchmark_quote_cannot_make_a_benchmark(self):
        # +99900/-120 "holds" -45% and used to pass the hold filter, producing a +90% log.
        for placeholder in (q(60, 7.5, 99900, -120), q(60, 7.5, 99900, -99900)):
            quotes = [placeholder, q(68, 7.5, -105, -105), q(12, 7.5, 150, -200)]
            self.assertIsNone(ve.exchange_benchmark(quotes, 7.5, "total", NOW))
            self.assertEqual(ve.scan_market(quotes, "total", NOW), [])

    def test_underround_beyond_half_a_point_is_excluded(self):
        # +110/+110 sums to .952 (hold -4.8%): not a real two-way price.
        self.assertIsNone(ve.exchange_benchmark(
            [q(60, 7.5, 110, 110), q(68, 7.5, -105, -105)], 7.5, "total", NOW))
        # +101/+100 sums to .9975 (hold -0.25%): within the tolerance, counts.
        self.assertIsNotNone(ve.exchange_benchmark(
            [q(60, 7.5, 101, 100), q(68, 7.5, -105, -105)], 7.5, "total", NOW))

    def test_retail_placeholder_side_gives_no_row(self):
        quotes = [q(60, 7.5, -105, -105), q(68, 7.5, -105, -105), q(12, 7.5, 110, -99900)]
        rows = ve.scan_market(quotes, "total", NOW)
        self.assertEqual([(r["book_id"], r["side"]) for r in rows], [(12, "a")])


class TestClockAndQuoteAge(unittest.TestCase):
    BENCH = [q(60, 7.5, -105, -105), q(68, 7.5, -105, -105)]

    def test_naive_now_is_rejected(self):
        naive = datetime(2026, 10, 25, 2, 12, 0)
        with self.assertRaises(ValueError):
            ve.exchange_benchmark(self.BENCH, 7.5, "total", naive)
        with self.assertRaises(ValueError):
            ve.scan_market(self.BENCH, "total", naive)

    def test_aware_now_in_another_zone_is_the_same_instant(self):
        az = timezone(timedelta(hours=-7))
        self.assertIsNotNone(ve.exchange_benchmark(self.BENCH, 7.5, "total", NOW.astimezone(az)))

    def test_future_stamped_benchmark_quote_is_excluded(self):
        # 4 hours after `now` was accepted before; up to 5 minutes of clock skew is fine.
        self.assertIsNone(ve.exchange_benchmark(
            [q(60, 7.5, -105, -105), q(68, 7.5, -105, -105, minutes_old=-240)], 7.5, "total", NOW))
        self.assertIsNone(ve.exchange_benchmark(
            [q(60, 7.5, -105, -105), q(68, 7.5, -105, -105, minutes_old=-6)], 7.5, "total", NOW))
        self.assertIsNotNone(ve.exchange_benchmark(
            [q(60, 7.5, -105, -105), q(68, 7.5, -105, -105, minutes_old=-4)], 7.5, "total", NOW))

    def test_retail_quote_older_than_a_day_or_future_stamped_gives_no_row(self):
        self.assertEqual(ve.MAX_RETAIL_QUOTE_AGE_MIN, 24 * 60)
        for age in (24 * 60 + 1, -240):
            rows = ve.scan_market(self.BENCH + [q(12, 7.5, 110, -130, minutes_old=age)], "total", NOW)
            self.assertEqual(rows, [], msg=age)
        rows = ve.scan_market(self.BENCH + [q(12, 7.5, 110, -130, minutes_old=23 * 60)], "total", NOW)
        self.assertEqual(len(rows), 2)

    def test_rows_carry_quote_and_benchmark_ages(self):
        bench = [q(60, 7.5, -105, -105, minutes_old=10), q(68, 7.5, -105, -105, minutes_old=45)]
        rows = ve.scan_market(bench + [q(12, 7.5, 110, -130, minutes_old=90)], "total", NOW)
        for r in rows:
            self.assertAlmostEqual(r["quote_age_min"], 90.0)
            self.assertAlmostEqual(r["benchmark_max_age_min"], 45.0)


class TestSpreadSideLine(unittest.TestCase):
    def test_side_b_reports_its_own_number(self):
        # Quote line is side A's: Raiders +3.5 means Chiefs -3.5.
        quotes = [q(60, 3.5, -105, -105), q(68, 3.5, -105, -105), q(12, 3.5, 110, -130)]
        rows = {r["side"]: r for r in ve.scan_market(quotes, "spread", NOW)}
        self.assertEqual(rows["a"]["line"], 3.5)
        self.assertEqual(rows["b"]["line"], -3.5)
        # Totals and props keep the shared number on both sides.
        rows = {r["side"]: r for r in ve.scan_market(
            [q(60, 7.5, -105, -105), q(68, 7.5, -105, -105), q(12, 7.5, 110, -130)], "total", NOW)}
        self.assertEqual((rows["a"]["line"], rows["b"]["line"]), (7.5, 7.5))


class TestPowerDevigBracket(unittest.TestCase):
    def test_underround_input_still_sums_to_one(self):
        fa, fb = ve.power_devig(0.001, 0.6)
        self.assertAlmostEqual(fa + fb, 1.0, places=9)
        self.assertGreater(fb, 0.6)   # an underround market is scaled UP, k < 1

    def test_sum_to_one_property_over_a_grid(self):
        grid = [0.001, 0.01, 0.05, 0.1, 0.25, 0.4, 0.5, 0.6, 0.75, 0.9, 0.95, 0.99, 0.999]
        for p_a in grid:
            for p_b in grid:
                fa, fb = ve.power_devig(p_a, p_b)
                self.assertAlmostEqual(fa + fb, 1.0, places=9, msg=(p_a, p_b))
                self.assertEqual(fa > fb, p_a > p_b, msg=(p_a, p_b))


if __name__ == "__main__":
    unittest.main()
