"""Tests for capturing closing lines at the close (not reconstructing them later).

The failure modes worth pinning:
  - a timezone slip silently shifts every capture window by hours (git-bash has no
    zoneinfo DB, so a named zone would resolve to UTC — the trap that already bit
    run-daily-picks.sh)
  - capturing AFTER first pitch, which is not a closing line at all
  - a later, worse snapshot overwriting one taken closer to the close
  - fabricating a close when the market isn't priced two-way
"""

import importlib.util
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

_DIR = Path(__file__).parent.parent / ".agents" / "skills" / "bet-tracker"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, _DIR / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    sys.modules[name] = mod
    return mod


cc = _load("close_capture")
AZ = cc.AZ


def _pick(pid="p1", date="2026-07-26", game_time="5:10 PM", result=None,
          bet="Zack Wheeler UNDER 17.5 pitcher outs vs PIT", line_num=17.5):
    return {"id": pid, "date": date, "game_time": game_time, "result": result,
            "bet": bet, "line_num": line_num, "sport": "MLB", "line": "-110", "units": 1}


def _at(h, m, date="2026-07-26"):
    y, mo, d = (int(x) for x in date.split("-"))
    return datetime(y, mo, d, h, m, tzinfo=AZ)


class TestStartParsing(unittest.TestCase):
    def test_parses_arizona_local_game_time(self):
        s = cc.parse_start(_pick(game_time="5:10 PM"))
        self.assertEqual((s.hour, s.minute), (17, 10))

    def test_timezone_is_fixed_utc_minus_7_not_a_named_zone(self):
        # A named zone would resolve to UTC under git-bash (no zoneinfo DB) and shift
        # every capture window by 7 hours.
        self.assertEqual(cc.parse_start(_pick()).utcoffset(), timedelta(hours=-7))

    def test_morning_and_24h_forms(self):
        self.assertEqual(cc.parse_start(_pick(game_time="10:40 AM")).hour, 10)
        self.assertEqual(cc.parse_start(_pick(game_time="13:05")).hour, 13)

    def test_missing_or_junk_game_time_is_none_not_a_guess(self):
        for gt in ("", None, "sometime", "25:99 PM"):
            with self.subTest(gt=gt):
                self.assertIsNone(cc.parse_start(_pick(game_time=gt)))


class TestCaptureWindow(unittest.TestCase):
    def test_inside_window_is_due(self):
        self.assertTrue(cc.due_for_capture(_pick(), _at(16, 40), window_minutes=45))

    def test_too_early_is_not_due(self):
        self.assertFalse(cc.due_for_capture(_pick(), _at(12, 0), window_minutes=45))

    def test_after_first_pitch_is_never_due(self):
        # A price after the game starts is not a closing line.
        self.assertFalse(cc.due_for_capture(_pick(), _at(17, 11), window_minutes=45))
        self.assertFalse(cc.due_for_capture(_pick(), _at(20, 0), window_minutes=45))

    def test_exactly_at_first_pitch_is_not_due(self):
        self.assertFalse(cc.due_for_capture(_pick(), _at(17, 10), window_minutes=45))


class TestSnapshotPrecedence(unittest.TestCase):
    def test_closer_to_first_pitch_wins(self):
        self.assertTrue(cc.should_replace({"minutes_before_start": 30}, 5))

    def test_further_from_first_pitch_does_not_overwrite(self):
        self.assertFalse(cc.should_replace({"minutes_before_start": 5}, 30))

    def test_first_snapshot_always_taken(self):
        self.assertTrue(cc.should_replace(None, 40))
        self.assertTrue(cc.should_replace({}, 40))


class TestCapture(unittest.TestCase):
    def _seams(self, close=None, ladders=None, raises=False):
        def fetch_ladders(ev, mk):
            if raises:
                raise RuntimeError("403 blocked")
            return ladders or ["ladder"]
        return dict(
            resolve_event=lambda date, player: 77,
            fetch_ladders=fetch_ladders,
            extract_prop=lambda bet, ln, sm=None: {
                "player": "zack wheeler", "stat_group": "pitching",
                "stat_key": "outs", "side": "under", "threshold": 17.5},
            normalize_name=lambda s: (s or "").lower(),
            two_way_at_line=lambda *a, **k: close,
            market_for_spec=lambda spec: 123,
            classify_bet=lambda p: "prop",
        )

    def test_captures_and_records_provenance(self):
        snaps, report = cc.capture([_pick()], _at(17, 5),
                                   **self._seams(close={"under": "-115", "over": "-105"}))
        s = snaps["p1"]
        self.assertEqual(s["close"], {"under": "-115", "over": "-105"})
        self.assertEqual(s["side"], "under")
        self.assertEqual(s["minutes_before_start"], 5.0)
        self.assertEqual(s["vintage"], "close")
        self.assertIn("captured_at", s)
        self.assertEqual([r[1] for r in report], ["captured"])

    def test_early_capture_is_marked_pre_close_not_close(self):
        # Recorded (better than nothing) but never labelled a close — an opening-ish
        # price passing as a closing line is the exact defect this module fixes.
        snaps, _ = cc.capture([_pick()], _at(16, 25),
                              **self._seams(close={"under": "-115", "over": "-105"}))
        self.assertEqual(snaps["p1"]["vintage"], "pre-close")

    def test_settled_picks_are_never_captured(self):
        snaps, report = cc.capture([_pick(result="win")], _at(17, 5),
                                   **self._seams(close={"under": "-115", "over": "-105"}))
        self.assertEqual(snaps, {})
        self.assertEqual(report, [])

    def test_one_sided_market_is_skipped_not_fabricated(self):
        snaps, report = cc.capture([_pick()], _at(17, 5), **self._seams(close=None))
        self.assertEqual(snaps, {})
        self.assertEqual(report[0][1], "skip")
        self.assertIn("both sides", report[0][2])

    def test_non_prop_is_skipped(self):
        seams = self._seams(close={"under": "-115", "over": "-105"})
        seams["classify_bet"] = lambda p: "total"
        snaps, report = cc.capture([_pick()], _at(17, 5), **seams)
        self.assertEqual(snaps, {})
        self.assertEqual(report[0][1], "skip")

    def test_fetch_failure_is_reported_not_swallowed(self):
        snaps, report = cc.capture([_pick()], _at(17, 5), **self._seams(raises=True))
        self.assertEqual(snaps, {})
        self.assertEqual(report[0][1], "error")
        self.assertIn("403", report[0][2])

    def test_existing_closer_snapshot_is_not_overwritten(self):
        prior = {"p1": {"close": {"under": "-110", "over": "-110"},
                        "minutes_before_start": 2.0, "vintage": "close"}}
        snaps, report = cc.capture([_pick()], _at(16, 40),
                                   **self._seams(close={"under": "-200", "over": "+150"}),
                                   snapshots=prior)
        self.assertEqual(snaps["p1"]["minutes_before_start"], 2.0)
        self.assertEqual(report[0][1], "keep")

    def test_later_snapshot_replaces_an_earlier_one(self):
        prior = {"p1": {"close": {"under": "-110", "over": "-110"},
                        "minutes_before_start": 40.0, "vintage": "pre-close"}}
        snaps, _ = cc.capture([_pick()], _at(17, 6),
                              **self._seams(close={"under": "-125", "over": "+100"}),
                              snapshots=prior)
        self.assertEqual(snaps["p1"]["minutes_before_start"], 4.0)
        self.assertEqual(snaps["p1"]["close"], {"under": "-125", "over": "+100"})


if __name__ == "__main__":
    unittest.main()
