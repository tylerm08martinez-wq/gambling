"""V3-Value de-vig / CLV engine — the pure, deterministic core of sports-betting-value.

Extracted out of the SKILL.md prompt (#44) so the de-vig + closing-line-value math
runs as tested code, not in-prompt arithmetic. No I/O — fully table-testable. The
formulas, thresholds, and worked examples are documented in the skill's REFERENCE.md;
the four autoeval fixtures encode the hand-verified answer key these functions
reproduce (experiments: skills/sports-betting-value/autoeval/fixtures.py).

One question drives every market: is a price I can take right now better than the
de-vigged Pinnacle (book_id 2) fair line? Beat it by ≥2% (game lines) / ≥3% (props)
and it's a CLV-Positive +EV candidate; otherwise sit out. Steam is confirmation-only.

Pipeline per market: implied prob -> de-vig Pinnacle to fair_p -> projected CLV
(fair_p / p_best - 1) -> gate by market -> fractional-Kelly units (hard cap 2u).
"""

import re

# --- thresholds (REFERENCE.md §3, §5) ---------------------------------------------
GAME_LINE_GATE = 0.02   # ≥2% projected CLV to log a game line (ML / spread / total)
PLAYER_PROP_GATE = 0.03  # ≥3% for player props (noisier; needs a fatter edge)

# Unit sizing keys off the ½-Kelly stake table in REFERENCE.md §5. The "⅛–¼ Kelly"
# line there is the variance philosophy; the unit *boundaries* are defined on ½-Kelly,
# which is what reproduces the fixtures. Hard cap 2u, no exceptions.
KELLY_FRACTION_FOR_SIZING = 0.5
MIN_HALF_KELLY_STAKE = 0.005   # < ~0.5% bankroll -> 0u (pass)
BIG_HALF_KELLY_STAKE = 0.015   # > ~1.5% bankroll, with CLV≥4-5% + confirmation -> 2u
TWO_UNIT_MIN_CLV = 0.04
MAX_UNITS = 2

# --- steam (REFERENCE.md §6) -------------------------------------------------------
STEAM_MIN_BOOKS = 3   # 3+ books off the opening line, same direction = steam
MEGA_STEAM_BOOKS = 4  # 4+ = mega steam


# ==================================================================================
# implied probability
# ==================================================================================
def american_to_prob(odds) -> float:
    """American odds -> implied probability. Accepts int/float or a string like '+120'."""
    o = _parse_odds(odds)
    if o < 0:
        return (-o) / (-o + 100.0)
    return 100.0 / (o + 100.0)


def prob_to_decimal(p: float) -> float:
    """Implied probability -> decimal odds (1/p)."""
    return 1.0 / p


# ==================================================================================
# de-vig — strip the overround to a fair probability
# ==================================================================================
def multiplicative_devig(p_a: float, p_b: float):
    """Default for two-way ML / props: fair_i = p_i / (p_a + p_b). Returns (fair_a, fair_b)."""
    s = p_a + p_b
    return p_a / s, p_b / s


def power_devig(p_a: float, p_b: float, iterations: int = 80):
    """Spreads / totals / heavy favorites: solve k s.t. p_a^k + p_b^k = 1, fair_i = p_i^k.

    Bisection on k ∈ [0.5, 1.5] (REFERENCE.md §2). Spreads the vig correctly where the
    multiplicative method under-corrects the longshot. Returns (fair_a, fair_b) which
    sum to 1 by construction.
    """
    lo, hi = 0.5, 1.5
    for _ in range(iterations):
        k = (lo + hi) / 2.0
        if p_a ** k + p_b ** k > 1.0:
            lo = k   # probs too big -> need a larger exponent
        else:
            hi = k
    k = (lo + hi) / 2.0
    return p_a ** k, p_b ** k


def devig_method(market: str) -> str:
    """'power' for spreads/totals, 'multiplicative' for moneylines/props (REFERENCE.md §2)."""
    kind = (market or "").strip().lower()
    if kind.startswith(("spread", "total", "run line", "puck line", "alt ")):
        return "power"
    return "multiplicative"


def fair_two_way(odds_a, odds_b, market: str):
    """De-vig a two-way market's American prices -> (fair_a, fair_b), method by market."""
    p_a, p_b = american_to_prob(odds_a), american_to_prob(odds_b)
    if devig_method(market) == "power":
        return power_devig(p_a, p_b)
    return multiplicative_devig(p_a, p_b)


# ==================================================================================
# the +EV / CLV gate
# ==================================================================================
def projected_clv(fair_p: float, p_best: float) -> float:
    """Projected closing-line-value / edge% = fair_p / p_best - 1 (the ranking key).

    Positive when the price you'd take implies a *lower* win prob than Pinnacle fair.
    """
    return fair_p / p_best - 1.0


def ev_per_dollar(fair_p: float, p_best: float) -> float:
    """Expected value per $1 staked = fair_p * decimal_odds - 1, decimal_odds = 1/p_best."""
    return fair_p * prob_to_decimal(p_best) - 1.0


def gate_threshold(market: str) -> float:
    """Minimum projected CLV to log: 3% for player props, 2% for game lines."""
    return PLAYER_PROP_GATE if _is_prop(market) else GAME_LINE_GATE


def clears_gate(clv: float, market: str) -> bool:
    """Does this projected CLV clear the gate for this market type?"""
    return clv >= gate_threshold(market)


# ==================================================================================
# sizing — fractional Kelly -> units
# ==================================================================================
def kelly_fraction(fair_p: float, p_best: float) -> float:
    """Full-Kelly stake as a fraction of bankroll: (fair_p*d - 1)/(d - 1), d = 1/p_best."""
    d = prob_to_decimal(p_best)
    if d <= 1.0:
        return 0.0
    return (fair_p * d - 1.0) / (d - 1.0)


def units_from_clv(fair_p: float, p_best: float, clv: float, market: str,
                   confirmation: bool = False) -> int:
    """Map fractional Kelly -> 0/1/2 units (REFERENCE.md §5). Hard cap 2u, no exceptions.

    0u when the ½-Kelly stake is < ~0.5% bankroll; 2u only on a strong edge (½-Kelly
    > ~1.5%, CLV ≥ 4-5%, *and* a confirmation signal); 1u otherwise. A Kelly output
    implying ≥3u almost always means a stale line — it caps at 2u, never scales up.
    """
    half_kelly = KELLY_FRACTION_FOR_SIZING * max(kelly_fraction(fair_p, p_best), 0.0)
    if half_kelly < MIN_HALF_KELLY_STAKE:
        return 0
    if half_kelly > BIG_HALF_KELLY_STAKE and clv >= TWO_UNIT_MIN_CLV and confirmation:
        return MAX_UNITS
    return 1


# ==================================================================================
# steam — confirmation only, never a standalone pick (REFERENCE.md §6)
# ==================================================================================
def classify_steam(opening, current_by_book: dict, pinnacle_now, side_is_favorite: bool,
                   market: str) -> dict:
    """Classify line movement as steam. Confirmation-only: it never *creates* a pick.

    Steam = STEAM_MIN_BOOKS+ books moved the same direction off `opening`. Legit only
    when the move is *toward* the current Pinnacle number; blowing *past* Pinnacle is
    retail overreaction (`usable` False). Direction is read in implied-prob space so it
    works for both ML/props and (line-based) spreads/totals via the favorite flag.
    """
    open_p = american_to_prob(opening)
    pin_p = american_to_prob(pinnacle_now)
    # A move "toward Pinnacle" shortens the price in the same direction Pinnacle sits.
    same_dir = 0
    for cur in current_by_book.values():
        cur_p = american_to_prob(cur)
        if (cur_p - open_p) > 0:   # price shortened (prob up) on this side
            same_dir += 1
    n = len(current_by_book)
    is_steam = same_dir >= STEAM_MIN_BOOKS
    is_mega = same_dir >= MEGA_STEAM_BOOKS
    # Average current book prob vs Pinnacle: still short of / at Pinnacle = toward it;
    # past Pinnacle (books more aggressive than the sharp number) = overreaction.
    avg_cur_p = sum(american_to_prob(c) for c in current_by_book.values()) / max(n, 1)
    toward_pinnacle = is_steam and (avg_cur_p <= pin_p + 1e-9)
    return {
        "is_steam": is_steam,
        "is_mega": is_mega,
        "books": same_dir,
        "toward_pinnacle": toward_pinnacle,
        "usable": bool(toward_pinnacle),   # confirmation signal only when toward Pinnacle
    }


# ==================================================================================
# board snapshot -> decision (the end-to-end entry point)
# ==================================================================================
def evaluate_market(market_snapshot: dict, confirmation: bool = False) -> dict:
    """Evaluate one two-way market snapshot -> {action, side, book, clv, units, ...}.

    `market_snapshot` carries `market`, `pinnacle` ({side: american}), and
    `best_book_prices` ({side: 'price (BOOK)' | american}). Picks the side with the
    highest *positive* projected CLV, then: clears gate -> log; positive but below
    gate -> reject; nothing positive -> no_bet (covers the post-steam chase).
    """
    market = market_snapshot.get("market", "")
    pinnacle = market_snapshot.get("pinnacle", {})
    best = market_snapshot.get("best_book_prices", {})
    sides = list(pinnacle.keys())
    if len(sides) != 2:
        return {"action": "no_bet", "market": market, "reason": "need a two-way Pinnacle market",
                "side": None, "book": None, "clv": None, "best_clv": None, "units": 0,
                "edge_type": None, "fair": {}}

    fair_a, fair_b = fair_two_way(pinnacle[sides[0]], pinnacle[sides[1]], market)
    fair = {sides[0]: fair_a, sides[1]: fair_b}

    candidates = []
    for side in sides:
        if side not in best:
            continue
        odds, book = _parse_best(best[side])
        p_best = american_to_prob(odds)
        clv = projected_clv(fair[side], p_best)
        candidates.append({"side": side, "book": book, "odds": odds, "p_best": p_best,
                           "clv": clv, "fair_p": fair[side]})

    result = {"action": "no_bet", "market": market, "side": None, "book": None,
              "clv": None, "best_clv": None, "units": 0, "edge_type": None, "fair": fair}
    if not candidates:
        result["reason"] = "no available price to take"
        return result

    top = max(candidates, key=lambda c: c["clv"])
    result["best_clv"] = top["clv"]
    if top["clv"] <= 0:
        result["reason"] = "no positive CLV — every price is at/worse than Pinnacle fair (chasing captures none)"
        return result

    units = units_from_clv(top["fair_p"], top["p_best"], top["clv"], market, confirmation)
    result.update(side=top["side"], book=top["book"], clv=top["clv"],
                  units=units, edge_type="clv_value")
    if clears_gate(top["clv"], market) and units >= 1:
        result["action"] = "log"
    else:
        result["action"] = "reject"
        result["reason"] = (
            f"+{top['clv']*100:.1f}% CLV is below the {gate_threshold(market)*100:.0f}% "
            f"{'player-prop' if _is_prop(market) else 'game-line'} gate"
            if units >= 1 else "stake below the 1u minimum (½-Kelly < 0.5% bankroll)"
        )
    return result


def evaluate_board(board: dict) -> dict:
    """Run the engine over a board snapshot -> {action, picks, rejected, considered}.

    A board is either a single market (top-level `pinnacle`/`best_book_prices`) or a
    slate (`markets: [...]`). Board action: `log` if anything cleared the gate; for a
    single market, surface that market's own verdict (reject / no_bet); for a slate
    with no logged pick, `sit_out`.
    """
    if "markets" in board:
        markets = board["markets"]
    else:
        markets = [board]

    considered = [evaluate_market(m) for m in markets]
    picks = [r for r in considered if r["action"] == "log"]
    rejected = [r for r in considered if r["action"] == "reject"]

    if picks:
        action = "log"
    elif len(considered) == 1:
        action = considered[0]["action"]   # single market: its own verdict (reject/no_bet)
    else:
        action = "sit_out"                 # slate, nothing beat fair anywhere

    return {"action": action, "picks": picks, "rejected": rejected, "considered": considered}


# ==================================================================================
# helpers
# ==================================================================================
def _is_prop(market: str) -> bool:
    return "prop" in (market or "").strip().lower()


def _parse_odds(v) -> int:
    """'+120' / '-118' / 120 / -118 -> int."""
    if isinstance(v, (int, float)):
        return int(v)
    return int(str(v).strip().replace("+", ""))


_BEST_RE = re.compile(r"^\s*([+-]?\d+)\s*(?:\(([^)]+)\))?\s*$")


def _parse_best(v):
    """'+120 (DK)' -> (120, 'DK'); a bare number/string -> (odds, None);
    a dict {'odds':..,'book':..} -> (odds, book)."""
    if isinstance(v, dict):
        return _parse_odds(v.get("odds")), v.get("book")
    if isinstance(v, (int, float)):
        return int(v), None
    m = _BEST_RE.match(str(v))
    if not m:
        raise ValueError(f"unparseable best price: {v!r}")
    return int(m.group(1)), m.group(2)


if __name__ == "__main__":
    import json
    import sys

    board = json.load(sys.stdin)
    json.dump(evaluate_board(board), sys.stdout, indent=1)
