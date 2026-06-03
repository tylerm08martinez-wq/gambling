"""CLV backfill — populate a pick's closing_line + realized CLV (#51).

The pure, testable core of the closing-line workflow. Given a pick and Pinnacle's
**two-way close** (fetched separately on the residential host — datacenter IPs 403,
ADR 0006), it de-vigs the close with value_engine and writes the realized CLV back
to the pick. Idempotent: only fills a missing closing_line/clv unless force=True.
Unmeasured picks (no close fetched) are left null — never a 0.0 placeholder, so
tracker.is_measured_clv (#46) keeps excluding them.

Realized CLV uses the **de-vigged Pinnacle close** (`fair_close / entry_implied - 1`),
the same definition as V3's *projected* CLV (value_engine) so the two are directly
comparable — not the legacy raw tracker.calc_clv. Expressed in percentage points to
match the existing `clv` field's scale.

The live Pinnacle fetch is the residential/HITL half (ADR 0006); this module consumes
*already-fetched* closes (a `{pick_id: {"close": {...}, "side": ..., "market": ...}}`
map), exactly like value_engine consumes pre-fetched boards — so it is fully testable.
"""

import re
import sys
from pathlib import Path

# Make value_engine importable whether run as a script (residential run) or loaded by
# file path under the test harness — add this module's own directory to the path.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import value_engine as ve  # noqa: E402


def _entry_odds(line):
    """Pull the bare American odds out of a pick's `line` field, which carries a book
    suffix like '+120 @ FanDuel' or '-105 (DK)' (matches tracker.american_to_implied_prob).
    value_engine expects clean odds, so strip the book before handing it over."""
    s = str(line).split("@")[0].strip()
    return re.sub(r"\s*\(.*\)\s*$", "", s).strip()


def realized_clv(pinnacle_close: dict, side: str, entry_line, market: str = "moneyline"):
    """Realized CLV in percentage points: (de-vigged Pinnacle fair on `side` / entry
    implied prob - 1) * 100. Returns None when it can't be computed (no close, missing
    side, or not a two-way market) — the caller must leave such picks Unmeasured."""
    if not pinnacle_close or len(pinnacle_close) != 2 or side not in pinnacle_close:
        return None
    s0, s1 = list(pinnacle_close.keys())
    fair0, fair1 = ve.fair_two_way(pinnacle_close[s0], pinnacle_close[s1], market)
    fair = {s0: fair0, s1: fair1}
    return ve.projected_clv(fair[side], ve.american_to_prob(_entry_odds(entry_line))) * 100.0


def backfill_pick(pick: dict, close_info, force: bool = False) -> bool:
    """Populate pick['closing_line'] + pick['clv'] from a fetched close. Returns True if
    the pick was updated. Idempotent: a no-op when the pick already has a closing_line
    unless force=True. No usable close → left null (never 0.0).

    `close_info` is {"close": {side: american, ...}, "side": <bet side>, "market": ...}
    or None when no close could be fetched for this pick.
    """
    if pick.get("closing_line") and not force:
        return False
    if not close_info or not close_info.get("close"):
        return False
    close = close_info["close"]
    side = close_info.get("side")
    market = close_info.get("market") or pick.get("bet_type") or "moneyline"
    if not side or side not in close:
        return False
    clv = realized_clv(close, side, pick.get("line"), market)
    if clv is None:
        return False
    pick["closing_line"] = str(close[side])   # Pinnacle's closing price on the bet side
    pick["clv"] = round(clv, 2)
    return True


def backfill_picks(picks: list, closes_by_id: dict, force: bool = False) -> int:
    """Apply fetched closes (keyed by pick id) to a list of picks; return # updated."""
    return sum(1 for p in picks if backfill_pick(p, closes_by_id.get(p.get("id")), force=force))


if __name__ == "__main__":
    # Apply pre-fetched Pinnacle closes to picks.json. The residential fetch wrapper
    # (HITL, ADR 0006) writes closes.json as {pick_id: {"close": {...}, "side", "market"}}.
    # Dry-run by default; pass --apply to write picks.json back.
    import argparse
    import json

    ap = argparse.ArgumentParser(description="Backfill realized CLV from pre-fetched Pinnacle closes.")
    ap.add_argument("picks", help="path to picks.json")
    ap.add_argument("closes", help="path to closes.json (from the residential fetch wrapper)")
    ap.add_argument("--apply", action="store_true", help="write picks.json back (default: dry-run)")
    ap.add_argument("--force", action="store_true", help="overwrite an existing closing_line/clv")
    args = ap.parse_args()

    with open(args.picks) as f:
        picks = json.load(f)
    with open(args.closes) as f:
        closes = json.load(f)
    n = backfill_picks(picks, closes, force=args.force)
    if args.apply:
        with open(args.picks, "w") as f:
            json.dump(picks, f, indent=2)
        print(f"Backfilled {n} pick(s) into {args.picks}.")
    else:
        print(f"[dry-run] would backfill {n} pick(s). Re-run with --apply to write.")
