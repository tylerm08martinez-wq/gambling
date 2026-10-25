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


if __name__ == "__main__":
    unittest.main()
