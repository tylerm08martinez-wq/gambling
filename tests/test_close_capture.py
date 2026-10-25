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

    def test_explicit_start_overrides_game_time(self):
        # Used for picks timed by their event's scheduled start (no game_time).
        p = _pick(game_time="")
        self.assertTrue(cc.due_for_capture(p, _at(16, 40), window_minutes=45, start=_at(17, 10)))
        self.assertFalse(cc.due_for_capture(p, _at(17, 10), window_minutes=45, start=_at(17, 10)))
        self.assertFalse(cc.due_for_capture(p, _at(16, 40), window_minutes=45))


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


# ── #107: NBA and NFL props through the live wiring ───────────────────────────────

tracker = _load("tracker")
cf = _load("clv_fetch")


class _FakeBP:
    """Stands in for the bettingpros module and records the sport of every call."""

    def __init__(self, props=None, events=None, ladders=None):
        self.props, self.events, self.ladders = props or {}, events or {}, ladders or {}
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


def _bp():
    # 2026-10-25: LAL @ OKC 23:00 UTC (16:00 AZ); NO-PIT London game 13:30 UTC (06:30 AZ);
    # BAL-CIN 17:00 UTC (10:00 AZ).
    return _FakeBP(
        props={"NBA": [{"event_id": 27926, "player": {"name": "Rui Hachimura"}},
                       {"event_id": 27926, "player": {"name": "Domantas Sabonis"}}],
               "NFL": [{"event_id": 22070, "player": {"name": "Joe Burrow"}},
                       {"event_id": 21915, "player": {"name": "Aaron Rodgers"}}]},
        events={"NBA": [{"id": 27926, "scheduled": "2026-10-25 23:00:00"}],
                "NFL": [{"id": 22070, "scheduled": "2026-10-25 17:00:00"},
                        {"id": 21915, "scheduled": "2026-10-25 13:30:00"}]},
        ladders={
            ("NBA", 27926, 156): [{"player": "Rui Hachimura",
                                   "sides": {"over": {16.5: -119}, "under": {16.5: -107}}}],
            ("NFL", 22070, 103): [{"player": "Joe Burrow",
                                   "sides": {"over": {245.5: -112}, "under": {245.5: -114}}}],
            ("NFL", 21915, 103): [{"player": "Aaron Rodgers",
                                   "sides": {"over": {229.5: -113}, "under": {229.5: -113}}}],
        })


def _open(pid, sport, bet, line_num, game_time="", date="2026-10-25"):
    return {"id": pid, "sport": sport, "bet": bet, "line_num": line_num, "line": "-110",
            "units": 1, "date": date, "game_time": game_time, "result": None,
            "bet_type": "prop"}


def _live(picks, now, bp=None, snapshots=None):
    return cc.capture_live(picks, now, tracker=tracker, bp=bp or _bp(), clv_fetch=cf,
                           window_minutes=45, snapshots=snapshots or {})


NBA_PICK = dict(pid="nba1", sport="NBA", bet="Rui Hachimura Under 16.5 Points (LAL @ OKC)",
                line_num=16.5, game_time="4:00 PM")
NFL_NO_TIME = dict(pid="nfl1", sport="NFL", bet="Joe Burrow (CIN) Over 245.5 passing yards vs BAL",
                   line_num=245.5)


class TestCaptureLiveNbaNfl(unittest.TestCase):
    def test_nba_prop_is_captured_from_the_nba_ladder(self):
        bp = _bp()
        snaps, report = _live([_open(**NBA_PICK)], _at(15, 50, "2026-10-25"), bp=bp)
        s = snaps["nba1"]
        self.assertEqual(s["close"], {"under": "-107", "over": "-119"})
        self.assertEqual((s["side"], s["market"], s["vintage"]), ("under", "prop", "close"))
        self.assertEqual(s["minutes_before_start"], 10.0)
        self.assertIn(("ladder", "NBA", 27926, 156), bp.calls)
        self.assertEqual([r[1] for r in report], ["captured"])

    def test_missing_game_time_falls_back_to_the_events_utc_start(self):
        # 17:00 UTC == 10:00 AZ; at 09:50 AZ the game is 10 minutes out.
        snaps, report = _live([_open(**NFL_NO_TIME)], _at(9, 50, "2026-10-25"))
        s = snaps["nfl1"]
        self.assertEqual(s["minutes_before_start"], 10.0)
        self.assertEqual(s["close"], {"under": "-114", "over": "-112"})
        self.assertEqual(s["side"], "over")
        self.assertEqual(s["start_source"], "event_scheduled")

    def test_event_start_fallback_keeps_the_strictly_pre_game_rule(self):
        bp = _bp()
        snaps, report = _live([_open(**NFL_NO_TIME)], _at(10, 5, "2026-10-25"), bp=bp)
        self.assertEqual(snaps, {})
        self.assertEqual(report[0][1], "skip")
        self.assertIn("already started", report[0][2])
        self.assertFalse([c for c in bp.calls if c[0] == "ladder"])

    def test_event_start_fallback_outside_window_fetches_no_ladder(self):
        bp = _bp()
        snaps, report = _live([_open(**NFL_NO_TIME)], _at(6, 0, "2026-10-25"), bp=bp)
        self.assertEqual(snaps, {})
        self.assertIn("outside window", report[0][2])
        self.assertFalse([c for c in bp.calls if c[0] == "ladder"])

    def test_no_game_time_on_a_past_date_is_skipped_without_network(self):
        bp = _bp()
        snaps, report = _live([_open(**dict(NFL_NO_TIME, date="2026-10-18"))],
                              _at(9, 50, "2026-10-25"), bp=bp)
        self.assertEqual(snaps, {})
        self.assertEqual(report[0][1], "skip")
        self.assertEqual(bp.calls, [])

    def test_event_with_no_scheduled_start_is_skipped(self):
        bp = _bp()
        bp.events["NFL"] = [{"id": 22070, "scheduled": None}]
        snaps, report = _live([_open(**NFL_NO_TIME)], _at(9, 50, "2026-10-25"), bp=bp)
        self.assertEqual(snaps, {})
        self.assertIn("scheduled", report[0][2])

    def test_rerun_is_idempotent_and_keeps_the_snapshot_closest_to_start(self):
        pick = _open(**NBA_PICK)
        snaps, _ = _live([pick], _at(15, 20, "2026-10-25"))
        self.assertEqual(snaps["nba1"]["vintage"], "pre-close")
        snaps, _ = _live([pick], _at(15, 55, "2026-10-25"), snapshots=snaps)
        snaps, report = _live([pick], _at(15, 40, "2026-10-25"), snapshots=snaps)
        self.assertEqual(list(snaps), ["nba1"])
        self.assertEqual(snaps["nba1"]["minutes_before_start"], 5.0)
        self.assertEqual(report[0][1], "keep")

    def test_unparseable_nba_combo_is_never_captured(self):
        pick = _open("nba2", "NBA", "Domantas Sabonis Over 21.5 Points + Assists (SAC @ LAC)",
                     21.5, game_time="4:00 PM")
        snaps, report = _live([pick], _at(15, 50, "2026-10-25"))
        self.assertEqual(snaps, {})
        self.assertIn("could not parse", report[0][2])

    def test_line_num_that_disagrees_with_the_bet_is_never_captured(self):
        pick = _open("nfl2", "NFL", "Aaron Rodgers Under 224.5 passing yards (NO @ PIT)",
                     229.5, game_time="6:30 AM")
        snaps, report = _live([pick], _at(6, 20, "2026-10-25"))
        self.assertEqual(snaps, {})

    def test_unsupported_sport_is_reported_and_not_fetched(self):
        bp = _bp()
        pick = _open("nhl1", "NHL", "Connor McDavid Over 0.5 goals", 0.5, game_time="5:00 PM")
        snaps, report = _live([pick], _at(16, 50, "2026-10-25"), bp=bp)
        self.assertEqual(snaps, {})
        self.assertEqual(report, [("nhl1", "skip", "sport NHL has no close capture")])
        self.assertEqual(bp.calls, [])

    def test_mlb_fixture_through_live_wiring_is_unchanged(self):
        # The original MLB path: pitcher index from /events, MLB stat map, sport=MLB.
        bp = _FakeBP(
            events={"MLB": [{"id": 98219, "pitchers": {"home": {"name": "Zack Wheeler"},
                                                       "visitor": None}}]},
            ladders={("MLB", 98219, 405): [{"player": "Zack Wheeler",
                                            "sides": {"under": {17.5: -115}, "over": {17.5: -105}}}]})
        snaps, report = cc.capture_live([_pick()], _at(17, 5), tracker=tracker, bp=bp,
                                        clv_fetch=cf, window_minutes=45, snapshots={})
        s = snaps["p1"]
        self.assertEqual(s["close"], {"under": "-115", "over": "-105"})
        self.assertEqual((s["side"], s["vintage"], s["minutes_before_start"]), ("under", "close", 5.0))
        self.assertNotIn("start_source", s)
        self.assertEqual([c[0] for c in bp.calls], ["events", "ladder"])
        self.assertIn(("ladder", "MLB", 98219, 405), bp.calls)


if __name__ == "__main__":
    unittest.main()
