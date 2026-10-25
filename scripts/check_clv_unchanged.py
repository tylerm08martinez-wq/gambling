#!/usr/bin/env python3
"""Prove the ADR 0011 engine leaves realized CLV unchanged (#106). Read-only.

For every pick with a measured de-vigged CLV (`clv_devig` set and `closing_line`
parsing as American odds, as tracker.is_measured_clv defines it), recompute
`clv_devig` with the new value_engine and diff it against the stored value.

picks.json stores only the bet side of the close, not the other side, so the other
side is reconstructed: it is the price that makes the BASELINE engine (the
pre-ADR-0011 value_engine, read from git) reproduce the stored value exactly. The new
engine is then run on that same two-way close. So the diff isolates one thing, the
change of engine: a prop must come out identical, and a moneyline, spread or total
may differ only where its de-vig method changed (moneyline: multiplicative -> power).

The market label is the one the backfill path passes: "prop" for player props
(clv_fetch / close_capture always pass "prop"), else the pick's `bet_type`, else
"moneyline" (clv_backfill.backfill_pick's default).

Never writes picks.json. Exit status 1 if any prop differs or cannot be recomputed.

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
BASELINE_REV = "4b6a309"   # main before #106: ADR 0011 merged, engine not yet changed


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


def market_label(pick, tracker):
    if tracker.classify_bet(pick) == "prop":
        return "prop"
    return pick.get("bet_type") or "moneyline"


def _fair_side(engine, label, p_side, p_other):
    """The engine's de-vigged fair probability on the bet side (probabilities in)."""
    if engine.devig_method(label) == "power":
        return engine.power_devig(p_side, p_other)[0]
    return engine.multiplicative_devig(p_side, p_other)[0]


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


def check(picks, base, new, tracker, cb):
    rows = []
    for pick in picks:
        if pick.get("clv_devig") is None or not tracker.is_measured_clv(pick, "devig"):
            continue
        stored = float(pick["clv_devig"])
        label = market_label(pick, tracker)
        row = {"id": pick["id"], "label": label, "stored": stored, "new": None,
               "kind": new.market_kind(label), "old_method": base.devig_method(label),
               "new_method": new.devig_method(label), "note": ""}
        try:
            entry_p = base.american_to_prob(cb._entry_odds(pick.get("line")))
            p_side = base.american_to_prob(tracker.parse_american(pick["closing_line"]))
        except (ValueError, TypeError) as exc:
            row["note"] = f"entry/close unparseable: {exc}"
            rows.append(row)
            continue
        fair_old = entry_p * (1.0 + stored / 100.0)
        p_other = reconstruct_other_side(row["old_method"], p_side, fair_old)
        if p_other is None:
            row["note"] = ("stored value is not reproducible from this close under the "
                           "baseline engine (legacy value, ADR 0008)")
            rows.append(row)
            continue
        old_val = (_fair_side(base, label, p_side, p_other) / entry_p - 1.0) * 100.0
        new_val = (_fair_side(new, label, p_side, p_other) / entry_p - 1.0) * 100.0
        row["baseline"] = round(old_val, 2)
        row["new"] = round(new_val, 2)
        row["implied_other_close"] = round(p_other, 4)
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
    cb = _load("clv_backfill_ro", SKILL / "clv_backfill.py")
    base = load_baseline_engine(args.baseline)

    with open(args.picks) as f:
        picks = json.load(f)
    rows = check(picks, base, new, tracker, cb)

    same = [r for r in rows if r["new"] is not None and r["new"] == r["stored"]]
    diff = [r for r in rows if r["new"] is not None and r["new"] != r["stored"]]
    unrec = [r for r in rows if r["new"] is None]
    print(f"measured de-vigged picks: {len(rows)}  (baseline engine {args.baseline})")
    print(f"  unchanged: {len(same)}   changed: {len(diff)}   not recomputable: {len(unrec)}")
    by_kind = {}
    for r in rows:
        by_kind.setdefault(r["kind"], [0, 0, 0])
        by_kind[r["kind"]][0 if r in same else 1 if r in diff else 2] += 1
    for kind, (s, d, u) in sorted(by_kind.items()):
        print(f"  {kind:9s} unchanged {s:3d}  changed {d:3d}  not recomputable {u:3d}")
    for r in diff:
        print(f"  CHANGED  {r['id']}  [{r['kind']}, {r['old_method']} -> {r['new_method']}] "
              f"stored {r['stored']:+.2f}  new {r['new']:+.2f}")
    for r in unrec:
        print(f"  SKIPPED  {r['id']}  [{r['kind']}] stored {r['stored']:+.2f}: {r['note']}")
    bad = [r for r in diff + unrec if r["kind"] == "prop"]
    if bad:
        print(f"FAIL: {len(bad)} prop pick(s) changed or could not be recomputed")
        return 1
    print("OK: every prop's realized CLV is unchanged")
    return 0


if __name__ == "__main__":
    sys.exit(main())
