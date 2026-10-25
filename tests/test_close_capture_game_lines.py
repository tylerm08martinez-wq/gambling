"""Close capture for game lines and V3 observations (#109, ADR 0010 + 0011).

The failures worth pinning, all of them the silent mis-resolution class:
  - a close taken for the wrong TEAM (the other side of the same market, or a team
    from another game that day)
  - a close taken at the wrong LINE (a spread of +6.5 against a consensus at +7.5,
    or a +6.5 dog matched to the favourite's -6.5 on the same side)
  - a close taken for the wrong SIDE of a V3 observation when the feed reorders the
    two selections between the morning scan and the capture
  - a moneyline de-vigged multiplicatively (ADR 0011: power for every game line)
Unmatched, one-sided or ambiguous markets stay unmeasured, never guessed.
"""

import copy
import importlib.util
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

_ROOT = Path(__file__).parent.parent
_DIR = _ROOT / ".agents" / "skills" / "bet-tracker"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, _DIR / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


bp = _load("bettingpros")

UPD = "2026-10-25 22:40:00"


def _line(line, cost, *, updated=UPD, is_off=False, active=True, main=True):
    return {"line": line, "cost": cost, "updated": updated, "main": main,
            "active": active, "is_off": is_off}


def _sel(label, books, *, participant=None, selection=""):
    """`books` maps book_id -> list of raw line dicts."""
    return {"participant": participant, "selection": selection, "label": label,
            "books": [{"id": bid, "lines": lines} for bid, lines in books.items()]}


def _team(abbr, name, city):
    return {"id": abbr, "name": name, "team": {"city": city, "abbreviation": abbr}}


CLIPPERS = _team("LAC", "Clippers", "Los Angeles")
THUNDER = _team("OKC", "Thunder", "Oklahoma City")


def spread_offer(lac=((14.5, -108),), okc=((-14.5, -112),), extra=None):
    """LAC @ OKC spread as /offers serves it (selections in feed order LAC, OKC).

    `extra` maps book_id -> ((line_a, cost_a), (line_b, cost_b))."""
    books_a = {0: [_line(l, c) for l, c in lac]}
    books_b = {0: [_line(l, c) for l, c in okc]}
    for bid, (a, b) in (extra or {}).items():
        books_a[bid] = [_line(*a)]
        books_b[bid] = [_line(*b)]
    return {"market_id": 129, "event_id": 27926, "participants": [CLIPPERS, THUNDER],
            "selections": [_sel("Clippers", books_a, participant="LAC"),
                           _sel("Thunder", books_b, participant="OKC")]}


def moneyline_offer():
    # Live feed order for this market was OKC first, LAC second (2026-10-25 05:28 UTC).
    return {"market_id": 127, "event_id": 27926, "participants": [CLIPPERS, THUNDER],
            "selections": [_sel("Thunder", {0: [_line(1, -1100)], 12: [_line(1, -950)]},
                                participant="OKC"),
                           _sel("Clippers", {0: [_line(1, 700)], 12: [_line(1, 625)]},
                                participant="LAC")]}


def total_offer(over=((43.5, -108),), under=((43.5, -110),)):
    return {"market_id": 2, "event_id": 21915, "participants": [],
            "selections": [_sel("Over", {0: [_line(l, c) for l, c in over]}, selection="over"),
                           _sel("Under", {0: [_line(l, c) for l, c in under]},
                                selection="under")]}


class TestGameLineLadder(unittest.TestCase):
    """bettingpros.game_line_ladder: book-0 consensus, keyed by team or over/under."""

    def test_spread_is_keyed_by_team_with_each_side_signed_as_it_reads(self):
        lad = bp.game_line_ladder(spread_offer())
        self.assertEqual(lad["sides"], {"LAC": {14.5: -108}, "OKC": {-14.5: -112}})
        self.assertEqual([p["id"] for p in lad["participants"]], ["LAC", "OKC"])

    def test_total_is_keyed_by_over_and_under(self):
        lad = bp.game_line_ladder(total_offer())
        self.assertEqual(lad["sides"], {"over": {43.5: -108}, "under": {43.5: -110}})

    def test_only_consensus_book_zero_is_read(self):
        lad = bp.game_line_ladder(moneyline_offer())
        self.assertEqual(lad["sides"], {"OKC": {1.0: -1100}, "LAC": {1.0: 700}})

    def test_off_inactive_and_placeholder_lines_are_not_prices(self):
        off = spread_offer()
        off["selections"][0]["books"][0]["lines"] = [
            _line(14.5, -108, is_off=True), _line(15.5, -120, active=False),
            _line(13.5, 99900)]
        lad = bp.game_line_ladder(off)
        self.assertNotIn("LAC", lad["sides"])

    def test_a_market_without_exactly_two_keyed_selections_is_unparseable(self):
        three = spread_offer()
        three["selections"].append(_sel("Draw", {0: [_line(1, 300)]}, participant="DRAW"))
        self.assertIsNone(bp.game_line_ladder(three))
        unkeyed = spread_offer()
        unkeyed["selections"][1]["participant"] = None
        self.assertIsNone(bp.game_line_ladder(unkeyed))
        same = spread_offer()
        same["selections"][1]["participant"] = "LAC"
        self.assertIsNone(bp.game_line_ladder(same))

    def test_fetch_reads_every_page_with_the_sport_on_the_url(self):
        urls = []

        def get_json(url):
            urls.append(url)
            return {"offers": [total_offer()] if "page=2" in url else [spread_offer()],
                    "_pagination": {"total_pages": 2}}
        out = bp.fetch_game_line_ladders(27926, 129, sport="NBA", get_json=get_json)
        self.assertEqual(len(out), 2)
        self.assertTrue(all("sport=NBA" in u for u in urls))


class TestTwoWayGameLine(unittest.TestCase):
    """bettingpros.two_way_game_line: the de-viggable pair at the bet's own number."""

    def test_spread_dog_matches_the_favourite_at_the_negated_number(self):
        lad = bp.game_line_ladder(spread_offer())
        self.assertEqual(bp.two_way_game_line(lad, "spread", "LAC", 14.5),
                         {"LAC": "-108", "OKC": "-112"})
        self.assertEqual(bp.two_way_game_line(lad, "spread", "OKC", -14.5),
                         {"OKC": "-112", "LAC": "-108"})

    def test_spread_at_another_number_or_the_wrong_sign_is_unmeasured(self):
        lad = bp.game_line_ladder(spread_offer())
        self.assertIsNone(bp.two_way_game_line(lad, "spread", "LAC", 15.5))
        self.assertIsNone(bp.two_way_game_line(lad, "spread", "LAC", -14.5))
        self.assertIsNone(bp.two_way_game_line(lad, "spread", "OKC", 14.5))

    def test_spread_priced_on_one_side_only_is_unmeasured(self):
        lad = bp.game_line_ladder(spread_offer(lac=((14.5, -108),), okc=((-15.5, -102),)))
        self.assertIsNone(bp.two_way_game_line(lad, "spread", "LAC", 14.5))

    def test_alt_ladder_rungs_are_matched_exactly(self):
        lad = bp.game_line_ladder(spread_offer(lac=((14.5, -108), (13.5, -125)),
                                               okc=((-14.5, -112), (-13.5, 104))))
        self.assertEqual(bp.two_way_game_line(lad, "spread", "LAC", 13.5),
                         {"LAC": "-125", "OKC": "+104"})

    def test_moneyline_ignores_the_feed_line_value(self):
        lad = bp.game_line_ladder(moneyline_offer())
        self.assertEqual(bp.two_way_game_line(lad, "moneyline", "LAC", None),
                         {"LAC": "+700", "OKC": "-1100"})

    def test_moneyline_with_two_prices_on_a_side_is_ambiguous(self):
        off = moneyline_offer()
        off["selections"][0]["books"][0]["lines"].append(_line(0, -1000, main=False))
        lad = bp.game_line_ladder(off)
        self.assertIsNone(bp.two_way_game_line(lad, "moneyline", "OKC", None))

    def test_total_needs_over_and_under_at_the_same_number(self):
        lad = bp.game_line_ladder(total_offer(over=((43.5, -108),), under=((44, -113),)))
        self.assertIsNone(bp.two_way_game_line(lad, "total", "under", 43.5))
        lad = bp.game_line_ladder(total_offer())
        self.assertEqual(bp.two_way_game_line(lad, "total", "under", 43.5),
                         {"under": "-110", "over": "-108"})

    def test_unknown_side_key_is_unmeasured(self):
        lad = bp.game_line_ladder(spread_offer())
        self.assertIsNone(bp.two_way_game_line(lad, "spread", "SAS", 14.5))


# ── game-line PICKS ──────────────────────────────────────────────────────────────

tracker = _load("tracker")
cc = _load("close_capture")
clv_backfill = _load("clv_backfill")
AZ = cc.AZ

KNICKS = _team("NYK", "Knicks", "New York")
MAGIC = _team("ORL", "Magic", "Orlando")
JAZZ = _team("UTH", "Jazz", "Utah")
LAKERS = _team("LAL", "Lakers", "Los Angeles")


def _at(h, m, date="2026-10-25"):
    y, mo, d = (int(x) for x in date.split("-"))
    return datetime(y, mo, d, h, m, tzinfo=AZ)


def _utc(h, m, day=25):
    return datetime(2026, 10, day, h, m, tzinfo=timezone.utc)


def nba_total_offer():
    off = total_offer(over=((220.5, -105),), under=((220.5, -115),))
    off.update(market_id=128, event_id=27927, participants=[MAGIC, KNICKS])
    return off


def _respread(event_id, away, home):
    off = spread_offer()
    off.update(event_id=event_id, participants=[away, home])
    off["selections"][0]["participant"] = away["id"]
    off["selections"][1]["participant"] = home["id"]
    return off


class FakeGameBoard:
    """events_for / fetch_ladders seams over a small NBA 2026-10-25 slate.

    LAC @ OKC and ORL @ NYK tip 23:00 UTC (16:00 AZ); LAL @ UTH at 21:00 UTC (14:00 AZ).
    Market ids: 127 moneyline, 128 total, 129 spread."""

    def __init__(self, offers=None):
        self.events = [{"id": 27926, "start": _utc(23, 0)},
                       {"id": 27927, "start": _utc(23, 0)},
                       {"id": 27924, "start": _utc(21, 0)}]
        self.offers = offers if offers is not None else {
            (27926, 129): [spread_offer()], (27926, 127): [moneyline_offer()],
            (27927, 128): [nba_total_offer()],
            (27927, 129): [_respread(27927, MAGIC, KNICKS)],
            (27924, 129): [_respread(27924, LAKERS, JAZZ)]}
        self.calls = []

    def events_for(self, date):
        self.calls.append(("events", date))
        return list(self.events) if date == "2026-10-25" else []

    def fetch_ladders(self, event_id, market_id):
        self.calls.append(("ladders", event_id, market_id))
        return [bp.game_line_ladder(o) for o in self.offers.get((event_id, market_id), [])]

    def ladder_calls(self):
        return [c for c in self.calls if c[0] == "ladders"]


MARKET_IDS = {"moneyline": 127, "total": 128, "spread": 129}


def _gl(pid, bet, line_num, *, game_time="4:00 PM", date="2026-10-25", result=None,
        bet_type=None, line="-110 @ FanDuel"):
    return {"id": pid, "sport": "NBA", "bet": bet, "line_num": line_num, "line": line,
            "units": 1, "date": date, "game_time": game_time, "result": result,
            "bet_type": bet_type}


def _capture(picks, now, board=None, snapshots=None):
    board = board or FakeGameBoard()
    snaps, report = cc.capture_game_lines(
        picks, now, events_for=board.events_for, fetch_ladders=board.fetch_ladders,
        market_for_kind=MARKET_IDS.get, classify_bet=tracker.classify_bet,
        window_minutes=45, snapshots=snapshots or {})
    return snaps, report, board


class TestParseGameLineBet(unittest.TestCase):
    def test_spread_reads_team_and_signed_line(self):
        b = cc.parse_game_line_bet(_gl("s", "San Antonio Spurs +6.5 vs Oklahoma City Thunder "
                                           "(WCF Game 1)", 6.5), "spread")
        self.assertEqual((b["kind"], b["team_text"], b["line"]),
                         ("spread", "San Antonio Spurs", 6.5))

    def test_spread_whose_line_num_disagrees_with_the_text_is_refused(self):
        self.assertIsInstance(cc.parse_game_line_bet(_gl("s", "Spurs +6.5 vs OKC", 7.5),
                                                     "spread"), str)

    def test_moneyline_needs_an_explicit_ml_marker(self):
        b = cc.parse_game_line_bet(_gl("m", "New York Mets ML vs New York Yankees", 0.0), "ml")
        self.assertEqual((b["kind"], b["team_text"], b["line"]),
                         ("moneyline", "New York Mets", None))
        self.assertIsInstance(cc.parse_game_line_bet(_gl("m", "Mets vs Yankees", 0.0), "ml"), str)

    def test_total_reads_side_and_number_after_it(self):
        b = cc.parse_game_line_bet(_gl("t", "CLE @ PHI Under 7.0 (correlated: Wheeler)", 7.0),
                                   "total")
        self.assertEqual((b["kind"], b["side"], b["line"]), ("total", "under", 7.0))
        b = cc.parse_game_line_bet(_gl("t", "Over 8.5 Giants vs Diamondbacks (at Chase Field)",
                                       8.5), "total")
        self.assertEqual((b["side"], b["line"]), ("over", 8.5))

    def test_total_with_a_line_num_that_is_not_the_total_is_refused(self):
        # Real ledger rows carry line_num -7.5 and -125.0 on totals.
        self.assertIsInstance(cc.parse_game_line_bet(
            _gl("t", "Under 7.5 Guardians at Phillies", -7.5), "total"), str)

    def test_partial_game_and_team_totals_are_refused(self):
        for bet, kind in (("Clippers +7.5 1H vs Thunder", "spread"),
                          ("Clippers +3.5 first half", "spread"),
                          ("Knicks Under 110.5 team total", "total"),
                          ("Yankees @ Red Sox Under 4.5 first 5 innings", "total"),
                          ("Thunder ML 1st quarter", "ml")):
            with self.subTest(bet=bet):
                self.assertIsInstance(cc.parse_game_line_bet(_gl("x", bet, None), kind), str)


class TestMatchTeams(unittest.TestCase):
    def setUp(self):
        self.parts = bp.game_line_ladder(spread_offer())["participants"]

    def test_nickname_full_name_and_uppercase_abbreviation_match(self):
        self.assertEqual(cc.match_teams("Clippers", self.parts), {"LAC"})
        self.assertEqual(cc.match_teams("Oklahoma City Thunder", self.parts), {"OKC"})
        self.assertEqual(cc.match_teams("LAC @ OKC", self.parts), {"LAC", "OKC"})

    def test_city_alone_lowercase_abbreviation_and_substrings_do_not_match(self):
        self.assertEqual(cc.match_teams("Los Angeles", self.parts), set())
        self.assertEqual(cc.match_teams("okc lac", self.parts), set())
        self.assertEqual(cc.match_teams("Clipperson", self.parts), set())


class TestCaptureGameLinePicks(unittest.TestCase):
    def test_spread_dog_is_captured_keyed_by_team_at_its_number(self):
        snaps, report, _ = _capture([_gl("g1", "Clippers +14.5 vs Thunder", 14.5)],
                                    _at(15, 50))
        s = snaps["g1"]
        self.assertEqual(s["close"], {"LAC": "-108", "OKC": "-112"})
        self.assertEqual((s["side"], s["market"], s["line"], s["event_id"]),
                         ("LAC", "spread", 14.5, 27926))
        self.assertEqual((s["minutes_before_start"], s["vintage"], s["source"]),
                         (10.0, "close", "bettingpros_consensus"))
        self.assertEqual([r[1] for r in report], ["captured"])

    def test_the_favourite_side_of_the_same_market_is_its_own_team(self):
        snaps, _, _ = _capture([_gl("g2", "Oklahoma City Thunder -14.5 vs Clippers", -14.5)],
                               _at(15, 50))
        self.assertEqual(snaps["g2"]["side"], "OKC")
        self.assertEqual(snaps["g2"]["close"], {"OKC": "-112", "LAC": "-108"})

    def test_off_line_spread_is_unmeasured(self):
        snaps, report, _ = _capture([_gl("g3", "Clippers +13.5 vs Thunder", 13.5)], _at(15, 50))
        self.assertEqual(snaps, {})
        self.assertIn("both sides", report[0][2])

    def test_opponent_from_another_game_is_ambiguous_not_guessed(self):
        snaps, report, _ = _capture([_gl("g4", "Clippers +14.5 vs Knicks", 14.5)], _at(15, 50))
        self.assertEqual(snaps, {})
        self.assertEqual(report[0][1], "skip")

    def test_team_named_by_city_only_is_not_found(self):
        snaps, report, _ = _capture([_gl("g5", "Los Angeles +14.5 vs Oklahoma City", 14.5)],
                                    _at(15, 50))
        self.assertEqual(snaps, {})
        self.assertEqual(report[0][1], "skip")

    def test_game_total_needs_both_teams_of_one_game(self):
        snaps, _, _ = _capture([_gl("t1", "Magic @ Knicks Under 220.5", 220.5)], _at(15, 50))
        self.assertEqual(snaps["t1"]["close"], {"under": "-115", "over": "-105"})
        self.assertEqual((snaps["t1"]["side"], snaps["t1"]["market"]), ("under", "total"))
        snaps, report, _ = _capture([_gl("t2", "Knicks Under 220.5 (game total)", 220.5)],
                                    _at(15, 50))
        self.assertEqual(snaps, {})

    def test_moneyline_is_captured_both_sides(self):
        snaps, _, _ = _capture([_gl("m1", "Clippers ML vs Thunder", 0.0, line="+750")],
                               _at(15, 50))
        self.assertEqual(snaps["m1"]["close"], {"LAC": "+700", "OKC": "-1100"})
        self.assertEqual(snaps["m1"]["market"], "moneyline")
        self.assertIsNone(snaps["m1"]["line"])

    def test_outside_window_or_started_fetches_nothing(self):
        for now in (_at(12, 0), _at(16, 1)):
            with self.subTest(now=now):
                snaps, report, board = _capture(
                    [_gl("g1", "Clippers +14.5 vs Thunder", 14.5)], now)
                self.assertEqual(snaps, {})
                self.assertEqual(board.ladder_calls(), [])

    def test_unparseable_bet_fetches_nothing(self):
        snaps, report, board = _capture([_gl("g6", "Clippers +14.5 vs Thunder", 13.5)],
                                        _at(15, 50))
        self.assertEqual(snaps, {})
        self.assertEqual(board.calls, [])

    def test_no_game_time_is_timed_by_the_event(self):
        snaps, _, _ = _capture([_gl("g7", "Clippers +14.5 vs Thunder", 14.5, game_time="")],
                               _at(15, 50))
        self.assertEqual(snaps["g7"]["minutes_before_start"], 10.0)
        self.assertEqual(snaps["g7"]["start_source"], "event_scheduled")

    def test_a_closer_existing_snapshot_is_kept(self):
        prior = {"g1": {"close": {"LAC": "-110", "OKC": "-110"}, "minutes_before_start": 3.0}}
        snaps, report, _ = _capture([_gl("g1", "Clippers +14.5 vs Thunder", 14.5)],
                                    _at(15, 50), snapshots=prior)
        self.assertEqual(snaps["g1"]["close"], {"LAC": "-110", "OKC": "-110"})
        self.assertEqual(report[0][1], "keep")

    def test_settled_and_prop_picks_are_not_touched(self):
        picks = [_gl("g1", "Clippers +14.5 vs Thunder", 14.5, result="win"),
                 _gl("p1", "Shai Gilgeous-Alexander Over 30.5 points", 30.5, bet_type="prop")]
        snaps, report, board = _capture(picks, _at(15, 50))
        self.assertEqual(snaps, {})
        self.assertEqual(board.calls, [])


class TestGameLineBackfill(unittest.TestCase):
    """The captured close flows through the existing backfill with POWER de-vig."""

    def test_moneyline_close_is_power_devigged_not_multiplicative(self):
        pick = _gl("m1", "Clippers ML vs Thunder", 0.0, line="+750 @ FanDuel")
        snaps, _, _ = _capture([pick], _at(15, 50))
        self.assertTrue(clv_backfill.backfill_pick(pick, snaps["m1"]))
        # Hand-checked: -1100/+700 power de-vig gives LAC fair 0.094143 (k = 1.13633);
        # against +750 (0.117647) that is -19.98%. Multiplicative would say +2.00%.
        self.assertAlmostEqual(pick["clv_devig"], -19.98, places=2)
        self.assertEqual(pick["closing_line"], "+700")
        self.assertAlmostEqual(pick["clv_pct_pts"], 0.74, places=2)


# ── V3 OBSERVATIONS ──────────────────────────────────────────────────────────────

v3 = _load("v3_scan")
_LIVE = json.loads((_ROOT / "tests" / "fixtures" / "exchange_benchmark_offers.json").read_text())
LIVE_NOW = datetime(2026, 10, 25, 2, 12, 0, tzinfo=timezone.utc)   # fixture pull time


def _colts_offer():
    """The live Colts @ Vikings moneyline without ProphetX (as test_v3_scan uses it)."""
    off = copy.deepcopy(_LIVE["colts_vikings_moneyline"])
    for sel in off["selections"]:
        sel["books"] = [b for b in sel["books"] if b.get("id") != 38]
    return off


def _colts_observation(start_utc="2026-10-25T02:30:00Z"):
    """The real scan's DraftKings Colts +260 observation, re-timed to start soon."""
    board = lambda url: ({"events": [{"id": 22068, "scheduled": "2026-10-25 17:00:00",
                                      "visitor": "IND", "home": "MIN"}]}
                         if "/events" in url else
                         {"offers": [_colts_offer()] if "market_id=1&" in url + "&" else [],
                          "_pagination": {"total_pages": 1}})
    result = v3.scan("2026-10-25", ["NFL"], LIVE_NOW, get_json=board, log=lambda m: None)
    obs = next(o for o in result["observations"] if o["book_id"] == 12)
    return dict(obs, start_utc=start_utc)


def _spread_observation():
    # DraftKings Thunder -14.5 at -105; scan row side B of a LAC/OKC spread market.
    return {"id": "v3obs-okc", "sport": "NBA", "event_id": 27926, "market_id": 129,
            "kind": "spread", "participant": "Thunder", "side": "Thunder", "selection": "b",
            "line": -14.5, "book_id": 12, "odds": -105, "projected_clv": 0.021,
            "start_utc": "2026-10-25T23:00:00Z", "close": None}


def _okc_spread_offer(reorder=False):
    off = spread_offer(extra={12: ((14.5, -115), (-14.5, -105)),
                              60: ((14.5, 104), (-14.5, -106)),
                              68: ((14.5, 104), (-14.5, -108))})
    if reorder:
        off["selections"].reverse()
    return off


def _restamp(off, ts):
    for sel in off["selections"]:
        for b in sel["books"]:
            for ln in b["lines"]:
                ln["updated"] = ts
    return off


class FakeOffers:
    def __init__(self, offers):
        self.offers, self.calls = offers, []

    def __call__(self, sport, event_id, market_id):
        self.calls.append((sport, event_id, market_id))
        return copy.deepcopy(self.offers.get((sport, event_id, market_id), []))


def _obs_capture(observations, now, offers, existing=None):
    store = {"runs": [], "observations": observations}
    fetch = FakeOffers(offers)
    updates, report = cc.capture_observations(store, now, fetch_offers=fetch,
                                              window_minutes=45)
    return updates, report, fetch


class TestObservationCloses(unittest.TestCase):
    def test_moneyline_observation_gets_both_closes_and_realized_clvs(self):
        obs = _colts_observation()
        updates, report, _ = _obs_capture([obs], LIVE_NOW,
                                          {("NFL", 22068, 1): [_colts_offer()]})
        u = updates[obs["id"]]
        close = u["close"]
        self.assertEqual(close["side"], "Colts")
        self.assertEqual(close["minutes_before_start"], 18.0)
        # Same instant as the scan, so the exchange close IS the scan's benchmark:
        # realized CLV against it equals the projected CLV the scan stored (+2.24%).
        self.assertAlmostEqual(u["realized_clv_exchange"], obs["projected_clv"], places=6)
        self.assertAlmostEqual(u["realized_clv_exchange"], 0.0224, delta=0.0005)
        self.assertEqual(sorted(close["exchange"]["operators"], key=str), [60, 68, "polymarket"])
        # Retail consensus +240 / -300, power de-vig: Colts fair 0.266916 (k 1.0793),
        # against DraftKings +260 (0.277778) = -3.91%. Hand-checked.
        self.assertEqual((close["retail_consensus"]["odds_side"],
                          close["retail_consensus"]["odds_other"]), (240, -300))
        self.assertAlmostEqual(close["retail_consensus"]["fair_p"], 0.266916, places=5)
        self.assertAlmostEqual(u["realized_clv_retail"], -0.0391, places=4)
        self.assertEqual([r[1] for r in report], ["captured"])

    def test_spread_side_b_is_priced_at_its_own_signed_number(self):
        obs = _spread_observation()
        updates, _, _ = _obs_capture([obs], _utc(22, 50),
                                     {("NBA", 27926, 129): [_okc_spread_offer()]})
        u = updates["v3obs-okc"]
        # Exchange: Novig 104/-106 and Kalshi 104/-108, power de-vigged, median OKC fair
        # 0.513394; vs -105 (0.512195) = +0.234%. Retail -108/-112: OKC fair 0.504641,
        # = -1.475%. Hand-checked.
        self.assertAlmostEqual(u["close"]["exchange"]["fair_p"], 0.513394, places=5)
        self.assertAlmostEqual(u["realized_clv_exchange"], 0.002341, places=5)
        self.assertAlmostEqual(u["realized_clv_retail"], -0.014749, places=5)
        self.assertEqual(u["close"]["retail_consensus"]["line"], -14.5)
        self.assertEqual(u["close"]["retail_consensus"]["odds_side"], -112)

    def test_feed_reordering_the_selections_never_swaps_the_side(self):
        obs = _spread_observation()
        a, _, _ = _obs_capture([obs], _utc(22, 50),
                               {("NBA", 27926, 129): [_okc_spread_offer()]})
        b, _, _ = _obs_capture([copy.deepcopy(obs)], _utc(22, 50),
                               {("NBA", 27926, 129): [_okc_spread_offer(reorder=True)]})
        self.assertAlmostEqual(a["v3obs-okc"]["realized_clv_exchange"],
                               b["v3obs-okc"]["realized_clv_exchange"], places=9)
        self.assertAlmostEqual(a["v3obs-okc"]["realized_clv_retail"],
                               b["v3obs-okc"]["realized_clv_retail"], places=9)

    def test_side_label_missing_from_the_market_is_unmeasured(self):
        obs = dict(_spread_observation(), side="Spurs", participant="Spurs")
        updates, report, _ = _obs_capture([obs], _utc(22, 50),
                                          {("NBA", 27926, 129): [_okc_spread_offer()]})
        self.assertEqual(updates, {})
        self.assertEqual(report[0][1], "skip")

    def test_prop_observation_is_matched_to_its_own_player(self):
        def prop(player, cost_over, cost_under):
            return {"participants": [{"id": player, "name": player}],
                    "selections": [
                        _sel("Over", {0: [_line(24.5, cost_over)],
                                      60: [_line(24.5, 100)], 68: [_line(24.5, 102)]}),
                        _sel("Under", {0: [_line(24.5, cost_under)],
                                       60: [_line(24.5, -110)], 68: [_line(24.5, -112)]})]}
        obs = {"id": "v3obs-p", "sport": "NBA", "event_id": 27926, "market_id": 156,
               "kind": "prop", "participant": "Jalen Williams", "side": "Over",
               "selection": "a", "line": 24.5, "book_id": 10, "odds": 110,
               "start_utc": "2026-10-25T23:00:00Z", "close": None}
        offers = {("NBA", 27926, 156): [prop("Chet Holmgren", -150, 120),
                                        prop("Jalen Williams", -110, -110)]}
        updates, _, _ = _obs_capture([obs], _utc(22, 50), offers)
        rc = updates["v3obs-p"]["close"]["retail_consensus"]
        self.assertEqual((rc["odds_side"], rc["odds_other"]), (-110, -110))
        self.assertAlmostEqual(rc["fair_p"], 0.5, places=9)   # multiplicative, -110/-110

    def test_no_benchmark_leaves_the_exchange_close_unmeasured(self):
        off = _okc_spread_offer()
        for sel in off["selections"]:
            sel["books"] = [b for b in sel["books"] if b["id"] != 68]   # 1 operator left
        updates, _, _ = _obs_capture([_spread_observation()], _utc(22, 50),
                                     {("NBA", 27926, 129): [off]})
        u = updates["v3obs-okc"]
        self.assertIsNone(u["close"]["exchange"])
        self.assertIsNone(u["realized_clv_exchange"])
        self.assertIsNotNone(u["realized_clv_retail"])

    def test_neither_close_available_writes_nothing(self):
        off = _okc_spread_offer()
        for sel in off["selections"]:
            sel["books"] = [b for b in sel["books"] if b["id"] not in (0, 68)]
        updates, report, _ = _obs_capture([_spread_observation()], _utc(22, 50),
                                          {("NBA", 27926, 129): [off]})
        self.assertEqual(updates, {})
        self.assertEqual(report[0][1], "skip")

    def test_outside_window_or_started_is_not_fetched(self):
        for now in (_utc(20, 0), _utc(23, 1)):
            with self.subTest(now=now):
                updates, report, fetch = _obs_capture(
                    [_spread_observation()], now, {("NBA", 27926, 129): [_okc_spread_offer()]})
                self.assertEqual(updates, {})
                self.assertEqual(fetch.calls, [])

    def test_each_close_keeps_the_capture_closest_to_start(self):
        obs = _spread_observation()
        early = _restamp(_okc_spread_offer(), "2026-10-25 22:25:00")
        first, _, _ = _obs_capture([obs], _utc(22, 30), {("NBA", 27926, 129): [early]})
        cc.apply_observation_updates({"observations": [obs]}, first)
        self.assertEqual(obs["close"]["exchange"]["minutes_before_start"], 30.0)
        # Ten minutes later the exchanges have gone quiet: retail is replaced by the
        # closer capture, but the T-30 exchange close is kept rather than erased.
        off = _okc_spread_offer()
        for sel in off["selections"]:
            sel["books"] = [b for b in sel["books"] if b["id"] != 68]
        later, _, _ = _obs_capture([obs], _utc(22, 50), {("NBA", 27926, 129): [off]})
        cc.apply_observation_updates({"observations": [obs]}, later)
        self.assertEqual(obs["close"]["exchange"]["minutes_before_start"], 30.0)
        self.assertEqual(obs["close"]["retail_consensus"]["minutes_before_start"], 10.0)
        self.assertIsNotNone(obs["realized_clv_exchange"])
        # A capture further from the start than what is stored changes nothing.
        stale, report, _ = _obs_capture([obs], _utc(22, 20),
                                        {("NBA", 27926, 129): [_okc_spread_offer()]})
        self.assertEqual(stale, {})
        self.assertEqual(report[0][1], "keep")

    def test_capture_never_touches_the_first_seen_price(self):
        obs = _colts_observation()
        before = {k: v for k, v in obs.items() if k != "close"}
        updates, _, _ = _obs_capture([obs], LIVE_NOW, {("NFL", 22068, 1): [_colts_offer()]})
        cc.apply_observation_updates({"observations": [obs]}, updates)
        after = {k: v for k, v in obs.items()
                 if k not in ("close", "realized_clv_exchange", "realized_clv_retail")}
        self.assertEqual(after, before)

    def test_saving_rereads_the_file_so_a_concurrent_scan_row_survives(self):
        obs = _spread_observation()
        updates, _, _ = _obs_capture([obs], _utc(22, 50),
                                     {("NBA", 27926, 129): [_okc_spread_offer()]})
        with tempfile.TemporaryDirectory() as d:
            path = str(Path(d) / "v3-observations.json")
            late = dict(_spread_observation(), id="v3obs-late")
            v3.save_store(path, {"runs": [{"scan_date": "2026-10-25"}],
                                 "observations": [_spread_observation(), late]})
            n = cc.save_observation_closes(path, updates)
            saved = v3.load_store(path)
        self.assertEqual(n, 1)
        self.assertEqual([o["id"] for o in saved["observations"]], ["v3obs-okc", "v3obs-late"])
        self.assertIsNotNone(saved["observations"][0]["close"])
        self.assertIsNone(saved["observations"][1]["close"])
        self.assertEqual(saved["runs"], [{"scan_date": "2026-10-25"}])


# ── live wiring ──────────────────────────────────────────────────────────────────

cf = _load("clv_fetch")


class FakeLiveBP:
    """The bettingpros surface capture_live / capture_observations_live use."""

    def __init__(self):
        self.calls = []
        self.offers = {("NBA", 27926, 129): [spread_offer()],
                       ("NBA", 27926, 127): [moneyline_offer()]}

    def fetch_events(self, sport, date):
        self.calls.append(("events", sport, date))
        return [{"id": 27926, "scheduled": "2026-10-25 23:00:00"}] if sport == "NBA" else []

    def fetch_props(self, sport, date=None):
        self.calls.append(("props", sport, date))
        return []

    def fetch_offer_ladder(self, event_id, market_id, *, sport="MLB"):
        self.calls.append(("ladder", sport, event_id, market_id))
        return []

    def fetch_game_line_ladders(self, event_id, market_id, *, sport):
        self.calls.append(("game_ladders", sport, event_id, market_id))
        return [bp.game_line_ladder(o) for o in self.offers.get((sport, event_id, market_id), [])]

    def fetch_raw_offers(self, event_id, market_id, *, sport):
        self.calls.append(("raw_offers", sport, event_id, market_id))
        return copy.deepcopy(self.offers.get((sport, event_id, market_id), []))


class TestLiveWiring(unittest.TestCase):
    def test_game_line_market_ids_agree_with_the_observation_scan(self):
        for sport, rows in v3.MARKETS.items():
            scan_ids = {kind: mid for mid, kind, _ in rows if kind != "prop"}
            self.assertEqual(cf.GAME_LINE_MARKET[sport], scan_ids, sport)

    def test_nba_spread_pick_is_captured_through_capture_live(self):
        fake = FakeLiveBP()
        snaps, report = cc.capture_live([_gl("g1", "Clippers +14.5 vs Thunder", 14.5)],
                                        _at(15, 50), tracker=tracker, bp=fake, clv_fetch=cf,
                                        window_minutes=45, snapshots={})
        self.assertEqual(snaps["g1"]["close"], {"LAC": "-108", "OKC": "-112"})
        self.assertIn(("game_ladders", "NBA", 27926, 129), fake.calls)
        self.assertFalse([c for c in fake.calls if c[0] == "ladder"])   # no prop ladder

    def test_observations_live_reads_and_writes_only_the_given_file(self):
        fake = FakeLiveBP()
        with tempfile.TemporaryDirectory() as d:
            path = str(Path(d) / "v3-observations.json")
            v3.save_store(path, {"runs": [], "observations": [
                dict(_spread_observation(), start_utc="2026-10-25T23:00:00Z")]})
            fake.offers[("NBA", 27926, 129)] = [_okc_spread_offer()]
            updates, report = cc.capture_observations_live(_utc(22, 50), bp=fake,
                                                           window_minutes=45, path=path)
            self.assertEqual(list(updates), ["v3obs-okc"])
            self.assertIn(("raw_offers", "NBA", 27926, 129), fake.calls)
            self.assertIsNone(v3.load_store(path)["observations"][0]["close"])  # not saved

    def test_missing_observations_file_is_a_quiet_no_op(self):
        fake = FakeLiveBP()
        with tempfile.TemporaryDirectory() as d:
            updates, report = cc.capture_observations_live(
                _utc(22, 50), bp=fake, window_minutes=45, path=str(Path(d) / "none.json"))
        self.assertEqual((updates, report), ({}, []))
        self.assertEqual(fake.calls, [])


class TestCaptureClosesCommand(unittest.TestCase):
    """tracker.py capture-closes writes both files only under --apply."""

    def _run(self, apply):
        import argparse
        import contextlib
        import io
        d = tempfile.mkdtemp()
        snap_path = str(Path(d) / "closing_lines.json")
        obs_path = str(Path(d) / "v3-observations.json")
        picks_path = Path(d) / "picks.json"
        picks_path.write_text("[]")
        v3.save_store(obs_path, {"runs": [], "observations": [_spread_observation()]})
        saved = dict(PICKS_FILE=tracker.PICKS_FILE, SNAP=cc.SNAPSHOT_FILE,
                     OBS=cc.OBSERVATIONS_FILE, live=cc.capture_live,
                     obs_live=cc.capture_observations_live)
        sys.modules["close_capture"] = cc
        tracker.PICKS_FILE = picks_path
        cc.SNAPSHOT_FILE, cc.OBSERVATIONS_FILE = snap_path, obs_path
        cc.capture_live = lambda picks, **k: ({"g1": {"close": {}}}, [("g1", "captured", "T-5m")])
        upd = {"v3obs-okc": {"close": {"side": "Thunder"}, "realized_clv_exchange": 0.01,
                             "realized_clv_retail": -0.01}}
        cc.capture_observations_live = lambda **k: (upd, [("v3obs-okc", "captured", "T-5m")])
        out = io.StringIO()
        try:
            with contextlib.redirect_stdout(out):
                tracker.cmd_capture_closes(argparse.Namespace(window_minutes=45, apply=apply,
                                                              verbose=False))
        finally:
            tracker.PICKS_FILE = saved["PICKS_FILE"]
            cc.SNAPSHOT_FILE, cc.OBSERVATIONS_FILE = saved["SNAP"], saved["OBS"]
            cc.capture_live, cc.capture_observations_live = saved["live"], saved["obs_live"]
        return out.getvalue(), snap_path, obs_path

    def test_apply_writes_snapshots_and_observation_closes(self):
        out, snap_path, obs_path = self._run(apply=True)
        self.assertEqual(json.loads(Path(snap_path).read_text()), {"g1": {"close": {}}})
        obs = v3.load_store(obs_path)["observations"][0]
        self.assertEqual(obs["close"], {"side": "Thunder"})
        self.assertEqual(out.count("📸"), 2)

    def test_dry_run_writes_neither(self):
        out, snap_path, obs_path = self._run(apply=False)
        self.assertFalse(Path(snap_path).exists())
        self.assertIsNone(v3.load_store(obs_path)["observations"][0]["close"])
        self.assertIn("dry-run", out)


if __name__ == "__main__":
    unittest.main()
