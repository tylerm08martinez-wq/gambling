import importlib.util
import sys
import unittest
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "prop_edge",
    Path(__file__).parent.parent / ".agents" / "skills" / "bet-tracker" / "prop_edge.py",
)
prop_edge = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(prop_edge)
sys.modules["prop_edge"] = prop_edge


def _prop(*, over_line, under_line, consensus, over_book=10, under_book=12,
          rec_side="over", diff=1.0, over_rating=4, over_ev=0.1):
    """A normalized prop (fetch_props output shape) for the extractor to consume."""
    return {
        "market_id": 405,
        "event_id": 98117,
        "player": {"name": "Test Pitcher", "team": "KC", "position": "SP"},
        "over": {"line": over_line, "odds": -110, "book": over_book,
                 "consensus_line": consensus, "consensus_odds": -115,
                 "ev": over_ev, "bet_rating": over_rating},
        "under": {"line": under_line, "odds": -110, "book": under_book,
                  "consensus_line": consensus, "consensus_odds": -115,
                  "ev": -0.1, "bet_rating": 2},
        "projection": {"recommended_side": rec_side, "value": 6.8, "diff": diff},
        "performance": {"season": {"over": 7, "under": 3, "push": 0}},
    }


class TestCrossBookGap(unittest.TestCase):
    def test_lower_best_line_than_consensus_is_an_over_gap(self):
        # Best over line 5.5 vs consensus 6.0 → a lower bar favors the over; the stale
        # book offering it is the bet target.
        c = prop_edge.extract_prop_edge(
            _prop(over_line=5.5, under_line=5.5, consensus=6.0, over_book=10)
        )
        self.assertEqual(c["primary_edge_type"], "cross_book_gap")
        self.assertEqual(c["side"], "over")
        self.assertEqual(c["bet_book"], 10)
        self.assertAlmostEqual(c["gap"], 0.5)

    def test_higher_best_line_than_consensus_is_an_under_gap(self):
        # Best line 7.0 vs consensus 6.0 → a higher bar favors the under.
        c = prop_edge.extract_prop_edge(
            _prop(over_line=7.0, under_line=7.0, consensus=6.0, under_book=12,
                  rec_side="under")
        )
        self.assertEqual(c["primary_edge_type"], "cross_book_gap")
        self.assertEqual(c["side"], "under")
        self.assertEqual(c["bet_book"], 12)
        self.assertAlmostEqual(c["gap"], 1.0)

    def test_no_gap_is_no_signal(self):
        c = prop_edge.extract_prop_edge(
            _prop(over_line=6.0, under_line=6.0, consensus=6.0, rec_side="over",
                  over_rating=2)
        )
        self.assertIsNone(c["primary_edge_type"])
        self.assertIsNone(c["side"])


class TestPropTrend(unittest.TestCase):
    def test_projection_agreeing_with_gap_side_confirms_trend(self):
        # Over gap, and the model also recommends the over → confirmation bonus.
        c = prop_edge.extract_prop_edge(
            _prop(over_line=5.5, under_line=5.5, consensus=6.0, rec_side="over")
        )
        self.assertEqual(c["primary_edge_type"], "cross_book_gap")
        self.assertTrue(c["trend_confirmed"])

    def test_projection_opposing_gap_side_does_not_confirm(self):
        c = prop_edge.extract_prop_edge(
            _prop(over_line=5.5, under_line=5.5, consensus=6.0, rec_side="under")
        )
        self.assertFalse(c["trend_confirmed"])

    def test_strong_projection_without_gap_is_standalone_prop_trend(self):
        # No line gap, but a strongly-rated projection → prop_trend as the primary edge.
        c = prop_edge.extract_prop_edge(
            _prop(over_line=6.0, under_line=6.0, consensus=6.0, rec_side="over",
                  over_rating=5)
        )
        self.assertEqual(c["primary_edge_type"], "prop_trend")
        self.assertEqual(c["side"], "over")
        self.assertTrue(c["trend_confirmed"])


class TestSelectEdges(unittest.TestCase):
    def test_keeps_only_signalled_candidates_sorted_by_gap(self):
        props = [
            _prop(over_line=6.0, under_line=6.0, consensus=6.0, rec_side="over", over_rating=2),  # none
            _prop(over_line=5.5, under_line=5.5, consensus=6.0),  # gap 0.5
            _prop(over_line=4.0, under_line=4.0, consensus=6.0),  # gap 2.0
        ]
        out = prop_edge.select_edges(props)
        self.assertEqual([c["gap"] for c in out], [2.0, 0.5])  # signalled only, biggest first


if __name__ == "__main__":
    unittest.main()
