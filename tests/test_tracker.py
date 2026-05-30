import importlib.util
import sys
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock
import json

# Load tracker module without installing it as a package
_spec = importlib.util.spec_from_file_location(
    "tracker",
    Path(__file__).parent.parent / ".agents" / "skills" / "bet-tracker" / "tracker.py",
)
tracker = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tracker)
# Register under its name so patch("tracker.<attr>") targets resolve.
sys.modules["tracker"] = tracker


class TestAmericanToImpliedProb(unittest.TestCase):
    def test_negative_odds(self):
        result = tracker.american_to_implied_prob("-110")
        self.assertAlmostEqual(result, 110 / 210, places=5)

    def test_positive_odds(self):
        result = tracker.american_to_implied_prob("+120")
        self.assertAlmostEqual(result, 100 / 220, places=5)

    def test_bookmaker_suffix_stripped(self):
        result = tracker.american_to_implied_prob("-110 @ DraftKings")
        self.assertAlmostEqual(result, 110 / 210, places=5)

    def test_plus_odds_with_suffix(self):
        result = tracker.american_to_implied_prob("+150 @ FanDuel")
        self.assertAlmostEqual(result, 100 / 250, places=5)

    def test_unparseable_raises(self):
        with self.assertRaises((ValueError, Exception)):
            tracker.american_to_implied_prob("even")


class TestCalcUnitsWonLost(unittest.TestCase):
    def test_win_negative_odds(self):
        # -110 line, 1 unit: win = 100/110 * 1
        result = tracker.calc_units_won_lost("-110", 1, "win")
        self.assertAlmostEqual(result, round(100 / 110, 3))

    def test_win_positive_odds(self):
        # +120 line, 2 units: win = 120/100 * 2
        result = tracker.calc_units_won_lost("+120", 2, "win")
        self.assertAlmostEqual(result, round(120 / 100 * 2, 3))

    def test_loss_negative_odds(self):
        result = tracker.calc_units_won_lost("-110", 2, "loss")
        self.assertEqual(result, -2.0)

    def test_loss_positive_odds(self):
        result = tracker.calc_units_won_lost("+150", 3, "loss")
        self.assertEqual(result, -3.0)

    def test_push_returns_zero(self):
        self.assertEqual(tracker.calc_units_won_lost("-110", 1, "push"), 0.0)

    def test_void_returns_zero(self):
        self.assertEqual(tracker.calc_units_won_lost("+120", 2, "void"), 0.0)


class TestCalcClv(unittest.TestCase):
    def test_positive_clv(self):
        # Bet at -110, closes at -120 → closing is more juice → positive CLV for us
        result = tracker.calc_clv("-110", "-120")
        self.assertGreater(result, 0)

    def test_negative_clv(self):
        # Bet at -110, closes at -100 → closing is less juice → negative CLV
        result = tracker.calc_clv("-110", "-100")
        self.assertLess(result, 0)

    def test_unparseable_closing_line_raises_or_returns_none(self):
        try:
            result = tracker.calc_clv("-110", "N/A")
            self.assertIsNone(result)
        except (ValueError, Exception):
            pass  # either behavior is acceptable per issue spec


class TestDetermineOutcome(unittest.TestCase):
    # Run line
    def test_rl_win(self):
        self.assertEqual(tracker.determine_outcome("rl", 2, 1.5), "win")

    def test_rl_loss_short(self):
        self.assertEqual(tracker.determine_outcome("rl", 1, 1.5), "loss")

    def test_rl_loss_negative_margin(self):
        self.assertEqual(tracker.determine_outcome("rl", -1, 1.5), "loss")

    def test_rl_push_whole_number_line(self):
        self.assertEqual(tracker.determine_outcome("rl", 2, 2.0), "push")

    def test_rl_no_push_on_half_line(self):
        # Margin exactly equal to a .5 line can't push
        self.assertEqual(tracker.determine_outcome("rl", 1, 1.0), "push")  # whole number = push
        self.assertNotEqual(tracker.determine_outcome("rl", 1, 1.5), "push")

    def test_rl_run_line_string(self):
        self.assertEqual(tracker.determine_outcome("run line", 3, 1.5), "win")

    # Moneyline
    def test_ml_win(self):
        self.assertEqual(tracker.determine_outcome("ml", 3, None), "win")

    def test_ml_loss(self):
        self.assertEqual(tracker.determine_outcome("ml", -2, None), "loss")

    def test_ml_push(self):
        self.assertEqual(tracker.determine_outcome("ml", 0, None), "push")


class TestFetchMlbResult(unittest.TestCase):
    def _make_game(self, home_score, away_score, status="Final", home_name="Arizona Diamondbacks", away_name="Los Angeles Dodgers"):
        return {
            "teams": {
                "home": {
                    "team": {"name": home_name, "abbreviation": "ARI"},
                    "score": home_score,
                },
                "away": {
                    "team": {"name": away_name, "abbreviation": "LAD"},
                    "score": away_score,
                },
            },
            "status": {"detailedState": status},
        }

    def _api_response(self, games):
        return json.dumps({
            "dates": [{"games": games}]
        }).encode()

    @patch("urllib.request.urlopen")
    def test_final_game_found(self, mock_urlopen):
        mock_cm = MagicMock()
        mock_cm.__enter__ = MagicMock(return_value=mock_cm)
        mock_cm.__exit__ = MagicMock(return_value=False)
        mock_cm.read.return_value = self._api_response([
            self._make_game(6, 3, status="Final")
        ])
        mock_urlopen.return_value = mock_cm

        result = tracker.fetch_mlb_result("2026-05-27", "Arizona")
        self.assertIsNotNone(result)
        self.assertEqual(result["margin"], 3)   # home won 6-3
        self.assertIn("Final", result["status"])

    @patch("urllib.request.urlopen")
    def test_game_not_yet_final(self, mock_urlopen):
        mock_cm = MagicMock()
        mock_cm.__enter__ = MagicMock(return_value=mock_cm)
        mock_cm.__exit__ = MagicMock(return_value=False)
        mock_cm.read.return_value = self._api_response([
            self._make_game(3, 2, status="In Progress")
        ])
        mock_urlopen.return_value = mock_cm

        result = tracker.fetch_mlb_result("2026-05-27", "Arizona")
        self.assertIsNone(result)

    @patch("urllib.request.urlopen")
    def test_no_game_found(self, mock_urlopen):
        mock_cm = MagicMock()
        mock_cm.__enter__ = MagicMock(return_value=mock_cm)
        mock_cm.__exit__ = MagicMock(return_value=False)
        mock_cm.read.return_value = json.dumps({"dates": []}).encode()
        mock_urlopen.return_value = mock_cm

        result = tracker.fetch_mlb_result("2026-05-27", "Arizona")
        self.assertIsNone(result)

    @patch("urllib.request.urlopen")
    def test_network_error(self, mock_urlopen):
        mock_urlopen.side_effect = Exception("timeout")

        result = tracker.fetch_mlb_result("2026-05-27", "Arizona")
        self.assertIsNone(result)


# ── Shared fixtures (issues #17/#18/#19) ────────────────────────────────────────

def make_game(home_score, away_score, status="Final",
              home_name="Arizona Diamondbacks", away_name="Pittsburgh Pirates",
              home_abbr="ARI", away_abbr="PIT", game_pk=12345):
    """Build a schedule game dict in the shape fetch_mlb_schedule returns."""
    return {
        "gamePk": game_pk,
        "teams": {
            "home": {"team": {"name": home_name, "abbreviation": home_abbr}, "score": home_score},
            "away": {"team": {"name": away_name, "abbreviation": away_abbr}, "score": away_score},
        },
        "status": {"detailedState": status},
    }


def make_boxscore():
    """Boxscore with a pitcher (Burnes), two same-last-name batters (Betts), and a no-pitching batter."""
    return {
        "teams": {
            "away": {"players": {
                "ID1": {"person": {"fullName": "Corbin Burnes"},
                        "stats": {"pitching": {"strikeOuts": 8}}},
                "ID2": {"person": {"fullName": "Mookie Betts"},
                        "stats": {"batting": {"hits": 2, "totalBases": 4, "rbi": 1,
                                              "baseOnBalls": 1, "runs": 2, "doubles": 1,
                                              "homeRuns": 1, "stolenBases": 0}}},
            }},
            "home": {"players": {
                "ID3": {"person": {"fullName": "Chad Betts"},
                        "stats": {"batting": {"hits": 0, "totalBases": 0, "rbi": 0}}},
            }},
        }
    }


def make_espn_nba_summary(booker_pts=30, durant_pts=20):
    """
    ESPN NBA summary fixture in the live shape the adapter consumes:
    boxscore.players[] team blocks, each statistics[0] with parallel labels/stats
    arrays (NOT a keyed object). Includes a DNP player (empty stats) to exercise
    the skip path. Two teams: Suns (home, idx 0), Lakers (away, idx 1).
    """
    labels = ["MIN", "PTS", "FG", "3PT", "FT", "REB", "AST", "STL", "BLK"]
    def athlete(name, stats):
        return {"athlete": {"displayName": name}, "didNotPlay": not stats, "stats": stats}
    return {
        "boxscore": {
            "players": [
                {"team": {"displayName": "Phoenix Suns"},
                 "statistics": [{"name": None, "labels": labels, "athletes": [
                     athlete("Devin Booker", ["36", str(booker_pts), "10-20", "3-7", "5-5", "4", "6", "1", "0"]),
                     athlete("Bench Warmer", []),  # DNP → skipped
                 ]}]},
                {"team": {"displayName": "Los Angeles Lakers"},
                 "statistics": [{"name": None, "labels": labels, "athletes": [
                     athlete("Kevin Durant", ["38", str(durant_pts), "8-18", "2-5", "2-2", "7", "3", "0", "1"]),
                 ]}]},
            ]
        }
    }


def make_nba_boxscore(booker_pts=30, durant_pts=20):
    """Sport-agnostic NBA boxscore (post-adapter) for direct routing tests."""
    return tracker.adapt_espn_nba_boxscore(make_espn_nba_summary(booker_pts, durant_pts))


def make_pick(**over):
    base = {"id": "test-1", "sport": "MLB", "bet": "", "line": "-110",
            "units": 1.0, "line_num": None, "model": "v1-trends", "result": None}
    base.update(over)
    return base


# ── #17: pure / fixture-only units ──────────────────────────────────────────────

class TestClassifyBet(unittest.TestCase):
    def test_explicit_bet_type_passthrough(self):
        for bt in ("prop", "total", "rl", "ml"):
            self.assertEqual(tracker.classify_bet({"bet_type": bt, "bet": "anything"}), bt)

    def test_explicit_bet_type_case_insensitive(self):
        self.assertEqual(tracker.classify_bet({"bet_type": "PROP", "bet": "x"}), "prop")

    def test_infer_run_line_from_rl_token(self):
        self.assertEqual(tracker.classify_bet({"bet": "Diamondbacks -1.5 RL"}), "rl")

    def test_infer_run_line_from_phrase(self):
        self.assertEqual(tracker.classify_bet({"bet": "Pirates +1.5 run line"}), "rl")

    def test_infer_game_total(self):
        self.assertEqual(tracker.classify_bet({"bet": "Over 8.5 runs"}), "total")

    def test_infer_prop_strikeouts(self):
        self.assertEqual(tracker.classify_bet({"bet": "Corbin Burnes Over 6.5 strikeouts"}), "prop")

    def test_infer_prop_nplus_form(self):
        self.assertEqual(tracker.classify_bet({"bet": "Mookie Betts 2+ hits"}), "prop")

    def test_fallback_moneyline(self):
        self.assertEqual(tracker.classify_bet({"bet": "Diamondbacks ML"}), "ml")

    def test_unrecognized_falls_back_to_ml(self):
        self.assertEqual(tracker.classify_bet({"bet": "Diamondbacks vs Pirates"}), "ml")


class TestExtractProp(unittest.TestCase):
    def test_over_form(self):
        spec = tracker.extract_prop("Corbin Burnes Over 6.5 strikeouts", 6.5)
        self.assertEqual(spec["player"], "corbin burnes")
        self.assertEqual(spec["stat_group"], "pitching")
        self.assertEqual(spec["stat_key"], "strikeOuts")
        self.assertEqual(spec["side"], "over")
        self.assertEqual(spec["threshold"], 6.5)

    def test_under_form(self):
        spec = tracker.extract_prop("Mookie Betts Under 1.5 total bases", 1.5)
        self.assertEqual(spec["side"], "under")
        self.assertEqual(spec["stat_group"], "batting")
        self.assertEqual(spec["stat_key"], "totalBases")
        self.assertEqual(spec["threshold"], 1.5)

    def test_nplus_form_becomes_over_minus_half(self):
        spec = tracker.extract_prop("Mookie Betts 2+ hits", None)
        self.assertEqual(spec["side"], "over")
        self.assertEqual(spec["threshold"], 1.5)
        self.assertEqual(spec["stat_key"], "hits")
        self.assertEqual(spec["player"], "mookie betts")

    def test_multiword_stat_preferred(self):
        spec = tracker.extract_prop("Mookie Betts Over 1.5 total bases", 1.5)
        self.assertEqual(spec["stat_key"], "totalBases")

    def test_unmapped_stat_returns_none(self):
        # "triples" is intentionally NOT in PROP_STAT_MAP → must not be scored.
        self.assertIsNone(tracker.extract_prop("Mike Trout Over 1.5 triples", 1.5))

    def test_surname_containing_keyword_does_not_false_match(self):
        # Whole-word matching: short stat keys must NOT match inside surnames.
        # Each bet is for the UNMAPPED stat "triples" → must return None, never
        # silently resolve as walks/runs/hits from the surname (walk⊂Walker,
        # run⊂Bruno, hit⊂White).
        for bet in ("Christian Walker Over 0.5 triples",
                    "Bruno Over 0.5 triples",
                    "Tyler White Over 0.5 triples"):
            self.assertIsNone(tracker.extract_prop(bet, 0.5), bet)

    def test_mapped_stat_still_matches_for_colliding_surname(self):
        # The fix must not over-correct: a real walks prop for Walker still resolves.
        spec = tracker.extract_prop("Christian Walker Over 0.5 walks", 0.5)
        self.assertEqual(spec["stat_key"], "baseOnBalls")
        self.assertEqual(spec["player"], "christian walker")

    def test_walks_maps_to_batting_base_on_balls(self):
        spec = tracker.extract_prop("Mookie Betts Over 0.5 walks", 0.5)
        self.assertEqual(spec["stat_group"], "batting")
        self.assertEqual(spec["stat_key"], "baseOnBalls")

    def test_home_runs_multiword_maps_correctly(self):
        spec = tracker.extract_prop("Mookie Betts Over 0.5 home runs", 0.5)
        self.assertEqual(spec["stat_key"], "homeRuns")

    def test_no_side_returns_none(self):
        self.assertIsNone(tracker.extract_prop("Mike Trout 2 hits", None))

    def test_over_without_line_num_returns_none(self):
        self.assertIsNone(tracker.extract_prop("Corbin Burnes Over strikeouts", None))

    def test_empty_player_returns_none(self):
        self.assertIsNone(tracker.extract_prop("Over 6.5 strikeouts", 6.5))


class TestResolvePropValue(unittest.TestCase):
    def setUp(self):
        self.box = make_boxscore()

    def test_found_by_last_name(self):
        value, reason = tracker.resolve_prop_value(self.box, "corbin burnes", "pitching", "strikeOuts")
        self.assertEqual(value, 8)
        self.assertIsNone(reason)

    def test_not_found(self):
        value, reason = tracker.resolve_prop_value(self.box, "nolan ryan", "pitching", "strikeOuts")
        self.assertIsNone(value)
        self.assertIn("not found", reason)

    def test_ambiguous_last_name(self):
        value, reason = tracker.resolve_prop_value(self.box, "anthony betts", "batting", "hits")
        self.assertIsNone(value)
        self.assertIn("ambiguous", reason)

    def test_exact_full_name_disambiguates(self):
        value, reason = tracker.resolve_prop_value(self.box, "mookie betts", "batting", "hits")
        self.assertEqual(value, 2)
        self.assertIsNone(reason)

    def test_missing_stat_group_skips(self):
        value, reason = tracker.resolve_prop_value(self.box, "mookie betts", "pitching", "strikeOuts")
        self.assertIsNone(value)
        self.assertIsNotNone(reason)


class TestPropOutcome(unittest.TestCase):
    def test_over_win(self):
        self.assertEqual(tracker.prop_outcome(8, "over", 6.5), "win")

    def test_over_loss(self):
        self.assertEqual(tracker.prop_outcome(5, "over", 6.5), "loss")

    def test_under_win(self):
        self.assertEqual(tracker.prop_outcome(1, "under", 1.5), "win")

    def test_under_loss(self):
        self.assertEqual(tracker.prop_outcome(3, "under", 1.5), "loss")

    def test_exact_threshold_pushes(self):
        self.assertEqual(tracker.prop_outcome(6, "over", 6), "push")
        self.assertEqual(tracker.prop_outcome(2, "under", 2), "push")


class TestNormalizeName(unittest.TestCase):
    def test_lowercases(self):
        self.assertEqual(tracker._normalize_name("Mookie Betts"), "mookie betts")

    def test_strips_accents(self):
        self.assertEqual(tracker._normalize_name("José Ramírez"), "jose ramirez")

    def test_strips_punctuation(self):
        self.assertEqual(tracker._normalize_name("Jr., Ronald Acuña!"), "jr ronald acuna")


# ── #21: pure player-name cleaner (annotation stripping before normalization) ────

class TestCleanPlayerName(unittest.TestCase):
    def test_strips_parenthetical_team(self):
        self.assertEqual(tracker.clean_player_name("Corbin Burnes (Diamondbacks)"),
                         "Corbin Burnes")

    def test_strips_bracketed_annotation(self):
        self.assertEqual(tracker.clean_player_name("Corbin Burnes [ARI]"),
                         "Corbin Burnes")

    def test_strips_sportsbook_suffix(self):
        self.assertEqual(tracker.clean_player_name("Corbin Burnes @ FanDuel"),
                         "Corbin Burnes")

    def test_strips_both_annotations(self):
        self.assertEqual(tracker.clean_player_name("Corbin Burnes (Diamondbacks) @ DraftKings"),
                         "Corbin Burnes")

    def test_plain_name_untouched(self):
        self.assertEqual(tracker.clean_player_name("Mookie Betts"), "Mookie Betts")

    def test_accents_and_jr_survive_through_normalization(self):
        # Cleaner only strips structure; accents/Jr. survive to _normalize_name.
        cleaned = tracker.clean_player_name("José Ramírez Jr. (Guardians)")
        self.assertEqual(tracker._normalize_name(cleaned), "jose ramirez jr")


# ── #18: MLB API client (mock-based) ────────────────────────────────────────────

class TestHttpGetJson(unittest.TestCase):
    def _cm(self, payload):
        cm = MagicMock()
        cm.__enter__ = MagicMock(return_value=cm)
        cm.__exit__ = MagicMock(return_value=False)
        cm.read.return_value = json.dumps(payload).encode()
        return cm

    @patch("urllib.request.urlopen")
    def test_success_returns_parsed_json(self, mock_urlopen):
        mock_urlopen.return_value = self._cm({"ok": True})
        self.assertEqual(tracker._http_get_json("http://x"), {"ok": True})

    @patch("urllib.request.urlopen")
    def test_sends_browser_user_agent(self, mock_urlopen):
        mock_urlopen.return_value = self._cm({"ok": 1})
        tracker._http_get_json("http://x")
        req = mock_urlopen.call_args.args[0]
        self.assertIn("Mozilla", " ".join(str(v) for v in req.headers.values()))

    @patch("tracker.time.sleep", lambda *_a, **_k: None)
    @patch("urllib.request.urlopen")
    def test_retries_then_succeeds(self, mock_urlopen):
        mock_urlopen.side_effect = [Exception("boom"), self._cm({"ok": 2})]
        self.assertEqual(tracker._http_get_json("http://x", retries=3), {"ok": 2})
        self.assertEqual(mock_urlopen.call_count, 2)

    @patch("tracker.time.sleep", lambda *_a, **_k: None)
    @patch("urllib.request.urlopen")
    def test_all_retries_fail_returns_none(self, mock_urlopen):
        mock_urlopen.side_effect = Exception("down")
        self.assertIsNone(tracker._http_get_json("http://x", retries=3))
        self.assertEqual(mock_urlopen.call_count, 3)


class TestFindMlbGameForBet(unittest.TestCase):
    @patch.object(tracker, "fetch_mlb_schedule")
    def test_matches_team_by_last_word(self, mock_sched):
        mock_sched.return_value = [make_game(5, 2)]  # ARI Diamondbacks vs PIT Pirates
        result = tracker.find_mlb_game_for_bet("2026-05-27", "Pittsburgh Pirates -1.5 RL")
        self.assertIsNotNone(result)
        self.assertEqual(result["total_runs"], 7)

    @patch.object(tracker, "fetch_mlb_schedule")
    def test_game_not_final_returns_none(self, mock_sched):
        mock_sched.return_value = [make_game(5, 2, status="In Progress")]
        self.assertIsNone(tracker.find_mlb_game_for_bet("2026-05-27", "Pirates ML"))

    @patch.object(tracker, "fetch_mlb_schedule")
    def test_no_matching_team_returns_none(self, mock_sched):
        mock_sched.return_value = [make_game(5, 2)]
        self.assertIsNone(tracker.find_mlb_game_for_bet("2026-05-27", "Yankees ML"))


# ── #19: cmd_auto_resolve routing + never-mis-score-as-ML regression ─────────────

class TestCmdAutoResolveRouting(unittest.TestCase):
    def _run(self, picks, **patches):
        """Run cmd_auto_resolve with load/save patched; returns whether SystemExit was raised."""
        ctxs = [patch.object(tracker, "load_picks", return_value=picks),
                patch.object(tracker, "save_picks")]
        for name, val in patches.items():
            ctxs.append(patch.object(tracker, name, return_value=val))
        exited = False
        started = [c.start() for c in ctxs]
        try:
            try:
                tracker.cmd_auto_resolve(None)
            except SystemExit:
                exited = True
        finally:
            for c in ctxs:
                c.stop()
        return exited

    def test_non_mlb_pick_left_open(self):
        p = make_pick(sport="NFL", bet="Chiefs -3.5 Spread")
        exited = self._run([p])
        self.assertIsNone(p["result"])
        self.assertTrue(exited)  # nothing resolved → sys.exit(0)

    def test_prop_routes_to_prop_path(self):
        p = make_pick(bet="Corbin Burnes Over 6.5 strikeouts", line_num=6.5)
        self._run([p],
                  find_mlb_game_for_bet={"game_pk": 1, "final_score": "PIT 2, ARI 5"},
                  fetch_mlb_boxscore=make_boxscore())
        self.assertEqual(p["result"], "win")  # 8 K vs over 6.5
        self.assertIn("prop_result", p)
        self.assertNotIn("game_margin", p)  # regression: NOT scored as moneyline

    def test_annotated_prop_with_team_resolves(self):
        # #21: a prop carrying a parenthetical team annotation now RESOLVES from
        # the boxscore (clean_player_name strips "(Diamondbacks)" before name
        # matching). It must still classify as a prop and never be scored on the
        # game margin.
        p = make_pick(bet="Corbin Burnes (Diamondbacks) Over 6.5 strikeouts", line_num=6.5)
        self._run([p],
                  find_mlb_game_for_bet={"game_pk": 1, "final_score": "PIT 2, ARI 5"},
                  fetch_mlb_boxscore=make_boxscore())
        self.assertEqual(tracker.classify_bet(p), "prop")
        self.assertEqual(p["result"], "win")  # 8 K vs over 6.5
        self.assertIn("prop_result", p)
        self.assertNotIn("game_margin", p)    # regression: never scored as moneyline

    def test_prop_with_sportsbook_suffix_resolves(self):
        # #21: a copy-pasted line with a trailing "@ FanDuel" suffix resolves.
        p = make_pick(bet="Corbin Burnes Over 6.5 strikeouts @ FanDuel", line_num=6.5)
        self._run([p],
                  find_mlb_game_for_bet={"game_pk": 1, "final_score": "PIT 2, ARI 5"},
                  fetch_mlb_boxscore=make_boxscore())
        self.assertEqual(p["result"], "win")
        self.assertNotIn("game_margin", p)

    def test_annotated_prop_unmatchable_player_still_left_open(self):
        # #21 / ADR 0004: stripping annotations must not relax the hard guarantee.
        # An unknown player (even after cleaning) is still left OPEN, never
        # mis-scored as a game-line bet.
        p = make_pick(bet="Unknown Player (Diamondbacks) Over 6.5 strikeouts @ DraftKings",
                      line_num=6.5)
        exited = self._run([p],
                           find_mlb_game_for_bet={"game_pk": 1, "final_score": "PIT 2, ARI 5"},
                           fetch_mlb_boxscore=make_boxscore())
        self.assertEqual(tracker.classify_bet(p), "prop")
        self.assertIsNone(p["result"])      # skipped, not guessed
        self.assertNotIn("game_margin", p)  # never scored as moneyline
        self.assertTrue(exited)             # nothing resolved → sys.exit(0)

    def test_total_routes_to_total_path(self):
        p = make_pick(bet="Over 8.5 runs", line_num=8.5)
        self._run([p],
                  find_mlb_game_for_bet={"total_runs": 10, "final_score": "PIT 4, ARI 6"})
        self.assertEqual(p["result"], "win")  # 10 vs over 8.5
        self.assertEqual(p["prop_result"], "10 total runs")

    def test_moneyline_routes_to_game_path(self):
        p = make_pick(bet="Diamondbacks ML")
        self._run([p],
                  fetch_mlb_result={"margin": 3, "final_score": "PIT 2, ARI 5"})
        self.assertEqual(p["result"], "win")
        self.assertEqual(p["game_margin"], 3)

    def test_run_line_routes_to_game_path(self):
        p = make_pick(bet="Diamondbacks -1.5 RL", line_num=1.5)
        self._run([p],
                  fetch_mlb_result={"margin": 3, "final_score": "PIT 2, ARI 5"})
        self.assertEqual(p["result"], "win")  # margin 3 covers -1.5
        self.assertEqual(p["game_margin"], 3)

    def test_unresolvable_prop_left_open(self):
        p = make_pick(bet="Corbin Burnes Over 6.5 strikeouts", line_num=6.5)
        exited = self._run([p], find_mlb_game_for_bet=None)  # game not final / not found
        self.assertIsNone(p["result"])
        self.assertTrue(exited)

    # ── #22: expanded MLB stat-keyword map (end-to-end routing regression) ────────
    # Fixture Mookie Betts: walks=1, runs=2, doubles=1, homeRuns=1, stolenBases=0.

    def _resolve_betts_prop(self, bet, line_num):
        p = make_pick(bet=bet, line_num=line_num)
        self._run([p],
                  find_mlb_game_for_bet={"game_pk": 1, "final_score": "PIT 2, ARI 5"},
                  fetch_mlb_boxscore=make_boxscore())
        return p

    def test_walks_prop_resolves_win(self):
        p = self._resolve_betts_prop("Mookie Betts Over 0.5 walks", 0.5)
        self.assertEqual(p["result"], "win")  # 1 walk vs over 0.5
        self.assertNotIn("game_margin", p)

    def test_walks_prop_resolves_loss(self):
        p = self._resolve_betts_prop("Mookie Betts Over 1.5 walks", 1.5)
        self.assertEqual(p["result"], "loss")  # 1 walk vs over 1.5

    def test_runs_scored_prop_resolves_win(self):
        p = self._resolve_betts_prop("Mookie Betts Over 1.5 runs", 1.5)
        self.assertEqual(p["result"], "win")  # 2 runs vs over 1.5

    def test_doubles_prop_resolves_win(self):
        p = self._resolve_betts_prop("Mookie Betts Over 0.5 doubles", 0.5)
        self.assertEqual(p["result"], "win")  # 1 double vs over 0.5

    def test_home_run_prop_resolves_win(self):
        p = self._resolve_betts_prop("Mookie Betts Over 0.5 home runs", 0.5)
        self.assertEqual(p["result"], "win")  # 1 HR vs over 0.5

    def test_stolen_base_prop_resolves_loss(self):
        p = self._resolve_betts_prop("Mookie Betts Over 0.5 stolen bases", 0.5)
        self.assertEqual(p["result"], "loss")  # 0 SB vs over 0.5

    def test_walks_push(self):
        # N+ form: "2+ walks" → Over (1.5). 1 walk vs over 1.5 → loss; use 1.0 to push.
        p = make_pick(bet="Mookie Betts Under 1 walks", line_num=1.0)
        self._run([p],
                  find_mlb_game_for_bet={"game_pk": 1, "final_score": "PIT 2, ARI 5"},
                  fetch_mlb_boxscore=make_boxscore())
        self.assertEqual(p["result"], "push")  # 1 walk == 1.0

    def test_nplus_form_still_resolves_as_over(self):
        # "2+ runs" → Over (1.5). Betts scored 2 → win. Confirms N+ form intact.
        p = make_pick(bet="Mookie Betts 2+ runs", line_num=None)
        self._run([p],
                  find_mlb_game_for_bet={"game_pk": 1, "final_score": "PIT 2, ARI 5"},
                  fetch_mlb_boxscore=make_boxscore())
        self.assertEqual(p["result"], "win")
        self.assertNotIn("game_margin", p)

    def test_unmapped_stat_prop_left_open(self):
        # "triples" is not in PROP_STAT_MAP → classify falls through to ml, the game
        # path can't match a player-named bet to a team, so it is left OPEN, never scored.
        p = make_pick(bet="Mookie Betts Over 0.5 triples", line_num=0.5)
        exited = self._run([p],
                           find_mlb_game_for_bet={"game_pk": 1, "final_score": "PIT 2, ARI 5"},
                           fetch_mlb_boxscore=make_boxscore(),
                           fetch_mlb_result=None)
        self.assertIsNone(p["result"])  # never scored
        self.assertTrue(exited)

    def test_unmapped_stat_for_colliding_surname_left_open(self):
        # Regression: a triples prop (unmapped) for a player whose surname contains
        # a stat keyword (Walker → "walk") must be left OPEN, never silently scored
        # as a walks prop. Boxscore is available, so only correct classification
        # keeps this open.
        p = make_pick(bet="Christian Walker Over 0.5 triples", line_num=0.5)
        exited = self._run([p],
                           find_mlb_game_for_bet={"game_pk": 1, "final_score": "PIT 2, ARI 5"},
                           fetch_mlb_boxscore=make_boxscore(),
                           fetch_mlb_result=None)
        self.assertIsNone(p["result"])      # never scored
        self.assertNotIn("prop_result", p)  # not resolved as any prop
        self.assertTrue(exited)

    # ── #24: NBA points Player Prop (ESPN path, end-to-end routing regression) ─────
    # Fixture: Devin Booker 30 pts, Kevin Durant 20 pts (make_nba_boxscore defaults).

    def test_nba_points_prop_resolves_win(self):
        p = make_pick(sport="NBA", bet="Devin Booker Over 27.5 points", line_num=27.5)
        self._run([p],
                  find_nba_game_for_bet={"game_id": "401", "final_score": "LAL 110, PHX 118"},
                  fetch_nba_boxscore=make_nba_boxscore())
        self.assertEqual(p["result"], "win")   # 30 pts vs over 27.5
        self.assertEqual(tracker.classify_bet(p), "prop")
        self.assertIn("prop_result", p)
        self.assertNotIn("game_margin", p)     # regression: never scored as a Game-Line Bet

    def test_nba_points_prop_resolves_loss(self):
        p = make_pick(sport="NBA", bet="Devin Booker Over 32.5 points", line_num=32.5)
        self._run([p],
                  find_nba_game_for_bet={"game_id": "401", "final_score": "LAL 110, PHX 118"},
                  fetch_nba_boxscore=make_nba_boxscore())
        self.assertEqual(p["result"], "loss")  # 30 pts vs over 32.5

    def test_nba_points_prop_resolves_push(self):
        p = make_pick(sport="NBA", bet="Devin Booker Under 30 points", line_num=30.0)
        self._run([p],
                  find_nba_game_for_bet={"game_id": "401", "final_score": "LAL 110, PHX 118"},
                  fetch_nba_boxscore=make_nba_boxscore())
        self.assertEqual(p["result"], "push")  # 30 == 30.0

    def test_nba_points_under_resolves_win(self):
        p = make_pick(sport="NBA", bet="Kevin Durant Under 24.5 points", line_num=24.5)
        self._run([p],
                  find_nba_game_for_bet={"game_id": "401", "final_score": "LAL 110, PHX 118"},
                  fetch_nba_boxscore=make_nba_boxscore())
        self.assertEqual(p["result"], "win")   # 20 pts vs under 24.5

    def test_nba_nplus_points_resolves_as_over(self):
        # "20+ points" → Over (19.5). Durant scored 20 → win. Confirms N+ form on NBA path.
        p = make_pick(sport="NBA", bet="Kevin Durant 20+ points", line_num=None)
        self._run([p],
                  find_nba_game_for_bet={"game_id": "401", "final_score": "LAL 110, PHX 118"},
                  fetch_nba_boxscore=make_nba_boxscore())
        self.assertEqual(p["result"], "win")   # 20 vs over 19.5
        self.assertNotIn("game_margin", p)

    def test_nba_unmatchable_player_left_open(self):
        # ADR 0004/0005 guarantee preserved on the NBA path: an unknown player is
        # left OPEN, never mis-scored.
        p = make_pick(sport="NBA", bet="Nobody Atall Over 27.5 points", line_num=27.5)
        exited = self._run([p],
                           find_nba_game_for_bet={"game_id": "401", "final_score": "LAL 110, PHX 118"},
                           fetch_nba_boxscore=make_nba_boxscore())
        self.assertIsNone(p["result"])         # skipped, not guessed
        self.assertNotIn("game_margin", p)     # never scored as a Game-Line Bet
        self.assertTrue(exited)                # nothing resolved → sys.exit(0)

    def test_nba_game_not_final_left_open(self):
        p = make_pick(sport="NBA", bet="Devin Booker Over 27.5 points", line_num=27.5)
        exited = self._run([p], find_nba_game_for_bet=None)  # not found / not final
        self.assertIsNone(p["result"])
        self.assertTrue(exited)

    def test_nba_non_prop_left_open(self):
        # Only NBA Player Props auto-resolve in #24; a moneyline is left open.
        p = make_pick(sport="NBA", bet="Suns ML")
        exited = self._run([p])
        self.assertIsNone(p["result"])
        self.assertTrue(exited)


class TestAdaptEspnNbaBoxscore(unittest.TestCase):
    """Focused unit test for the ESPN → sport-agnostic adapter (issue #24)."""

    def test_adapts_to_person_fullname_and_scoring_points(self):
        box = tracker.adapt_espn_nba_boxscore(make_espn_nba_summary(booker_pts=33, durant_pts=21))
        # Booker is on the home block (idx 0), Durant on away (idx 1).
        players = {**box["teams"]["home"]["players"], **box["teams"]["away"]["players"]}
        by_name = {pd["person"]["fullName"]: pd for pd in players.values()}
        self.assertIn("Devin Booker", by_name)
        self.assertIn("Kevin Durant", by_name)
        self.assertEqual(by_name["Devin Booker"]["stats"]["scoring"]["points"], 33)
        self.assertEqual(by_name["Kevin Durant"]["stats"]["scoring"]["points"], 21)

    def test_dnp_player_skipped(self):
        box = tracker.adapt_espn_nba_boxscore(make_espn_nba_summary())
        names = [pd["person"]["fullName"]
                 for side in ("home", "away")
                 for pd in box["teams"][side]["players"].values()]
        self.assertNotIn("Bench Warmer", names)  # DNP (empty stats) excluded

    def test_adapter_output_resolves_via_shared_resolver(self):
        # The adapted shape must feed the SAME resolve_prop_value used for MLB.
        box = tracker.adapt_espn_nba_boxscore(make_espn_nba_summary(booker_pts=28))
        value, reason = tracker.resolve_prop_value(box, "devin booker", "scoring", "points")
        self.assertIsNone(reason)
        self.assertEqual(value, 28)

    def test_missing_boxscore_yields_empty_teams(self):
        box = tracker.adapt_espn_nba_boxscore({})
        self.assertEqual(box["teams"]["home"]["players"], {})
        self.assertEqual(box["teams"]["away"]["players"], {})


if __name__ == "__main__":
    unittest.main()
