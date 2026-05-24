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
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Optional

# Force UTF-8 output on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BASE_DIR = Path(__file__).parent
PICKS_FILE = BASE_DIR / "picks.json"
REJECTED_CANDIDATES_FILE = BASE_DIR / "rejected-candidates.json"


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

def load_json_list(path: Path) -> list:
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError(f"{path} must contain a JSON list")
    return data

def save_json_list(path: Path, rows: list):
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=2)
    tmp.replace(path)


# ── Validation ───────────────────────────────────────────────────────────────

def normalize_key(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    normalized = re.sub(r"[^a-z0-9]+", "_", str(value).strip().lower()).strip("_")
    return normalized or None

def parse_source_evidence(raw: str) -> list:
    if not raw:
        return []
    try:
        evidence = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"source evidence must be valid JSON: {e}") from e
    if not isinstance(evidence, list):
        raise ValueError("source evidence must be a JSON list")
    for idx, item in enumerate(evidence, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"source evidence item {idx} must be an object")
    return evidence

def validate_primary_edge(primary_edge_type: Optional[str], source_evidence: list) -> tuple[bool, list[str]]:
    edge_type = normalize_key(primary_edge_type)
    if edge_type != "hard_rlm":
        return True, []

    by_category: dict[str, list[dict]] = {}
    for item in source_evidence:
        category = normalize_key(item.get("category"))
        if category:
            by_category.setdefault(category, []).append(item)

    required = ["public_ticket_data", "line_movement_data"]
    failures = []
    for category in required:
        usable = [
            item for item in by_category.get(category, [])
            if normalize_key(item.get("status")) == "usable"
        ]
        if not usable:
            failures.append(f"missing usable {category}")

    return not failures, failures

def record_rejected_candidate(candidate: dict):
    rejected = load_json_list(REJECTED_CANDIDATES_FILE)
    rejected.append(candidate)
    save_json_list(REJECTED_CANDIDATES_FILE, rejected)


# ── Math ─────────────────────────────────────────────────────────────────────

def calc_units_won_lost(line_str: str, units: int, result: str) -> float:
    if result == "push":
        return 0.0
    if result == "loss":
        return float(-units)
    line = int(str(line_str).split("@")[0].strip().replace("+", ""))
    if line < 0:
        return round((100 / abs(line)) * units, 3)
    else:
        return round((line / 100) * units, 3)

def needed_to_cover(line_num: float) -> int:
    """Minimum whole-number margin needed to cover a spread/RL."""
    return math.ceil(abs(line_num))

def american_to_implied_prob(line_str: str) -> float:
    """Convert American odds (e.g. '+120', '-110', '+120 @ FanDuel') to implied probability (0–1)."""
    raw = str(line_str).split("@")[0].strip().replace("+", "")
    line = int(raw)
    if line < 0:
        return abs(line) / (abs(line) + 100)
    return 100 / (line + 100)

def calc_clv(bet_line: str, closing_line: str) -> float:
    """CLV in percentage points (closing_implied_prob - bet_implied_prob) * 100.
    Positive = you got a better price than the market settled at = good process."""
    return round((american_to_implied_prob(closing_line) - american_to_implied_prob(bet_line)) * 100, 2)


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


# ── MLB Stats API ─────────────────────────────────────────────────────────────

def extract_bet_team(bet: str) -> str:
    """Extract the team we're betting on from a bet description."""
    parts = re.split(r'\s+(?:ML\b|[+-]?\d+\.?\d*\s+RL\b|[+-]?\d+\.?\d*\s+Spread\b)', bet, maxsplit=1, flags=re.IGNORECASE)
    team = parts[0].strip()
    if not team:
        team = re.split(r'\s+vs\s+', bet, flags=re.IGNORECASE)[0].strip()
    return team


def fetch_mlb_result(date: str, team_name: str) -> Optional[dict]:
    """
    Query MLB Stats API for a final game result on `date` involving `team_name`.
    Returns a result dict or None if game not found / not yet final.
    """
    url = f"https://statsapi.mlb.com/api/v1/schedule?sportId=1&date={date}&hydrate=linescore"
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            data = json.loads(r.read())
    except Exception as e:
        print(f"⚠️  MLB API error: {e}", file=sys.stderr)
        return None

    team_lower = team_name.lower()
    for date_entry in data.get("dates", []):
        for game in date_entry.get("games", []):
            home = game["teams"]["home"]["team"]["name"]
            away = game["teams"]["away"]["team"]["name"]
            if team_lower not in home.lower() and team_lower not in away.lower():
                continue
            status = game.get("status", {}).get("detailedState", "")
            if "Final" not in status:
                return None  # game not yet final
            home_score = game["teams"]["home"].get("score", 0)
            away_score = game["teams"]["away"].get("score", 0)
            our_is_home = team_lower in home.lower()
            our_score = home_score if our_is_home else away_score
            opp_score = away_score if our_is_home else home_score
            margin = our_score - opp_score
            away_abbr = game["teams"]["away"]["team"].get("abbreviation", away[:3].upper())
            home_abbr = game["teams"]["home"]["team"].get("abbreviation", home[:3].upper())
            final_score = f"{away_abbr} {away_score}, {home_abbr} {home_score}"
            return {
                "home": home, "away": away,
                "our_score": our_score, "opp_score": opp_score,
                "margin": margin,
                "final_score": final_score,
                "status": status,
            }
    return None


# ── Commands ──────────────────────────────────────────────────────────────────

def roi_emoji(roi: float) -> str:
    if roi > 0: return "🟢"
    if roi < 0: return "🔴"
    return "🟡"

def divider() -> str:
    return "━" * 34


def cmd_stats(_args):
    picks = load_picks()
    today = datetime.now().strftime("%B %d, %Y")

    v1_picks = [p for p in picks if p["model"] == "v1-trends"]
    v2_picks = [p for p in picks if p["model"] == "v2-sharp"]

    v1 = model_stats(v1_picks)
    v2 = model_stats(v2_picks)
    cb = model_stats(picks)

    settled_all = [p for p in picks if p.get("result")]
    open_picks = [p for p in picks if p.get("result") is None]

    diff = v1["units_net"] - v2["units_net"]
    if diff > 0:
        leader = f"V1-Trends by {diff:.2f}u"
    elif diff < 0:
        leader = f"V2-Sharp by {abs(diff):.2f}u"
    else:
        leader = "Tied"

    print(f"\n📊 BETTING TRACKER — {today}")
    print(f"{len(picks)} picks tracked · {cb['settled']} settled · {cb['open']} open\n")
    print(divider())

    # ── Model cards ──
    for label, emoji, st in [("V1-TRENDS", "🎯", v1), ("V2-SHARP", "🔪", v2)]:
        avg = f"{st['avg_score']:.1f}/10" if st['avg_score'] is not None else "—"
        print(f"\n{emoji} {label}")
        print(f"Record: {fmt_record(st)} · Win %: {st['win_pct']:.1f}%")
        print(f"Net: {fmt_net(st['units_net'])} · ROI: {fmt_roi(st['roi'])} {roi_emoji(st['roi'])}")
        print(f"Avg score: {avg} · {st['open']} open")

    print(f"\n📈 COMBINED")
    print(f"Record: {fmt_record(cb)} · Win %: {cb['win_pct']:.1f}%")
    print(f"Net: {fmt_net(cb['units_net'])} · ROI: {fmt_roi(cb['roi'])} {roi_emoji(cb['roi'])}")
    print(f"Units wagered: {cb['units_wagered']}u")

    print(f"\n🏆 Leading: {leader}")
    if cb['settled'] < 20:
        print(f"⚠️  Need 20+ settled picks for statistical significance ({cb['settled']} so far)")
    print(f"Breakeven win rate at −110: 52.4%")

    # ── Recent Picks ──
    recent = sorted(picks, key=lambda p: p["date"], reverse=True)[:10]
    print(f"\n{divider()}\n")
    print("📋 RECENT PICKS\n")
    for p in recent:
        model_label = "V1" if p["model"] == "v1-trends" else "V2"
        result = p.get("result")
        icon = RESULT_ICON.get(result, "—").split()[0]
        date_short = p["date"][5:]  # MM-DD
        pl_str = fmt_net(p.get("units_won_lost") or 0) if result else "pending"
        bet_display = p["bet"][:38]
        print(f"{icon} {date_short} · {model_label} · {bet_display} · {p['line']} · {p['units']}u · {pl_str}")
        ctx = build_context(p)
        if ctx != "⏳ Pending":
            print(f"   {ctx}")
    print()

    # ── Open Tonight ──
    if open_picks:
        print(divider())
        print(f"\n⏳ OPEN / PENDING\n")
        for p in open_picks:
            model_label = "V1" if p["model"] == "v1-trends" else "V2"
            print(f"• {p['bet']} · {p['line']} · {p['units']}u  [{model_label}]")
        print()

    # ── Edge Breakdown ──
    if settled_all:
        edges: dict = {}
        for p in settled_all:
            raw_edge = p.get("primary_edge") or "Unknown"
            edge_key = raw_edge.split("—")[0].split("-")[0].strip().split()[0].upper()
            if edge_key not in edges:
                edges[edge_key] = {"picks": 0, "wins": 0, "wagered": 0.0, "net": 0.0}
            e = edges[edge_key]
            e["picks"] += 1
            e["wagered"] += p["units"]
            e["net"] += p.get("units_won_lost") or 0
            if p["result"] == "win":
                e["wins"] += 1

        print(divider())
        print(f"\n🔍 EDGE BREAKDOWN\n")
        for edge, e in sorted(edges.items(), key=lambda x: -x[1]["net"]):
            wp = e["wins"] / e["picks"] * 100
            roi = e["net"] / e["wagered"] * 100 if e["wagered"] else 0
            print(f"• {edge}: {e['picks']} picks · {wp:.0f}% W · {fmt_net(e['net'])} ({fmt_roi(roi)}) {roi_emoji(roi)}")
        print()

    # ── Sport Breakdown ──
    if settled_all:
        sports: dict = {}
        for p in settled_all:
            s = p.get("sport", "Unknown").upper()
            if s not in sports:
                sports[s] = {"picks": 0, "wins": 0, "wagered": 0.0, "net": 0.0}
            sp = sports[s]
            sp["picks"] += 1
            sp["wagered"] += p["units"]
            sp["net"] += p.get("units_won_lost") or 0
            if p["result"] == "win":
                sp["wins"] += 1

        print(divider())
        print(f"\n🏟️  BY SPORT\n")
        for sport, s in sorted(sports.items(), key=lambda x: -x[1]["net"]):
            wp = s["wins"] / s["picks"] * 100 if s["picks"] else 0
            roi = s["net"] / s["wagered"] * 100 if s["wagered"] else 0
            print(f"• {sport}: {s['picks']} picks · {wp:.0f}% W · {fmt_net(s['net'])} ({fmt_roi(roi)}) {roi_emoji(roi)}")
        print()

    # ── Score Calibration ──
    scored_settled = [p for p in settled_all if p.get("score") is not None] if settled_all else []
    if scored_settled:
        buckets = {"9-10": [], "7-8": [], "5-6": []}
        for p in scored_settled:
            sc = p["score"]
            if sc >= 9: buckets["9-10"].append(p)
            elif sc >= 7: buckets["7-8"].append(p)
            elif sc >= 5: buckets["5-6"].append(p)

        has_data = any(buckets[k] for k in buckets)
        if has_data:
            print(divider())
            print(f"\n🎯 SCORE CALIBRATION\n")
            for bucket, bpicks in buckets.items():
                if not bpicks:
                    continue
                wins = sum(1 for p in bpicks if p["result"] == "win")
                losses = sum(1 for p in bpicks if p["result"] == "loss")
                net = sum(p.get("units_won_lost") or 0 for p in bpicks)
                wp = wins / (wins + losses) * 100 if (wins + losses) > 0 else 0
                flag = " ⚠️" if wp < 52.4 and (wins + losses) >= 3 else ""
                print(f"• Score {bucket}: {len(bpicks)} picks · {wp:.0f}% W · {fmt_net(net)}{flag}")
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
    checked_at = datetime.now().isoformat(timespec="seconds")
    try:
        source_evidence = parse_source_evidence(args.source_evidence_json)
    except ValueError as e:
        print(f"❌ Validation input error: {e}", file=sys.stderr)
        sys.exit(2)

    primary_edge_type = normalize_key(args.primary_edge_type)
    validation_passed, validation_notes = validate_primary_edge(primary_edge_type, source_evidence)
    run_type = normalize_key(args.run_type) or "manual"
    if run_type not in {"manual", "scheduled"}:
        print("❌ --run-type must be manual or scheduled", file=sys.stderr)
        sys.exit(2)
    override_reason = (args.override_validation or "").strip()
    if run_type == "scheduled" and override_reason:
        print("❌ Scheduled runs cannot override validation", file=sys.stderr)
        sys.exit(2)
    if override_reason and not validation_notes:
        print("❌ --override-validation is only allowed when validation fails", file=sys.stderr)
        sys.exit(2)

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

    if validation_notes and not override_reason:
        rejected = {
            "id": pick_id,
            "date": date,
            "checked_at": checked_at,
            "run_type": run_type,
            "model": args.model,
            "sport": args.sport,
            "bet": args.bet,
            "line": args.line,
            "units": args.units,
            "score": args.score,
            "primary_edge": args.edge or "",
            "primary_edge_type": primary_edge_type,
            "source_evidence": source_evidence,
            "rejection_reason": "; ".join(validation_notes),
            "validation_status": "failed",
            "validation_notes": validation_notes,
        }
        record_rejected_candidate(rejected)
        print(f"❌ Rejected: {pick_id}", file=sys.stderr)
        print(f"Reason: {rejected['rejection_reason']}", file=sys.stderr)
        print(f"Recorded in: {REJECTED_CANDIDATES_FILE}", file=sys.stderr)
        sys.exit(1)

    validation_status = "not_required"
    if primary_edge_type:
        validation_status = "passed" if validation_passed else "overridden"
    if override_reason:
        validation_notes = [*validation_notes, f"override: {override_reason}"]

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
        "primary_edge_type": primary_edge_type,
        "source_evidence": source_evidence,
        "validation_status": validation_status,
        "validation_notes": validation_notes,
        "game_time": args.game_time or None,
        "result": None,
        "units_won_lost": None,
        "closing_line": None,
        "clv": None,
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


def cmd_auto_resolve(_args):
    """Automatically resolve open picks using official APIs. MLB ML and RL only."""
    picks = load_picks()
    open_picks = [p for p in picks if p.get("result") is None]

    if not open_picks:
        print("✅ No open picks to resolve.")
        return

    resolved = []
    skipped = []

    for p in open_picks:
        sport = p.get("sport", "").upper()
        bet = p.get("bet", "")
        date = p.get("date", datetime.now().strftime("%Y-%m-%d"))

        if sport != "MLB":
            skipped.append((p["id"], f"sport={sport} — only MLB supported"))
            continue

        team = extract_bet_team(bet)
        if not team:
            skipped.append((p["id"], "could not extract team name from bet"))
            continue

        result_data = fetch_mlb_result(date, team)
        if result_data is None:
            skipped.append((p["id"], f"game not found or not final for '{team}' on {date}"))
            continue

        margin = result_data["margin"]
        line_num = p.get("line_num")
        bet_lower = bet.lower()

        if "rl" in bet_lower or "run line" in bet_lower:
            if line_num is None:
                skipped.append((p["id"], "RL pick missing line_num — resolve manually"))
                continue
            if margin > line_num:
                outcome = "win"
            elif margin == line_num and line_num == int(line_num):
                outcome = "push"
            else:
                outcome = "loss"
        else:
            # Moneyline
            if margin > 0:
                outcome = "win"
            elif margin < 0:
                outcome = "loss"
            else:
                outcome = "push"

        p["result"] = outcome
        p["units_won_lost"] = calc_units_won_lost(p["line"], p["units"], outcome)
        p["final_score"] = result_data["final_score"]
        p["game_margin"] = margin
        # CLV skipped — no automated closing line source

        sign = "+" if p["units_won_lost"] >= 0 else ""
        print(f"✅ {p['id']}: {outcome.upper()} — {result_data['final_score']} (margin {margin:+d}) → {sign}{p['units_won_lost']}u")
        resolved.append(p["id"])

    if resolved:
        save_picks(picks)

    if skipped:
        print(f"\n⏭️  Skipped {len(skipped)} pick(s):")
        for pick_id, reason in skipped:
            print(f"   • {pick_id}: {reason}")

    if not resolved:
        print("ℹ️  No picks were auto-resolved.")
        sys.exit(0)

    print(f"\n✅ Resolved {len(resolved)} pick(s). Run `stats` to see updated dashboard.")


def cmd_resolve(args):
    picks = load_picks()
    pick = next((p for p in picks if p["id"] == args.id), None)
    if not pick:
        print(f"❌ Pick not found: {args.id}", file=sys.stderr)
        sys.exit(1)

    pick["result"] = args.outcome
    pick["units_won_lost"] = calc_units_won_lost(pick["line"], pick["units"], args.outcome)
    if args.closing_line:
        pick["closing_line"] = args.closing_line
        try:
            pick["clv"] = calc_clv(pick["line"], args.closing_line)
        except (ValueError, ZeroDivisionError) as e:
            print(f"⚠️  CLV calc failed ({e}); stored closing_line but clv=null", file=sys.stderr)
            pick["clv"] = None
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
    sub.add_parser("auto-resolve", help="Auto-resolve open MLB picks via MLB Stats API")

    log_p = sub.add_parser("log", help="Log a new pick")
    log_p.add_argument("--model", required=True, choices=["v1-trends", "v2-sharp"])
    log_p.add_argument("--sport", required=True)
    log_p.add_argument("--bet", required=True, help="Full bet description incl. opponent")
    log_p.add_argument("--line", required=True, help="Odds (e.g. -110, +146)")
    log_p.add_argument("--units", type=int, required=True, choices=[1, 2, 3])
    log_p.add_argument("--score", type=float, default=None)
    log_p.add_argument("--edge", default="", help="Primary edge type")
    log_p.add_argument("--primary-edge-type", default="",
                       help="Structured primary edge type, e.g. hard_rlm")
    log_p.add_argument("--source-evidence-json", default="",
                       help="JSON list of source evidence objects for validation")
    log_p.add_argument("--run-type", default="manual", choices=["manual", "scheduled"],
                       help="manual allows reasoned override; scheduled cannot override")
    log_p.add_argument("--override-validation", default="",
                       help="Manual override reason when validation fails")
    log_p.add_argument("--line-num", type=float, default=None,
                       help="Spread/RL number (e.g. 1.5 for -1.5 RL, 0 for ML)")
    log_p.add_argument("--game-time", default="",
                       help="Game start time in Arizona time, e.g. '5:10 PM' or '1:05 PM'")

    res_p = sub.add_parser("resolve", help="Record a result for an open pick")
    res_p.add_argument("id", help="Pick ID")
    res_p.add_argument("outcome", choices=["win", "loss", "push"])
    res_p.add_argument("--closing-line", default="",
                       help="American odds at close, e.g. '-110' or '+105'. Used to compute CLV.")
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
    elif args.command == "auto-resolve":
        cmd_auto_resolve(args)
    elif args.command == "log":
        cmd_log(args)
    elif args.command == "resolve":
        cmd_resolve(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
