"""Tests for the V3 Observation Scan (#108, ADR 0011).

The scan runs the merged Exchange Benchmark engine over the morning board and writes
candidates to v3-observations.json, never picks.json. The failures worth pinning:
  - a candidate that clears the CLV gate being dropped because its ½-Kelly stake
    rounds under 1u (measurement mode sizes flat, ADR 0009)
  - a re-run duplicating rows or overwriting the first-seen price
  - a wrong market id returning [] and passing as a quiet, healthy day
  - observations leaking into picks.json, tracker stats or the dashboard
"""

import copy
import importlib.util
import json
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse

_ROOT = Path(__file__).parent.parent
_DIR = _ROOT / ".agents" / "skills" / "bet-tracker"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, _DIR / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    sys.modules[name] = mod
    return mod


v3 = _load("v3_scan")

_LIVE = json.loads((_ROOT / "tests" / "fixtures" / "exchange_benchmark_offers.json").read_text())
LIVE_NOW = datetime(2026, 10, 25, 2, 12, 0, tzinfo=timezone.utc)   # when the fixture was pulled


def _without_book(offer, book_id):
    out = copy.deepcopy(offer)
    for sel in out["selections"]:
        sel["books"] = [b for b in sel["books"] if b.get("id") != book_id]
    return out


def _event(eid, visitor, home, scheduled="2026-10-25 17:00:00"):
    return {"id": eid, "scheduled": scheduled, "visitor": visitor, "home": home}


class FakeBoard:
    """A get_json stand-in routing /events and paginated /offers URLs to canned data.

    `offers` maps (sport, event_id, market_id) -> list of pages (each a list of offers)."""

    def __init__(self, events, offers):
        self.events = events     # sport -> [event]
        self.offers = offers
        self.urls = []

    def __call__(self, url):
        self.urls.append(url)
        u = urlparse(url)
        qs = {k: v[0] for k, v in parse_qs(u.query).items()}
        if u.path.endswith("/events"):
            return {"events": self.events.get(qs["sport"], [])}
        if u.path.endswith("/offers"):
            pages = self.offers.get((qs["sport"], int(qs["event_id"]), int(qs["market_id"])), [[]])
            page = int(qs.get("page", 1))
            return {"offers": pages[page - 1] if page <= len(pages) else [],
                    "_pagination": {"page": page, "total_pages": len(pages)}}
        raise AssertionError(f"unexpected URL {url}")


def colts_board():
    # The live Colts @ Vikings moneyline without ProphetX: DraftKings Colts +260 is
    # +2.24% against a 3-operator benchmark, which clears the 2% gate, but its ½-Kelly
    # stake (0.43%) is under the 1u floor, so scan_market calls it `reject`.
    colts = _without_book(_LIVE["colts_vikings_moneyline"], 38)
    return FakeBoard({"NFL": [_event(22068, "IND", "MIN")]},
                     {("NFL", 22068, 1): [[colts]]})


class TestColtsObservation(unittest.TestCase):
    def test_a_price_that_clears_the_gate_is_observed_even_when_kelly_says_zero_units(self):
        result = v3.scan("2026-10-25", ["NFL"], LIVE_NOW, get_json=colts_board())
        dk = [o for o in result["observations"] if o["book_id"] == 12]
        self.assertEqual(len(dk), 1)
        obs = dk[0]
        self.assertAlmostEqual(obs["projected_clv"], 0.0224, delta=0.0005)
        self.assertEqual(obs["units_kelly"], 0)
        self.assertEqual(obs["odds"], 260)
        self.assertEqual(obs["side"], "Colts")
        self.assertEqual(obs["participant"], "Colts")
        self.assertEqual(obs["bet"], "Colts ML")
        self.assertEqual(obs["book"], "DraftKings")
        self.assertEqual(obs["kind"], "moneyline")
        self.assertEqual(obs["market_id"], 1)
        self.assertEqual(obs["event_id"], 22068)
        self.assertEqual(obs["start_utc"], "2026-10-25T17:00:00Z")
        self.assertEqual(len(obs["benchmark_operators"]), 3)
        self.assertIsNone(obs["close"])
        self.assertEqual(obs["scan_date"], "2026-10-25")


FRESH = "2026-10-25 02:05:00"   # 7 minutes before LIVE_NOW


def two_way_offer(labels, books, participants=None):
    """A raw /offers market. `books` maps book_id -> (line_a, cost_a, line_b, cost_b)."""
    sels = []
    for i, label in enumerate(labels):
        sels.append({"label": label, "books": [
            {"id": bid, "lines": [{"line": quote[2 * i], "cost": quote[2 * i + 1],
                                   "updated": FRESH, "main": True, "active": True,
                                   "is_off": False}]}
            for bid, quote in books.items()]})
    return {"participants": participants or [], "selections": sels}


def gainwell_under():
    # Novig and Kalshi at 14.5 -105/-105 -> fair Under .500; BetMGM Under +110 (.476)
    # is +5.0%, over the 3% prop gate. The Over at -150 is worse than fair.
    return two_way_offer(("Over", "Under"), {
        60: (14.5, -105, 14.5, -105), 68: (14.5, -105, 14.5, -105),
        19: (14.5, -150, 14.5, 110)}, participants=[{"id": "23310", "name": "Kenny Gainwell"}])


def dolphins_spread():
    # Jets -4.5 / Dolphins +4.5. Benchmark -105/-105 at Jets -4.5 -> fair .500 each;
    # FanDuel Dolphins +4.5 at +115 (.465) is +7.5%.
    return two_way_offer(("Jets", "Dolphins"), {
        60: (-4.5, -105, 4.5, -105), 68: (-4.5, -105, 4.5, -105),
        10: (-4.5, -140, 4.5, 115)})


class TestBoardShapes(unittest.TestCase):
    def test_a_prop_on_the_second_offers_page_is_observed_with_a_readable_bet(self):
        board = FakeBoard({"NFL": [_event(22072, "TB", "CAR")]},
                          {("NFL", 22072, 105): [[], [gainwell_under()]]})
        obs = v3.scan("2026-10-25", ["NFL"], LIVE_NOW, get_json=board)["observations"]
        self.assertEqual([o["bet"] for o in obs], ["Kenny Gainwell Under 14.5 receiving yards"])
        self.assertEqual(obs[0]["participant"], "Kenny Gainwell")
        self.assertEqual((obs[0]["line"], obs[0]["side"], obs[0]["book"]), (14.5, "Under", "BetMGM"))
        self.assertAlmostEqual(obs[0]["projected_clv"], 0.05, delta=0.001)
        self.assertTrue(any("page=2" in u for u in board.urls))

    def test_a_spread_reports_the_observed_sides_own_number(self):
        board = FakeBoard({"NFL": [_event(22069, "MIA", "NYJ")]},
                          {("NFL", 22069, 3): [[dolphins_spread()]]})
        obs = v3.scan("2026-10-25", ["NFL"], LIVE_NOW, get_json=board)["observations"]
        self.assertEqual([o["bet"] for o in obs], ["Dolphins +4.5"])
        self.assertEqual((obs[0]["participant"], obs[0]["line"]), ("Dolphins", 4.5))

    def test_an_event_that_has_started_is_never_scanned(self):
        board = FakeBoard({"NFL": [_event(22069, "MIA", "NYJ", scheduled="2026-10-25 02:00:00")]},
                          {("NFL", 22069, 3): [[dolphins_spread()]]})
        result = v3.scan("2026-10-25", ["NFL"], LIVE_NOW, get_json=board)
        self.assertEqual(result["observations"], [])
        self.assertFalse(any("/offers" in u for u in board.urls))


class TestRunRow(unittest.TestCase):
    def test_run_row_counts_what_was_scanned(self):
        result = v3.scan("2026-10-25", ["NFL"], LIVE_NOW, get_json=colts_board())
        run = result["run"]
        self.assertEqual(run["scan_date"], "2026-10-25")
        self.assertEqual(run["scanned_at"], "2026-10-25T02:12:00Z")
        self.assertEqual(run["sports"], ["NFL"])
        self.assertEqual(run["markets_scanned"], 1)        # the one Colts @ Vikings offer
        self.assertEqual(run["markets_with_benchmark"], 1)
        self.assertEqual(run["candidates"], len(result["observations"]))
        self.assertEqual(run["status"], "ok")
        # One count per (sport, market id): an empty id is visible, not silent.
        self.assertEqual(run["offers_by_market"]["NFL:1"], 1)
        self.assertEqual(run["offers_by_market"]["NFL:105"], 0)

    def test_a_sport_with_events_but_zero_offers_on_every_market_fails_loudly(self):
        board = FakeBoard({"NFL": [_event(22068, "IND", "MIN")]}, {})
        run = v3.scan("2026-10-25", ["NFL"], LIVE_NOW, get_json=board)["run"]
        self.assertEqual(run["status"], "failed")
        self.assertTrue(any("NFL" in e and "zero offers" in e for e in run["errors"]))

    def test_one_sport_with_no_events_is_a_quiet_day_not_a_failure(self):
        board = colts_board()
        run = v3.scan("2026-10-25", ["NFL", "MLB"], LIVE_NOW, get_json=board)["run"]
        self.assertEqual(run["status"], "ok")
        self.assertEqual(run["events_by_sport"], {"NFL": 1, "MLB": 0})

    def test_no_events_for_any_sport_fails_loudly(self):
        run = v3.scan("2026-10-25", ["NFL", "NBA"], LIVE_NOW, get_json=FakeBoard({}, {}))["run"]
        self.assertEqual(run["status"], "failed")
        self.assertTrue(run["errors"])

    def test_every_event_already_started_is_ok_with_nothing_scanned(self):
        board = FakeBoard({"NFL": [_event(22068, "IND", "MIN", scheduled="2026-10-25 01:00:00")]}, {})
        run = v3.scan("2026-10-25", ["NFL"], LIVE_NOW, get_json=board)["run"]
        self.assertEqual((run["status"], run["markets_scanned"], run["events_started"]), ("ok", 0, 1))


def gainwell_board(under_cost=110):
    offer = gainwell_under()
    offer["selections"][1]["books"][2]["lines"][0]["cost"] = under_cost   # BetMGM Under
    return FakeBoard({"NFL": [_event(22072, "TB", "CAR")]}, {("NFL", 22072, 105): [[offer]]})


class TestMergeAndIdempotence(unittest.TestCase):
    def test_id_is_deterministic_and_keyed_on_book(self):
        a = v3.scan("2026-10-25", ["NFL"], LIVE_NOW, get_json=gainwell_board())["observations"][0]
        b = v3.scan("2026-10-25", ["NFL"], LIVE_NOW, get_json=gainwell_board())["observations"][0]
        self.assertEqual(a["id"], b["id"])
        self.assertNotEqual(a["id"], v3.observation_id("2026-10-25", 22072, 105, "Kenny Gainwell",
                                                       14.5, "Under", 10))
        self.assertNotEqual(a["id"], v3.observation_id("2026-10-26", 22072, 105, "Kenny Gainwell",
                                                       14.5, "Under", 19))

    def test_rerun_appends_a_run_row_but_never_duplicates_or_overwrites(self):
        store = v3.merge({"runs": [], "observations": []},
                         v3.scan("2026-10-25", ["NFL"], LIVE_NOW, get_json=gainwell_board(110)))
        # Later the same morning BetMGM has moved to +115: the first-seen +110 stands.
        store = v3.merge(store, v3.scan("2026-10-25", ["NFL"], LIVE_NOW,
                                        get_json=gainwell_board(115)))
        self.assertEqual(len(store["runs"]), 2)
        self.assertEqual(len(store["observations"]), 1)
        self.assertEqual(store["observations"][0]["odds"], 110)
        self.assertEqual([r["new_observations"] for r in store["runs"]], [1, 0])


class TestCli(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.tmp = Path(tempfile.mkdtemp())
        self.out = self.tmp / "v3-observations.json"

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _main(self, *extra, board=None):
        import contextlib
        import io
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(io.StringIO()):
            rc = v3.main(["--date", "2026-10-25", "--sports", "NFL", "--out", str(self.out), *extra],
                         get_json=board or gainwell_board(), now=LIVE_NOW)
        return rc, buf.getvalue()

    def test_without_apply_it_prints_and_writes_nothing(self):
        rc, printed = self._main()
        self.assertEqual(rc, 0)
        self.assertFalse(self.out.exists())
        self.assertIn("Kenny Gainwell Under 14.5 receiving yards", printed)

    def test_apply_writes_runs_and_observations(self):
        self._main("--apply")
        self._main("--apply")
        data = json.loads(self.out.read_text())
        self.assertEqual(sorted(data), ["observations", "runs"])
        self.assertEqual(len(data["runs"]), 2)
        self.assertEqual(len(data["observations"]), 1)

    def test_a_failed_scan_exits_nonzero_and_still_records_the_run(self):
        rc, _ = self._main("--apply", board=FakeBoard({"NFL": [_event(1, "A", "B")]}, {}))
        self.assertEqual(rc, 2)
        self.assertEqual(json.loads(self.out.read_text())["runs"][0]["status"], "failed")


if __name__ == "__main__":
    unittest.main()
