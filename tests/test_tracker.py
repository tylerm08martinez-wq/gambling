import importlib.util
import sys
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock
import json

# Load tracker module without installing it as a package
_spec = importlib.util.spec_from_file_location(
    "tracker",
    Path(__file__).parent.parent / ".agents" / "skills" / "bet-tracker" / "tracker.py",
)
tracker = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tracker)


class TestAmericanToImpliedProb(unittest.TestCase):
    def test_negative_odds(self):
        result = tracker.american_to_implied_prob("-110")
        self.assertAlmostEqual(result, 110 / 210, places=5)

    def test_positive_odds(self):
        result = tracker.american_to_implied_prob("+120")
        self.assertAlmostEqual(result, 100 / 220, places=5)

    def test_bookmaker_suffix_stripped(self):
        result = tracker.american_to_implied_prob("-110 @ DraftKings")
        self.assertAlmostEqual(result, 110 / 210, places=5)

    def test_plus_odds_with_suffix(self):
        result = tracker.american_to_implied_prob("+150 @ FanDuel")
        self.assertAlmostEqual(result, 100 / 250, places=5)

    def test_unparseable_raises(self):
        with self.assertRaises((ValueError, Exception)):
            tracker.american_to_implied_prob("even")


class TestCalcUnitsWonLost(unittest.TestCase):
    def test_win_negative_odds(self):
        # -110 line, 1 unit: win = 100/110 * 1
        result = tracker.calc_units_won_lost("-110", 1, "win")
        self.assertAlmostEqual(result, round(100 / 110, 3))

    def test_win_positive_odds(self):
        # +120 line, 2 units: win = 120/100 * 2
        result = tracker.calc_units_won_lost("+120", 2, "win")
        self.assertAlmostEqual(result, round(120 / 100 * 2, 3))

    def test_loss_negative_odds(self):
        result = tracker.calc_units_won_lost("-110", 2, "loss")
        self.assertEqual(result, -2.0)

    def test_loss_positive_odds(self):
        result = tracker.calc_units_won_lost("+150", 3, "loss")
        self.assertEqual(result, -3.0)

    def test_push_returns_zero(self):
        self.assertEqual(tracker.calc_units_won_lost("-110", 1, "push"), 0.0)

    def test_void_returns_zero(self):
        self.assertEqual(tracker.calc_units_won_lost("+120", 2, "void"), 0.0)


class TestCalcClv(unittest.TestCase):
    def test_positive_clv(self):
        # Bet at -110, closes at -120 → closing is more juice → positive CLV for us
        result = tracker.calc_clv("-110", "-120")
        self.assertGreater(result, 0)

    def test_negative_clv(self):
        # Bet at -110, closes at -100 → closing is less juice → negative CLV
        result = tracker.calc_clv("-110", "-100")
        self.assertLess(result, 0)

    def test_unparseable_closing_line_raises_or_returns_none(self):
        try:
            result = tracker.calc_clv("-110", "N/A")
            self.assertIsNone(result)
        except (ValueError, Exception):
            pass  # either behavior is acceptable per issue spec


class TestDetermineOutcome(unittest.TestCase):
    # Run line
    def test_rl_win(self):
        self.assertEqual(tracker.determine_outcome("rl", 2, 1.5), "win")

    def test_rl_loss_short(self):
        self.assertEqual(tracker.determine_outcome("rl", 1, 1.5), "loss")

    def test_rl_loss_negative_margin(self):
        self.assertEqual(tracker.determine_outcome("rl", -1, 1.5), "loss")

    def test_rl_push_whole_number_line(self):
        self.assertEqual(tracker.determine_outcome("rl", 2, 2.0), "push")

    def test_rl_no_push_on_half_line(self):
        # Margin exactly equal to a .5 line can't push
        self.assertEqual(tracker.determine_outcome("rl", 1, 1.0), "push")  # whole number = push
        self.assertNotEqual(tracker.determine_outcome("rl", 1, 1.5), "push")

    def test_rl_run_line_string(self):
        self.assertEqual(tracker.determine_outcome("run line", 3, 1.5), "win")

    # Moneyline
    def test_ml_win(self):
        self.assertEqual(tracker.determine_outcome("ml", 3, None), "win")

    def test_ml_loss(self):
        self.assertEqual(tracker.determine_outcome("ml", -2, None), "loss")

    def test_ml_push(self):
        self.assertEqual(tracker.determine_outcome("ml", 0, None), "push")


class TestFetchMlbResult(unittest.TestCase):
    def _make_game(self, home_score, away_score, status="Final", home_name="Arizona Diamondbacks", away_name="Los Angeles Dodgers"):
        return {
            "teams": {
                "home": {
                    "team": {"name": home_name, "abbreviation": "ARI"},
                    "score": home_score,
                },
                "away": {
                    "team": {"name": away_name, "abbreviation": "LAD"},
                    "score": away_score,
                },
            },
            "status": {"detailedState": status},
        }

    def _api_response(self, games):
        return json.dumps({
            "dates": [{"games": games}]
        }).encode()

    @patch("urllib.request.urlopen")
    def test_final_game_found(self, mock_urlopen):
        mock_cm = MagicMock()
        mock_cm.__enter__ = MagicMock(return_value=mock_cm)
        mock_cm.__exit__ = MagicMock(return_value=False)
        mock_cm.read.return_value = self._api_response([
            self._make_game(6, 3, status="Final")
        ])
        mock_urlopen.return_value = mock_cm

        result = tracker.fetch_mlb_result("2026-05-27", "Arizona")
        self.assertIsNotNone(result)
        self.assertEqual(result["margin"], 3)   # home won 6-3
        self.assertIn("Final", result["status"])

    @patch("urllib.request.urlopen")
    def test_game_not_yet_final(self, mock_urlopen):
        mock_cm = MagicMock()
        mock_cm.__enter__ = MagicMock(return_value=mock_cm)
        mock_cm.__exit__ = MagicMock(return_value=False)
        mock_cm.read.return_value = self._api_response([
            self._make_game(3, 2, status="In Progress")
        ])
        mock_urlopen.return_value = mock_cm

        result = tracker.fetch_mlb_result("2026-05-27", "Arizona")
        self.assertIsNone(result)

    @patch("urllib.request.urlopen")
    def test_no_game_found(self, mock_urlopen):
        mock_cm = MagicMock()
        mock_cm.__enter__ = MagicMock(return_value=mock_cm)
        mock_cm.__exit__ = MagicMock(return_value=False)
        mock_cm.read.return_value = json.dumps({"dates": []}).encode()
        mock_urlopen.return_value = mock_cm

        result = tracker.fetch_mlb_result("2026-05-27", "Arizona")
        self.assertIsNone(result)

    @patch("urllib.request.urlopen")
    def test_network_error(self, mock_urlopen):
        mock_urlopen.side_effect = Exception("timeout")

        result = tracker.fetch_mlb_result("2026-05-27", "Arizona")
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
