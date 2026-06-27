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
import sys
from pathlib import Path

_DIR = Path(__file__).resolve().parent


def _load(name):
    spec = importlib.util.spec_from_file_location(name, _DIR / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules.setdefault(name, mod)
    spec.loader.exec_module(mod)
    return mod


# (boxscore group, stat key) -> BettingPros MLB market_id. Verified against /v3/markets
# on 2026-06-27. Only stats with a confident BP market are mapped; an unmapped stat (or a
# combined-stat tuple) -> pick skipped (left Unmeasured) rather than mis-matched. Keys are
# the (stat_group, stat_key) that tracker.extract_prop returns via PROP_STAT_MAP.
STAT_MARKET = {
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
}


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


def market_for_spec(spec):
    """BettingPros market_id for an extract_prop spec, or None if unmapped/combined."""
    key = (spec.get("stat_group"), spec.get("stat_key"))
    return STAT_MARKET.get(key)


def build_closes(picks, *, resolve_event, fetch_ladders, extract_prop, normalize_name,
                 stat_map=None, classify_bet=None, force=False, only_date=None):
    """Build the {pick_id: close_info} map for settled MLB player-prop picks.

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
        if (p.get("sport") or "").upper() != "MLB":
            continue
        if p.get("closing_line") and not force:
            continue
        if classify_bet is not None and classify_bet(p) != "prop":
            continue
        spec = extract_prop(p.get("bet", ""), p.get("line_num"), stat_map) if stat_map \
            else extract_prop(p.get("bet", ""), p.get("line_num"))
        if not spec:
            continue
        market_id = market_for_spec(spec)
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

def build_closes_live(picks, *, tracker=None, bp=None, force=False, only_date=None):
    """Live build: one /props pull per pick-date (player -> event_id) + one offer-ladder
    fetch per (event, market). Residential IP only (BettingPros 403s datacenter)."""
    tracker = tracker or _load("tracker")
    bp = bp or _load("bettingpros")

    # Per-date player -> event_id index. Built cheaply from /events (the day's ~15 games,
    # which carry both probable pitchers) — our book is pitcher props, so this resolves
    # every pick in one page instead of paginating ~50 pages of /props. A batter prop (not
    # a probable pitcher) triggers a one-time /props fallback for that date only.
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

    def resolve_event(date, player_norm):
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

    return build_closes(
        picks,
        resolve_event=resolve_event,
        fetch_ladders=lambda ev, mk: bp.fetch_offer_ladder(ev, mk),
        extract_prop=tracker.extract_prop,
        normalize_name=tracker._normalize_name,
        stat_map=tracker.PROP_STAT_MAP,
        classify_bet=tracker.classify_bet,
        force=force,
        only_date=only_date,
    )
