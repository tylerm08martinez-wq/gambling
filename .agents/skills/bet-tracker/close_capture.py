"""Capture closing lines AT the close, instead of reconstructing them days later.

WHY THIS EXISTS
---------------
`backfill-clv` fetches whatever BettingPros is serving *after* the game — sometimes
days after (a 2026-07-19 pick was backfilled on 2026-07-25). That has two failures
that compound:

  1. **Coverage.** Post-game the prop market is usually gone, so most picks never get
     a close at all. Measured CLV sits at 22% against the 90% CONTEXT.md requires
     before ROI is a mature signal.
  2. **Vintage.** `fetch_offer_ladder` has no timestamp and no "closing" flag. When it
     *does* return something for a finished game, nothing distinguishes a true close
     from a stale or reopened line. The number gets recorded as "the close" regardless.

This module snapshots the two-way market in the minutes before first pitch, while it
is still live, and records **when** it was taken. That makes CLV measurable for the
majority of picks and makes every stored close carry its own provenance.

Why it matters more than it sounds: CLV converges far faster than ROI. Distinguishing
a 55% strategy from breakeven on results alone needs ~2,300 bets. CLV answers the same
question in a fraction of that — but only if it is actually measured. Coverage is the
binding constraint on learning anything from this project.

SCOPE: MLB player props (the Primary Edge, and what the offer-ladder endpoint prices
two-way). Game lines and totals need a different market id and stay out until there is
a reason to add them. Residential IP only — BettingPros 403s datacenter (ADR 0006).
"""

import json
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Arizona: fixed UTC-7, no DST. Deliberately NOT a named zone — git-bash/MSYS2 ships no
# zoneinfo database, so 'America/Phoenix' silently resolves to UTC there and every
# capture window would be 7 hours wrong (the same trap documented in run-daily-picks.sh).
AZ = timezone(timedelta(hours=-7))

SNAPSHOT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "closing_lines.json")

# How close to first pitch a snapshot must be to count as "the close". A capture taken
# earlier than this is still recorded (better than nothing) but flagged, because an
# opening-ish line masquerading as a close is exactly the vintage problem this module
# exists to fix.
CLOSE_GRADE_MINUTES = 30


def parse_start(pick, *, tz=AZ):
    """Pick date + game_time ('5:10 PM', Arizona) -> aware datetime. None if unparseable.

    game_time is present on 81 of 87 logged picks; the rest simply can't be scheduled
    for capture and are skipped rather than guessed at.
    """
    d, t = pick.get("date"), (pick.get("game_time") or "").strip()
    if not d or not t:
        return None
    for fmt in ("%Y-%m-%d %I:%M %p", "%Y-%m-%d %I:%M%p", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(f"{d} {t.upper()}", fmt).replace(tzinfo=tz)
        except ValueError:
            continue
    return None


def minutes_until(pick, now, *, tz=AZ):
    """Minutes from `now` until first pitch. Negative once underway. None if unknown."""
    start = parse_start(pick, tz=tz)
    if start is None:
        return None
    return (start - now).total_seconds() / 60.0


def due_for_capture(pick, now, *, window_minutes, tz=AZ):
    """True if this pick's game starts within the window and hasn't started yet.

    Strictly pre-game: once first pitch passes, the price is no longer a closing line.
    """
    mins = minutes_until(pick, now, tz=tz)
    return mins is not None and 0 < mins <= window_minutes


def load_snapshots(path=SNAPSHOT_FILE):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_snapshots(snaps, path=SNAPSHOT_FILE):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(snaps, f, indent=2, sort_keys=True)
        f.write("\n")


def should_replace(existing, minutes_before):
    """Keep the snapshot taken CLOSEST to first pitch.

    The scheduler fires repeatedly through the day, so a pick can be captured at T-25
    and again at T-4. The later one is the better estimate of the close, so it wins.
    """
    if not existing:
        return True
    prev = existing.get("minutes_before_start")
    return prev is None or minutes_before < prev


def capture(picks, now, *, resolve_event, fetch_ladders, extract_prop, normalize_name,
            two_way_at_line, market_for_spec, stat_map=None, classify_bet=None,
            window_minutes=45, snapshots=None, tz=AZ):
    """Snapshot the two-way close for every pick inside its capture window.

    Pure w.r.t. I/O — all network access arrives through the injected seams, mirroring
    clv_fetch.build_closes so this is testable without a residential IP or live market.

    Returns (snapshots, report) where report rows are (pick_id, status, detail).
    """
    snaps = dict(snapshots or {})
    report = []
    ladder_cache = {}

    for p in picks:
        pid = p.get("id")
        if p.get("result") is not None:
            continue                                  # already settled; nothing to close
        mins = minutes_until(p, now, tz=tz)
        if mins is None:
            report.append((pid, "skip", "no parseable game_time"))
            continue
        if not due_for_capture(p, now, window_minutes=window_minutes, tz=tz):
            report.append((pid, "skip",
                           f"outside window ({mins:.0f}m to start)" if mins > 0
                           else f"already started ({-mins:.0f}m ago)"))
            continue
        if classify_bet is not None and classify_bet(p) != "prop":
            report.append((pid, "skip", f"{classify_bet(p)} — only props are priced two-way"))
            continue
        if not should_replace(snaps.get(pid), mins):
            report.append((pid, "keep", "existing snapshot is closer to first pitch"))
            continue

        spec = extract_prop(p.get("bet", ""), p.get("line_num"), stat_map) if stat_map \
            else extract_prop(p.get("bet", ""), p.get("line_num"))
        if not spec:
            report.append((pid, "skip", "could not parse player/stat/side/threshold"))
            continue
        market_id = market_for_spec(spec)
        if market_id is None:
            report.append((pid, "skip", "stat has no BettingPros market id"))
            continue
        event_id = resolve_event(p.get("date"), spec["player"])
        if event_id is None:
            report.append((pid, "skip", "player not found in the day's events"))
            continue

        ck = (event_id, market_id)
        if ck not in ladder_cache:
            try:
                ladder_cache[ck] = fetch_ladders(event_id, market_id)
            except Exception as e:                     # noqa: BLE001 - network boundary
                report.append((pid, "error", f"ladder fetch failed: {e}"))
                continue
        close = two_way_at_line(ladder_cache[ck], spec["player"], spec["threshold"],
                                normalize_name=normalize_name)
        if close is None:
            # Not priced two-way at our number → not de-viggable. Never fabricate.
            report.append((pid, "skip", "line not priced on both sides"))
            continue

        snaps[pid] = {
            "close": close,
            "side": spec["side"],
            "market": "prop",
            "captured_at": now.isoformat(),
            "minutes_before_start": round(mins, 1),
            # Honest label: only a snapshot taken near first pitch deserves to be called
            # a close. Anything earlier is recorded but marked, so a stale price can
            # never silently pass as a closing line.
            "vintage": "close" if mins <= CLOSE_GRADE_MINUTES else "pre-close",
            "source": "bettingpros_consensus",
        }
        report.append((pid, "captured",
                       f"T-{mins:.0f}m {close} ({snaps[pid]['vintage']})"))

    return snaps, report


def capture_live(picks, now=None, *, tracker=None, bp=None, clv_fetch=None,
                 window_minutes=45, snapshots=None):
    """Live wiring: same seams clv_fetch.build_closes_live uses, aimed at open picks."""
    import importlib
    tracker = tracker or importlib.import_module("tracker")
    bp = bp or importlib.import_module("bettingpros")
    cf = clv_fetch or importlib.import_module("clv_fetch")
    now = now or datetime.now(AZ)

    event_index, props_done = {}, set()

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
        if date not in props_done:
            props_done.add(date)
            for pr in bp.fetch_props("MLB", date):
                nm = tracker._normalize_name((pr.get("player") or {}).get("name") or "")
                ev = pr.get("event_id")
                if nm and ev is not None:
                    event_index[date].setdefault(nm, ev)
        return event_index[date].get(player_norm)

    return capture(
        picks, now,
        resolve_event=resolve_event,
        fetch_ladders=lambda ev, mk: bp.fetch_offer_ladder(ev, mk),
        extract_prop=tracker.extract_prop,
        normalize_name=tracker._normalize_name,
        two_way_at_line=cf.two_way_at_line,
        market_for_spec=cf.market_for_spec,
        stat_map=tracker.PROP_STAT_MAP,
        classify_bet=tracker.classify_bet,
        window_minutes=window_minutes,
        snapshots=snapshots if snapshots is not None else load_snapshots(),
    )
