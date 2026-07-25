"""Invariants over the REAL picks.json — the ledger, not a fixture.

Every other test in this suite validates logic against cases someone thought of.
This one validates the actual money record against properties that must hold no
matter how a row got written. It exists because every bug found in the 2026-07-25
audit was already visible in the data:

  - six picks carried a hand-written `clv` of 0.0 beside unparseable free text
    ('Mets ML +110') and were counted as Measured CLV
  - four `-rl` picks were totals/props against the Ma-RL-ins (a substring bug)
  - game totals carried `game_margin`, a game-line field, because they had been
    routed to the moneyline resolver
  - CLV values were written under two incompatible formulas into one field

None of those were caught by a fixture test, and all of them are trivially
detectable here. A failure means the LEDGER is wrong — which is worse than a code
bug, because it is what the dashboard, the ROI figures, and every conclusion about
edge are computed from.

Legacy rows predating a rule are scoped explicitly by date rather than silently
skipped, so the exemption is visible and shrinks over time.
"""

import importlib.util
import json
import sys
import unittest
from collections import Counter
from pathlib import Path

_ROOT = Path(__file__).parent.parent
_spec = importlib.util.spec_from_file_location(
    "tracker", _ROOT / ".agents" / "skills" / "bet-tracker" / "tracker.py")
tracker = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tracker)
sys.modules["tracker"] = tracker

PICKS_FILE = _ROOT / ".agents" / "skills" / "bet-tracker" / "picks.json"

# Rules introduced on 2026-07-25. Rows logged before this predate them; they were
# migrated where possible and are exempted where not. New picks get no exemption.
SCHEMA_CUTOVER = "2026-07-25"

# Picks whose `line` field holds the BET rather than the PRICE, e.g.
# 'under 17.5 @ Underdog'. Logged 2026-07-01 and 2026-07-07, before `log` validated
# --line. Their true odds were never recorded and are not recoverable, so the four
# WINNING rows were paid out at an assumed -110 (1.818u on a 2u stake). The two losing
# rows are unaffected — a loss costs the stake whatever the price.
#
# These are named individually rather than waved through by date so the exemption
# cannot silently grow: any NEW pick with an unparseable line fails this suite, and
# `log` now rejects one outright. Do not add to this list — fix the pick instead.
#
# Material: these four carry +3.27u of the book's +4.06u total P&L.
UNRECOVERABLE_PRICE_IDS = frozenset({
    "20260701-mlb-v1-troy-total",
    "20260701-mlb-v1-paul-total",
    "20260701-mlb-v1-junior-total",
    "20260701-mlb-v2-zack-total",
})


def _load():
    raw = json.loads(PICKS_FILE.read_text(encoding="utf-8"))
    return raw["picks"] if isinstance(raw, dict) and "picks" in raw else raw


class TestPicksLedgerInvariants(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.picks = _load()

    def test_ledger_is_non_empty(self):
        self.assertGreater(len(self.picks), 0, "picks.json is empty or unreadable")

    def test_pick_ids_are_unique(self):
        # v3-value picks were stamped "v2" in the id, so a V2 and a V3 pick on the
        # same team/date/type collided — and cmd_resolve takes the FIRST match while
        # clv_backfill keys by id, so the wrong pick got resolved.
        dupes = [i for i, n in Counter(p["id"] for p in self.picks).items() if n > 1]
        self.assertEqual(dupes, [], f"duplicate pick ids: {dupes}")

    def test_results_are_from_the_known_vocabulary(self):
        # calc_units_won_lost pays a WIN on any unrecognised result string.
        allowed = {None, "win", "loss", "push", "void"}
        bad = [(p["id"], p.get("result")) for p in self.picks if p.get("result") not in allowed]
        self.assertEqual(bad, [], f"unknown result values: {bad}")

    def test_units_won_lost_reproduces_from_line_units_result(self):
        """The money column must be derivable from its own inputs.

        This is the single most important assertion in the suite: it catches a lost
        bet booked as a win, a push paying out, and any hand-edited payout.
        """
        bad = []
        for p in self.picks:
            if p.get("result") is None or p.get("units_won_lost") is None:
                continue
            if p["id"] in UNRECOVERABLE_PRICE_IDS:
                continue
            try:
                expected = tracker.calc_units_won_lost(p["line"], p["units"], p["result"])
            except (ValueError, TypeError) as e:
                bad.append((p["id"], f"unparseable line {p.get('line')!r}: {e}"))
                continue
            if abs(expected - p["units_won_lost"]) > 0.001:
                bad.append((p["id"], f"stored {p['units_won_lost']} != computed {expected}"))
        self.assertEqual(bad, [], f"units_won_lost does not reproduce:\n  " +
                                  "\n  ".join(f"{i}: {m}" for i, m in bad))

    def test_no_new_picks_with_an_unrecoverable_price(self):
        """`line` must be the PRICE. The known-bad cohort is fixed and named; any new
        one is a regression, since `log` now rejects an unparseable --line outright."""
        bad = [(p["id"], p.get("line")) for p in self.picks
               if tracker.parse_american(p.get("line")) is None
               and p["id"] not in UNRECOVERABLE_PRICE_IDS
               # the two losing rows in the same cohort: a loss costs the stake
               # regardless of price, so their payout is still correct
               and p.get("result") != "loss"]
        self.assertEqual(bad, [], f"`line` is not American odds: {bad}")

    def test_the_exemption_list_does_not_grow(self):
        self.assertEqual(len(UNRECOVERABLE_PRICE_IDS), 4,
                         "UNRECOVERABLE_PRICE_IDS must not grow — fix the pick instead")
        live = {p["id"] for p in self.picks}
        self.assertTrue(UNRECOVERABLE_PRICE_IDS <= live,
                        "exemption names a pick that no longer exists; prune it")

    def test_pushes_and_voids_are_flat(self):
        bad = [(p["id"], p["units_won_lost"]) for p in self.picks
               if p.get("result") in ("push", "void") and p.get("units_won_lost") not in (0, 0.0)]
        self.assertEqual(bad, [], f"push/void must be 0 units: {bad}")

    def test_no_clv_without_a_parseable_close(self):
        """A CLV value implies a real fetched close.

        Six picks stored clv 0.0 beside 'Mets ML +110' / 'Spurs +6.5 -110' and were
        counted in the Measured denominator, dragging avg_clv toward zero.
        """
        bad = []
        for p in self.picks:
            has_clv = any(p.get(k) is not None
                          for k in ("clv", "clv_devig", "clv_pct_pts"))
            if has_clv and tracker.parse_american(p.get("closing_line")) is None:
                bad.append((p["id"], p.get("closing_line")))
        self.assertEqual(bad, [], f"CLV recorded against an unparseable close: {bad}")

    def test_clv_pct_pts_reproduces_from_line_and_close(self):
        """Percentage-point CLV must be derivable, which makes hand-edits detectable.

        This is what enforces CLAUDE.md's "never edit picks.json manually" for the
        CLV column — a typed-in number will not reproduce.
        """
        bad = []
        for p in self.picks:
            if p.get("clv_pct_pts") is None:
                continue
            try:
                expected = tracker.calc_clv(p["line"], p["closing_line"])
            except (ValueError, TypeError, ZeroDivisionError) as e:
                bad.append((p["id"], f"inputs unparseable: {e}"))
                continue
            if abs(expected - p["clv_pct_pts"]) > 0.02:
                bad.append((p["id"], f"stored {p['clv_pct_pts']} != computed {expected}"))
        self.assertEqual(bad, [], f"clv_pct_pts does not reproduce:\n  " +
                                  "\n  ".join(f"{i}: {m}" for i, m in bad))

    def test_clv_mirror_matches_its_source_fields(self):
        bad = []
        for p in self.picks:
            if "clv_devig" not in p and "clv_pct_pts" not in p:
                continue
            expected = p.get("clv_devig") if p.get("clv_devig") is not None else p.get("clv_pct_pts")
            if p.get("clv") != expected:
                bad.append((p["id"], p.get("clv"), expected))
        self.assertEqual(bad, [], f"legacy `clv` mirror out of sync: {bad}")

    def test_game_margin_only_on_game_line_bets(self):
        """`game_margin` on a total or prop means it was graded by the wrong resolver.

        Legacy rows carry it because game totals were classified as moneylines and
        routed through the margin path — the ADR 0004 mis-resolution class.
        """
        bad = [(p["id"], tracker.classify_bet(p), p.get("game_margin"))
               for p in self.picks
               if p.get("date", "") >= SCHEMA_CUTOVER
               and p.get("game_margin") is not None
               and tracker.classify_bet(p) in ("prop", "total")]
        self.assertEqual(bad, [], f"game_margin set on a non-game-line bet: {bad}")

    def test_bet_type_when_present_is_from_the_known_vocabulary(self):
        allowed = {"prop", "total", "spread", "rl", "ml"}
        bad = [(p["id"], p["bet_type"]) for p in self.picks
               if p.get("bet_type") is not None and p["bet_type"] not in allowed]
        self.assertEqual(bad, [], f"unknown bet_type: {bad}")

    def test_new_picks_record_how_their_bet_type_was_decided(self):
        """Persisting bet_type turns a guess into permanent data, so the provenance
        must travel with it — otherwise an inference is indistinguishable from a fact."""
        bad = [p["id"] for p in self.picks
               if p.get("date", "") >= SCHEMA_CUTOVER
               and p.get("bet_type") is not None
               and p.get("bet_type_source") not in ("declared", "inferred")]
        self.assertEqual(bad, [], f"bet_type without bet_type_source: {bad}")

    def test_settled_picks_have_a_stake(self):
        bad = [(p["id"], p.get("units")) for p in self.picks
               if p.get("result") is not None
               and not isinstance(p.get("units"), (int, float))]
        self.assertEqual(bad, [], f"settled pick with no numeric stake: {bad}")

    def test_every_pick_has_the_identity_fields(self):
        required = ("id", "date", "model", "sport", "bet", "line", "units")
        bad = [(p.get("id", "<no id>"), k) for p in self.picks for k in required if k not in p]
        self.assertEqual(bad, [], f"missing required field: {bad}")


if __name__ == "__main__":
    unittest.main()
