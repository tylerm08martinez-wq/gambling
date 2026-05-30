#!/usr/bin/env python3
"""
Bet Tracker CLI
Usage:
  tracker.py stats
  tracker.py open
  tracker.py log --model <v1-trends|v2-sharp> --sport <sport> --bet <bet> --line <line> --units <1-3> [--score <float>] [--edge <str>]
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
from datetime import datetime
from pathlib import Path
from typing import Optional

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
SCHEDULED_DAILY_PICK_CAP = 5
SCHEDULED_DAILY_MODEL_CAP = 3

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

def fmt_score(s) -> str:
    return f"{s:.1f}/10" if s is not None else "—"

def fmt_record(s: dict) -> str:
    base = f"{s['wins']}-{s['losses']}-{s['pushes']}"
    if s.get("voids"):
        return f"{base} ({s['voids']} void)"
    return base

RESULT_ICON = {"win": "✅ Win", "loss": "❌ Loss", "push": "➡️ Push", "void": "🚫 Void", None: "⏳ Open"}


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
    if result == "void":
        return prop_result or final_score or "Void / DNP"

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


def _http_get_json(url: str, retries: int = 3) -> Optional[dict]:
    """GET JSON with a browser User-Agent and exponential backoff. None on failure."""
    last_err = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": _MLB_UA})
            with urllib.request.urlopen(req, timeout=10) as r:
                return json.loads(r.read())
        except Exception as e:
            last_err = e
            if attempt < retries - 1:
                time.sleep(1.5 * (attempt + 1))  # 1.5s, 3.0s backoff
    print(f"⚠️  MLB API error after {retries} attempts: {last_err}", file=sys.stderr)
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
    "strikeout": ("pitching", "strikeOuts"),
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
    # Player prop: a mapped stat keyword + a side (Over/Under or N+).
    if any(k in low for k in PROP_STAT_MAP) and re.search(r'\b(over|under)\b|\d+\+', low):
        return "prop"
    return "ml"


def _normalize_name(s: str) -> str:
    """Lowercase, strip accents and punctuation for name matching."""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r'[^a-z\s]', '', s.lower()).strip()


def extract_prop(bet: str, line_num) -> Optional[dict]:
    """
    Parse a player prop. Returns {player, stat_group, stat_key, side, threshold}
    or None if any component can't be resolved (caller then skips — never guesses).
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
    for kw in sorted(PROP_STAT_MAP, key=len, reverse=True):
        if kw in low:
            stat_group, stat_key = PROP_STAT_MAP[kw]
            break
    if not stat_key:
        return None
    player = _normalize_name(player_cut)
    if not player:
        return None
    return {"player": player, "stat_group": stat_group, "stat_key": stat_key,
            "side": side, "threshold": threshold}


def resolve_prop_value(box: dict, player_norm: str, stat_group: str, stat_key: str):
    """
    Find `player_norm` (matched on last name) across both teams in the boxscore and
    return their stat value. Returns (value, None) on success, or (None, reason) on
    failure — including a same-last-name collision, which is skipped not guessed.
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
    stats = pdata.get("stats", {}).get(stat_group, {})
    if not stats or stat_key not in stats:
        return None, f"no {stat_group}.{stat_key} stat for player (did not play that role?)"
    return stats[stat_key], None


def prop_outcome(actual, side: str, threshold: float) -> str:
    """win/loss/push for an Over/Under prop given the actual stat value."""
    if actual == threshold:
        return "push"
    if side == "over":
        return "win" if actual > threshold else "loss"
    return "win" if actual < threshold else "loss"


def find_mlb_game_for_bet(date: str, bet: str) -> Optional[dict]:
    """Find the final game on `date` whose home/away team name appears in `bet`. None if none/not final."""
    low = bet.lower()
    for game in fetch_mlb_schedule(date):
        home = game["teams"]["home"]["team"]["name"]
        away = game["teams"]["away"]["team"]["name"]
        # Match on the distinctive last word of each team name (e.g. "pirates", "twins").
        if home.split()[-1].lower() in low or away.split()[-1].lower() in low:
            if "Final" not in game.get("status", {}).get("detailedState", ""):
                return None
            return _game_result_dict(game, home.lower())
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

    settled_all = [p for p in picks if p.get("result") in {"win", "loss", "push"}]
    open_picks = [p for p in picks if p.get("result") is None]
    void_picks = [p for p in picks if p.get("result") == "void"]

    diff = v1["units_net"] - v2["units_net"]
    if diff > 0:
        leader = f"V1-Trends by {diff:.2f}u"
    elif diff < 0:
        leader = f"V2-Sharp by {abs(diff):.2f}u"
    else:
        leader = "Tied"

    print(f"\n📊 BETTING TRACKER — {today}")
    void_label = f" · {len(void_picks)} void" if void_picks else ""
    print(f"{len(picks)} picks tracked · {cb['settled']} settled · {cb['open']} open{void_label}\n")
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
        pl_str = "void" if result == "void" else fmt_net(p.get("units_won_lost") or 0) if result else "pending"
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
        line_num = p.get("line_num")

        if sport != "MLB":
            skipped.append((p["id"], f"sport={sport} — only MLB auto-resolves (resolve manually)"))
            continue

        kind = classify_bet(p)

        # ── Player Prop: resolve from the boxscore. Hard guard — never fall through. ──
        if kind == "prop":
            spec = extract_prop(bet, line_num)
            if spec is None:
                skipped.append((p["id"], "prop: could not parse player/stat/side/threshold — resolve manually"))
                continue
            game = find_mlb_game_for_bet(date, bet)
            if game is None:
                skipped.append((p["id"], f"prop: game not found or not final on {date}"))
                continue
            box = fetch_mlb_boxscore(game["game_pk"])
            if box is None:
                skipped.append((p["id"], "prop: boxscore fetch failed (API blocked?) — left open"))
                continue
            value, reason = resolve_prop_value(box, spec["player"], spec["stat_group"], spec["stat_key"])
            if reason:
                skipped.append((p["id"], f"prop: {reason}"))
                continue
            outcome = prop_outcome(value, spec["side"], spec["threshold"])
            p["result"] = outcome
            p["units_won_lost"] = calc_units_won_lost(p["line"], p["units"], outcome)
            p["final_score"] = game["final_score"]
            p["prop_result"] = f"{value} {spec['stat_key']}"
            p["prop_margin"] = int(value - spec["threshold"]) if float(value).is_integer() else round(value - spec["threshold"], 1)
            sign = "+" if p["units_won_lost"] >= 0 else ""
            print(f"✅ {p['id']}: {outcome.upper()} — {value} {spec['stat_key']} vs {spec['side']} {spec['threshold']} → {sign}{p['units_won_lost']}u")
            resolved.append(p["id"])
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
