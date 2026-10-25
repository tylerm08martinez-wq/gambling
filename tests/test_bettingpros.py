import importlib.util
import json
import sys
import unittest
from pathlib import Path

# Load the bettingpros module without installing it as a package (mirrors
# tests/test_tracker.py's loader so `python3 -m pytest tests/` finds it).
_spec = importlib.util.spec_from_file_location(
    "bettingpros",
    Path(__file__).parent.parent / ".agents" / "skills" / "bet-tracker" / "bettingpros.py",
)
bettingpros = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bettingpros)
sys.modules["bettingpros"] = bettingpros

_FIXTURES = Path(__file__).parent / "fixtures"


def _load(name):
    return json.loads((_FIXTURES / name).read_text())


def _fetcher(payload):
    """An injectable get_json that ignores the URL and returns a fixed payload."""
    return lambda url: payload


class TestFetchProps(unittest.TestCase):
    def test_normalizes_a_prop_into_the_extractor_shape(self):
        props = bettingpros.fetch_props(
            "MLB", get_json=_fetcher(_load("bp_props.json"))
        )
        self.assertTrue(props, "expected at least one normalized prop")
        p = props[0]
        # Identity + participant
        self.assertIn("market_id", p)
        self.assertIn("event_id", p)
        self.assertEqual(set(p["player"]), {"name", "team", "position"})
        # Both sides carry best-book line/odds AND consensus for gap detection
        for side in ("over", "under"):
            self.assertEqual(
                set(p[side]),
                {"line", "odds", "book", "consensus_line", "consensus_odds", "ev", "bet_rating"},
            )
        # Projection drives recommended side / prop-trend
        self.assertEqual(set(p["projection"]), {"recommended_side", "value", "diff"})

    def test_returns_empty_when_fetch_fails_never_fabricates(self):
        # A persistent block / timeout makes the shared client return None.
        self.assertEqual(bettingpros.fetch_props("MLB", get_json=_fetcher(None)), [])

    def test_follows_pagination_across_all_pages(self):
        # The API caps each page at 50; a real MLB slate spans many pages. The client
        # must return every prop, not just page 1, or it silently drops the edge.
        raw = _load("bp_props.json")["props"]
        pages = {
            1: {"props": raw, "_pagination": {"page": 1, "total_pages": 3, "next": "x"}},
            2: {"props": raw, "_pagination": {"page": 2, "total_pages": 3, "next": "x"}},
            3: {"props": raw, "_pagination": {"page": 3, "total_pages": 3, "next": None}},
        }

        def paged_get(url):
            import re as _re
            m = _re.search(r"page=(\d+)", url)
            return pages[int(m.group(1)) if m else 1]

        props = bettingpros.fetch_props("MLB", get_json=paged_get)
        self.assertEqual(len(props), len(raw) * 3)


class TestFetchEvents(unittest.TestCase):
    def test_normalizes_events_with_utc_time_and_pitchers(self):
        events = bettingpros.fetch_events(
            "MLB", "2026-06-01", get_json=_fetcher(_load("bp_events.json"))
        )
        self.assertTrue(events, "expected at least one normalized event")
        e = events[0]
        self.assertEqual(set(e), {"id", "scheduled", "home", "visitor", "pitchers",
                                  "participants"})
        # scheduled is the source UTC timestamp — the game-time of record (no DST table)
        self.assertEqual(e["scheduled"], "2026-06-01 22:40:00")
        self.assertEqual(set(e["pitchers"]), {"home", "visitor"})
        # The teams by name: game-line close capture matches bet text against these
        # (home/visitor are abbreviations only) (#109).
        self.assertEqual(e["participants"], [
            {"id": "TB", "name": "Rays", "city": "Tampa Bay", "abbreviation": "TB"},
            {"id": "DET", "name": "Tigers", "city": "Detroit", "abbreviation": "DET"}])

    def test_returns_empty_when_fetch_fails_never_fabricates(self):
        self.assertEqual(
            bettingpros.fetch_events("MLB", "2026-06-01", get_json=_fetcher(None)), []
        )


class TestScrapeApiKey(unittest.TestCase):
    def test_extracts_public_key_from_bundle_js(self):
        js = (_FIXTURES / "bp_bundle.js").read_text()
        self.assertEqual(
            bettingpros.scrape_api_key(get_text=lambda url: js),
            "FAKEtestkey000000000000000000000000000",
        )

    def test_returns_none_when_key_absent(self):
        js = (_FIXTURES / "bp_bundle_nokey.js").read_text()
        self.assertIsNone(bettingpros.scrape_api_key(get_text=lambda url: js))


class TestFetchOffers(unittest.TestCase):
    def test_normalizes_cross_book_snapshot_with_names_and_opening(self):
        offers = bettingpros.fetch_offers(
            98221, 285, get_json=_fetcher(_load("bp_offers.json"))
        )
        self.assertTrue(offers, "expected at least one normalized offer")
        sel = offers[0]["selections"][0]
        self.assertIn("label", sel)
        # opening_line is a plain number (the line that opened), for steam vs current
        self.assertIsInstance(sel["opening_line"], (int, float))
        b = sel["books"][0]
        self.assertEqual(set(b), {"book_id", "book", "line", "odds"})
        # book_id is decoded to a human name via the books map
        self.assertEqual(bettingpros.BOOKS.get(2), "Pinnacle")
        self.assertEqual(b["book"], bettingpros.BOOKS.get(b["book_id"], "book-%s" % b["book_id"]))

    def test_returns_empty_when_fetch_fails_never_fabricates(self):
        self.assertEqual(bettingpros.fetch_offers(1, 2, get_json=_fetcher(None)), [])


class TestResolveApiKey(unittest.TestCase):
    def test_env_override_takes_precedence_over_scrape(self):
        import os
        from unittest.mock import patch
        with patch.dict(os.environ, {"BETTINGPROS_API_KEY": "ENVKEY"}):
            # get_text would find a different key, but env wins and scrape is skipped.
            self.assertEqual(
                bettingpros.resolve_api_key(get_text=lambda url: 'api_key:"SCRAPEDKEYxxxxxxxxxxxxxxxxxxxxxxxx"'),
                "ENVKEY",
            )

    def test_falls_back_to_public_key_when_no_env_and_scrape_empty(self):
        import os
        from unittest.mock import patch
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("BETTINGPROS_API_KEY", None)
            # Scrape finds nothing → the committed public fallback is used.
            self.assertEqual(
                bettingpros.resolve_api_key(get_text=lambda url: "no key here"),
                bettingpros._PUBLIC_KEY_FALLBACK,
            )


def _ladder_offer(name, over, under, team="DEN"):
    """One raw /offers row: a player with consensus (book 0) over/under ladders."""
    def sel(label, ladder):
        return {"label": label, "books": [
            {"id": 0, "lines": [{"line": l, "cost": c} for l, c in ladder.items()]},
            {"id": 12, "lines": [{"line": 99.5, "cost": -110, "main": True}]},
        ]}
    return {"participants": [{"name": name, "player": {"team": team}}],
            "selections": [sel("Over", over), sel("Under", under)]}


class TestOffersSportAndPagination(unittest.TestCase):
    """NBA and NFL closes need sport=NBA/NFL, and /offers pages at 10 players, so a
    player on page 2 silently had no close at all."""

    def _paged(self, pages, seen):
        def get(url):
            import re as _re
            seen.append(url)
            m = _re.search(r"[?&]page=(\d+)", url)
            return pages.get(int(m.group(1)) if m else 1)
        return get

    def test_ladder_defaults_to_mlb(self):
        seen = []
        bettingpros.fetch_offer_ladder(1, 285, get_json=self._paged({1: {"offers": []}}, seen))
        self.assertIn("sport=MLB", seen[0])

    def test_ladder_uses_requested_sport(self):
        seen = []
        bettingpros.fetch_offer_ladder(27926, 156, sport="NBA",
                                       get_json=self._paged({1: {"offers": []}}, seen))
        self.assertIn("sport=NBA", seen[0])
        self.assertNotIn("sport=MLB", seen[0])

    def test_ladder_follows_pagination_to_every_page(self):
        pages = {
            1: {"offers": [_ladder_offer("Rui Hachimura", {16.5: -119}, {16.5: -107})],
                "_pagination": {"page": 1, "total_pages": 2}},
            2: {"offers": [_ladder_offer("Austin Reaves", {22.5: -110}, {22.5: -112})],
                "_pagination": {"page": 2, "total_pages": 2}},
        }
        seen = []
        out = bettingpros.fetch_offer_ladder(27926, 156, sport="NBA",
                                             get_json=self._paged(pages, seen))
        self.assertEqual([r["player"] for r in out], ["Rui Hachimura", "Austin Reaves"])
        self.assertEqual(out[1]["sides"], {"over": {22.5: -110}, "under": {22.5: -112}})
        self.assertEqual(len(seen), 2)
        self.assertIn("page=2", seen[1])

    def test_ladder_keeps_earlier_pages_when_a_later_page_fails(self):
        pages = {1: {"offers": [_ladder_offer("Rui Hachimura", {16.5: -119}, {16.5: -107})],
                     "_pagination": {"page": 1, "total_pages": 3}}}
        out = bettingpros.fetch_offer_ladder(27926, 156, sport="NBA",
                                             get_json=self._paged(pages, []))
        self.assertEqual([r["player"] for r in out], ["Rui Hachimura"])

    def test_ladder_empty_when_first_page_fails(self):
        self.assertEqual(bettingpros.fetch_offer_ladder(1, 2, sport="NFL",
                                                        get_json=_fetcher(None)), [])

    def test_offers_uses_sport_and_follows_pagination(self):
        raw = _load("bp_offers.json")["offers"]
        pages = {1: {"offers": raw, "_pagination": {"page": 1, "total_pages": 2}},
                 2: {"offers": raw, "_pagination": {"page": 2, "total_pages": 2}}}
        seen = []
        out = bettingpros.fetch_offers(21915, 103, sport="NFL", get_json=self._paged(pages, seen))
        self.assertEqual(len(out), len(raw) * 2)
        self.assertTrue(all("sport=NFL" in u for u in seen))

    def test_offers_defaults_to_mlb(self):
        seen = []
        bettingpros.fetch_offers(1, 2, get_json=self._paged({1: {"offers": []}}, seen))
        self.assertIn("sport=MLB", seen[0])


if __name__ == "__main__":
    unittest.main()
