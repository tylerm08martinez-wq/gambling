"""CLV fetch — the residential half of the closing-line workflow (ADR 0006, #51).

Builds the `{pick_id: {"close": {side: odds}, "side": ..., "market": "prop"}}` map that
`clv_backfill` consumes, by matching each settled player-prop pick to its BettingPros
CONSENSUS closing line. Runs ONLY from a residential IP — BettingPros 403s datacenter
egress (ADR 0006), which is why this can't live in the cloud nightly resolver.

Why this works without Pinnacle: a player prop is already a two-way market (over + under
priced at the same number), so its de-vigged close is computed exactly like a moneyline.
Pinnacle is absent from the prop grid (#51), so the two-way close comes from BettingPros
Consensus (book 0) via `bettingpros.fetch_offer_ladder` — the full alt-line ladder, so the
entry's line number is matchable even when the displayed main line is split.

Never fabricates: when the market dropped post-game, the player isn't found, or the entry
line number isn't priced on BOTH sides at close, the pick is omitted from the map →
`clv_backfill` keeps it Unmeasured (null clv, not 0.0; preserves tracker.is_measured_clv).

The fetchers are injected so the matching core is unit-tested offline against fixtures
(the same seam-not-monkeypatch discipline as the resolver's Player Prop Sources).
"""

import importlib.util
import re
import sys
from collections import Counter
from pathlib import Path

_DIR = Path(__file__).resolve().parent


def _load(name):
    spec = importlib.util.spec_from_file_location(name, _DIR / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules.setdefault(name, mod)
    spec.loader.exec_module(mod)
    return mod


# sport -> (stat group, stat key) -> BettingPros market_id. Keys are the
# (stat_group, stat_key) that tracker.extract_prop returns via that sport's stat map
# (tracker._stat_map_for_sport). Only stats with a confident BP market are mapped; an
# unmapped stat (or a combined-stat tuple with no market) -> pick skipped (left
# Unmeasured) rather than mis-matched. Market ids are per sport and never borrowed.
STAT_MARKET = {
    # Verified against /v3/markets?sport=MLB on 2026-06-27.
    "MLB": {
        ("pitching", "outs"): 405,        # outs-recorded
        ("pitching", "strikeOuts"): 285,  # strikeouts
        ("pitching", "baseOnBalls"): 408, # walks-allowed
        ("batting", "hits"): 287,         # hits
        ("batting", "totalBases"): 293,   # total-bases
        ("batting", "homeRuns"): 299,     # homeruns
        ("batting", "rbi"): 289,          # rbi
        ("batting", "runs"): 288,         # runs
        ("batting", "stolenBases"): 294,  # steals
        ("batting", "doubles"): 291,      # doubles
    },
    # /v3/markets?sport=NBA, 2026-10-21 (memory: nba-offers-market-ids). The P+A (335),
    # P+R (336) and R+A (337) markets exist but are deliberately unmapped: extract_prop
    # cannot parse those combos (NBA_PROP_STAT_MAP has no entry), so they stay Unmeasured.
    "NBA": {
        ("scoring", "points"): 156,
        ("scoring", "rebounds"): 157,
        ("scoring", "assists"): 151,
        ("scoring", "threes"): 162,
        ("scoring", "steals"): 160,
        ("scoring", "blocks"): 152,
        ("scoring", ("points", "rebounds", "assists")): 338,   # PRA
    },
    # /v3/markets?sport=NFL, discovered live 2026-10-24 (category "player-props").
    "NFL": {
        ("passing", "passingYards"): 103,
        ("passing", "passingAttempts"): 333,
        ("passing", "completions"): 100,
        ("rushing", "rushingYards"): 107,
        ("rushing", "rushingAttempts"): 106,
        ("receiving", "receivingYards"): 105,
        ("receiving", "receptions"): 104,
        ("scrimmage", ("rushingYards", "receivingYards")): 406,  # rushing + receiving yds
    },
}

# sport -> value_engine market kind -> BettingPros game-line market id (#109). The
# same ids v3_scan.MARKETS scans (a test pins the two together). Per sport and never
# borrowed: a wrong id returns an empty market that reads like an outage.
GAME_LINE_MARKET = {
    "MLB": {"moneyline": 122, "total": 175, "spread": 176},   # spread = run line
    "NBA": {"moneyline": 127, "total": 128, "spread": 129},
    "NFL": {"moneyline": 1, "total": 2, "spread": 3},
}

# Sports whose settled/open props get a consensus close. MLB first: its behaviour is
# the original, ADR 0010 path and is unchanged.
CLOSE_SPORTS = ("MLB", "NBA", "NFL")


def _fmt_odds(o):
    """BettingPros odds are bare numbers (104, -120); CLV/de-vig want American strings."""
    o = int(o)
    return f"+{o}" if o > 0 else str(o)


def two_way_at_line(ladders, player_norm, threshold, *, normalize_name):
    """Consensus {'under': odds, 'over': odds} for a player's prop at `threshold`, or None.

    `ladders` is bettingpros.fetch_offer_ladder output. Requires BOTH sides priced at the
    SAME line number as the entry — otherwise the pair isn't a de-viggable two-way and the
    pick stays Unmeasured."""
    t = float(threshold)
    for lad in ladders:
        if normalize_name(lad.get("player") or "") != player_norm:
            continue
        over = (lad.get("sides") or {}).get("over") or {}
        under = (lad.get("sides") or {}).get("under") or {}
        if t in over and t in under:
            return {"under": _fmt_odds(under[t]), "over": _fmt_odds(over[t])}
        return None  # right player, line not priced both sides -> Unmeasured (don't fabricate)
    return None


def market_for_spec(spec, sport="MLB"):
    """BettingPros market_id for an extract_prop spec in `sport` (default MLB, the
    original caller), or None if unmapped/combined. Never falls back to another sport."""
    key = (spec.get("stat_group"), spec.get("stat_key"))
    return STAT_MARKET.get((sport or "MLB").upper(), {}).get(key)


# Words that appear inside stat keywords but name no stat on their own.
_NON_STAT_WORDS = {"and", "made", "yards", "yds"}


def _words(text):
    return re.findall(r"[a-z0-9]+", (text or "").lower())


def strict_extract_prop(extract_prop):
    """Wrap tracker.extract_prop so a spec is returned only when the bet text confirms it.

    Used for NBA and NFL (MLB keeps its original path, so existing measured CLV cannot
    move). extract_prop takes the threshold from `line_num`, and logged NBA/NFL picks
    carry line_num values that are not the bet's line — odds stored as line_num
    (-113.0), or 235.0 on a "Under 224.5" bet. Matched as-is, a close would be taken at
    the wrong line. So, beyond extract_prop's own checks, this refuses (returns None):

      * a bet whose text names an Over/Under side but has no number right after the
        side extract_prop chose, or a different number. An "N+" anywhere in the text
        does NOT exempt it: extract_prop reads "N+" first, so "Bo Nix (3+ games) Under
        224.5 passing yards" would otherwise come back as Over 2.5. Only a bet with no
        Over/Under word at all ("Jalen Brunson 25+ Points") is taken in N+ form;
      * a parsed player name that contains a joining token (and, &, +, /) or a whole
        stat keyword. extract_prop takes everything before the side as the player, so
        "Jalen Brunson points and rebounds Over 30.5" parses as player "jalen brunson
        points and" on plain rebounds 30.5 — the first stat hides inside the "name";
      * a bet naming a second stat once the matched keyword and the player's own name
        are removed, e.g. "Over 23.5 points and rebounds", which extract_prop silently
        reads as rebounds alone. The (already vetted) player's name is removed first so
        "Cooper Rush ... passing yards" is not refused for the word "rush", which is a
        stat word but not a stat keyword;
      * a missing or empty stat map (callers pass none for a sport with no map).

    A refusal leaves the pick Unmeasured. Never a guess.
    """
    def _strict(bet, line_num, stat_map=None):
        if not stat_map:
            return None
        spec = extract_prop(bet, line_num, stat_map)
        if not spec:
            return None
        text = bet or ""
        if re.search(r"\b(over|under)\b", text, flags=re.IGNORECASE):
            m = re.search(rf"\b{spec['side']}\s+(\d+(?:\.\d+)?)", text, flags=re.IGNORECASE)
            if not m or float(m.group(1)) != float(spec["threshold"]):
                return None
        # The player segment (text before the side, or before "N+") must be a name only.
        side_at = re.search(r"\b(over|under)\b|\d+(?:\.\d+)?\+", text, flags=re.IGNORECASE)
        segment = text[:side_at.start()] if side_at else text
        if re.search(r"[&+/]", segment):
            return None
        player = spec["player"]
        if re.search(r"\band\b", player) or any(
                re.search(rf"\b{re.escape(kw)}\b", player) for kw in stat_map):
            return None
        # Same longest-first keyword choice extract_prop makes; remove it, then any
        # remaining stat word means the bet names more than one stat.
        low = text.lower()
        for kw in sorted(stat_map, key=len, reverse=True):
            pat = rf"\b{re.escape(kw)}\b"
            if re.search(pat, low):
                low = re.sub(pat, " ", low, count=1)
                break
        remaining = Counter(_words(low))
        remaining.subtract(Counter(_words(spec["player"])))   # one use per name word
        stat_words = {w for k in stat_map for w in _words(k)} - _NON_STAT_WORDS
        if any(n > 0 for w, n in remaining.items() if w in stat_words):
            return None
        return spec
    return _strict


def build_closes(picks, *, resolve_event, fetch_ladders, extract_prop, normalize_name,
                 stat_map=None, classify_bet=None, force=False, only_date=None, sport="MLB"):
    """Build the {pick_id: close_info} map for settled player-prop picks of one `sport`
    (default MLB). build_closes_live calls it once per sport in CLOSE_SPORTS, with that
    sport's resolver, ladder fetcher and stat map bound into the seams.

    Injected seams (live wiring passes the tracker/bettingpros implementations):
      resolve_event(date, player_norm) -> event_id | None   (player -> game, from /props)
      fetch_ladders(event_id, market_id) -> ladder list      (bettingpros.fetch_offer_ladder)
      extract_prop(bet, line_num, stat_map) -> spec | None   (tracker.extract_prop)
      normalize_name(str) -> str                             (tracker._normalize_name)
      classify_bet(pick) -> kind                             (tracker.classify_bet; optional)

    Only settled (win/loss/push) props lacking a closing_line are considered (unless force).
    Skips — with no map entry — are silent by design: the pick simply stays Unmeasured.
    """
    closes = {}
    ladder_cache = {}
    for p in picks:
        if only_date is not None and p.get("date") != only_date:
            continue
        if p.get("result") not in ("win", "loss", "push"):
            continue
        if (p.get("sport") or "").upper() != sport:
            continue
        if p.get("closing_line") and not force:
            continue
        if classify_bet is not None and classify_bet(p) != "prop":
            continue
        spec = extract_prop(p.get("bet", ""), p.get("line_num"), stat_map) if stat_map \
            else extract_prop(p.get("bet", ""), p.get("line_num"))
        if not spec:
            continue
        market_id = market_for_spec(spec, sport=sport)
        if market_id is None:
            continue
        event_id = resolve_event(p.get("date"), spec["player"])
        if event_id is None:
            continue
        ck = (event_id, market_id)
        if ck not in ladder_cache:
            ladder_cache[ck] = fetch_ladders(event_id, market_id)
        close = two_way_at_line(ladder_cache[ck], spec["player"], spec["threshold"],
                                normalize_name=normalize_name)
        if close is None:
            continue
        closes[p["id"]] = {"close": close, "side": spec["side"], "market": "prop"}
    return closes


# ── Live wiring (residential run) ───────────────────────────────────────────────

def make_event_resolver(sport, *, tracker, bp):
    """`resolve_event(date, player_norm) -> event_id | None` for one sport, live.

    MLB (unchanged): index the day's ~15 /events by probable pitcher — our book is
    pitcher props, so one page resolves nearly every pick — and fall back to a one-time
    /props pull per date for batter props.

    NBA / NFL: index the day's /props by normalized player name. A name listed under
    more than one event that day is ambiguous and resolves to None (Unmeasured), never
    to whichever event happened to come first.
    """
    sport = sport.upper()
    if sport == "MLB":
        event_index = {}
        props_done = set()

        def _index_from_events(date):
            idx = {}
            for ev in bp.fetch_events("MLB", date):
                for who in ("home", "visitor"):
                    pit = (ev.get("pitchers") or {}).get(who) or {}
                    nm = tracker._normalize_name(pit.get("name") or "")
                    if nm and ev.get("id") is not None:
                        idx.setdefault(nm, ev["id"])
            return idx

        def resolve_mlb(date, player_norm):
            if date not in event_index:
                event_index[date] = _index_from_events(date)
            if player_norm in event_index[date]:
                return event_index[date][player_norm]
            if date not in props_done:  # batter-prop fallback: pay the /props cost once per date
                props_done.add(date)
                for pr in bp.fetch_props("MLB", date):
                    nm = tracker._normalize_name((pr.get("player") or {}).get("name") or "")
                    ev = pr.get("event_id")
                    if nm and ev is not None:
                        event_index[date].setdefault(nm, ev)
            return event_index[date].get(player_norm)

        return resolve_mlb

    by_date = {}

    def resolve_by_props(date, player_norm):
        if date not in by_date:
            idx = {}
            for pr in bp.fetch_props(sport, date):
                nm = tracker._normalize_name((pr.get("player") or {}).get("name") or "")
                ev = pr.get("event_id")
                if nm and ev is not None:
                    idx.setdefault(nm, set()).add(ev)
            by_date[date] = idx
        events = by_date[date].get(player_norm) or set()
        return next(iter(events)) if len(events) == 1 else None

    return resolve_by_props


def sport_seams(sport, *, tracker, bp):
    """The per-sport seams build_closes and close_capture.capture take, bound live.

    MLB is exactly the original wiring (tracker.extract_prop + PROP_STAT_MAP). NBA and
    NFL use their own stat map, their own sport on every BettingPros call, and the
    strict extract_prop wrapper (see strict_extract_prop for why).
    """
    sport = sport.upper()
    return dict(
        resolve_event=make_event_resolver(sport, tracker=tracker, bp=bp),
        fetch_ladders=lambda ev, mk: bp.fetch_offer_ladder(ev, mk, sport=sport),
        extract_prop=(tracker.extract_prop if sport == "MLB"
                      else strict_extract_prop(tracker.extract_prop)),
        stat_map=(tracker.PROP_STAT_MAP if sport == "MLB"
                  else tracker._stat_map_for_sport(sport)),
        market_for_spec=lambda spec: market_for_spec(spec, sport=sport),
    )


def build_closes_live(picks, *, tracker=None, bp=None, force=False, only_date=None):
    """Live build for MLB, NBA and NFL props: per sport, one player -> event_id index per
    pick-date + one offer-ladder fetch per (event, market). Residential IP only
    (BettingPros 403s datacenter)."""
    tracker = tracker or _load("tracker")
    bp = bp or _load("bettingpros")

    closes = {}
    for sport in CLOSE_SPORTS:
        seams = sport_seams(sport, tracker=tracker, bp=bp)
        seams.pop("market_for_spec")          # build_closes looks the market up by sport
        closes.update(build_closes(
            picks,
            normalize_name=tracker._normalize_name,
            classify_bet=tracker.classify_bet,
            force=force,
            only_date=only_date,
            sport=sport,
            **seams,
        ))
    return closes
