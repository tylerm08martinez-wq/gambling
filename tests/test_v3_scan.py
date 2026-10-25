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


if __name__ == "__main__":
    unittest.main()
