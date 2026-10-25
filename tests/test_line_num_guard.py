"""Issue #113: `line_num` must never be trusted over the bet text.

The nightly resolver wrote odds and game margins into `line_num` on props and totals
(Ace Bailey's row holds -108). Anything that grades from `line_num` would then grade an
Over 11.5 against -108: every Over a WIN, every Under a LOSS. These tests pin the guard:
the threshold comes from the bet text, and a disagreeing `line_num` leaves the pick OPEN.
"""

import argparse
import contextlib
import importlib.util
import io
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

_spec = importlib.util.spec_from_file_location(
    "tracker", Path(__file__).parent.parent / ".agents" / "skills" / "bet-tracker" / "tracker.py")
tracker = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tracker)
sys.modules["tracker"] = tracker

# The real 2026-10-23 row: the bet says 11.5, line_num holds the price.
ACE_BET = "Ace Bailey Over 11.5 Points (NOR @ UTA)"
ACE_CORRUPT_LINE_NUM = -108.0


class TestExtractPropRefusesADisagreeingLineNum(unittest.TestCase):
    def test_ace_bailey_row_shape_is_refused(self):
        self.assertIsNone(tracker.extract_prop(ACE_BET, ACE_CORRUPT_LINE_NUM,
                                               tracker.NBA_PROP_STAT_MAP))

    def test_ace_bailey_with_the_true_threshold_parses(self):
        spec = tracker.extract_prop(ACE_BET, 11.5, tracker.NBA_PROP_STAT_MAP)
        self.assertEqual((spec["player"], spec["side"], spec["threshold"]),
                         ("ace bailey", "over", 11.5))

    def test_over_under_pair_refused_when_line_num_is_odds(self):
        for bet in ("Jayson Tatum Over 26.5 Points (NYK @ BOS)",
                    "Jayson Tatum Under 26.5 Points (NYK @ BOS)"):
            self.assertIsNone(tracker.extract_prop(bet, -105.0, tracker.NBA_PROP_STAT_MAP), bet)

    def test_over_under_pair_parses_with_matching_line_num(self):
        over = tracker.extract_prop("Jayson Tatum Over 26.5 Points", 26.5, tracker.NBA_PROP_STAT_MAP)
        under = tracker.extract_prop("Jayson Tatum Under 26.5 Points", 26.5, tracker.NBA_PROP_STAT_MAP)
        self.assertEqual((over["side"], over["threshold"]), ("over", 26.5))
        self.assertEqual((under["side"], under["threshold"]), ("under", 26.5))

    def test_line_num_off_by_a_point_is_refused(self):
        # 16.0 vs "Under 16.5" (Grant Holmes, 2026-06-03): a near-miss is still a mismatch.
        self.assertIsNone(tracker.extract_prop("Grant Holmes Under 16.5 Outs Recorded", 16.0))

    def test_signed_total_style_line_num_is_refused(self):
        self.assertIsNone(tracker.extract_prop("Corbin Burnes Under 7.5 strikeouts", -7.5))

    def test_missing_line_num_uses_the_bet_text(self):
        spec = tracker.extract_prop("Corbin Burnes Over 6.5 strikeouts", None)
        self.assertEqual((spec["side"], spec["threshold"]), ("over", 6.5))

    def test_whole_number_threshold_in_text(self):
        spec = tracker.extract_prop("Peter Lambert Over 4 Strikeouts at Tampa Bay Rays", 4.0)
        self.assertEqual(spec["threshold"], 4.0)

    def test_two_different_thresholds_in_text_is_ambiguous(self):
        self.assertIsNone(tracker.extract_prop(
            "Corbin Burnes Under 5.5 strikeouts (moved from Under 6.5)", 5.5))

    def test_no_number_after_side_is_refused_even_with_line_num(self):
        # Without a threshold in the text there is nothing to check line_num against.
        self.assertIsNone(tracker.extract_prop("Corbin Burnes Over strikeouts", 6.5))

    def test_nplus_accepts_either_line_convention_and_refuses_odds(self):
        for ln in (None, 2.0, 1.5):
            spec = tracker.extract_prop("Mookie Betts 2+ hits", ln)
            self.assertEqual((spec["side"], spec["threshold"]), ("over", 1.5), ln)
        self.assertIsNone(tracker.extract_prop("Mookie Betts 2+ hits", -120.0))



def _ace_box(points=6):
    """Sport-agnostic (post-adapter) boxscore: Ace Bailey scored 6 on 2026-10-23."""
    return {"teams": {
        "away": {"players": {"1": {"person": {"fullName": "Ace Bailey"},
                                   "stats": {"scoring": {"points": points}}}}},
        "home": {"players": {}}}}


def _open_pick(**over):
    base = {"id": "20261023-nba-v1-ace-prop", "date": "2026-10-23", "sport": "NBA",
            "model": "v1-trends", "bet": ACE_BET, "bet_type": "prop", "line": "-108 @ Novig",
            "units": 1, "line_num": ACE_CORRUPT_LINE_NUM, "result": None}
    base.update(over)
    return base


def _auto_resolve(picks, box):
    src = tracker.PlayerPropSource(
        find_game=lambda date, bet: tracker.ResolvedGame(ref="401", final_score="UTA 120, NOR 119"),
        fetch_boxscore=lambda ref: box,
        stat_map=tracker.NBA_PROP_STAT_MAP)
    out = io.StringIO()
    with patch.object(tracker, "load_picks", return_value=picks), \
         patch.object(tracker, "save_picks") as save, \
         contextlib.redirect_stdout(out):
        try:
            tracker.cmd_auto_resolve(None, sources={"NBA": src})
        except SystemExit:
            pass
    return save, out.getvalue()


class TestOpenPropWithOddsInLineNumStaysOpen(unittest.TestCase):
    def test_open_nba_prop_with_odds_in_line_num_is_not_auto_resolved(self):
        # Graded against -108, "Over" with 6 points would be a WIN. It is a LOSS.
        p = _open_pick()
        save, out = _auto_resolve([p], _ace_box(6))
        self.assertIsNone(p["result"])
        self.assertNotIn("units_won_lost", p)
        save.assert_not_called()
        self.assertIn(p["id"], out)
        self.assertIn("line_num -108", out)     # the skip names the real cause
        self.assertIn("11.5", out)

    def test_corrupt_pra_row_is_not_reported_as_an_unsummable_combo(self):
        p = _open_pick(bet="Victor Wembanyama Under 40.5 Points+Rebounds+Assists (HOU @ SAS)",
                       line_num=-112.0)
        _, out = _auto_resolve([p], _ace_box(6))
        self.assertIsNone(p["result"])
        self.assertIn("line_num -112", out)
        self.assertNotIn("combined-stat", out)

    def test_same_pick_with_true_threshold_grades_from_the_box_score(self):
        p = _open_pick(line_num=11.5)
        _auto_resolve([p], _ace_box(6))
        self.assertEqual(p["result"], "loss")
        self.assertEqual(p["units_won_lost"], -1.0)
        self.assertEqual(p["prop_margin"], -5.5)



def _resolve_cli(pick, *argv):
    """Run `tracker.py resolve ...` through main() (so the argparse block is covered).
    Returns (exit_code, stderr, save_mock); exit_code is None on success."""
    picks = [pick]
    err = io.StringIO()
    code = None
    with patch.object(tracker, "load_picks", return_value=picks), \
         patch.object(tracker, "save_picks") as save, \
         patch.object(sys, "argv", ["tracker.py", "resolve", pick["id"], *argv]), \
         contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
        try:
            tracker.main()
        except SystemExit as e:
            code = e.code
    return code, err.getvalue(), save


def _settled_prop(**over):
    base = {"id": "20261023-nba-v1-jayson-prop", "date": "2026-10-23", "sport": "NBA",
            "model": "v1-trends", "bet": "Jayson Tatum Under 26.5 Points (NYK @ BOS)",
            "bet_type": "prop", "line": "-105", "units": 1, "line_num": 26.5, "result": None}
    base.update(over)
    return base


def _total(**over):
    base = {"id": "20260830-mlb-v2-sea-total", "date": "2026-08-30", "sport": "MLB",
            "model": "v2-sharp", "bet": "SEA @ TOR Under 8.5 total runs", "bet_type": "total",
            "line": "-130", "units": 1, "line_num": 8.5, "result": None}
    base.update(over)
    return base


class TestResolveRefusesGameLineFieldsOnPropsAndTotals(unittest.TestCase):
    def test_game_margin_refused_on_a_prop(self):
        p = _settled_prop()
        code, err, save = _resolve_cli(p, "loss", "--game-margin", "4")
        self.assertEqual(code, 1)
        self.assertIn("--game-margin", err)
        save.assert_not_called()
        self.assertIsNone(p["result"])          # nothing mutated
        self.assertNotIn("game_margin", p)

    def test_game_margin_refused_on_a_total(self):
        p = _total()
        code, err, save = _resolve_cli(p, "win", "--game-margin", "7")
        self.assertEqual(code, 1)
        save.assert_not_called()
        self.assertIsNone(p["result"])

    def test_game_margin_still_accepted_on_a_moneyline(self):
        p = {"id": "x-ml", "date": "2026-08-30", "sport": "MLB", "model": "v1-trends",
             "bet": "Yankees ML", "bet_type": "ml", "line": "-150", "units": 1, "result": None}
        code, _, save = _resolve_cli(p, "win", "--game-margin", "3", "--line-num", "0")
        self.assertIsNone(code)
        save.assert_called_once()
        self.assertEqual((p["result"], p["game_margin"]), ("win", 3))

    def test_odds_passed_as_line_num_refused_on_a_prop(self):
        p = _settled_prop()
        code, err, save = _resolve_cli(p, "loss", "--line-num", "-105")
        self.assertEqual(code, 1)
        self.assertIn("26.5", err)
        save.assert_not_called()
        self.assertEqual(p["line_num"], 26.5)

    def test_margin_passed_as_line_num_refused_on_a_total(self):
        p = _total()
        code, _, save = _resolve_cli(p, "win", "--line-num", "7")
        self.assertEqual(code, 1)
        save.assert_not_called()

    def test_true_threshold_accepted_as_line_num(self):
        p = _settled_prop(line_num=None)
        code, _, save = _resolve_cli(p, "loss", "--line-num", "26.5")
        self.assertIsNone(code)
        self.assertEqual((p["result"], p["line_num"]), ("loss", 26.5))

    def test_line_num_refused_when_bet_text_has_no_threshold(self):
        p = _settled_prop(bet="Jayson Tatum Under Points (NYK @ BOS)", line_num=None)
        code, _, save = _resolve_cli(p, "loss", "--line-num", "26.5")
        self.assertEqual(code, 1)
        save.assert_not_called()

    def test_prop_margin_accepts_a_half_point(self):
        # Thresholds end in .5, so a real margin is fractional: 13 pts vs U26.5 → -13.5.
        p = _settled_prop()
        code, _, _ = _resolve_cli(p, "win", "--prop-result", "13 points", "--prop-margin", "-13.5")
        self.assertIsNone(code)
        self.assertEqual(p["prop_margin"], -13.5)

    def test_whole_prop_margin_is_stored_as_an_int(self):
        p = _settled_prop(bet="Peter Lambert Over 4 Strikeouts", line_num=4.0, sport="MLB")
        _resolve_cli(p, "win", "--prop-margin", "2")
        self.assertEqual(p["prop_margin"], 2)
        self.assertIsInstance(p["prop_margin"], int)



def _auto_resolve_total(pick, total_runs, final_score="SEA 3, TOR 4"):
    game = {"game_pk": 1, "final_score": final_score, "total_runs": total_runs}
    with patch.object(tracker, "load_picks", return_value=[pick]), \
         patch.object(tracker, "save_picks"), \
         patch.object(tracker, "find_mlb_game_for_bet", return_value=game), \
         contextlib.redirect_stdout(io.StringIO()):
        try:
            tracker.cmd_auto_resolve(None, sources={})
        except SystemExit:
            pass


class TestGameTotalGradesFromTheBetText(unittest.TestCase):
    """The MLB total branch read `float(line_num)` directly. Real settled totals carry
    odds there (SEA @ TOR Under 8.5 has line_num -130): an open one would grade
    Under 8.5 against -130 and LOSE whatever the score."""

    def test_open_total_with_odds_in_line_num_stays_open(self):
        p = _total(line_num=-130.0)
        _auto_resolve_total(p, total_runs=7)
        self.assertIsNone(p["result"])

    def test_open_total_with_true_line_num_grades(self):
        p = _total()
        _auto_resolve_total(p, total_runs=7)
        self.assertEqual(p["result"], "win")       # 7 runs, Under 8.5

    def test_matchup_style_over_is_graded_as_an_over(self):
        # The side used to come from `^over`, so "Angels @ Rangers Over 8" graded as an
        # UNDER: 3 runs would have been a WIN. It is a LOSS.
        p = _total(id="20260822-mlb-v2-angels-total", bet="Angels @ Rangers Over 8", line_num=8.0)
        _auto_resolve_total(p, total_runs=3, final_score="Angels 3, Rangers 0")
        self.assertEqual(p["result"], "loss")



def _ledger():
    """Row shapes taken from the real picks.json (ids and values as of 2026-10-24)."""
    return [
        # odds in line_num + a game margin on a prop → both repaired
        _open_pick(result="loss", units_won_lost=-1.0, game_margin=1,
                   final_score="UTA 120, NOR 119", prop_result="6 points", prop_margin=-6),
        # line_num already right, game margin only
        {"id": "20261022-nfl-v1-hunter-prop", "date": "2026-10-22", "sport": "NFL",
         "model": "v1-trends", "bet": "Hunter Henry Over 31.5 receiving yards (NE @ CHI)",
         "bet_type": "prop", "line": "-110", "units": 1, "result": "win",
         "units_won_lost": 0.909, "line_num": 31.5, "game_margin": -6},
        # signed total
        {"id": "20260524-mlb-v1-under-total", "date": "2026-05-24", "sport": "MLB",
         "model": "v1-trends", "bet": "Under 7.5 Guardians at Phillies (Citizens Bank Park)",
         "line": "-110", "units": 1, "result": "win", "units_won_lost": 0.909,
         "line_num": -7.5, "game_margin": -4},
        # wrong final_score, correct result
        _settled_prop(line_num=-105.0, result="loss", units_won_lost=-1.0, game_margin=13,
                      final_score="NYK 107, BOS 103"),
        # ambiguous text: two thresholds → listed, left alone
        {"id": "amb-prop", "date": "2026-08-01", "sport": "MLB", "model": "v1-trends",
         "bet": "Corbin Burnes Under 5.5 strikeouts (moved from Under 6.5)", "bet_type": "prop",
         "line": "-110", "units": 1, "result": "loss", "units_won_lost": -1.0, "line_num": -110.0},
        # N+ with odds → convention ambiguous → listed, left alone
        {"id": "nplus-prop", "date": "2026-08-01", "sport": "MLB", "model": "v1-trends",
         "bet": "Mookie Betts 2+ hits", "bet_type": "prop", "line": "+120", "units": 1,
         "result": "win", "units_won_lost": 1.2, "line_num": 120.0},
        # moneyline keeps its game_margin and line_num
        {"id": "ml", "date": "2026-08-01", "sport": "MLB", "model": "v1-trends",
         "bet": "Yankees ML", "bet_type": "ml", "line": "-150", "units": 1, "result": "win",
         "units_won_lost": 0.667, "line_num": 0.0, "game_margin": 3},
    ]


def _money(picks):
    return [(p["id"], p.get("result"), p.get("units"), p.get("units_won_lost"), p.get("line"))
            for p in picks]


def _migrate(picks, apply=False):
    out = io.StringIO()
    with patch.object(tracker, "load_picks", return_value=picks), \
         patch.object(tracker, "save_picks") as save, contextlib.redirect_stdout(out):
        tracker.cmd_migrate_line_num(argparse.Namespace(apply=apply))
    return save, out.getvalue()


class TestMigrateLineNum(unittest.TestCase):
    def setUp(self):
        self.picks = _ledger()
        self.by_id = {p["id"]: p for p in self.picks}

    def test_dry_run_reports_but_never_writes(self):
        save, out = _migrate(self.picks)
        save.assert_not_called()
        self.assertIn("dry-run", out)
        self.assertIn("20261023-nba-v1-ace-prop", out)

    def test_apply_writes(self):
        save, _ = _migrate(self.picks, apply=True)
        save.assert_called_once()

    def test_game_margin_cleared_on_props_and_totals_only(self):
        _migrate(self.picks, apply=True)
        for pid in ("20261023-nba-v1-ace-prop", "20261022-nfl-v1-hunter-prop",
                    "20260524-mlb-v1-under-total", "20261023-nba-v1-jayson-prop"):
            self.assertIsNone(self.by_id[pid].get("game_margin"), pid)
        self.assertEqual(self.by_id["ml"]["game_margin"], 3)

    def test_line_num_restored_from_unambiguous_bet_text(self):
        _migrate(self.picks, apply=True)
        self.assertEqual(self.by_id["20261023-nba-v1-ace-prop"]["line_num"], 11.5)
        self.assertEqual(self.by_id["20261023-nba-v1-jayson-prop"]["line_num"], 26.5)
        self.assertEqual(self.by_id["20260524-mlb-v1-under-total"]["line_num"], 7.5)
        self.assertEqual(self.by_id["20261022-nfl-v1-hunter-prop"]["line_num"], 31.5)
        self.assertEqual(self.by_id["ml"]["line_num"], 0.0)

    def test_ambiguous_rows_are_listed_and_left_alone(self):
        _, out = _migrate(self.picks, apply=True)
        self.assertEqual(self.by_id["amb-prop"]["line_num"], -110.0)
        self.assertEqual(self.by_id["nplus-prop"]["line_num"], 120.0)
        self.assertIn("amb-prop", out)
        self.assertIn("nplus-prop", out)

    def test_the_two_named_final_scores_are_fixed(self):
        _migrate(self.picks, apply=True)
        self.assertEqual(self.by_id["20261023-nba-v1-jayson-prop"]["final_score"], "BOS 107, NY 103")
        self.assertEqual(self.by_id["20261023-nba-v1-ace-prop"]["final_score"], "UTA 120, NOR 119")

    def test_no_result_or_units_change(self):
        before = _money(self.picks)
        _migrate(self.picks, apply=True)
        self.assertEqual(_money(self.picks), before)

    def test_second_run_is_a_no_op(self):
        _migrate(self.picks, apply=True)
        save, out = _migrate(self.picks, apply=True)
        self.assertIn("changed rows: 0", out)



class TestReviewFollowUps(unittest.TestCase):
    """PR #115 review: three parse/format edge cases."""

    def test_vulgar_fraction_threshold_is_refused_not_truncated(self):
        # "Under 8½" used to parse as 8.0 — a different bet (8 can push, 8.5 cannot).
        for bet in ("Twins @ Cubs Under 8½ (game total)", "Twins @ Cubs Under 18½",
                    "Corbin Burnes Over 6¼ strikeouts", "Corbin Burnes Over 6.5¾ strikeouts"):
            self.assertIsNone(tracker.parse_bet_threshold(bet), bet)
        self.assertIsNone(tracker.extract_prop("Corbin Burnes Under 5½ strikeouts", None))

    def test_string_line_num_does_not_crash_the_nightly_run(self):
        # The skip message formatted line_num with :g, which raises on a str and would
        # abort cmd_auto_resolve for every pick after it.
        p = _open_pick(line_num="-108")
        save, out = _auto_resolve([p], _ace_box(6))
        self.assertIsNone(p["result"])
        save.assert_not_called()
        self.assertIn("line_num '-108'", out)

    def test_parenthetical_n_plus_does_not_block_parsing(self):
        spec = tracker.parse_bet_threshold("Corbin Burnes Under 5.5 strikeouts (steam at 3+ books)")
        self.assertEqual((spec["side"], spec["threshold"]), ("under", 5.5))
        spec = tracker.parse_bet_threshold("Mookie Betts 2+ hits (steam at 3+ books)")
        self.assertEqual((spec["side"], spec["threshold"], spec["start"]), ("over", 1.5, 13))
        spec = tracker.extract_prop("Corbin Burnes Under 5.5 strikeouts (steam at 3+ books)", 5.5)
        self.assertEqual((spec["player"], spec["threshold"]), ("corbin burnes", 5.5))


if __name__ == "__main__":
    unittest.main()
