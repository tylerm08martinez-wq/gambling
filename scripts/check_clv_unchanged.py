#!/usr/bin/env python3
"""Prove the ADR 0011 engine leaves realized CLV unchanged (#106). Read-only.

For every pick with a measured de-vigged CLV (`clv_devig` set and `closing_line`
parsing as American odds, as tracker.is_measured_clv defines it), recompute
`clv_devig` through the REAL backfill path, `clv_backfill.realized_clv`, once with
the baseline value_engine (pre-ADR-0011, read from git) and once with the new one, on
the same two-way close, and diff both against the stored value.

picks.json stores only the bet side of the close, not the other side, so the other
side is reconstructed: the price that makes the baseline engine's de-vig reproduce the
stored value, rounded to whole American odds (the form a real close takes). Both
engines then see exactly that close through `realized_clv`. So:

  * `baseline - stored` is the reconstruction residual (whole-odds rounding only);
  * `new - baseline` is the effect of the engine change, and must be exactly 0 for
    every prop. A moneyline may differ (multiplicative -> power); it is listed.

The market label is the one the backfill path passes: "prop" for player props
(clv_fetch / close_capture always pass "prop"), else the pick's `bet_type`, else
"moneyline" (clv_backfill.backfill_pick's default).

Never writes picks.json. Exit status 1 if any prop changes or cannot be recomputed.

    python3 scripts/check_clv_unchanged.py [--picks PATH] [--baseline REV]
"""

import argparse
import importlib.util
import json
import math
import subprocess
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / ".agents" / "skills" / "bet-tracker"
ENGINE_PATH = ".agents/skills/bet-tracker/value_engine.py"
# main before #106 (ADR 0011 merged, engine not yet changed). Pinned rather than
# `main` so the check still means something after this branch merges.
BASELINE_REV = "4b6a309"
RESIDUAL_TOL = 0.05   # max |baseline - stored| from rounding the rebuilt side to whole odds


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def load_baseline_engine(rev):
    src = subprocess.run(["git", "-C", str(ROOT), "show", f"{rev}:{ENGINE_PATH}"],
                         check=True, capture_output=True, text=True).stdout
    mod = types.ModuleType("value_engine_baseline")
    exec(compile(src, f"{rev}:{ENGINE_PATH}", "exec"), mod.__dict__)
    return mod


def backfill_with(engine, name):
    """A private copy of clv_backfill whose `ve` is `engine` (the real realized_clv)."""
    mod = _load(name, SKILL / "clv_backfill.py")
    mod.ve = engine
    return mod


def market_label(pick, tracker):
    if tracker.classify_bet(pick) == "prop":
        return "prop"
    return pick.get("bet_type") or "moneyline"


def reconstruct_other_side(method, p_side, fair_side):
    """The other side's implied probability that makes `method` give `fair_side`."""
    if not (0.0 < fair_side < 1.0):
        return None
    if method == "power":
        if fair_side == p_side:
            return None
        k = math.log(fair_side) / math.log(p_side)
        p_other = (1.0 - fair_side) ** (1.0 / k)
    else:
        p_other = p_side / fair_side - p_side
    return p_other if 0.0 < p_other < 1.0 else None


def prob_to_american(p):
    odds = -100.0 * p / (1.0 - p) if p >= 0.5 else 100.0 * (1.0 - p) / p
    odds = int(round(odds))
    if -100 < odds < 100:            # whole American odds are never inside (-100, 100)
        odds = 100 if odds >= 0 else -100
    return odds


def check(picks, base, new, tracker, cb_old, cb_new):
    rows = []
    for pick in picks:
        if pick.get("clv_devig") is None or not tracker.is_measured_clv(pick, "devig"):
            continue
        stored = float(pick["clv_devig"])
        label = market_label(pick, tracker)
        close_side = tracker.parse_american(pick["closing_line"])
        row = {"id": pick["id"], "label": label, "stored": stored, "new": None,
               "kind": new.market_kind(label), "old_method": base.devig_method(label),
               "new_method": new.devig_method(label), "note": ""}
        try:
            entry_p = base.american_to_prob(cb_old._entry_odds(pick.get("line")))
            p_side = base.american_to_prob(close_side)
        except (ValueError, TypeError) as exc:
            row["note"] = f"entry/close unparseable: {exc}"
            rows.append(row)
            continue
        p_other = reconstruct_other_side(row["old_method"], p_side, entry_p * (1.0 + stored / 100.0))
        if p_other is None:
            row["note"] = ("stored value is not reproducible from this close under the "
                           "baseline engine (legacy value, ADR 0008)")
            rows.append(row)
            continue
        close = {"bet": close_side, "other": prob_to_american(p_other)}
        old_val = cb_old.realized_clv(close, "bet", pick.get("line"), label)
        new_val = cb_new.realized_clv(close, "bet", pick.get("line"), label)
        if old_val is None or new_val is None:
            row["note"] = f"realized_clv returned None (old {old_val}, new {new_val})"
            rows.append(row)
            continue
        row.update(close=close, baseline=old_val, new=new_val,
                   residual=old_val - stored, engine_delta=new_val - old_val)
        if abs(row["residual"]) > RESIDUAL_TOL:
            row["note"] = f"reconstruction residual {row['residual']:+.3f} exceeds {RESIDUAL_TOL}"
        rows.append(row)
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--picks", default=str(SKILL / "picks.json"))
    ap.add_argument("--baseline", default=BASELINE_REV)
    args = ap.parse_args(argv)

    sys.path.insert(0, str(SKILL))
    new = _load("value_engine", SKILL / "value_engine.py")
    sys.modules["value_engine"] = new
    tracker = _load("tracker_ro", SKILL / "tracker.py")
    base = load_baseline_engine(args.baseline)
    cb_old = backfill_with(base, "clv_backfill_baseline")
    cb_new = backfill_with(new, "clv_backfill_new")

    with open(args.picks) as f:
        picks = json.load(f)
    rows = check(picks, base, new, tracker, cb_old, cb_new)

    done = [r for r in rows if r["new"] is not None and not r["note"]]
    same = [r for r in done if r["engine_delta"] == 0.0]
    diff = [r for r in done if r["engine_delta"] != 0.0]
    unrec = [r for r in rows if r not in done]
    print(f"measured de-vigged picks: {len(rows)}  (baseline engine {args.baseline}, "
          f"via clv_backfill.realized_clv)")
    print(f"  engine change 0: {len(same)}   changed: {len(diff)}   not recomputable: {len(unrec)}")
    if done:
        worst = max(done, key=lambda r: abs(r["residual"]))
        print(f"  reconstruction residual |baseline - stored|: max {abs(worst['residual']):.4f} "
              f"({worst['id']}); rounded to 2dp, baseline == stored for "
              f"{sum(round(r['baseline'], 2) == r['stored'] for r in done)}/{len(done)}")
        print(f"  new == stored at 2dp for "
              f"{sum(round(r['new'], 2) == r['stored'] for r in done)}/{len(done)}")
    by_kind = {}
    for r in rows:
        by_kind.setdefault(r["kind"], [0, 0, 0])
        by_kind[r["kind"]][0 if r in same else 1 if r in diff else 2] += 1
    for kind, (s, d, u) in sorted(by_kind.items()):
        print(f"  {kind:9s} unchanged {s:3d}  changed {d:3d}  not recomputable {u:3d}")
    for r in diff:
        print(f"  CHANGED  {r['id']}  [{r['kind']}, {r['old_method']} -> {r['new_method']}] "
              f"close {r['close']}  stored {r['stored']:+.2f}  baseline {r['baseline']:+.2f}  "
              f"new {r['new']:+.2f}")
    for r in unrec:
        print(f"  SKIPPED  {r['id']}  [{r['kind']}] stored {r['stored']:+.2f}: {r['note']}")
    bad = [r for r in diff + unrec if r["kind"] == "prop"]
    if bad:
        print(f"FAIL: {len(bad)} prop pick(s) changed or could not be recomputed")
        return 1
    print("OK: every prop's realized CLV is unchanged through clv_backfill.realized_clv")
    return 0


if __name__ == "__main__":
    sys.exit(main())
