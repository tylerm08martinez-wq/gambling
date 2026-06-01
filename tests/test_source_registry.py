import importlib.util
import json
import sys
import unittest
from pathlib import Path

# Load the source_registry module without installing it as a package
# (mirrors tests/test_bettingpros.py's loader so the .py-by-path pattern works).
_spec = importlib.util.spec_from_file_location(
    "source_registry",
    Path(__file__).parent.parent / ".agents" / "skills" / "bet-tracker" / "source_registry.py",
)
source_registry = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(source_registry)
sys.modules["source_registry"] = source_registry

_FIXTURES = Path(__file__).parent / "fixtures"


def _write_tmp(tmpdir, name, payload):
    """Write a synthetic registry to a temp path and return it."""
    p = Path(tmpdir) / name
    if isinstance(payload, str):
        p.write_text(payload)
    else:
        p.write_text(json.dumps(payload))
    return p


class TestLoadRegistry(unittest.TestCase):
    def test_well_formed_real_registry_exposes_all_four_role_lists(self):
        reg = source_registry.load_registry()  # defaults to the canonical file
        # Role-keyed: the four roles are present and are lists.
        for role in ("primary_splits", "secondary_splits", "line_movement", "stale"):
            self.assertIn(role, reg)
            self.assertIsInstance(reg[role], list)
        # Every active list has at least one source; stale is non-empty too.
        self.assertTrue(reg["primary_splits"])
        self.assertTrue(reg["secondary_splits"])
        self.assertTrue(reg["line_movement"])
        self.assertTrue(reg["stale"])


class TestMalformedRaises(unittest.TestCase):
    def test_invalid_json_raises_not_empty(self):
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            p = _write_tmp(d, "bad.json", "{ not valid json,,,")
            with self.assertRaises(source_registry.RegistryError):
                source_registry.load_registry(p)

    def test_missing_role_raises_not_empty(self):
        import tempfile

        # Valid JSON, but the line_movement role is absent — must raise, never
        # return {} or silently drop the role.
        payload = {"primary_splits": [], "secondary_splits": [], "stale": []}
        with tempfile.TemporaryDirectory() as d:
            p = _write_tmp(d, "missing_role.json", payload)
            with self.assertRaises(source_registry.RegistryError):
                source_registry.load_registry(p)


class TestActiveStaleCollisionRaises(unittest.TestCase):
    def test_same_url_in_active_and_stale_raises(self):
        import tempfile

        # cleatz appears as a live primary source AND in the never-fetch list —
        # a contradiction the parser must surface, not swallow.
        payload = {
            "primary_splits": [{"url": "https://cleatz.com/public-betting/mlb/", "sports": ["mlb"]}],
            "secondary_splits": [],
            "line_movement": [],
            "stale": [{"url": "cleatz.com/public-betting/mlb"}],
        }
        with tempfile.TemporaryDirectory() as d:
            p = _write_tmp(d, "collision.json", payload)
            with self.assertRaises(source_registry.RegistryError):
                source_registry.load_registry(p)

    def test_real_registry_has_no_collision(self):
        # The migrated data is legal under full-URL normalization: the dknetwork
        # splits-page URL and the bare dknetwork.draftkings.com stale entry are
        # distinct URLs, as are contests.covers.com/... and covers.com.
        reg = source_registry.load_registry()
        self.assertTrue(reg["primary_splits"] and reg["stale"])


class TestNoLossAndSportAware(unittest.TestCase):
    def setUp(self):
        self.reg = source_registry.load_registry()

    def _all_urls(self, role):
        return [e["url"] for e in self.reg[role]]

    def test_all_step2_active_sources_migrated(self):
        self.assertIn("https://cleatz.com/public-betting/mlb/", self._all_urls("primary_splits"))
        self.assertIn(
            "https://dknetwork.draftkings.com/draftkings-sportsbook-betting-splits/",
            self._all_urls("primary_splits"),
        )
        self.assertIn(
            "https://www.wunderdog.com/mlb-baseball/public-consensus",
            self._all_urls("secondary_splits"),
        )
        self.assertIn(
            "https://contests.covers.com/consensus/topconsensus/all/overall",
            self._all_urls("secondary_splits"),
        )
        self.assertIn(
            "https://www.vegasinsider.com/[sport]/odds/las-vegas/",
            self._all_urls("line_movement"),
        )

    def test_all_eleven_stale_domains_migrated(self):
        expected = {
            "actionnetwork.com", "sportsbettingdime.com", "docsports.com",
            "sportsinsights.com", "betql.com", "covers.com", "vsin.com",
            "sportsbookreview.com", "oddsshark.com", "winnersandwhiners.com",
            "dknetwork.draftkings.com",
        }
        self.assertEqual(set(self._all_urls("stale")), expected)

    def test_sources_are_sport_aware(self):
        # Each active entry carries a `sports` field: a list of sports or "all".
        for role in ("primary_splits", "secondary_splits", "line_movement"):
            for entry in self.reg[role]:
                self.assertIn("sports", entry)
                self.assertTrue(
                    entry["sports"] == "all" or isinstance(entry["sports"], list),
                    f"{entry['url']} sports must be a list or 'all'",
                )
        # The sport-specific cleatz source enumerates its sports.
        cleatz = next(e for e in self.reg["primary_splits"] if "cleatz" in e["url"])
        self.assertEqual(cleatz["sports"], ["mlb", "nba", "nhl"])


if __name__ == "__main__":
    unittest.main()
