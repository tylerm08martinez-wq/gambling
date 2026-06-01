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


class TestFetchEvents(unittest.TestCase):
    def test_normalizes_events_with_utc_time_and_pitchers(self):
        events = bettingpros.fetch_events(
            "MLB", "2026-06-01", get_json=_fetcher(_load("bp_events.json"))
        )
        self.assertTrue(events, "expected at least one normalized event")
        e = events[0]
        self.assertEqual(set(e), {"id", "scheduled", "home", "visitor", "pitchers"})
        # scheduled is the source UTC timestamp — the game-time of record (no DST table)
        self.assertEqual(e["scheduled"], "2026-06-01 22:40:00")
        self.assertEqual(set(e["pitchers"]), {"home", "visitor"})

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


if __name__ == "__main__":
    unittest.main()
