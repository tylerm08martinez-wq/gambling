#!/usr/bin/env python3
"""Run a live resolver verification against an isolated in-memory pick.

Examples:
  python3 scripts/verify_resolution.py --sport MLB --date 2026-05-29 --bet "Sal Stewart Over 1.5 hits vs Braves" --line-num 1.5 --expect win
  python3 scripts/verify_resolution.py --sport NBA --date 2026-05-18 --bet "Jalen Brunson Over 28.5 points vs Celtics" --line-num 28.5 --expect open

Hits live MLB Stats / ESPN APIs and leaves the real picks.json untouched.
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path
from unittest.mock import patch


def load_tracker():
    repo_root = Path(__file__).resolve().parents[1]
    tracker_path = repo_root / ".agents" / "skills" / "bet-tracker" / "tracker.py"
    spec = importlib.util.spec_from_file_location("tracker", tracker_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load tracker module from {tracker_path}")

    tracker = importlib.util.module_from_spec(spec)
    sys.modules["tracker"] = tracker
    spec.loader.exec_module(tracker)
    return tracker


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Verify live auto-resolution without touching real picks.json."
    )
    parser.add_argument("--sport", required=True, help="Sport code, e.g. MLB or NBA")
    parser.add_argument("--bet", required=True, help="Full bet text, including a team name")
    parser.add_argument("--date", required=True, help="Bet date in YYYY-MM-DD format")
    parser.add_argument("--line", default="-110", help="American odds")
    parser.add_argument("--line-num", type=float, default=None, help="Prop threshold")
    parser.add_argument("--units", type=int, default=1, help="Units staked")
    parser.add_argument("--expect", choices=("win", "loss", "push", "open"))
    parser.add_argument("--id", default="verify-1", help="Synthetic pick id")
    return parser


def report_pick(pick: dict) -> None:
    print("\nVerification report")
    print(f"id: {pick.get('id')}")
    print(f"result: {pick.get('result')}")
    print(f"prop_result: {pick.get('prop_result')}")
    print(f"prop_margin: {pick.get('prop_margin')}")
    print(f"final_score: {pick.get('final_score')}")
    print(f"game_margin_present: {'game_margin' in pick}")


def expectation_failed(pick: dict, expected: str | None) -> bool:
    if expected is None:
        return False

    actual = pick.get("result")
    if expected == "open":
        matches = actual is None
    else:
        matches = actual == expected

    if matches:
        return False

    got = "open" if actual is None else actual
    print(f"FAIL: expected {expected} got {got}")
    return True


def main() -> int:
    args = build_parser().parse_args()
    tracker = load_tracker()

    pick = {
        "id": args.id,
        "sport": args.sport,
        "model": "v1-trends",
        "bet": args.bet,
        "line": args.line,
        "units": args.units,
        "line_num": args.line_num,
        "result": None,
        "date": args.date,
    }

    with patch.object(tracker, "load_picks", return_value=[pick]), patch.object(
        tracker, "save_picks", return_value=None
    ):
        try:
            tracker.cmd_auto_resolve(None)
        except SystemExit as exc:
            if exc.code not in (0, None):
                raise

    report_pick(pick)

    if tracker.classify_bet(pick) == "prop" and "game_margin" in pick:
        print("FAIL: prop was mis-scored as a Game-Line Bet")
        return 2

    if expectation_failed(pick, args.expect):
        return 1

    print("VERIFY OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
