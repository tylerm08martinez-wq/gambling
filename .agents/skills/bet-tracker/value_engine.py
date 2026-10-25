"""V3-Value de-vig / CLV engine — the pure, deterministic core of sports-betting-value.

Extracted out of the SKILL.md prompt (#44) so the de-vig + closing-line-value math
runs as tested code, not in-prompt arithmetic. No I/O — fully table-testable. The
formulas, thresholds, and worked examples are documented in the skill's REFERENCE.md;
the four autoeval fixtures encode the hand-verified answer key these functions
reproduce (experiments: skills/sports-betting-value/autoeval/fixtures.py).

One question drives every market: is a price I can take right now better than the
fair line? Beat it by ≥2% (game lines) / ≥3% (props) and it's a CLV-Positive +EV
candidate; otherwise sit out. Steam is confirmation-only.

The fair line was de-vigged Pinnacle (book_id 2, ADR 0007). Pinnacle has been absent
from the BettingPros feed since about July, so ADR 0011 replaces it with the
**Exchange Benchmark**: the median de-vigged price across low-hold exchange operators
quoting the identical line (`exchange_benchmark`, `scan_market`): Novig, Kalshi,
Polymarket (one operator with Polymarket US) and ProphetX, each quote two-way, hold
-0.5% to 3%, updated within 60 minutes, at least 2 operators. Retail sportsbooks are
the only candidates, compared only at the same number. `evaluate_market` still
accepts a `pinnacle` key for the existing boards and fixtures.

The market kind (moneyline / spread / total / prop, `market_kind`) is explicit and
picks both the de-vig and the gate: **power de-vig for every game line** (moneyline,
spread, total; ADR 0011 moved moneylines off multiplicative, which inflated
longshots) and multiplicative for player props; a 2% gate for game lines, 3% for props.

Pipeline per market: implied prob -> de-vig the benchmark to fair_p -> projected CLV
(fair_p / p_best - 1) -> gate by market kind -> fractional-Kelly units (hard cap 2u).
"""

import re
import statistics
from datetime import datetime, timezone

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

# --- market kind (ADR 0011) --------------------------------------------------------
# The kind decides the de-vig method and the gate, so it is passed explicitly and looked
# up in an explicit table. It is never inferred by searching the label: the old
# `"prop" in label` test gave "points" and "PRA" the 2% game-line gate.
MARKET_KINDS = {"moneyline", "spread", "total", "prop"}
GAME_KINDS = frozenset({"moneyline", "spread", "total"})

# Every label an existing caller passes today, normalised (lower-case, single spaces,
# a trailing line number such as "total 210.5" / "spread -3.5" dropped):
#   clv_fetch / close_capture -> "prop"; clv_backfill -> the pick's bet_type
#   (tracker.classify_bet: prop/total/spread/rl/ml) or its "moneyline" default;
#   V3 SKILL boards -> "moneyline" / "player_prop" / "total 210.5"; the old
#   devig_method power list -> "run line" / "puck line" / "pl".
_KIND_BY_LABEL = {
    "moneyline": "moneyline", "money line": "moneyline", "ml": "moneyline",
    "spread": "spread", "rl": "spread", "run line": "spread", "runline": "spread",
    "pl": "spread", "puck line": "spread", "puckline": "spread",
    "alt spread": "spread", "alt run line": "spread", "alt puck line": "spread",
    "total": "total", "totals": "total", "game total": "total", "alt total": "total",
    "prop": "prop", "props": "prop", "player_prop": "prop", "player prop": "prop",
    "player props": "prop",
}
_TRAILING_LINE_RE = re.compile(r"\s+[+-]?\d+(?:\.\d+)?$")

# --- Exchange Benchmark (ADR 0011) -------------------------------------------------
# Low-hold venues whose de-vigged prices form the fair line: Novig (60), Kalshi (68),
# Polymarket (73) and Polymarket US (75), ProphetX (38).
BENCHMARK_BOOKS = {60, 68, 73, 75, 38}
# Polymarket and Polymarket US are one operator; every other book is its own operator.
OPERATOR = {73: "polymarket", 75: "polymarket"}
# Retail sportsbooks: the only candidates. FanDuel 10, DraftKings 12, Caesars 13,
# Fanatics 14, BetRivers 18, BetMGM 19, bet365 24, theScore Bet 33, Fliff 39, Betr 45,
# Hard Rock 49. Exchanges, DFS / pick'em venues and the skins SugarHouse (15) and
# PartyCasino (27) are never candidates.
RETAIL_BOOKS = {10, 12, 13, 14, 18, 19, 24, 33, 39, 45, 49}
MAX_BENCHMARK_HOLD = 0.03   # a benchmark quote's two-way hold must be at most 3%
MIN_BENCHMARK_HOLD = -0.005  # ... and at least -0.5%: a deeper underround isn't a real price
MAX_QUOTE_AGE_MIN = 60      # ... and updated within 60 minutes of the scan
MIN_OPERATORS = 2           # fewer distinct operators -> no benchmark, market skipped
MAX_RETAIL_QUOTE_AGE_MIN = 24 * 60  # a retail candidate updated over 24h ago is a dead rung
MAX_FUTURE_SKEW_MIN = 5     # a quote stamped more than 5 min after the scan is rejected
PLACEHOLDER_ODDS = 10000    # |odds| at or above this is the feed's suspended-side placeholder


# ==================================================================================
# market kind
# ==================================================================================
def market_kind(label) -> str:
    """Map a market label to one of MARKET_KINDS through an explicit table.

    Accepts the kinds themselves and every label existing callers pass. Raises
    ValueError on anything else, including a bare stat name ("points", "PRA"): the
    kind must be stated, never guessed from the label's wording.
    """
    if not isinstance(label, str):
        raise ValueError(f"market kind must be a label string, got {label!r}")
    norm = " ".join(label.strip().lower().split())
    norm = _TRAILING_LINE_RE.sub("", norm)
    try:
        return _KIND_BY_LABEL[norm]
    except KeyError:
        raise ValueError(
            f"unknown market kind {label!r}; pass one of {sorted(MARKET_KINDS)}") from None


# ==================================================================================
# implied probability
# ==================================================================================
def american_to_prob(odds) -> float:
    """American odds -> implied probability. Accepts int/float or a string like '+120'.

    NB: tracker.py has a sibling `american_to_implied_prob`. This engine keeps its own
    copy on purpose so it stays import-isolated (no dependency on the 1.5k-line tracker
    module or its I/O); consolidating tracker onto this engine is follow-up, not #44.
    """
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
def _require_probabilities(p_a, p_b) -> None:
    """Both inputs must be implied probabilities strictly inside (0, 1).

    Passing American odds by mistake used to reach `p ** k` with a negative base and
    die as a complex-number TypeError deep inside power_devig (or, multiplicatively,
    return nonsense silently). Fail at the boundary with a clear ValueError instead.
    """
    for p in (p_a, p_b):
        if isinstance(p, bool) or not isinstance(p, (int, float)) or not 0.0 < p < 1.0:
            raise ValueError(
                f"de-vig needs implied probabilities in (0, 1), got {p_a!r}, {p_b!r} "
                "(convert American odds with american_to_prob first)")


def multiplicative_devig(p_a: float, p_b: float):
    """Two-way props: fair_i = p_i / (p_a + p_b). Returns (fair_a, fair_b).

    Raises ValueError unless both inputs are probabilities in (0, 1)."""
    _require_probabilities(p_a, p_b)
    s = p_a + p_b
    return p_a / s, p_b / s


def power_devig(p_a: float, p_b: float, iterations: int = 80):
    """Every game line (ML / spread / total): solve k s.t. p_a^k + p_b^k = 1, fair_i = p_i^k.

    Bisection on k ∈ [0.5, 1.5] (REFERENCE.md §2). Spreads the vig correctly where the
    multiplicative method under-corrects the longshot. Returns (fair_a, fair_b) which
    sum to 1 by construction. Raises ValueError unless both inputs are probabilities
    in (0, 1).
    """
    _require_probabilities(p_a, p_b)
    lo, hi = 0.5, 1.5
    # Expand the upper bound so the root is always bracketed. Wide/lopsided markets
    # (large overround) push k above the nominal 1.5; a clamped k would silently return
    # fair probs that don't sum to 1. Keep doubling hi until f(hi) < 1 brackets the root.
    while p_a ** hi + p_b ** hi > 1.0 and hi < 1e6:
        lo, hi = hi, hi * 2.0
    # Likewise lower the bottom bound for an underround pair (p_a + p_b < 1, k < 1):
    # without this, (0.001, 0.6) returned fair probs summing to 0.806.
    while p_a ** lo + p_b ** lo < 1.0 and lo > 1e-6:
        lo, hi = lo / 2.0, lo
    for _ in range(iterations):
        k = (lo + hi) / 2.0
        if p_a ** k + p_b ** k > 1.0:
            lo = k   # probs too big -> need a larger exponent
        else:
            hi = k
    k = (lo + hi) / 2.0
    return p_a ** k, p_b ** k


def devig_method(market: str) -> str:
    """'power' for every game line (moneyline, spread, total), 'multiplicative' for props.

    ADR 0011. `market` is a kind or any label `market_kind` knows (tracker's `bet_type`
    tokens such as 'rl', or the SKILL's 'total 210.5'); an unknown label raises
    ValueError. Moneylines were multiplicative before ADR 0011, which inflates the
    longshot: on a heavy favourite it can turn a negative CLV positive.
    """
    return "power" if market_kind(market) in GAME_KINDS else "multiplicative"


def fair_two_way(odds_a, odds_b, market: str):
    """De-vig a two-way market's American prices -> (fair_a, fair_b), method by kind.

    `market` is a kind or a label `market_kind` maps; unknown labels raise ValueError."""
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
    """Minimum projected CLV to log: 3% for player props, 2% for the three game kinds.

    `market` is a kind or a label `market_kind` maps; anything else raises ValueError
    (it used to fall through to the 2% game-line gate)."""
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
def classify_steam(opening, current_by_book: dict, pinnacle_now) -> dict:
    """Classify line movement as steam. Confirmation-only: it never *creates* a pick.

    Steam = STEAM_MIN_BOOKS+ books moved the same direction (shortened the price) off
    `opening`. Legit only when the move is *toward* the current Pinnacle number; blowing
    *past* Pinnacle is retail overreaction (`usable` False). Read in implied-prob space,
    so this covers moneylines/props only — spreads/totals move in line units and are out
    of scope for this helper.
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
    # A snapshot may carry a confirmation signal (e.g. usable steam / pm_win_pct agreement)
    # the skill computed separately; it can only *raise* size to 2u, never create a pick.
    confirmation = confirmation or bool(market_snapshot.get("confirmation"))
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
    picks = sorted((r for r in considered if r["action"] == "log"),
                   key=lambda r: r["clv"], reverse=True)   # rank by CLV desc (SKILL.md spec)
    rejected = [r for r in considered if r["action"] == "reject"]

    if picks:
        action = "log"
    elif len(considered) == 1:
        action = considered[0]["action"]   # single market: its own verdict (reject/no_bet)
    else:
        action = "sit_out"                 # slate, nothing beat fair anywhere

    return {"action": action, "picks": picks, "rejected": rejected, "considered": considered}


# ==================================================================================
# Exchange Benchmark (ADR 0011) — the fair line now that Pinnacle is off the feed
# ==================================================================================
# A quote is one book's two-way price at one line:
#   {"book_id": int, "line": number | None, "odds_a": american, "odds_b": american,
#    "updated": "YYYY-MM-DD HH:MM:SS" (UTC, as BettingPros sends it) | datetime}
# `odds_a` / `odds_b` are the market's two selections in a fixed order (see
# `quotes_from_offer`). A spread quote's `line` is selection A's signed number, so
# +2.5 and +3 are different lines. A moneyline has no number: its line is ignored.

def operator_of(book_id):
    """The operator a book belongs to (Polymarket + Polymarket US are one)."""
    return OPERATOR.get(book_id, book_id)


def quote_hold(quote):
    """Two-way hold (overround) of a quote: p_a + p_b - 1. None if either side is
    missing or unparseable."""
    try:
        return american_to_prob(quote["odds_a"]) + american_to_prob(quote["odds_b"]) - 1.0
    except (KeyError, TypeError, OddsParseError):
        return None


def _two_sided(quote) -> bool:
    return quote.get("odds_a") is not None and quote.get("odds_b") is not None


def _same_line(a, b, kind) -> bool:
    if kind == "moneyline":
        return True
    try:
        return abs(float(a) - float(b)) < 1e-9
    except (TypeError, ValueError):
        return False


def is_placeholder_odds(odds) -> bool:
    """True for the feed's suspended-side placeholders (+99900 / -99900 and the like).

    BettingPros marks a side it isn't really offering with an absurd price. Paired with
    a live side, +99900/-120 "holds" about -45% and sailed through an upper-bound-only
    hold filter, producing a +90% "edge". Any |odds| ≥ PLACEHOLDER_ODDS is not a price."""
    try:
        return abs(_parse_odds(odds)) >= PLACEHOLDER_ODDS
    except OddsParseError:
        return False


def _require_aware(now) -> datetime:
    """The scan clock must be a timezone-aware datetime (naive raises ValueError)."""
    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
        raise ValueError(f"`now` must be a timezone-aware datetime, got {now!r}")
    return now


def _as_utc(ts):
    """'2026-10-25 02:09:30' / ISO string / datetime -> aware UTC datetime, else None.

    BettingPros `updated` strings are UTC without an offset, so a naive value is read
    as UTC; an aware one is converted."""
    if isinstance(ts, datetime):
        dt = ts
    elif isinstance(ts, str) and ts.strip():
        try:
            dt = datetime.fromisoformat(ts.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _age_minutes(quote, now):
    """Minutes from the quote's `updated` to `now` (negative = stamped after `now`)."""
    now = _require_aware(now)
    updated = _as_utc(quote.get("updated"))
    if updated is None:
        return None
    return (now - updated).total_seconds() / 60.0


def _age_ok(age, max_age_min) -> bool:
    return age is not None and -MAX_FUTURE_SKEW_MIN - 1e-9 <= age <= max_age_min + 1e-9


def benchmark_eligible(quote, line, kind, now) -> bool:
    """Does this quote count toward the Exchange Benchmark at `line`?

    Benchmark book, both sides quoted with real prices (no placeholder), identical
    line, hold between -0.5% and 3%, updated no more than 60 minutes before `now` and
    no more than 5 minutes after it. A quote with no parseable `updated` is excluded,
    never assumed fresh. `now` must be timezone-aware."""
    _require_aware(now)
    if quote.get("book_id") not in BENCHMARK_BOOKS or not _two_sided(quote):
        return False
    if is_placeholder_odds(quote["odds_a"]) or is_placeholder_odds(quote["odds_b"]):
        return False
    if not _same_line(quote.get("line"), line, kind):
        return False
    hold = quote_hold(quote)
    if hold is None or not (MIN_BENCHMARK_HOLD - 1e-12 <= hold <= MAX_BENCHMARK_HOLD + 1e-12):
        return False
    return _age_ok(_age_minutes(quote, now), MAX_QUOTE_AGE_MIN)


def exchange_benchmark(quotes, line, kind, now):
    """The Exchange Benchmark fair price at `line`, or None when there isn't one.

    Keeps benchmark quotes eligible at exactly `line` (`benchmark_eligible`), keeps the
    freshest per operator, and needs at least MIN_OPERATORS operators. The fair price
    per side is the median of the per-operator de-vigged prices (power for game kinds,
    multiplicative for props). Returns {fair_a, fair_b, operators, quotes_used}.
    `now` must be a timezone-aware datetime.
    """
    kind = market_kind(kind)
    _require_aware(now)
    freshest = {}
    for quote in quotes:
        if not benchmark_eligible(quote, line, kind, now):
            continue
        op = operator_of(quote["book_id"])
        held = freshest.get(op)
        if held is None or _age_minutes(quote, now) < _age_minutes(held, now):
            freshest[op] = quote
    if len(freshest) < MIN_OPERATORS:
        return None
    operators = sorted(freshest, key=str)
    used = [freshest[op] for op in operators]
    fairs = [fair_two_way(u["odds_a"], u["odds_b"], kind) for u in used]
    return {
        "fair_a": statistics.median(f[0] for f in fairs),
        "fair_b": statistics.median(f[1] for f in fairs),
        "operators": operators,
        "quotes_used": used,
    }


def _usable_lines(book):
    """A book's priced, live lines from a raw /offers selection (drops is_off/inactive)."""
    out = []
    for ln in book.get("lines") or []:
        if ln.get("cost") is None or ln.get("is_off") or ln.get("active") is False:
            continue
        try:
            cost = _parse_odds(ln["cost"])
        except OddsParseError:
            continue
        out.append((ln.get("line"), cost, ln.get("updated"), bool(ln.get("main"))))
    return out


def _older(ts_a, ts_b):
    """The staler of two `updated` stamps (a pair is only as fresh as its older side)."""
    da, db = _as_utc(ts_a), _as_utc(ts_b)
    if da is None or db is None:
        return None
    return ts_a if da <= db else ts_b


def quotes_from_offer(offer, kind):
    """Turn one raw BettingPros /offers market into two-way quotes. Pure; no I/O.

    `offer` is one element of the feed's `offers` list, with exactly two selections
    (A then B, in feed order). Each book's selection-A line is paired with its
    selection-B line at the same number (total, prop), or at the negated number
    (spread: A -6.5 with B +6.5, quoted at A's line). A moneyline has no number, so
    each book's main price on each side is paired. Lines flagged `is_off` or inactive
    are dropped; a side a book doesn't price leaves no quote. Returns
    {"labels": (label_a, label_b), "quotes": [quote, ...]}.
    """
    kind = market_kind(kind)
    sels = offer.get("selections") or []
    if len(sels) != 2:
        return {"labels": None, "quotes": []}
    labels = tuple((s.get("label") or s.get("selection") or "").strip() for s in sels)
    books_b = {b.get("id"): _usable_lines(b) for b in sels[1].get("books") or []}
    quotes = []
    for book in sels[0].get("books") or []:
        bid = book.get("id")
        lines_a, lines_b = _usable_lines(book), books_b.get(bid) or []
        if not lines_a or not lines_b:
            continue
        if kind == "moneyline":
            la = next((x for x in lines_a if x[3]), lines_a[0])
            lb = next((x for x in lines_b if x[3]), lines_b[0])
            quotes.append({"book_id": bid, "line": la[0], "odds_a": la[1], "odds_b": lb[1],
                           "updated": _older(la[2], lb[2])})
            continue
        for line_a, cost_a, upd_a, _ in lines_a:
            try:
                want = -float(line_a) if kind == "spread" else float(line_a)
            except (TypeError, ValueError):
                continue
            match = [x for x in lines_b if x[0] is not None and abs(float(x[0]) - want) < 1e-9]
            if not match:
                continue
            line_b, cost_b, upd_b, _ = match[0]
            quotes.append({"book_id": bid, "line": float(line_a), "odds_a": cost_a,
                           "odds_b": cost_b, "updated": _older(upd_a, upd_b)})
    return {"labels": labels, "quotes": quotes}


def _line_key(line, kind):
    if kind == "moneyline":
        return None
    try:
        return round(float(line), 6)
    except (TypeError, ValueError):
        return ("unparseable", line)


def scan_market(quotes, kind, now):
    """Score every retail price in one market against the Exchange Benchmark.

    Groups quotes by line. For each retail quote (RETAIL_BOOKS only — a benchmark or
    any other book is never a candidate) and each side it prices, computes projected
    CLV against the benchmark at that same line and returns one row per side:
    `log` (clears the kind's gate with ≥1u), `reject` (positive but below the gate or
    the 1u stake floor) or `no_bet` (at or worse than fair). A line with no
    benchmark yields no rows: a price is never compared with a different number.

    A retail quote must be updated within MAX_RETAIL_QUOTE_AGE_MIN (24h) of `now` and
    no more than 5 minutes after it (dead rungs linger on the feed for days); a
    placeholder side (|odds| ≥ 10000) gives no row. Each row carries `quote_age_min`
    and `benchmark_max_age_min` so the freshness rules can be tightened from data. A
    spread row reports its own side's number (side B is the negation of the quote's
    line). Rows are sorted by CLV, best first. `now` must be timezone-aware.
    """
    kind = market_kind(kind)
    _require_aware(now)
    gate = gate_threshold(kind)
    benchmarks = {}
    rows = []
    for quote in quotes:
        if quote.get("book_id") not in RETAIL_BOOKS:
            continue
        key = _line_key(quote.get("line"), kind)
        if isinstance(key, tuple):
            continue
        quote_age = _age_minutes(quote, now)
        if not _age_ok(quote_age, MAX_RETAIL_QUOTE_AGE_MIN):
            continue
        if key not in benchmarks:
            benchmarks[key] = exchange_benchmark(quotes, quote.get("line"), kind, now)
        bench = benchmarks[key]
        if bench is None:
            continue
        bench_age = max(_age_minutes(u, now) for u in bench["quotes_used"])
        for side, odds_key, fair_key in (("a", "odds_a", "fair_a"), ("b", "odds_b", "fair_b")):
            odds = quote.get(odds_key)
            if odds is None or is_placeholder_odds(odds):
                continue
            line = quote.get("line")
            if kind == "spread" and side == "b" and line is not None:
                line = -float(line)
            try:
                p_best = american_to_prob(odds)
            except OddsParseError:
                continue
            fair_p = bench[fair_key]
            clv = projected_clv(fair_p, p_best)
            units = units_from_clv(fair_p, p_best, clv, kind) if clv > 0 else 0
            if clv <= 0:
                action, reason = "no_bet", "at or worse than the Exchange Benchmark fair price"
            elif clv >= gate and units >= 1:
                action, reason = "log", None
            elif clv < gate:
                action = "reject"
                reason = (f"+{clv*100:.1f}% CLV is below the {gate*100:.0f}% "
                          f"{'player-prop' if kind == 'prop' else 'game-line'} gate")
            else:
                action, reason = "reject", "stake below the 1u minimum (½-Kelly < 0.5% bankroll)"
            rows.append({
                "book_id": quote["book_id"], "line": line, "side": side,
                "odds": odds, "p_best": p_best, "fair_p": fair_p, "clv": clv,
                "gate": gate, "units": units, "action": action, "reason": reason,
                "edge_type": "clv_value" if clv > 0 else None, "kind": kind,
                "operators": bench["operators"], "updated": quote.get("updated"),
                "quote_age_min": quote_age, "benchmark_max_age_min": bench_age,
            })
    rows.sort(key=lambda r: r["clv"], reverse=True)
    return rows


# ==================================================================================
# helpers
# ==================================================================================
def _is_prop(market: str) -> bool:
    """Kind lookup, not a substring search (raises ValueError on an unknown label)."""
    return market_kind(market) == "prop"


class OddsParseError(ValueError):
    """Raised when a value cannot be read as American odds.

    Subclasses ValueError so pre-existing `except ValueError` callers keep working.
    Exists so callers that legitimately encounter junk (e.g. the CLV backfill reading
    free-text `line` fields written before validation existed) can catch *this*
    specifically and skip the row, instead of blanket-catching ValueError and
    masking a real arithmetic bug.
    """


def _parse_odds(v) -> int:
    """'+120' / '-118' / 120 / -118 -> int.

    Raises OddsParseError on anything else. Guarded because a single malformed
    `line`/`closing_line` in picks.json used to abort the entire daily run: this
    crashed on 'under 17.5' and '' under `set -e` in run-daily-picks.sh, killing
    pick generation before the agent was even invoked (dead 2026-06-03 → 07-25).
    """
    if isinstance(v, bool):                      # bool is an int subclass; never odds
        raise OddsParseError(f"cannot parse odds from bool: {v!r}")
    if isinstance(v, (int, float)):
        return int(v)
    s = str(v).strip().replace("+", "")
    if not re.fullmatch(r"-?\d+", s):
        raise OddsParseError(f"cannot parse American odds from {v!r}")
    return int(s)


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
