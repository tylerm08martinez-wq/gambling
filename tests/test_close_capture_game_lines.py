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


if __name__ == "__main__":
    unittest.main()
