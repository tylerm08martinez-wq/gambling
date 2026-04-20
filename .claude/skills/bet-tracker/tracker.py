#!/usr/bin/env python3
"""
Bet Tracker CLI
Usage:
  tracker.py stats
  tracker.py open
  tracker.py log --model <v1-trends|v2-sharp> --sport <sport> --bet <bet> --line <line> --units <1-3> [--score <float>] [--edge <str>]
  tracker.py resolve <id> <win|loss|push> --final-score <str> --game-margin <int> --line-num <float> [--prop-result <str>]
"""

import json
import sys
import re
import argparse
import math
from datetime import datetime
from pathlib import Path

# Force UTF-8 output on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BASE_DIR = Path(__file__).parent
PICKS_FILE = BASE_DIR / "picks.json"


# ── I/O ──────────────────────────────────────────────────────────────────────

def load_picks():
    if not PICKS_FILE.exists():
        return []
    with open(PICKS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_picks(picks):
    tmp = PICKS_FILE.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(picks, f, indent=2)
    tmp.replace(PICKS_FILE)


# ── Math ─────────────────────────────────────────────────────────────────────

def calc_units_won_lost(line_str: str, units: int, result: str) -> float:
    if result == "push":
        return 0.0
    if result == "loss":
        return float(-units)
    line = int(str(line_str).replace("+", ""))
    if line < 0:
        return round((100 / abs(line)) * units, 3)
    else:
        return round((line / 100) * units, 3)

def needed_to_cover(line_num: float) -> int:
    """Minimum whole-number margin needed to cover a spread/RL."""
    return math.ceil(abs(line_num))


# ── Formatting ────────────────────────────────────────────────────────────────

def fmt_net(n: float) -> str:
    return f"+{n:.3f}u" if n >= 0 else f"{n:.3f}u"

def fmt_roi(r: float) -> str:
    return f"+{r:.1f}%" if r >= 0 else f"{r:.1f}%"

def fmt_score(s) -> str:
    return f"{s:.1f}/10" if s is not None else "—"

def fmt_record(s: dict) -> str:
    return f"{s['wins']}-{s['losses']}-{s['pushes']}"

RESULT_ICON = {"win": "✅ Win", "loss": "❌ Loss", "push": "➡️ Push", None: "⏳ Open"}


# ── Context line (two-line Recent Picks format) ───────────────────────────────

def build_context(pick: dict) -> str:
    result = pick.get("result")
    final_score = pick.get("final_score") or ""
    game_margin = pick.get("game_margin")   # actual whole-number game margin (positive = we won)
    line_num = pick.get("line_num")         # the spread/RL number (e.g. 1.5 for -1.5 RL)
    prop_result = pick.get("prop_result")   # e.g. "3/9 from three"
    prop_margin = pick.get("prop_margin")   # actual - threshold (e.g. -1 if needed 4, got 3)
    bet = pick.get("bet", "").lower()

    if result is None:
        return "⏳ Pending"

    score_prefix = f"{final_score} — " if final_score else ""

    # ── Player prop ──
    if prop_result:
        m = prop_margin if prop_margin is not None else 0
        if result == "win":
            barely = " (barely!)" if m == 1 else ""
            return f"Went {prop_result} — hit with {int(m)} to spare ✅{barely}"
        else:
            near = " 🔥 Near miss!" if abs(m) <= 1 else ""
            return f"Went {prop_result} — {int(abs(m))} short{near}"

    # ── Spread / Run Line ──
    is_spread = line_num is not None and abs(line_num) != 0 and "ml" not in bet
    if is_spread:
        needed = needed_to_cover(line_num)
        if result == "win":
            won_by = game_margin if game_margin is not None else "?"
            return f"{score_prefix}needed to win by {needed}+, won by {won_by} ✅"
        else:
            lost_by = abs(game_margin) if game_margin is not None else "?"
            near = " 🔥 Near miss!" if game_margin is not None and game_margin >= -(needed + 2) else ""
            return f"{score_prefix}needed to win by {needed}+, lost by {lost_by}{near}"

    # ── Moneyline ──
    if result == "win":
        won_by = game_margin if game_margin is not None else "?"
        return f"{score_prefix}won outright by {won_by} ✅"
    else:
        lost_by = abs(game_margin) if game_margin is not None else "?"
        near = " 🔥 Near miss!" if game_margin is not None and game_margin >= -1 else ""
        return f"{score_prefix}lost by {lost_by}{near}"


def build_cover_check(pick: dict) -> str:
    result = pick.get("result")
    game_margin = pick.get("game_margin")
    line_num = pick.get("line_num")
    bet = pick.get("bet", "").lower()
    prop_result = pick.get("prop_result")

    if prop_result:
        if result == "win":
            return f"Hit — {pick['prop_result']}"
        return f"Miss — {pick['prop_result']}"

    is_spread = line_num is not None and abs(line_num) != 0 and "ml" not in bet
    if is_spread:
        needed = needed_to_cover(line_num)
        if result == "win":
            won_by = game_margin if game_margin is not None else "?"
            return f"Needed {needed}+, won by {won_by}"
        else:
            lost_by = abs(game_margin) if game_margin is not None else "?"
            return f"Needed {needed}+, lost by {lost_by}"

    if result == "win":
        won_by = game_margin if game_margin is not None else "?"
        return f"ML — won outright by {won_by}"
    lost_by = abs(game_margin) if game_margin is not None else "?"
    return f"ML — lost by {lost_by}"


def extract_matchup(bet: str) -> str:
    """Pull 'Team A vs Team B' from bet description."""
    if " vs " in bet.lower():
        idx = bet.lower().index(" vs ")
        left = re.split(r"[\-\+]?\d", bet[:idx])[0].strip()
        right = bet[idx + 4:].strip()
        return f"{left} vs {right}"
    return bet[:38]


# ── Stats calculation ─────────────────────────────────────────────────────────

def model_stats(picks: list) -> dict:
    settled = [p for p in picks if p.get("result") is not None]
    wins = sum(1 for p in settled if p["result"] == "win")
    losses = sum(1 for p in settled if p["result"] == "loss")
    pushes = sum(1 for p in settled if p["result"] == "push")
    units_wagered = sum(p["units"] for p in settled)
    units_net = sum(p.get("units_won_lost") or 0 for p in settled)
    win_pct = (wins / (wins + losses) * 100) if (wins + losses) > 0 else 0.0
    roi = (units_net / units_wagered * 100) if units_wagered > 0 else 0.0
    scores = [p["score"] for p in picks if p.get("score") is not None]
    avg_score = sum(scores) / len(scores) if scores else None
    open_count = sum(1 for p in picks if p.get("result") is None)
    return dict(
        total=len(picks), settled=len(settled),
        wins=wins, losses=losses, pushes=pushes,
        units_wagered=units_wagered, units_net=units_net,
        win_pct=win_pct, roi=roi, avg_score=avg_score, open=open_count,
    )


# ── Commands ──────────────────────────────────────────────────────────────────

def cmd_stats(_args):
    picks = load_picks()
    today = datetime.now().strftime("%Y-%m-%d")

    v1_picks = [p for p in picks if p["model"] == "v1-trends"]
    v2_picks = [p for p in picks if p["model"] == "v2-sharp"]

    v1 = model_stats(v1_picks)
    v2 = model_stats(v2_picks)
    cb = model_stats(picks)

    # Leading model
    diff = v1["units_net"] - v2["units_net"]
    if diff > 0:
        leader = f"V1-Trends by {diff:.3f}u"
    elif diff < 0:
        leader = f"V2-Sharp by {abs(diff):.3f}u"
    else:
        leader = "Tied"

    def col(v1_val, v2_val, cb_val, fmt=str):
        return f"│ {fmt(v1_val):<12} │ {fmt(v2_val):<12} │ {fmt(cb_val):<12} │"

    print(f"""
╔══════════════════════════════════════════════════════╗
║           BETTING MODEL PERFORMANCE TRACKER           ║
╚══════════════════════════════════════════════════════╝

📅 Last updated: {today}   |   📊 Total picks tracked: {len(picks)}

┌─────────────────┬──────────────┬──────────────┬──────────────┐
│ Metric          │ V1-Trends    │ V2-Sharp     │ Combined     │
├─────────────────┼──────────────┼──────────────┼──────────────┤
│ Total picks     {col(v1['total'], v2['total'], cb['total'])}
│ Settled         {col(v1['settled'], v2['settled'], cb['settled'])}
│ Record (W-L-P)  {col(fmt_record(v1), fmt_record(v2), fmt_record(cb))}
│ Win %           {col(f"{v1['win_pct']:.1f}%", f"{v2['win_pct']:.1f}%", f"{cb['win_pct']:.1f}%")}
│ Units wagered   {col(v1['units_wagered'], v2['units_wagered'], cb['units_wagered'])}
│ Units net       {col(fmt_net(v1['units_net']), fmt_net(v2['units_net']), fmt_net(cb['units_net']))}
│ ROI             {col(fmt_roi(v1['roi']), fmt_roi(v2['roi']), fmt_roi(cb['roi']))}
│ Avg pick score  {col(fmt_score(v1['avg_score']), fmt_score(v2['avg_score']), '—')}
│ Open (pending)  {col(v1['open'], v2['open'], cb['open'])}
└─────────────────┴──────────────┴──────────────┴──────────────┘

🏆 LEADING MODEL: {leader}

Breakeven win rate (−110): 52.4%""")

    # ── Recent Picks ──
    recent = sorted(picks, key=lambda p: p["date"], reverse=True)[:10]
    divider = "─" * 86
    print(f"\nRecent Picks\n{divider}")
    print(f"{'Date':<12}{'Model':<11}{'Bet':<35}{'Line':<8}{'Units':<7}{'Result':<12}{'P/L'}")
    print(f"{'':>12}Context")
    print(divider)
    for p in recent:
        model_label = "V1-Trends" if p["model"] == "v1-trends" else "V2-Sharp"
        result_str = RESULT_ICON.get(p.get("result"), "—")
        pl_str = fmt_net(p.get("units_won_lost") or 0) if p.get("result") else "—"
        bet_display = p["bet"][:34]
        print(f"{p['date']:<12}{model_label:<11}{bet_display:<35}{str(p['line']):<8}{str(p['units'])+'u':<7}{result_str:<12}{pl_str}")
        ctx = build_context(p)
        print(f"{'':>12}{ctx}")
        print()
    print(divider)

    # ── Open Picks ──
    open_picks = [p for p in picks if p.get("result") is None]
    if open_picks:
        print(f"\n⏳ Open Picks — Need Results\n{'─'*72}")
        print(f"{'ID':<35}{'Model':<12}{'Bet':<25}{'Units'}")
        print("─" * 72)
        for p in open_picks:
            model_label = "V1-Trends" if p["model"] == "v1-trends" else "V2-Sharp"
            print(f"{p['id']:<35}{model_label:<12}{p['bet'][:24]:<25}{p['units']}u")
        print()

    # ── Game Scores ──
    scored = sorted(
        [p for p in picks if p.get("result") and p.get("final_score")],
        key=lambda p: p["date"], reverse=True
    )
    if scored:
        print(f"\nGame Scores\n{'─'*82}")
        print(f"{'Date':<12}{'Matchup':<38}{'Final Score':<18}Cover Check")
        print("─" * 82)
        for p in scored:
            matchup = extract_matchup(p["bet"])[:37]
            cover = build_cover_check(p)
            icon = "✅" if p["result"] == "win" else "❌" if p["result"] == "loss" else "➡️"
            print(f"{p['date']:<12}{matchup:<38}{p['final_score']:<18}{icon} {cover}")
        print()

    # ── Edge Type Breakdown ──
    settled_all = [p for p in picks if p.get("result")]
    if settled_all:
        edges: dict = {}
        for p in settled_all:
            raw_edge = p.get("primary_edge") or "Unknown"
            # Normalize: take first word or token before " —"
            edge_key = raw_edge.split("—")[0].split("-")[0].strip().split()[0].upper()
            if edge_key not in edges:
                edges[edge_key] = {"picks": 0, "wins": 0, "wagered": 0.0, "net": 0.0}
            e = edges[edge_key]
            e["picks"] += 1
            e["wagered"] += p["units"]
            e["net"] += p.get("units_won_lost") or 0
            if p["result"] == "win":
                e["wins"] += 1

        print(f"\nEdge Type Performance\n{'─'*58}")
        print(f"{'Edge':<18}{'Picks':<8}{'W%':<9}{'Net':<10}{'ROI'}")
        print("─" * 58)
        for edge, e in sorted(edges.items(), key=lambda x: -x[1]["net"]):
            wp = e["wins"] / e["picks"] * 100
            roi = e["net"] / e["wagered"] * 100 if e["wagered"] else 0
            wp_str = f"{wp:.1f}%"
            print(f"{edge:<18}{e['picks']:<8}{wp_str:<9}{fmt_net(e['net']):<10}{fmt_roi(roi)}")
        print()

    # ── Sport Breakdown ──
    if settled_all:
        sports: dict = {}
        for p in settled_all:
            s = p.get("sport", "Unknown").upper()
            if s not in sports:
                sports[s] = {"picks": 0, "wins": 0, "wagered": 0.0, "net": 0.0,
                             "v1": {"picks": 0, "wins": 0, "net": 0.0},
                             "v2": {"picks": 0, "wins": 0, "net": 0.0}}
            sp = sports[s]
            sp["picks"] += 1
            sp["wagered"] += p["units"]
            net = p.get("units_won_lost") or 0
            sp["net"] += net
            if p["result"] == "win":
                sp["wins"] += 1
            model_key = "v1" if p["model"] == "v1-trends" else "v2"
            sp[model_key]["picks"] += 1
            sp[model_key]["net"] += net
            if p["result"] == "win":
                sp[model_key]["wins"] += 1

        print(f"\nBy Sport\n{'─'*72}")
        print(f"{'Sport':<8}{'Picks':<7}{'W%':<8}{'Net':<10}{'ROI':<10}{'V1 ROI':<12}{'V2 ROI'}")
        print("─" * 72)
        for sport, s in sorted(sports.items(), key=lambda x: -x[1]["net"]):
            wp = s["wins"] / s["picks"] * 100 if s["picks"] else 0
            roi = s["net"] / s["wagered"] * 100 if s["wagered"] else 0
            v1_roi = (s["v1"]["net"] / s["v1"]["picks"] * 100) if s["v1"]["picks"] else None
            v2_roi = (s["v2"]["net"] / s["v2"]["picks"] * 100) if s["v2"]["picks"] else None
            v1_str = fmt_roi(v1_roi) if v1_roi is not None else "—"
            v2_str = fmt_roi(v2_roi) if v2_roi is not None else "—"
            wp_str = f"{wp:.1f}%"
            print(f"{sport:<8}{s['picks']:<7}{wp_str:<8}{fmt_net(s['net']):<10}{fmt_roi(roi):<10}{v1_str:<12}{v2_str}")
        print()

    # ── Score Calibration ──
    scored_settled = [p for p in settled_all if p.get("score") is not None] if settled_all else []
    if scored_settled:
        buckets = {"9-10": [], "7-8": [], "5-6": []}
        for p in scored_settled:
            sc = p["score"]
            if sc >= 9:
                buckets["9-10"].append(p)
            elif sc >= 7:
                buckets["7-8"].append(p)
            elif sc >= 5:
                buckets["5-6"].append(p)

        print(f"\nScore Calibration\n{'─'*62}")
        print(f"{'Score':<10}{'Picks':<8}{'W%':<10}{'Net':<12}{'Breakeven'}")
        print("─" * 62)
        for bucket, bpicks in buckets.items():
            if not bpicks:
                continue
            wins = sum(1 for p in bpicks if p["result"] == "win")
            losses = sum(1 for p in bpicks if p["result"] == "loss")
            net = sum(p.get("units_won_lost") or 0 for p in bpicks)
            wp = wins / (wins + losses) * 100 if (wins + losses) > 0 else 0
            # Flag if win% is below breakeven (52.4%) for picks that should be high confidence
            flag = " ⚠️ Below breakeven" if wp < 52.4 and (wins + losses) >= 3 else ""
            wp_str = f"{wp:.1f}%"
            print(f"{bucket:<10}{len(bpicks):<8}{wp_str:<10}{fmt_net(net):<12}52.4%{flag}")
        print()
        # Calibration verdict
        high = buckets["9-10"]
        low = buckets["5-6"]
        if len(high) >= 3 and len(low) >= 3:
            high_wp = sum(1 for p in high if p["result"] == "win") / len(high) * 100
            low_wp = sum(1 for p in low if p["result"] == "win") / len(low) * 100
            if high_wp > low_wp:
                print(f"  ✅ Scores are predictive — high-scored picks winning at {high_wp:.0f}% vs {low_wp:.0f}% for low-scored")
            else:
                print(f"  ⚠️  Scores may need recalibration — high-scored picks at {high_wp:.0f}% vs {low_wp:.0f}% for low-scored")
        print()


def cmd_open(_args):
    """Print open picks as JSON for the skill to process."""
    picks = load_picks()
    open_picks = [p for p in picks if p.get("result") is None]
    if not open_picks:
        print("[]")
        return
    output = [
        {"id": p["id"], "date": p["date"], "bet": p["bet"],
         "sport": p["sport"], "line": p["line"], "units": p["units"]}
        for p in open_picks
    ]
    print(json.dumps(output, indent=2))


def cmd_log(args):
    picks = load_picks()
    date = datetime.now().strftime("%Y-%m-%d")
    sport_abbrev = re.sub(r"[^a-z]", "", args.sport.lower())[:3]
    team_raw = re.split(r"[\s\-\+]", args.bet)[0].lower()
    team_abbrev = re.sub(r"[^a-z]", "", team_raw)[:6]
    bet_lower = args.bet.lower()
    if "ml" in bet_lower:
        btype = "ml"
    elif "rl" in bet_lower or "run line" in bet_lower:
        btype = "rl"
    elif "over" in bet_lower or "under" in bet_lower:
        btype = "total"
    else:
        btype = "spread"
    pick_id = f"{date.replace('-','')}-{sport_abbrev}-{team_abbrev}-{btype}"

    pick = {
        "id": pick_id,
        "date": date,
        "model": args.model,
        "sport": args.sport,
        "bet": args.bet,
        "line": args.line,
        "units": args.units,
        "score": args.score,
        "primary_edge": args.edge or "",
        "result": None,
        "units_won_lost": None,
        "final_score": None,
        "game_margin": None,
        "line_num": args.line_num,
        "prop_result": None,
        "prop_margin": None,
    }
    picks.append(pick)
    save_picks(picks)
    print(f"✅ Logged: {pick_id}")
    print(json.dumps(pick, indent=2))


def cmd_resolve(args):
    picks = load_picks()
    pick = next((p for p in picks if p["id"] == args.id), None)
    if not pick:
        print(f"❌ Pick not found: {args.id}", file=sys.stderr)
        sys.exit(1)

    pick["result"] = args.outcome
    pick["units_won_lost"] = calc_units_won_lost(pick["line"], pick["units"], args.outcome)
    if args.final_score:
        pick["final_score"] = args.final_score
    if args.game_margin is not None:
        pick["game_margin"] = args.game_margin
    if args.line_num is not None:
        pick["line_num"] = args.line_num
    if args.prop_result:
        pick["prop_result"] = args.prop_result
    if args.prop_margin is not None:
        pick["prop_margin"] = args.prop_margin

    save_picks(picks)
    sign = "+" if pick["units_won_lost"] >= 0 else ""
    print(f"✅ {args.id}: {args.outcome.upper()} ({sign}{pick['units_won_lost']}u)")


# ── CLI wiring ────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Bet Tracker CLI")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("stats", help="Show full performance dashboard")
    sub.add_parser("open", help="Print open picks as JSON")

    log_p = sub.add_parser("log", help="Log a new pick")
    log_p.add_argument("--model", required=True, choices=["v1-trends", "v2-sharp"])
    log_p.add_argument("--sport", required=True)
    log_p.add_argument("--bet", required=True, help="Full bet description incl. opponent")
    log_p.add_argument("--line", required=True, help="Odds (e.g. -110, +146)")
    log_p.add_argument("--units", type=int, required=True, choices=[1, 2, 3])
    log_p.add_argument("--score", type=float, default=None)
    log_p.add_argument("--edge", default="", help="Primary edge type")
    log_p.add_argument("--line-num", type=float, default=None,
                       help="Spread/RL number (e.g. 1.5 for -1.5 RL, 0 for ML)")

    res_p = sub.add_parser("resolve", help="Record a result for an open pick")
    res_p.add_argument("id", help="Pick ID")
    res_p.add_argument("outcome", choices=["win", "loss", "push"])
    res_p.add_argument("--final-score", default="", help="e.g. 'ARI 6, TOR 3'")
    res_p.add_argument("--game-margin", type=int, default=None,
                       help="Actual game margin (positive = our team won by X)")
    res_p.add_argument("--line-num", type=float, default=None,
                       help="Spread/RL number for cover check display")
    res_p.add_argument("--prop-result", default="", help="e.g. '3/9 from three'")
    res_p.add_argument("--prop-margin", type=int, default=None,
                       help="actual - threshold (negative = short)")

    args = parser.parse_args()

    if args.command == "stats" or args.command is None:
        cmd_stats(args)
    elif args.command == "open":
        cmd_open(args)
    elif args.command == "log":
        cmd_log(args)
    elif args.command == "resolve":
        cmd_resolve(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
