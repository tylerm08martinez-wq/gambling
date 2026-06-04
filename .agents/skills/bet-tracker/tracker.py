#!/usr/bin/env python3
"""
Bet Tracker CLI
Usage:
  tracker.py stats
  tracker.py open
  tracker.py log --model <v1-trends|v2-sharp|v3-value> --sport <sport> --bet <bet> --line <line> --units <1-3> [--score <float>] [--edge <str>]
  tracker.py resolve <id> <win|loss|push|void> --final-score <str> --game-margin <int> --line-num <float> [--prop-result <str>]
"""

import json
import sys
import re
import argparse
import math
import time
import unicodedata
import urllib.request
import urllib.parse
from datetime import datetime
from pathlib import Path
from typing import Optional, NamedTuple

# Force UTF-8 output on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BASE_DIR = Path(__file__).parent
PICKS_FILE = BASE_DIR / "picks.json"
ACTUAL_BETS_FILE = BASE_DIR / "actual_bets.json"
REJECTED_CANDIDATES_FILE = BASE_DIR / "rejected-candidates.json"
LEGACY_ACTUAL_BETS_FILE = BASE_DIR.parents[2] / ".claude" / "skills" / "bet-tracker" / "actual_bets.json"


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

def load_json_object(path: Path) -> dict:
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return data

def save_json_object(path: Path, rows: dict):
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=2)
        f.write("\n")
    tmp.replace(path)

def merge_actual_bets(canonical: dict, legacy: dict) -> dict:
    merged = dict(canonical)
    for key, legacy_value in legacy.items():
        if key == "_settings" and isinstance(legacy_value, dict):
            merged[key] = {**legacy_value, **merged.get(key, {})}
        elif key not in merged:
            merged[key] = legacy_value
        elif isinstance(legacy_value, dict) and isinstance(merged[key], dict):
            merged[key] = {**legacy_value, **merged[key]}
    return merged


# ── Validation ───────────────────────────────────────────────────────────────

CANONICAL_PRIMARY_EDGE_TYPES = {
    "cross_book_gap",
    "clv_value",
    "steam",
    "hard_rlm",
    "soft_rlm",
    "ats_trend",
    "quant_convergence",
    "pitching_edge",
    "prop_trend",
    "matchup_edge",
    "plus_money_start",
    "underdog_fade",
}
SCHEDULED_DAILY_PICK_CAP = 7  # 7 total across V1+V2+V3 (ADR 0007); per-model cap below
SCHEDULED_DAILY_MODEL_CAP = 3

# Model registry — the dashboard renders one card per entry and resolves labels here,
# so adding a model is a one-row data change, never a new conditional branch (#45).
MODELS = [
    {"id": "v1-trends", "name": "V1-Trends", "label": "V1-TRENDS", "short": "V1", "emoji": "🎯"},
    {"id": "v2-sharp",  "name": "V2-Sharp",  "label": "V2-SHARP",  "short": "V2", "emoji": "🔪"},
    {"id": "v3-value",  "name": "V3-Value",  "label": "V3-VALUE",  "short": "V3", "emoji": "💎"},
]

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
    failures = []
    if edge_type and edge_type not in CANONICAL_PRIMARY_EDGE_TYPES:
        failures.append(f"unknown primary_edge_type: {edge_type}")

    if edge_type != "hard_rlm":
        return not failures, failures

    by_category: dict[str, list[dict]] = {}
    for item in source_evidence:
        category = normalize_key(item.get("category"))
        if category:
            by_category.setdefault(category, []).append(item)

    required = ["public_ticket_data", "line_movement_data"]
    for category in required:
        usable = [
            item for item in by_category.get(category, [])
            if normalize_key(item.get("status")) == "usable"
        ]
        if not usable:
            failures.append(f"missing usable {category}")

    return not failures, failures

def validate_scheduled_contract(primary_edge_type: Optional[str], source_evidence: list) -> list[str]:
    failures = []
    edge_type = normalize_key(primary_edge_type)
    if not edge_type:
        failures.append("scheduled run missing primary_edge_type")
    elif edge_type not in CANONICAL_PRIMARY_EDGE_TYPES:
        failures.append(f"unknown primary_edge_type: {edge_type}")

    usable_sources = [
        item for item in source_evidence
        if normalize_key(item.get("status")) == "usable"
        and str(item.get("source", "")).strip()
        and str(item.get("freshness", "")).strip()
    ]
    if not usable_sources:
        failures.append("scheduled run missing usable source evidence with source and freshness")

    return failures

def validate_scheduled_cap(picks: list, model: str, date: str) -> list[str]:
    todays_picks = [pick for pick in picks if pick.get("date") == date]
    model_picks = [pick for pick in todays_picks if pick.get("model") == model]
    failures = []
    if len(todays_picks) >= SCHEDULED_DAILY_PICK_CAP:
        failures.append(f"scheduled daily pick cap reached: {len(todays_picks)}/{SCHEDULED_DAILY_PICK_CAP}")
    if len(model_picks) >= SCHEDULED_DAILY_MODEL_CAP:
        failures.append(f"scheduled daily model cap reached for {model}: {len(model_picks)}/{SCHEDULED_DAILY_MODEL_CAP}")
    return failures

def normalize_bet_key(value: str) -> str:
    normalized = str(value or "").lower()
    normalized = normalized.replace("&", " and ")
    normalized = re.sub(r"\s[-+]\s", " ", normalized)
    normalized = re.sub(r"[^a-z0-9.+-]+", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()

def validate_scheduled_duplicate_market(picks: list, sport: str, bet: str, date: str) -> list[str]:
    sport_key = normalize_key(sport)
    bet_key = normalize_bet_key(bet)
    if not bet_key:
        return []
    for pick in picks:
        if pick.get("date") != date:
            continue
        if normalize_key(pick.get("sport")) != sport_key:
            continue
        if normalize_bet_key(pick.get("bet", "")) == bet_key:
            return [f"scheduled duplicate market already logged: {pick.get('id')}"]
    return []

def record_rejected_candidate(candidate: dict):
    rejected = load_json_list(REJECTED_CANDIDATES_FILE)
    rejected.append(candidate)
    save_json_list(REJECTED_CANDIDATES_FILE, rejected)


# ── Math ─────────────────────────────────────────────────────────────────────

def calc_units_won_lost(line_str: str, units: int, result: str) -> float:
    if result in {"push", "void"}:
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

def determine_outcome(bet_type: str, margin: int, line_num) -> str:
    """Pure function: derive win/push/loss from bet type, actual margin, and line threshold."""
    bt = (bet_type or "").lower()
    if "rl" in bt or "run line" in bt:
        if margin > line_num:
            return "win"
        if margin == line_num and line_num == int(line_num):
            return "push"
        return "loss"
    # Moneyline
    if margin > 0:
        return "win"
    if margin < 0:
        return "loss"
    return "push"


def calc_clv(bet_line: str, closing_line: str) -> float:
    """CLV in percentage points (closing_implied_prob - bet_implied_prob) * 100.
    Positive = you got a better price than the market settled at = good process."""
    return round((american_to_implied_prob(closing_line) - american_to_implied_prob(bet_line)) * 100, 2)


# ── Formatting ────────────────────────────────────────────────────────────────

def fmt_net(n: float) -> str:
    return f"+{n:.3f}u" if n >= 0 else f"{n:.3f}u"

def fmt_roi(r: float) -> str:
    return f"+{r:.1f}%" if r >= 0 else f"{r:.1f}%"

def fmt_clv(c: float) -> str:
    """Format a CLV value (percentage points) with an explicit sign, e.g. '+2.50%'."""
    return f"+{c:.2f}%" if c >= 0 else f"{c:.2f}%"

def fmt_score(s) -> str:
    return f"{s:.1f}/10" if s is not None else "—"

def fmt_record(s: dict) -> str:
    base = f"{s['wins']}-{s['losses']}-{s['pushes']}"
    if s.get("voids"):
        return f"{base} ({s['voids']} void)"
    return base

RESULT_ICON = {"win": "✅ Win", "loss": "❌ Loss", "push": "➡️ Push", "void": "🚫 Void", None: "⏳ Open"}


# ── Context line (two-line Recent Picks format) ───────────────────────────────

def fmt_margin(m) -> str:
    """Render a prop margin for display: integer when whole (2, not 2.0),
    else its decimal (0.5). prop_margin is stored as int-or-1-decimal (see
    prop_margin()), so this just drops the trailing .0 on whole values."""
    return str(int(m)) if float(m).is_integer() else str(m)


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
    if result == "void":
        return prop_result or final_score or "Void / DNP"

    score_prefix = f"{final_score} — " if final_score else ""

    # ── Player prop ──
    if prop_result:
        m = prop_margin if prop_margin is not None else 0
        if result == "win":
            barely = " (barely!)" if abs(m) <= 1 else ""  # sub-1 incl. 0.5 = close call
            return f"Went {prop_result} — hit with {fmt_margin(m)} to spare ✅{barely}"
        else:
            near = " 🔥 Near miss!" if abs(m) <= 1 else ""
            return f"Went {prop_result} — {fmt_margin(abs(m))} short{near}"

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

    if result == "void":
        return pick.get("prop_result") or "Void / DNP"

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
    settled = [p for p in picks if p.get("result") in {"win", "loss", "push"}]
    voids = sum(1 for p in picks if p.get("result") == "void")
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
        total=len(picks), settled=len(settled), voids=voids,
        wins=wins, losses=losses, pushes=pushes,
        units_wagered=units_wagered, units_net=units_net,
        win_pct=win_pct, roi=roi, avg_score=avg_score, open=open_count,
    )


def model_label(model_id: str, models: list = MODELS) -> str:
    """Short dashboard label for a model id ('v1-trends' -> 'V1'). Unknown ids echo
    back the id rather than being silently mislabeled (the old code defaulted to 'V2')."""
    for m in models:
        if m["id"] == model_id:
            return m["short"]
    return model_id or "?"


def dashboard_summaries(picks: list, models: list = MODELS) -> list:
    """Registry-driven per-model summary rows: each registry entry merged with its
    model_stats(). Order follows the registry; adding a model needs only a MODELS row."""
    rows = []
    for m in models:
        mp = [p for p in picks if p.get("model") == m["id"]]
        clv = clv_stats(mp)
        rows.append({**m, **model_stats(mp),
                     "clv_measured": clv["measured"],
                     "clv_plus_rate": clv["clv_plus_rate"],
                     "avg_clv": clv["avg_clv"]})
    return rows


def is_measured_clv(pick: dict) -> bool:
    """Measured CLV requires a fetched Pinnacle close. Unmeasured CLV — null clv, or a
    placeholder +0.00% with no close fetched (CONTEXT.md) — is excluded from CLV stats
    rather than counted as zero. A genuine measured 0.00% (close fetched, price tied the
    close) IS measured: it counts in the denominator but did not beat the close."""
    return pick.get("clv") is not None and bool(pick.get("closing_line"))


def clv_stats(picks: list) -> dict:
    """CLV process metrics over Measured-CLV picks (Unmeasured excluded). The V3-Value
    model is judged by these, not short-run ROI: CLV+ rate (share that beat the close),
    average CLV, and a per-Primary-Edge-Type breakdown."""
    measured = [p for p in picks if is_measured_clv(p)]
    n = len(measured)
    by_edge: dict = {}
    for p in measured:
        et = p.get("primary_edge_type") or "(unclassified)"
        b = by_edge.setdefault(et, {"n": 0, "clv_plus": 0, "clv_sum": 0.0})
        b["n"] += 1
        b["clv_sum"] += p["clv"]
        if p["clv"] > 0:
            b["clv_plus"] += 1
    for b in by_edge.values():
        b["avg_clv"] = b["clv_sum"] / b["n"]
        b["plus_rate"] = b["clv_plus"] / b["n"] * 100
    clv_plus = sum(1 for p in measured if p["clv"] > 0)
    return {
        "measured": n,
        "unmeasured": len(picks) - n,
        "clv_plus_rate": (clv_plus / n * 100) if n else None,
        "avg_clv": (sum(p["clv"] for p in measured) / n) if n else None,
        "by_edge_type": by_edge,
    }


# ── MLB Stats API ─────────────────────────────────────────────────────────────

def extract_bet_team(bet: str) -> str:
    """Extract the team we're betting on from a bet description."""
    parts = re.split(r'\s+(?:ML\b|[+-]?\d+\.?\d*\s+RL\b|[+-]?\d+\.?\d*\s+Spread\b)', bet, maxsplit=1, flags=re.IGNORECASE)
    team = parts[0].strip()
    if not team:
        team = re.split(r'\s+vs\s+', bet, flags=re.IGNORECASE)[0].strip()
    return team


# statsapi.mlb.com is a structured JSON source and is the durable resolution
# source (ADR 0004). Python-urllib's default User-Agent can be WAF-blocked (403)
# from datacenter egress IPs, so we always send a browser UA and retry with
# backoff. A persistent block returns None → the caller leaves the pick open.
_MLB_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"


def _http_get_json(url: str, retries: int = 3, headers: Optional[dict] = None) -> Optional[dict]:
    """GET JSON with a browser User-Agent and exponential backoff. None on failure.

    `headers` are merged on top of the browser User-Agent — used to pass a public
    `x-api-key` to datacenter-tolerant APIs like BettingPros (ADR 0006). Existing
    callers pass nothing and are unaffected.
    """
    req_headers = {"User-Agent": _MLB_UA}
    if headers:
        req_headers.update(headers)
    last_err = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=req_headers)
            with urllib.request.urlopen(req, timeout=10) as r:
                return json.loads(r.read())
        except Exception as e:
            last_err = e
            if attempt < retries - 1:
                time.sleep(1.5 * (attempt + 1))  # 1.5s, 3.0s backoff
    host = urllib.parse.urlparse(url).netloc or "API"
    print(f"⚠️  HTTP error from {host} after {retries} attempts: {last_err}", file=sys.stderr)
    return None


def fetch_mlb_schedule(date: str) -> list:
    """Return the list of MLB game dicts for `date` (empty list on failure)."""
    url = f"https://statsapi.mlb.com/api/v1/schedule?sportId=1&date={date}&hydrate=linescore"
    data = _http_get_json(url)
    if not data:
        return []
    games = []
    for date_entry in data.get("dates", []):
        games.extend(date_entry.get("games", []))
    return games


_TEAM_ABBR_CACHE: Optional[dict] = None


def fetch_mlb_team_abbrevs() -> dict:
    """Map MLB team id → official abbreviation (e.g. 147 → 'NYY', 135 → 'SD').

    The schedule endpoint returns only team id + name, but picks name the opponent by
    abbreviation ("vs SD", "vs TOR"). One cheap /teams call gives the canonical abbrev;
    cached for the process since abbreviations are stable. Returns {} on failure, so the
    finder degrades to name-last-word matching rather than crashing."""
    global _TEAM_ABBR_CACHE
    if _TEAM_ABBR_CACHE is None:
        data = _http_get_json("https://statsapi.mlb.com/api/v1/teams?sportId=1")
        _TEAM_ABBR_CACHE = {
            tm["id"]: tm["abbreviation"]
            for tm in (data or {}).get("teams", [])
            if tm.get("id") and tm.get("abbreviation")
        }
    return _TEAM_ABBR_CACHE


def _game_result_dict(game: dict, team_lower: str) -> dict:
    """Build the standard result dict for a final game, oriented to `team_lower`."""
    home = game["teams"]["home"]["team"]["name"]
    away = game["teams"]["away"]["team"]["name"]
    home_score = game["teams"]["home"].get("score", 0)
    away_score = game["teams"]["away"].get("score", 0)
    our_is_home = team_lower in home.lower()
    our_score = home_score if our_is_home else away_score
    opp_score = away_score if our_is_home else home_score
    away_abbr = game["teams"]["away"]["team"].get("abbreviation", away[:3].upper())
    home_abbr = game["teams"]["home"]["team"].get("abbreviation", home[:3].upper())
    return {
        "home": home, "away": away,
        "our_score": our_score, "opp_score": opp_score,
        "margin": our_score - opp_score,
        "total_runs": home_score + away_score,
        "final_score": f"{away_abbr} {away_score}, {home_abbr} {home_score}",
        "status": game.get("status", {}).get("detailedState", ""),
        "game_pk": game.get("gamePk"),
    }


def fetch_mlb_result(date: str, team_name: str) -> Optional[dict]:
    """
    Query MLB Stats API for a final game result on `date` involving `team_name`.
    Returns a result dict (incl. game_pk and total_runs) or None if not found / not final.
    """
    team_lower = team_name.lower()
    for game in fetch_mlb_schedule(date):
        home = game["teams"]["home"]["team"]["name"]
        away = game["teams"]["away"]["team"]["name"]
        if team_lower not in home.lower() and team_lower not in away.lower():
            continue
        if "Final" not in game.get("status", {}).get("detailedState", ""):
            return None  # game not yet final
        return _game_result_dict(game, team_lower)
    return None


def fetch_mlb_boxscore(game_pk) -> Optional[dict]:
    """Fetch the boxscore JSON for a gamePk. None on failure."""
    return _http_get_json(f"https://statsapi.mlb.com/api/v1/game/{game_pk}/boxscore")


# ── Bet classification & prop resolution (ADR 0004) ─────────────────────────────

# stat keyword → (boxscore stat group, statKey). Pitcher strikeouts come from the
# pitching group, NOT batting.strikeOuts. Add new prop types here only.
PROP_STAT_MAP = {
    # Both singular and plural forms are listed because matching is whole-word
    # (\bstrikeout\b does NOT match "strikeouts"), see _stat_keyword_in.
    "strikeouts": ("pitching", "strikeOuts"),
    "strikeout": ("pitching", "strikeOuts"),
    # Pitcher "outs recorded" (= innings pitched × 3). Whole-word matching means
    # \bouts\b never fires inside "strikeouts" (no boundary in "strike-outs"), and
    # "outs recorded" is checked before bare "outs" (keys sorted longest-first).
    "outs recorded": ("pitching", "outs"),
    "outs": ("pitching", "outs"),
    "total bases": ("batting", "totalBases"),
    "rbi": ("batting", "rbi"),
    "hits": ("batting", "hits"),
    "hit": ("batting", "hits"),
    # Walks map to the BATTING group: retail "walks" props are almost always batter
    # walks (e.g. "Mookie Betts Over 0.5 walks"). Pitcher-walk props are rare; if added
    # they need a distinct keyword mapping to ("pitching", "baseOnBalls").
    "walks": ("batting", "baseOnBalls"),
    "walk": ("batting", "baseOnBalls"),
    "stolen bases": ("batting", "stolenBases"),
    "stolen base": ("batting", "stolenBases"),
    "home runs": ("batting", "homeRuns"),
    "home run": ("batting", "homeRuns"),
    "doubles": ("batting", "doubles"),
    "double": ("batting", "doubles"),
    "runs": ("batting", "runs"),
    "run": ("batting", "runs"),
}

# NBA stat keyword → (boxscore stat group, statKey). Issues #24 (points) + #25
# (rebounds, assists, three-pointers made, steals, blocks, and the PRA combo).
# All group/key values are SYNTHETIC: the ESPN adapter (adapt_espn_nba_boxscore)
# produces the sport-agnostic shape stats["scoring"][<key>] from the parallel
# labels/stats arrays, so resolve_prop_value works unchanged. (ESPN's own
# statistics[].name is null; see adapter comment.) Everything is emitted under the
# single synthetic "scoring" group for simplicity — the key disambiguates the stat.
#
# COMBO (PRA): the stat_key is a TUPLE of component keys. resolve_prop_value sums
# the components (issue #25). It is NOT a separate boxscore key — there is no "PRA"
# column in ESPN's boxscore; PRA is defined as points+rebounds+assists summed.
# If ANY component is missing, resolve_prop_value returns a reason → pick left OPEN.
NBA_PROP_STAT_MAP = {
    "points": ("scoring", "points"),
    "point": ("scoring", "points"),
    "pts": ("scoring", "points"),
    "rebounds": ("scoring", "rebounds"),
    "rebound": ("scoring", "rebounds"),
    "reb": ("scoring", "rebounds"),
    "assists": ("scoring", "assists"),
    "assist": ("scoring", "assists"),
    "ast": ("scoring", "assists"),
    # Three-pointers made. ESPN's 3PT column is "made-attempted" (e.g. "7-12"); the
    # adapter parses the MADE integer (before the dash) and stores it here.
    "three pointers made": ("scoring", "threes"),
    "three pointers": ("scoring", "threes"),
    "three-pointers made": ("scoring", "threes"),
    "threes made": ("scoring", "threes"),
    "threes": ("scoring", "threes"),
    "3pm": ("scoring", "threes"),
    "3pt": ("scoring", "threes"),
    "steals": ("scoring", "steals"),
    "steal": ("scoring", "steals"),
    "stl": ("scoring", "steals"),
    "blocks": ("scoring", "blocks"),
    "block": ("scoring", "blocks"),
    "blk": ("scoring", "blocks"),
    # PRA combo — resolved by SUMMING the component keys (see resolve_prop_value).
    "points+rebounds+assists": ("scoring", ("points", "rebounds", "assists")),
    "pts+reb+ast": ("scoring", ("points", "rebounds", "assists")),
    "pra": ("scoring", ("points", "rebounds", "assists")),
}


# ── Player Prop Source seam (CONTEXT.md: "Player Prop Source") ───────────────────
# A per-sport adapter that supplies everything needed to settle a Player Prop from a
# finished game, behind one small interface. The resolver looks the source up by sport
# and runs ONE shared path regardless of sport — so adding a sport is registering a
# source, not adding a branch. ADR 0004/0005 (classify-before-resolve, never-guess,
# ESPN boxscore adaptation) all live BEHIND this seam, unchanged.
class ResolvedGame(NamedTuple):
    """A located final game for a bet. `ref` is an OPAQUE handle (MLB gamePk, NBA
    event id) — the resolver never inspects it; it hands `ref` straight back to the
    SAME source's fetch_boxscore. This is why the gamePk-vs-game_id difference never
    reaches shared code."""
    ref: object
    final_score: str


class PlayerPropSource(NamedTuple):
    """Per-sport Player Prop adapter.
      find_game(date, bet) -> ResolvedGame | None   (locate the final game)
      fetch_boxscore(ref)  -> boxscore | None        (sport-agnostic per-player shape:
                                  teams.<side>.players[*].{person.fullName, stats.<group>.<key>})
      stat_map: stat-keyword -> (group, key) for this sport
    On any failure the callables return None and the resolver leaves the pick OPEN."""
    find_game: object
    fetch_boxscore: object
    stat_map: dict


def _whole_word_in(phrase: str, text: str) -> bool:
    """
    True if `phrase` appears in `text` on word boundaries (case-insensitive).
    Plain substring matching silently collides with longer words — `walk` ⊂
    "Walker", `run` ⊂ "Bruno", `hit` ⊂ "White", and (the bug this guards) team
    last word `rays` ⊂ "Grayson". Word boundaries make `\\brays\\b` not match
    "grayson", so a Rays game can't masquerade as Grayson Rodriguez's game.
    """
    return re.search(rf'\b{re.escape(phrase)}\b', text, flags=re.IGNORECASE) is not None


def _stat_keyword_in(kw: str, text: str) -> bool:
    """Whole-word match for a stat keyword (see _whole_word_in for the why)."""
    return _whole_word_in(kw, text)


# A "+" joining stat WORDS ("Hits+Runs+RBIs", "Runs + RBIs") marks a COMBINED stat —
# a sum of components the single-stat resolver would silently grade as just one of
# them (a confident wrong result). The "N+" line form ("2+ Total Bases") is digit-
# then-plus, so it does NOT match (letter required on both sides of the "+").
_COMBINED_STAT_RE = re.compile(r'[a-z]\s*\+\s*[a-z]', re.IGNORECASE)


def _is_combined_stat(bet: str) -> bool:
    """True if `bet` names a combined (summed) stat the inline grader must not score
    as a single component. Such props are left OPEN for manual review, never guessed."""
    return bool(_COMBINED_STAT_RE.search(bet or ""))


def classify_bet(pick: dict) -> str:
    """Return 'prop', 'total', 'rl', or 'ml'. Uses bet_type when present, else infers."""
    bt = (pick.get("bet_type") or "").lower()
    if bt in ("prop", "total", "rl", "ml"):
        return bt
    bet = pick.get("bet", "")
    low = bet.lower()
    if "rl" in low.split() or "run line" in low:
        return "rl"
    # Game total: starts with Over/Under and has no player name before it.
    if re.match(r'^\s*(over|under)\b', low):
        return "total"
    # Player prop: a mapped stat keyword + a side (Over/Under or N+). Use the
    # sport-appropriate stat map so NBA points props classify as prop, not ml.
    # NOTE: classification reads the GLOBAL PROP_SOURCES (via _stat_map_for_sport),
    # not any `sources` registry injected into cmd_auto_resolve. In production these
    # are the same object, so there is no divergence; an injected source with a
    # non-standard stat_map would be honored for resolution but not classification.
    stat_map = _stat_map_for_sport(pick.get("sport", ""))
    if any(_stat_keyword_in(k, low) for k in stat_map) and re.search(r'\b(over|under)\b|\d+\+', low):
        return "prop"
    return "ml"


def clean_player_name(s: str) -> str:
    """
    Strip structural annotations from a raw prop player segment, BEFORE
    normalization. Pure: no I/O, no team-name list (those go stale seasonally).

    Removes:
      - parenthetical/bracketed segments: ``(...)`` and ``[...]``
      - sportsbook suffixes: everything from an ``@`` onward (e.g. ``@ FanDuel``)

    Whatever leading name tokens remain are returned (still un-normalized);
    callers pass the result through ``_normalize_name`` for matching.
    """
    s = re.sub(r'\([^)]*\)', ' ', s)   # parenthetical segments
    s = re.sub(r'\[[^\]]*\]', ' ', s)  # bracketed segments
    s = s.split('@')[0]                # drop sportsbook suffix and anything after
    return re.sub(r'\s+', ' ', s).strip()


def _normalize_name(s: str) -> str:
    """Lowercase, strip accents and punctuation for name matching."""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r'[^a-z\s]', '', s.lower()).strip()


def extract_prop(bet: str, line_num, stat_map: dict = PROP_STAT_MAP) -> Optional[dict]:
    """
    Parse a player prop. Returns {player, stat_group, stat_key, side, threshold}
    or None if any component can't be resolved (caller then skips — never guesses).

    `stat_map` is the sport's stat-keyword → (group, key) map, supplied by the pick's
    Player Prop Source (the resolver passes src.stat_map). Defaults to the MLB map for
    direct/unit-test callers; the resolution path always passes an explicit map.
    Return shape is unchanged so downstream callers are untouched.
    """
    low = bet.lower()
    # Side + threshold. "N+" means at least N → Over (N-0.5). Else Over/Under + line_num.
    nplus = re.search(r'(\d+(?:\.\d+)?)\+', bet)
    if nplus:
        side, threshold = "over", float(nplus.group(1)) - 0.5
        player_cut = bet[:nplus.start()]
    elif re.search(r'\bover\b', low):
        side = "over"
        player_cut = re.split(r'\bover\b', bet, flags=re.IGNORECASE)[0]
        threshold = float(line_num) if line_num is not None else None
    elif re.search(r'\bunder\b', low):
        side = "under"
        player_cut = re.split(r'\bunder\b', bet, flags=re.IGNORECASE)[0]
        threshold = float(line_num) if line_num is not None else None
    else:
        return None
    if threshold is None:
        return None
    # Stat: first mapped keyword present (check multiword keys before single).
    stat_group = stat_key = None
    matched_kw = None
    for kw in sorted(stat_map, key=len, reverse=True):
        if _stat_keyword_in(kw, low):
            stat_group, stat_key = stat_map[kw]
            matched_kw = kw
            break
    if not stat_key:
        return None
    # Combined-stat guard: a "+" joining stat words ("Hits+Runs+RBIs") is a SUM. If the
    # map resolved it to a proper combo (tuple stat_key, e.g. NBA PRA) we sum and resolve.
    # But if it resolved to a SINGLE component (str), grading it would be a confident wrong
    # result → refuse, so the caller leaves the pick OPEN for manual review.
    if _is_combined_stat(bet) and not isinstance(stat_key, (tuple, list)):
        return None
    # The stat keyword can appear BEFORE the side ("Aranda Total Bases Over 1.5"),
    # which leaves it inside the player segment. Strip it (whole-word, so a stat
    # that is a substring of a surname — walks⊂Walker — never damages the name).
    player_cut = re.sub(rf'\b{re.escape(matched_kw)}\b', ' ', player_cut, flags=re.IGNORECASE)
    # Strip structural annotations (parentheticals/brackets, @sportsbook suffix)
    # BEFORE accent/punctuation normalization so annotated props still match.
    player = _normalize_name(clean_player_name(player_cut))
    if not player:
        return None
    return {"player": player, "stat_group": stat_group, "stat_key": stat_key,
            "side": side, "threshold": threshold}


# Sentinel reason returned when a rostered player recorded NO stats in ANY group
# (a did-not-play / scratch). The caller voids the prop (stake refunded) instead of
# leaving it open forever. Distinct from "played another role", which is left open.
PROP_DNP = "player did not play (no stats recorded — void/refund)"


def resolve_prop_value(box: dict, player_norm: str, stat_group: str, stat_key):
    """
    Find `player_norm` (matched on last name) across both teams in the boxscore and
    return their stat value. Returns (value, None) on success, or (None, reason) on
    failure — including a same-last-name collision, which is skipped not guessed.
    A did-not-play returns (None, PROP_DNP) so the caller can void rather than skip.

    `stat_key` may be a single key (str) OR a tuple/list of component keys for a
    COMBO prop (e.g. NBA PRA = points+rebounds+assists). For a combo we SUM the
    component values; if ANY component is missing the pick is left OPEN (returns a
    reason), never partial-guessed. This keeps prop_outcome generic and unchanged.
    """
    target_last = player_norm.split()[-1]
    matches = []
    for side in ("away", "home"):
        for pdata in box.get("teams", {}).get(side, {}).get("players", {}).values():
            full = _normalize_name(pdata.get("person", {}).get("fullName", ""))
            if full and full.split()[-1] == target_last:
                matches.append((full, pdata))
    if not matches:
        return None, f"player '{player_norm}' not found in boxscore"
    if len(matches) > 1:
        # Disambiguate by full normalized name if exactly one is an exact match.
        exact = [m for m in matches if m[0] == player_norm]
        if len(exact) == 1:
            matches = exact
        else:
            return None, f"ambiguous last name '{target_last}' ({len(matches)} players)"
    pdata = matches[0][1]
    all_stats = pdata.get("stats", {})
    stats = all_stats.get(stat_group, {})
    if not stats:
        # Empty requested group. If EVERY group is empty the player didn't appear
        # (scratch/DNP) → void. If another group has data they played a different
        # role → leave open for manual review (a real game must never be voided).
        if not any(all_stats.values()):
            return None, PROP_DNP
        return None, f"no {stat_group} stats for player (played another role?)"
    # Combo prop: sum the component keys, leaving the pick OPEN if any are missing.
    if isinstance(stat_key, (tuple, list)):
        total = 0
        for key in stat_key:
            if key not in stats:
                return None, f"combo component {stat_group}.{key} missing (left open, not guessed)"
            total += stats[key]
        return total, None
    if stat_key not in stats:
        return None, f"no {stat_group}.{stat_key} stat for player (did not play that role?)"
    return stats[stat_key], None


def prop_outcome(actual, side: str, threshold: float) -> str:
    """win/loss/push for an Over/Under prop given the actual stat value."""
    if actual == threshold:
        return "push"
    if side == "over":
        return "win" if actual > threshold else "loss"
    return "win" if actual < threshold else "loss"


def prop_margin(value, threshold):
    """Signed margin (value - threshold) for a resolved prop.

    Returns an int when the difference is a whole number (e.g. 8 vs 6.0 -> 2),
    otherwise the difference rounded to one decimal (e.g. 28 vs 27.5 -> 0.5).
    The bug this replaces gated integer formatting on whether `value` was whole
    rather than whether the *difference* was whole, truncating a real 0.5 margin
    (28 vs 27.5) to 0.
    """
    diff = value - threshold
    if float(diff).is_integer():
        return int(diff)
    return round(diff, 1)


def find_mlb_game_for_bet(date: str, bet: str) -> Optional[dict]:
    """Find the final game on `date` whose home/away team appears in `bet`. None if
    none/not final. Matches on either the team-name last word ("Pirates", "Rockies")
    OR the official abbreviation ("vs SD", "vs TOR") — picks use both forms."""
    low = bet.lower()
    abbrevs = None  # fetched lazily, only when a team dict lacks an inline abbreviation
    for game in fetch_mlb_schedule(date):
        home_team = game["teams"]["home"]["team"]
        away_team = game["teams"]["away"]["team"]
        home = home_team["name"]
        away = away_team["name"]
        # Match keys: each team's distinctive last word + its official abbreviation.
        # Whole-word, not substring: "rays" must not match inside "Grayson" — a
        # substring match grabbed the wrong game (DET@TAM) and mis-resolved the prop.
        keys = [home.split()[-1], away.split()[-1]]
        for team in (home_team, away_team):
            abbr = team.get("abbreviation")
            if abbr is None:                    # real schedule omits it → use the id map
                if abbrevs is None:
                    abbrevs = fetch_mlb_team_abbrevs()
                abbr = abbrevs.get(team.get("id"))
            if abbr:
                keys.append(abbr)
        if any(_whole_word_in(k, low) for k in keys):
            if "Final" not in game.get("status", {}).get("detailedState", ""):
                return None
            return _game_result_dict(game, home.lower())
    return None


def _mlb_find_game(date: str, bet: str) -> Optional[ResolvedGame]:
    """MLB Player Prop Source `find_game`: locate the final MLB game for a bet and
    project it to the opaque-handle ResolvedGame the resolver consumes (ref = gamePk).
    The rich game-line finder (find_mlb_game_for_bet) is reused unchanged for the
    MLB game-line paths; here we keep only what a prop needs."""
    g = find_mlb_game_for_bet(date, bet)
    if g is None:
        return None
    return ResolvedGame(ref=g["game_pk"], final_score=g["final_score"])


def _nba_find_game(date: str, bet: str) -> Optional[ResolvedGame]:
    g = find_nba_game_for_bet(date, bet)
    if g is None:
        return None
    return ResolvedGame(ref=g["game_id"], final_score=g["final_score"])


# ── NBA Player Prop resolution (ADR 0005, ESPN hidden API) ──────────────────────
# Source: ESPN hidden API (site.api.espn.com) — no key, no special headers, reuses
# the shared _http_get_json client (browser UA + retry/backoff). A persistent block
# returns None → the caller leaves the pick OPEN (never guesses), identical to MLB.

def _espn_nba_scoreboard(date: str) -> list:
    """
    Return the list of ESPN NBA event dicts for `date` (YYYY-MM-DD).
    ESPN scoreboard expects YYYYMMDD (no dashes) — we convert. Empty list on failure.
    """
    espn_date = date.replace("-", "")
    url = (f"https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard"
           f"?dates={espn_date}")
    data = _http_get_json(url)
    if not data:
        return []
    return data.get("events", [])


def find_nba_game_for_bet(date: str, bet: str) -> Optional[dict]:
    """
    Find the final NBA game on `date` whose home/away team name appears in `bet`.
    Returns a result dict with `game_id` and `final_score`, or None if none found /
    not final. Analogous to find_mlb_game_for_bet.
    """
    low = bet.lower()
    for event in _espn_nba_scoreboard(date):
        comps = event.get("competitions", [])
        if not comps:
            continue
        competitors = comps[0].get("competitors", [])
        by_side = {}
        for c in competitors:
            team = c.get("team", {})
            by_side[c.get("homeAway")] = {
                "name": team.get("displayName", ""),
                "abbr": team.get("abbreviation", ""),
                "score": c.get("score", "0"),
            }
        home, away = by_side.get("home"), by_side.get("away")
        if not home or not away:
            continue
        # Match on the distinctive last word of each team name (e.g. "celtics").
        home_hit = home["name"] and home["name"].split()[-1].lower() in low
        away_hit = away["name"] and away["name"].split()[-1].lower() in low
        if not (home_hit or away_hit):
            continue
        status = event.get("status", {}).get("type", {}).get("name", "")
        if status != "STATUS_FINAL":
            return None  # game not yet final
        return {
            "game_id": event.get("id"),
            "final_score": f"{away['abbr']} {away['score']}, {home['abbr']} {home['score']}",
        }
    return None


def adapt_espn_nba_boxscore(summary: dict) -> dict:
    """
    Adapt an ESPN NBA summary response into the SAME sport-agnostic per-player shape
    the MLB resolver consumes — a `teams.<side>.players` map of records, each with
    `person.fullName` and `stats.<group>.<key>` — so resolve_prop_value / prop_outcome
    stay source-agnostic and shared across both sports.

    ESPN shape (self-annealed against the live endpoint 2026-05-30):
      summary["boxscore"]["players"]  → list of TWO team blocks
        block["statistics"][0]["labels"] → parallel label array, e.g.
          ["MIN","PTS","FG","3PT","FT","REB","AST","STL","BLK", ...]
        block["statistics"][0]["athletes"][i]["athlete"]["displayName"]
        block["statistics"][0]["athletes"][i]["stats"]  → parallel value array
      NOTE: ESPN's statistics[].name is null (NOT a real group name like "scoring"),
      so we do NOT key off it. We index the value array by each label's POSITION and
      emit values under the SYNTHETIC group "scoring" with keys NBA_PROP_STAT_MAP
      points at. DNP players have stats == [] and are skipped (empty stats group →
      resolve_prop_value returns a reason, never guesses).

    Label → synthetic key mapping (issues #24 + #25):
      PTS → points, REB → rebounds, AST → assists, STL → steals, BLK → blocks.
      3PT → threes: this column is "made-attempted" (e.g. "7-12"), NOT a bare int —
      we parse the MADE value (the integer before the dash). All others are bare ints.
      A label absent from a given boxscore simply omits that key for those players,
      so a prop on a missing stat is left OPEN by resolve_prop_value (never guessed).
    """
    # label → (synthetic key, is the value a "made-attempted" string?)
    LABEL_MAP = {
        "PTS": ("points", False),
        "REB": ("rebounds", False),
        "AST": ("assists", False),
        "STL": ("steals", False),
        "BLK": ("blocks", False),
        "3PT": ("threes", True),  # "made-attempted", parse the made integer
    }
    box = summary.get("boxscore", {})
    team_blocks = box.get("players", [])
    teams = {"away": {"players": {}}, "home": {"players": {}}}
    # ESPN lists home team first in boxscore.players; map index→side accordingly.
    # (Orientation does not affect resolution — resolve_prop_value scans both sides.)
    for idx, block in enumerate(team_blocks):
        side = "home" if idx == 0 else "away"
        stat_sets = block.get("statistics", [])
        if not stat_sets:
            continue
        stat_set = stat_sets[0]
        labels = stat_set.get("labels", [])
        # Resolve the column index of each label we care about that is present.
        col_idx = {}
        for label, (key, _made_att) in LABEL_MAP.items():
            try:
                col_idx[label] = labels.index(label)
            except ValueError:
                pass  # label absent → that stat omitted; prop on it left OPEN
        for i, ath in enumerate(stat_set.get("athletes", [])):
            full = ath.get("athlete", {}).get("displayName", "")
            vals = ath.get("stats", [])
            if not full or not vals:
                continue  # DNP / missing → leave out; resolver leaves pick open
            scoring = {}
            for label, pos in col_idx.items():
                if pos >= len(vals):
                    continue
                key, made_att = LABEL_MAP[label]
                raw = vals[pos]
                try:
                    if made_att:
                        # "7-12" → 7 (made). Take the integer before the dash.
                        scoring[key] = int(str(raw).split("-")[0])
                    else:
                        scoring[key] = int(raw)
                except (ValueError, TypeError):
                    continue  # unparseable cell → omit that key, never guess
            if not scoring:
                continue
            teams[side]["players"][f"{side}-{i}"] = {
                "person": {"fullName": full},
                "stats": {"scoring": scoring},
            }
    return {"teams": teams}


def fetch_nba_boxscore(game_id) -> Optional[dict]:
    """
    Fetch the ESPN NBA summary for `game_id` and adapt it into the sport-agnostic
    boxscore shape. None on failure (caller leaves the pick open).
    """
    url = (f"https://site.api.espn.com/apis/site/v2/sports/basketball/nba/summary"
           f"?event={game_id}")
    summary = _http_get_json(url)
    if summary is None:
        return None
    return adapt_espn_nba_boxscore(summary)


# Registry of Player Prop Sources, keyed by uppercase sport. MLB's fetch_boxscore is
# effectively identity — the MLB Stats API already returns the sport-agnostic
# teams.<side>.players[*].{person,stats} shape. NBA's source adapts ESPN's summary.
PROP_SOURCES = {
    "MLB": PlayerPropSource(
        find_game=_mlb_find_game,
        fetch_boxscore=fetch_mlb_boxscore,
        stat_map=PROP_STAT_MAP,
    ),
    "NBA": PlayerPropSource(
        find_game=_nba_find_game,
        fetch_boxscore=fetch_nba_boxscore,
        stat_map=NBA_PROP_STAT_MAP,
    ),
}


def _stat_map_for_sport(sport: str, sources: Optional[dict] = None) -> dict:
    """Stat-keyword map for a sport.

    Empty/blank sport defaults to MLB to preserve legacy MLB-style picks that omitted
    sport. The unknown-sport-defaults-to-MLB fallback has been removed: an
    unregistered sport now yields no stat keywords, so classify_bet cannot classify
    its bet as a prop. It routes to the game-line path, where non-MLB/NBA is skipped
    and left open — never mis-resolved against the MLB stat map.
    """
    reg = PROP_SOURCES if sources is None else sources
    key = (sport or "").upper()
    if key == "":
        key = "MLB"
    src = reg.get(key)
    return src.stat_map if src is not None else {}


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

    summaries = dashboard_summaries(picks)
    cb = model_stats(picks)

    settled_all = [p for p in picks if p.get("result") in {"win", "loss", "push"}]
    open_picks = [p for p in picks if p.get("result") is None]
    void_picks = [p for p in picks if p.get("result") == "void"]

    # Leader = registered model with the highest net units; margin to the runner-up.
    ranked = sorted(summaries, key=lambda r: r["units_net"], reverse=True)
    top = ranked[0]
    runner_up_net = ranked[1]["units_net"] if len(ranked) > 1 else 0.0
    margin = top["units_net"] - runner_up_net
    leader = f"{top['name']} by {margin:.2f}u" if margin > 0 else "Tied"

    print(f"\n📊 BETTING TRACKER — {today}")
    void_label = f" · {len(void_picks)} void" if void_picks else ""
    print(f"{len(picks)} picks tracked · {cb['settled']} settled · {cb['open']} open{void_label}\n")
    print(divider())

    # ── Model cards (one per registered model) ──
    for st in summaries:
        avg = f"{st['avg_score']:.1f}/10" if st['avg_score'] is not None else "—"
        print(f"\n{st['emoji']} {st['label']}")
        print(f"Record: {fmt_record(st)} · Win %: {st['win_pct']:.1f}%")
        print(f"Net: {fmt_net(st['units_net'])} · ROI: {fmt_roi(st['roi'])} {roi_emoji(st['roi'])}")
        print(f"Avg score: {avg} · {st['open']} open")
        if st["clv_measured"]:
            print(f"CLV+: {st['clv_plus_rate']:.0f}% · avg {fmt_clv(st['avg_clv'])} · {st['clv_measured']} measured")
        else:
            print("CLV+: — no measured picks yet")

    print(f"\n📈 COMBINED")
    print(f"Record: {fmt_record(cb)} · Win %: {cb['win_pct']:.1f}%")
    print(f"Net: {fmt_net(cb['units_net'])} · ROI: {fmt_roi(cb['roi'])} {roi_emoji(cb['roi'])}")
    print(f"Units wagered: {cb['units_wagered']}u")

    print(f"\n🏆 Leading: {leader}")
    if cb['settled'] < 20:
        print(f"⚠️  Need 20+ settled picks for statistical significance ({cb['settled']} so far)")
    print(f"Breakeven win rate at −110: 52.4%")

    # ── CLV Calibration (V3-Value scorecard — judge by CLV, not short-run ROI) ──
    clv = clv_stats(picks)
    if clv["measured"]:
        print(f"\n{divider()}\n")
        print(f"💹 CLV CALIBRATION  ({clv['measured']} measured · {clv['unmeasured']} unmeasured excluded)")
        print(f"CLV+ rate: {clv['clv_plus_rate']:.0f}% · Avg CLV: {fmt_clv(clv['avg_clv'])}")
        if clv["by_edge_type"]:
            print("By edge type:")
            for et, b in sorted(clv["by_edge_type"].items(), key=lambda x: -x[1]["avg_clv"]):
                print(f"• {et}: {b['n']} · {b['plus_rate']:.0f}% CLV+ · avg {fmt_clv(b['avg_clv'])}")

    # ── Recent Picks ──
    recent = sorted(picks, key=lambda p: p["date"], reverse=True)[:10]
    print(f"\n{divider()}\n")
    print("📋 RECENT PICKS\n")
    for p in recent:
        mlabel = model_label(p["model"])
        result = p.get("result")
        icon = RESULT_ICON.get(result, "—").split()[0]
        date_short = p["date"][5:]  # MM-DD
        pl_str = "void" if result == "void" else fmt_net(p.get("units_won_lost") or 0) if result else "pending"
        bet_display = p["bet"][:38]
        print(f"{icon} {date_short} · {mlabel} · {bet_display} · {p['line']} · {p['units']}u · {pl_str}")
        ctx = build_context(p)
        if ctx != "⏳ Pending":
            print(f"   {ctx}")
    print()

    # ── Open Tonight ──
    if open_picks:
        print(divider())
        print(f"\n⏳ OPEN / PENDING\n")
        for p in open_picks:
            print(f"• {p['bet']} · {p['line']} · {p['units']}u  [{model_label(p['model'])}]")
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


def cmd_migrate_actual_bets(_args):
    """Merge stale .claude My Bets data into the canonical .agents file."""
    canonical = load_json_object(ACTUAL_BETS_FILE)
    if not LEGACY_ACTUAL_BETS_FILE.exists():
        print(f"No legacy actual bets file found at {LEGACY_ACTUAL_BETS_FILE}")
        print(f"Canonical source of truth: {ACTUAL_BETS_FILE}")
        return

    legacy = load_json_object(LEGACY_ACTUAL_BETS_FILE)
    merged = merge_actual_bets(canonical, legacy)
    save_json_object(ACTUAL_BETS_FILE, merged)
    LEGACY_ACTUAL_BETS_FILE.unlink()
    print(f"Migrated {len(legacy)} legacy entries into {ACTUAL_BETS_FILE}")
    print(f"Removed stale file: {LEGACY_ACTUAL_BETS_FILE}")


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
    if run_type == "scheduled":
        validation_notes.extend(validate_scheduled_contract(primary_edge_type, source_evidence))
        validation_notes.extend(validate_scheduled_cap(picks, args.model, date))
        validation_notes.extend(validate_scheduled_duplicate_market(picks, args.sport, args.bet, date))
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
    model_abbrev = "v1" if "v1" in args.model.lower() else "v2"
    pick_id = f"{date.replace('-','')}-{sport_abbrev}-{model_abbrev}-{team_abbrev}-{btype}"

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


def cmd_auto_resolve(_args, sources=None):
    """Automatically resolve open picks using official APIs.

    `sources` is the Player Prop Source registry (sport → PlayerPropSource); it
    defaults to PROP_SOURCES and is injectable so tests can pass fake sources (the
    seam IS the test surface — no monkeypatching of module functions, no live HTTP)."""
    sources = PROP_SOURCES if sources is None else sources
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
        line_num = p.get("line_num")

        kind = classify_bet(p)

        # ── Player Prop: resolve via the sport's Player Prop Source. Hard guard — ──
        # never fall through to a game-line path (ADR 0004). The source supplies the
        # game finder, boxscore fetcher, and stat map; the opaque `ref` is handed
        # straight back to the same source's fetch_boxscore.
        if kind == "prop":
            src = sources.get(sport)
            if src is None:
                skipped.append((p["id"], f"prop: no Player Prop Source for sport={sport} — resolve manually"))
                continue
            spec = extract_prop(bet, line_num, src.stat_map)
            if spec is None:
                # extract_prop refuses an un-summable combo (a "+" stat the map only
                # resolves to a single component); give that a clear reason vs. a plain
                # parse failure. A proper combo (NBA PRA → tuple) returns a spec and resolves.
                reason = ("combined-stat (sum of components) — resolve manually"
                          if _is_combined_stat(bet)
                          else "could not parse player/stat/side/threshold — resolve manually")
                skipped.append((p["id"], f"prop: {reason}"))
                continue
            game = src.find_game(date, bet)
            if game is None:
                skipped.append((p["id"], f"prop: game not found or not final on {date}"))
                continue
            box = src.fetch_boxscore(game.ref)
            if box is None:
                skipped.append((p["id"], "prop: boxscore fetch failed (API blocked?) — left open"))
                continue
            value, reason = resolve_prop_value(box, spec["player"], spec["stat_group"], spec["stat_key"])
            if reason == PROP_DNP:
                # Player didn't appear → void (stake refunded), don't leave open.
                p["result"] = "void"
                p["units_won_lost"] = calc_units_won_lost(p["line"], p["units"], "void")
                p["final_score"] = game.final_score
                p["prop_result"] = "DNP"
                print(f"🚫 {p['id']}: VOID — player did not play → stake refunded")
                resolved.append(p["id"])
                continue
            if reason:
                skipped.append((p["id"], f"prop: {reason}"))
                continue
            outcome = prop_outcome(value, spec["side"], spec["threshold"])
            sk = spec["stat_key"]
            stat_label = "+".join(sk) if isinstance(sk, (tuple, list)) else sk
            p["result"] = outcome
            p["units_won_lost"] = calc_units_won_lost(p["line"], p["units"], outcome)
            p["final_score"] = game.final_score
            p["prop_result"] = f"{value} {stat_label}"
            p["prop_margin"] = prop_margin(value, spec["threshold"])
            sign = "+" if p["units_won_lost"] >= 0 else ""
            print(f"✅ {p['id']}: {outcome.upper()} — {value} {stat_label} vs {spec['side']} {spec['threshold']} → {sign}{p['units_won_lost']}u")
            resolved.append(p["id"])
            continue

        if sport != "MLB":
            skipped.append((p["id"], f"sport={sport} — only MLB/NBA auto-resolve (resolve manually)"))
            continue

        # ── Game total: orientation is symmetric, match game by either team name. ──
        if kind == "total":
            result_data = find_mlb_game_for_bet(date, bet)
            if result_data is None:
                skipped.append((p["id"], f"total: game not found or not final on {date}"))
                continue
            if line_num is None:
                skipped.append((p["id"], "total missing line_num — resolve manually"))
                continue
            total = result_data["total_runs"]
            side = "over" if re.match(r'^\s*over\b', bet.lower()) else "under"
            outcome = prop_outcome(total, side, float(line_num))
            p["result"] = outcome
            p["units_won_lost"] = calc_units_won_lost(p["line"], p["units"], outcome)
            p["final_score"] = result_data["final_score"]
            p["prop_result"] = f"{total} total runs"
            sign = "+" if p["units_won_lost"] >= 0 else ""
            print(f"✅ {p['id']}: {outcome.upper()} — {total} runs vs {side} {line_num} → {sign}{p['units_won_lost']}u")
            resolved.append(p["id"])
            continue

        # ── Moneyline / run line: margin must be oriented to the team we bet on. ──
        team = extract_bet_team(bet)
        result_data = fetch_mlb_result(date, team) if team else None
        if result_data is None:
            skipped.append((p["id"], f"game not found or not final for '{team}' on {date}"))
            continue
        margin = result_data["margin"]
        if kind == "rl":
            if line_num is None:
                skipped.append((p["id"], "RL pick missing line_num — resolve manually"))
                continue
            outcome = determine_outcome("rl", margin, line_num)
        else:
            outcome = determine_outcome("ml", margin, line_num)

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
    sub.add_parser("migrate-actual-bets", help="Merge stale .claude My Bets data into .agents")

    log_p = sub.add_parser("log", help="Log a new pick")
    log_p.add_argument("--model", required=True, choices=[m["id"] for m in MODELS])
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
    res_p.add_argument("outcome", choices=["win", "loss", "push", "void"])
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
    elif args.command == "migrate-actual-bets":
        cmd_migrate_actual_bets(args)
    elif args.command == "log":
        cmd_log(args)
    elif args.command == "resolve":
        cmd_resolve(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
