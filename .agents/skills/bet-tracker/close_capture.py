"""Capture closing lines AT the close, instead of reconstructing them days later.

WHY THIS EXISTS
---------------
`backfill-clv` fetches whatever BettingPros is serving *after* the game — sometimes
days after (a 2026-07-19 pick was backfilled on 2026-07-25). That has two failures
that compound:

  1. **Coverage.** Post-game the prop market is usually gone, so most picks never get
     a close at all. Measured CLV sits at 22% against the 90% GLOSSARY.md requires
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

SCOPE: MLB, NBA and NFL player props (the Primary Edge; NBA/NFL added in #107), and
since #109 MLB, NBA and NFL game lines (moneyline, spread / run line, game total) plus
every V3 observation in v3-observations.json (ADR 0011). Game-line picks are matched by
game, team and exact line (`capture_game_lines`); observations get a retail-consensus
close and an Exchange Benchmark close (`capture_observations`). Residential IP only —
BettingPros 403s datacenter (ADR 0006).
"""

import json
import os
import re
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


def due_for_capture(pick, now, *, window_minutes, tz=AZ, start=None):
    """True if this pick's game starts within the window and hasn't started yet.

    Strictly pre-game: once first pitch passes, the price is no longer a closing line.
    `start` overrides the pick's game_time (a pick timed by its event's scheduled start).
    """
    mins = minutes_until(pick, now, tz=tz) if start is None \
        else (start - now).total_seconds() / 60.0
    return mins is not None and 0 < mins <= window_minutes


# The V3 Observation Scan's output (v3_scan.OBSERVATIONS_FILE); capture fills in each
# observation's `close` (#109).
OBSERVATIONS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                 "v3-observations.json")


def load_snapshots(path=None):
    # The path is resolved at call time, not bound as a default argument, so pointing
    # SNAPSHOT_FILE at a temp copy really redirects every read and write.
    path = path or SNAPSHOT_FILE
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_snapshots(snaps, path=None):
    path = path or SNAPSHOT_FILE
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
            window_minutes=45, snapshots=None, tz=AZ, event_start=None):
    """Snapshot the two-way close for every pick inside its capture window.

    Pure w.r.t. I/O — all network access arrives through the injected seams, mirroring
    clv_fetch.build_closes so this is testable without a residential IP or live market.

    `event_start(date, event_id) -> aware datetime | None` is optional. When given, a
    pick with no parseable game_time is located first (player -> event) and timed by
    that event's scheduled start instead of being skipped. Without it (the MLB wiring),
    a pick with no game_time is skipped exactly as before.

    Returns (snapshots, report) where report rows are (pick_id, status, detail).
    """
    snaps = dict(snapshots or {})
    report = []
    ladder_cache = {}

    def _locate(p):
        """(spec, market_id, event_id), or a skip reason string."""
        spec = extract_prop(p.get("bet", ""), p.get("line_num"), stat_map) if stat_map \
            else extract_prop(p.get("bet", ""), p.get("line_num"))
        if not spec:
            return "could not parse player/stat/side/threshold"
        market_id = market_for_spec(spec)
        if market_id is None:
            return "stat has no BettingPros market id"
        event_id = resolve_event(p.get("date"), spec["player"])
        if event_id is None:
            return "player not found in the day's events"
        return spec, market_id, event_id

    today = now.astimezone(tz).date().isoformat()

    for p in picks:
        pid = p.get("id")
        if p.get("result") is not None:
            continue                                  # already settled; nothing to close
        start = parse_start(p, tz=tz)
        located = None
        start_source = "game_time"
        if start is None and event_start is not None:
            # No game_time: find the event first, then time the pick by its start.
            if (p.get("date") or "") < today:
                report.append((pid, "skip", "no game_time and the pick's date has passed"))
                continue
            if classify_bet is not None and classify_bet(p) != "prop":
                report.append((pid, "skip", f"{classify_bet(p)} — only props are priced two-way"))
                continue
            located = _locate(p)
            if isinstance(located, str):
                report.append((pid, "skip", located))
                continue
            start = event_start(p.get("date"), located[2])
            if start is None:
                report.append((pid, "skip", "no game_time and the event has no scheduled start"))
                continue
            start_source = "event_scheduled"
        if start is None:
            report.append((pid, "skip", "no parseable game_time"))
            continue
        mins = (start - now).total_seconds() / 60.0
        if not due_for_capture(p, now, window_minutes=window_minutes, tz=tz, start=start):
            report.append((pid, "skip",
                           f"outside window ({mins:.0f}m to start)" if mins > 0
                           else f"already started ({-mins:.0f}m ago)"))
            continue
        if located is None and classify_bet is not None and classify_bet(p) != "prop":
            report.append((pid, "skip", f"{classify_bet(p)} — only props are priced two-way"))
            continue
        if not should_replace(snaps.get(pid), mins):
            report.append((pid, "keep", "existing snapshot is closer to first pitch"))
            continue

        if located is None:
            located = _locate(p)
            if isinstance(located, str):
                report.append((pid, "skip", located))
                continue
        spec, market_id, event_id = located

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
        if start_source != "game_time":
            # Provenance for the start itself: timed by the BettingPros event, not by a
            # game_time logged with the pick.
            snaps[pid]["start_source"] = start_source
        report.append((pid, "captured",
                       f"T-{mins:.0f}m {close} ({snaps[pid]['vintage']})"))

    return snaps, report


# ── Game lines (#109) ────────────────────────────────────────────────────────────
#
# Moneyline, spread / run line and game total picks. Same capture rules as props
# (strictly pre-game, closest-to-start wins, both sides at our number or nothing), plus
# the matching a game line needs: which GAME (team names against the event's two
# participants) and which TEAM (the side), from the bet text. Every step that cannot be
# made with certainty leaves the pick unmeasured.

# classify_bet's game-line tokens -> value_engine market kind. 'rl' (run line) is a
# spread. The kind picks the de-vig (power for all three, ADR 0011) and the market id.
GAME_LINE_KIND = {"ml": "moneyline", "spread": "spread", "rl": "spread", "total": "total"}

# A partial-game or team market is NOT the full-game market BettingPros prices under
# these ids. Capturing the full-game close for "Chiefs -3 1H" or "Knicks Under 110.5
# team total" would be a close for a different bet, so these are refused outright.
# Only the explicit forms: a bare "half" also appears in "half-Kelly". Alt lines are
# not refused; exact-line matching already prices them only at their own number.
_PARTIAL_MARKET_RE = re.compile(
    r"\b(1h|2h|1q|2q|3q|4q|f5|"
    r"(first|second|1st|2nd)\s+half|"
    r"(first|second|third|fourth|1st|2nd|3rd|4th)\s+quarter|"
    r"(first|1st)\s+(5|five)(\s+innings?)?|team\s+total)\b", re.IGNORECASE)

# A signed handicap: the same test classify_bet's spread branch applies (|value| < 100
# so an American price is never read as a spread).
_HANDICAP_RE = re.compile(r"(?<![\w.])([+-]\d+(?:\.\d+)?)\b")


def _depar(text):
    return re.sub(r"\([^)]*\)|\[[^\]]*\]", " ", text or "")


def _same_number(a, b):
    try:
        return abs(float(a) - float(b)) < 1e-9
    except (TypeError, ValueError):
        return False


# A consensus (book 0) line whose `updated` is more than this before the capture is a
# dead line, not a close: no close is stored (#116 review, decided). Every stored
# consensus close records `quote_updated` so the #110 review can filter tighter.
CONSENSUS_MAX_AGE_MIN = 24 * 60


def consensus_is_fresh(updated, now):
    """True if a BettingPros `updated` stamp (UTC) is within CONSENSUS_MAX_AGE_MIN of
    `now`. A missing or unparseable stamp is never assumed fresh."""
    import value_engine as ve
    ts = ve._as_utc(updated)
    return ts is not None and (now - ts).total_seconds() / 60.0 <= CONSENSUS_MAX_AGE_MIN


def parse_game_line_bet(pick, bet_kind):
    """Read a game-line pick's market from its text -> dict, or a refusal reason (str).

    `bet_kind` is tracker.classify_bet's token (ml / spread / rl / total). Returns
    {"kind", "team_text", "side", "line", "text"}:
      * moneyline: team_text = the words before an explicit ML / moneyline marker.
        Without the marker there is no confident side (a bare "Mets -150" could be a
        price or a typo), so it is refused.
      * spread / run line: team_text = the words before the first signed handicap,
        line = that handicap SIGNED AS THE BET READS (ADR 0008).
      * total: side = the first Over/Under, line = the number right after it.
    `line_num`, when present, must equal the text's number: logged picks carry
    line_num values that are not the bet's line (odds stored as -125.0, -7.5 on an
    Under 7.5), and a close taken at line_num would be the wrong line. Partial-game
    (1H, quarter, F5) and team-total bets are refused: no full-game close fits them.
    """
    kind = GAME_LINE_KIND.get(bet_kind)
    if kind is None:
        return f"{bet_kind} is not a game line"
    text = " ".join(_depar(pick.get("bet")).split())
    if not text:
        return "empty bet text"
    if _PARTIAL_MARKET_RE.search(text):
        return "partial-game or team market — no full-game close fits it"
    line_num = pick.get("line_num")
    out = {"kind": kind, "team_text": None, "side": None, "line": None, "text": text}
    if kind == "moneyline":
        m = re.search(r"\b(ml|moneyline|money\s+line)\b", text, flags=re.IGNORECASE)
        if not m or not text[:m.start()].strip():
            return "no team before an explicit ML marker"
        out["team_text"] = text[:m.start()].strip()
        return out
    if kind == "spread":
        if re.search(r"\b(over|under)\b", text, flags=re.IGNORECASE):
            return "spread text names an Over/Under"
        m = next((h for h in _HANDICAP_RE.finditer(text) if abs(float(h.group(1))) < 100),
                 None)
        if not m or not text[:m.start()].strip():
            return "no team before a signed handicap"
        line = float(m.group(1))
        if line_num is not None and not _same_number(line_num, line):
            return f"line_num {line_num} disagrees with the bet's {m.group(1)}"
        out.update(team_text=text[:m.start()].strip(), line=line)
        return out
    m = re.search(r"\b(over|under)\s+(\d+(?:\.\d+)?)\b", text, flags=re.IGNORECASE)
    if not m:
        return "no Over/Under number"
    sides = re.findall(r"\b(over|under)\b", text, flags=re.IGNORECASE)
    if len(sides) != 1:
        return "more than one Over/Under in the bet"
    line = float(m.group(2))
    if line_num is not None and not _same_number(line_num, line):
        return f"line_num {line_num} disagrees with the bet's {m.group(2)}"
    out.update(side=m.group(1).lower(), line=line,
               text=(text[:m.start()] + " " + text[m.end():]).strip())
    return out


def _team_patterns(participant):
    """(regex, flags) that name this team: its nickname (which also covers 'city
    nickname'), or its abbreviation in capitals. A city alone is deliberately NOT a
    match — 'Los Angeles' is two NBA teams playing the same day (LAL, LAC)."""
    pats = []
    name = (participant.get("name") or "").strip()
    abbr = (participant.get("abbreviation") or participant.get("id") or "").strip()
    edge = r"(?<![A-Za-z0-9]){}(?![A-Za-z0-9])"
    if name:
        pats.append((edge.format(re.escape(name).replace(r"\ ", r"\s+")), re.IGNORECASE))
    if abbr:
        pats.append((edge.format(re.escape(abbr)), 0))
    return pats


def match_teams(text, participants):
    """The participant ids (abbreviations) that `text` names. Pure."""
    found = set()
    for p in participants or []:
        pid = p.get("id")
        if pid and any(re.search(pat, text or "", flags) for pat, flags in _team_patterns(p)):
            found.add(pid)
    return found


def capture_game_lines(picks, now, *, events_for, fetch_ladders, market_for_kind,
                       classify_bet, window_minutes=45, snapshots=None, tz=AZ):
    """Snapshot the two-way consensus close for open game-line picks of ONE sport.

    Injected seams (live wiring in `capture_live`):
      events_for(date) -> [{"id", "start": aware datetime, "participants"}]  (/events)
      fetch_ladders(event_id, market_id) -> [bettingpros.game_line_ladder(...)]
      market_for_kind(kind) -> market_id | None                (per sport)
      classify_bet(pick) -> ml / spread / rl / total / prop    (tracker.classify_bet)

    Matching, all of it required: the bet parses (`parse_game_line_bet`); exactly one
    event starting inside the window has the bet's team (or, for a total, BOTH of the
    bet's teams) among its /events teams, and every team the text names belongs to
    that event; that event's market has the event's two teams (or over/under) as its
    selections; the consensus prices both sides at the bet's own number
    (`bettingpros.two_way_game_line`), updated within 24h (CONSENSUS_MAX_AGE_MIN).
    Snapshot keys are the side ('LAC', or 'over'/'under') so clv_backfill de-vigs the
    close with the power method for every game line (ADR 0011).

    Returns (snapshots, report) like `capture`. Prop picks are not this function's.
    """
    import bettingpros as bp

    snaps = dict(snapshots or {})
    report = []
    events_cache, ladder_cache = {}, {}
    today = now.astimezone(tz).date().isoformat()

    for p in picks:
        pid = p.get("id")
        if p.get("result") is not None:
            continue
        bet_kind = classify_bet(p)
        if bet_kind not in GAME_LINE_KIND:
            continue                                  # props are capture()'s
        parsed = parse_game_line_bet(p, bet_kind)
        if isinstance(parsed, str):
            report.append((pid, "skip", parsed))
            continue
        kind = parsed["kind"]
        market_id = market_for_kind(kind)
        if market_id is None:
            report.append((pid, "skip", f"no BettingPros {kind} market id for this sport"))
            continue
        start = parse_start(p, tz=tz)
        if start is not None:
            mins = (start - now).total_seconds() / 60.0
            if not 0 < mins <= window_minutes:
                report.append((pid, "skip", f"outside window ({mins:.0f}m to start)"
                               if mins > 0 else f"already started ({-mins:.0f}m ago)"))
                continue
            if not should_replace(snaps.get(pid), mins):
                report.append((pid, "keep", "existing snapshot is closer to first pitch"))
                continue
        elif (p.get("date") or "") < today:
            report.append((pid, "skip", "no game_time and the pick's date has passed"))
            continue

        date = p.get("date")
        if date not in events_cache:
            try:
                events_cache[date] = events_for(date) or []
            except Exception as e:                     # noqa: BLE001 - network boundary
                report.append((pid, "error", f"events fetch failed: {e}"))
                continue
        in_window = [ev for ev in events_cache[date] if ev.get("start") is not None
                     and 0 < (ev["start"] - now).total_seconds() / 60.0 <= window_minutes]
        if not in_window:
            report.append((pid, "skip", "no event starting inside the window"))
            continue

        # The game is found from /events (home + visitor), never from the offer: a live
        # total market carries `participants: []`, so offer-side matching skipped every
        # total. Only the matched game's market is then fetched.
        named = {ev["id"]: match_teams(parsed["text"], ev.get("participants"))
                 for ev in in_window}
        named = {eid: t for eid, t in named.items() if t}
        if len(named) != 1:
            report.append((pid, "skip", "bet's teams not found in exactly one game "
                                        f"starting inside the window ({len(named)} games)"))
            continue
        (event_id, teams), = named.items()
        event = next(ev for ev in in_window if ev["id"] == event_id)
        event_teams = {pp.get("id") for pp in event.get("participants") or [] if pp.get("id")}
        if len(event_teams) != 2:
            report.append((pid, "skip", "the event does not list exactly two teams"))
            continue
        if kind == "total":
            if teams != event_teams:
                report.append((pid, "skip", "a game total must name both teams of the game"))
                continue
            side_key, market_keys = parsed["side"], {"over", "under"}
        else:
            side = match_teams(parsed["team_text"], event.get("participants"))
            if len(side) != 1:
                report.append((pid, "skip", "bet side is not exactly one team of the game"))
                continue
            (side_key,), market_keys = side, event_teams

        ck = (event_id, market_id)
        if ck not in ladder_cache:
            try:
                ladder_cache[ck] = fetch_ladders(event_id, market_id) or []
            except Exception as e:                     # noqa: BLE001 - network boundary
                report.append((pid, "error", f"ladder fetch failed: {e}"))
                continue
        # The market's two selections must be this game's two teams (or over/under).
        candidates = [lad for lad in ladder_cache[ck]
                      if set(lad.get("keys") or []) == market_keys]
        priced = [(c, lad) for c, lad in
                  ((bp.two_way_game_line(lad, kind, side_key, parsed["line"]), lad)
                   for lad in candidates) if c is not None]
        if len(priced) != 1:
            # No pair (or, impossibly, two different pairs) at our number: not de-viggable.
            report.append((pid, "skip", "line not priced on both sides"
                           if not priced else "more than one consensus market matches"))
            continue
        close, ladder = priced[0]
        quote_updated = bp.game_line_quote_updated(ladder, kind, side_key, parsed["line"])
        if not consensus_is_fresh(quote_updated, now):
            # A consensus number nobody has touched for a day is a dead line, not a close.
            report.append((pid, "skip", f"consensus line not updated within 24h "
                                        f"(updated {quote_updated})"))
            continue

        start_source = "game_time"
        if start is None:
            start = next(ev["start"] for ev in in_window if ev["id"] == event_id)
            start_source = "event_scheduled"
        mins = (start - now).total_seconds() / 60.0
        if not should_replace(snaps.get(pid), mins):
            report.append((pid, "keep", "existing snapshot is closer to first pitch"))
            continue
        snaps[pid] = {
            "close": close,
            "side": side_key,
            "market": kind,
            "line": parsed["line"],
            "event_id": event_id,
            "captured_at": now.isoformat(),
            "minutes_before_start": round(mins, 1),
            "vintage": "close" if mins <= CLOSE_GRADE_MINUTES else "pre-close",
            "source": "bettingpros_consensus",
            "quote_updated": quote_updated,
        }
        if start_source != "game_time":
            snaps[pid]["start_source"] = start_source
        report.append((pid, "captured", f"T-{mins:.0f}m {kind} {side_key} {close} "
                                        f"({snaps[pid]['vintage']})"))
    return snaps, report


# ── V3 observations (#109, ADR 0011) ─────────────────────────────────────────────
#
# Every observation in v3-observations.json gets two closes, captured pre-start:
#   retail_consensus — BettingPros consensus (book 0) two-way at the observation's line
#   exchange         — value_engine.exchange_benchmark at that line, at capture time
# and from them two realized CLVs, `fair_p(close) / p(entry) - 1`, kind-correct de-vig
# (power for game lines, multiplicative for props). They are FRACTIONS, the same scale
# as the row's own `projected_clv` and `gate` (0.0224 = +2.24%), not the percent the
# picks ledger stores in clv_devig; hence the `_frac` field names. Each close keeps the capture closest to the start
# on its own: an exchange benchmark that goes stale at T-5 does not erase a good T-20
# one. Nothing else on the row is ever touched (the first-seen price is what the
# week-end review measures).


def _obs_start(obs):
    ts = (obs.get("start_utc") or "").strip()
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def _obs_quote_line(obs, kind, idx):
    """The quote line (selection A's number, as value_engine keys quotes) for an
    observation whose side sits at feed index `idx`. None for a moneyline."""
    if kind == "moneyline":
        return None
    line = float(obs["line"])
    return -line if kind == "spread" and idx == 1 else line


def capture_observations(store, now, *, fetch_offers, window_minutes=45):
    """Closes for every observation starting inside the window. Pure w.r.t. I/O.

    `fetch_offers(sport, event_id, market_id) -> [raw /offers rows]` is the one seam.
    The observation's market is found again by its stored side LABEL (and, for a
    prop, its participant), never by the stored selection index: the feed's selection
    order is not stable (one market served OKC first, its sibling LAC first), and an
    index match would silently swap sides. No match, or more than one, is skipped.

    Returns (updates, report): updates maps observation id -> {"close",
    "realized_clv_exchange", "realized_clv_retail"} for `apply_observation_updates`.
    """
    import value_engine as ve

    updates, report = {}, []
    offers_cache = {}
    for obs in (store or {}).get("observations") or []:
        oid = obs.get("id") if isinstance(obs, dict) else None
        # One malformed row is reported and skipped; it never ends the pass.
        try:
            row = _capture_observation(obs, now, ve, fetch_offers, offers_cache,
                                       window_minutes)
        except Exception as e:                       # noqa: BLE001 - per-row isolation
            report.append((oid, "error", f"bad observation row: {type(e).__name__}: {e}"))
            continue
        update, rep = row
        report.append(rep)
        if update is not None:
            updates[oid] = update
    return updates, report


def _capture_observation(obs, now, ve, fetch_offers, offers_cache, window_minutes):
    """One observation -> (update | None, report row). See capture_observations."""
    oid = obs.get("id")
    start = _obs_start(obs)
    if start is None:
        return None, (oid, "skip", "no parseable start_utc")
    mins = (start - now).total_seconds() / 60.0
    if not 0 < mins <= window_minutes:
        return None, (oid, "skip", f"outside window ({mins:.0f}m to start)" if mins > 0
                       else f"already started ({-mins:.0f}m ago)")
    existing = obs.get("close") or {}
    want = {name: should_replace(existing.get(name), mins)
            for name in ("retail_consensus", "exchange")}
    if not any(want.values()):
        return None, (oid, "keep", "existing closes are closer to the start")
    try:
        kind = ve.market_kind(obs.get("kind"))
        p_entry = ve.american_to_prob(obs.get("odds"))
    except ValueError as e:
        return None, (oid, "skip", f"unusable observation: {e}")

    ck = (obs.get("sport"), obs.get("event_id"), obs.get("market_id"))
    if ck not in offers_cache:
        try:
            offers_cache[ck] = fetch_offers(*ck) or []
        except Exception as e:                     # noqa: BLE001 - network boundary
            return None, (oid, "error", f"offers fetch failed: {e}")
    side = obs.get("side")
    matches = []
    for off in offers_cache[ck]:
        if kind == "prop":
            parts = off.get("participants") or []
            if not parts or parts[0].get("name") != obs.get("participant"):
                continue
        parsed = ve.quotes_from_offer(off, kind)
        labels = parsed["labels"]
        if not labels or labels[0] == labels[1] or side not in labels:
            continue
        matches.append((parsed["quotes"], labels.index(side)))
    if len(matches) != 1:
        return None, (oid, "skip", f"observation's market/side found {len(matches)} "
                                    "times in the feed (need exactly 1)")
    quotes, idx = matches[0]
    qline = _obs_quote_line(obs, kind, idx)
    mine, theirs = ("odds_a", "odds_b") if idx == 0 else ("odds_b", "odds_a")
    stamp = {"captured_at": now.isoformat(), "minutes_before_start": round(mins, 1),
             "vintage": "close" if mins <= CLOSE_GRADE_MINUTES else "pre-close"}

    retail = None
    book0 = [q for q in quotes if q.get("book_id") == 0
             and (kind == "moneyline" or _same_number(q.get("line"), qline))]
    if (len(book0) == 1
            and not any(ve.is_placeholder_odds(book0[0][k]) for k in (mine, theirs))
            and consensus_is_fresh(book0[0].get("updated"), now)):
        q = book0[0]
        fair = ve.fair_two_way(q["odds_a"], q["odds_b"], kind)
        retail = dict(stamp, line=obs.get("line"), odds_side=q[mine], odds_other=q[theirs],
                      fair_p=fair[idx], quote_updated=q.get("updated"),
                      source="bettingpros_consensus")

    exchange = None
    bench = ve.exchange_benchmark(quotes, qline, kind, now)
    if bench is not None:
        fair_keys = ("fair_a", "fair_b") if idx == 0 else ("fair_b", "fair_a")
        exchange = dict(stamp, line=obs.get("line"), fair_p=bench[fair_keys[0]],
                        fair_other=bench[fair_keys[1]], operators=bench["operators"],
                        quotes_used=[{"book_id": u["book_id"], "odds_side": u[mine],
                                      "odds_other": u[theirs], "updated": u.get("updated")}
                                     for u in bench["quotes_used"]],
                        source="exchange_benchmark")

    new = {"retail_consensus": retail, "exchange": exchange}
    replaced = [name for name in new if want[name] and new[name] is not None]
    if not replaced:
        if retail is None and exchange is None:
            return None, (oid, "skip", "no fresh two-way consensus and no exchange "
                                       "benchmark at the observation's line")
        return None, (oid, "keep", "existing closes are closer to the start")
    close = {"retail_consensus": existing.get("retail_consensus"),
             "exchange": existing.get("exchange")}
    for name in replaced:
        close[name] = new[name]
    close.update(side=side, captured_at=stamp["captured_at"],
                 minutes_before_start=stamp["minutes_before_start"])

    def _realized(sub):
        return None if not sub else round(ve.projected_clv(sub["fair_p"], p_entry), 6)

    update = {"close": close,
              "realized_clv_exchange_frac": _realized(close["exchange"]),
              "realized_clv_retail_frac": _realized(close["retail_consensus"])}
    return update, (oid, "captured",
                    f"T-{mins:.0f}m {obs.get('bet') or side} "
                    f"exchange={update['realized_clv_exchange_frac']} "
                    f"retail={update['realized_clv_retail_frac']} ({stamp['vintage']})")


def apply_observation_updates(store, updates):
    """Write capture_observations' updates onto the store's rows; returns # updated.
    Only `close` and the two realized CLV fields are set."""
    n = 0
    for obs in (store or {}).get("observations") or []:
        u = (updates or {}).get(obs.get("id"))
        if u:
            obs.update(close=u["close"],
                       realized_clv_exchange_frac=u["realized_clv_exchange_frac"],
                       realized_clv_retail_frac=u["realized_clv_retail_frac"])
            n += 1
    return n


def save_observation_closes(path, updates, lock_timeout=None):
    """Re-read the observations file, apply `updates`, write it back atomically.

    Re-reading right before the write (not reusing the copy loaded before the network
    calls) keeps an observation or run row the 09:00 scan appended meanwhile, and the
    read-merge-write holds `v3_scan.store_lock` (the scan's --apply holds it too). If
    the lock stays held past `lock_timeout` (default v3_scan.LOCK_TIMEOUT_SEC), this
    write is skipped and logged; the next pass captures again. Returns # rows updated."""
    import v3_scan
    with v3_scan.store_lock(path, lock_timeout) as locked:
        if not locked:
            print(f"  ⚠️  v3 observations: {v3_scan.lock_path(path)} held past the timeout; "
                  "closes NOT written this pass", file=sys.stderr)
            return 0
        store = v3_scan.load_store(path)
        n = apply_observation_updates(store, updates)
        if n:
            v3_scan.save_store(path, store)
        return n


def make_event_start(sport, *, bp):
    """`event_start(date, event_id) -> aware UTC datetime | None` from the day's /events.

    BettingPros `scheduled` is UTC ("2026-10-25 17:00:00"). One /events call per date.
    An event missing from the list, or with no parseable `scheduled`, gives None.
    """
    by_date = {}

    def event_start(date, event_id):
        if date not in by_date:
            by_date[date] = {ev.get("id"): _parse_scheduled(ev.get("scheduled"))
                             for ev in bp.fetch_events(sport, date)}
        return by_date[date].get(event_id)

    return event_start


def _parse_scheduled(ts):
    """BettingPros `scheduled` (UTC, no offset) -> aware UTC datetime, else None."""
    ts = (ts or "").strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            return datetime.strptime(ts, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def make_events_for(sport, *, bp):
    """`events_for(date) -> [{"id", "start", "participants"}]` for capture_game_lines,
    from the day's /events (scheduled UTC start; home + visitor teams). An event with
    no parseable start is dropped: it can never be shown to be pre-game."""
    def events_for(date):
        out = []
        for ev in bp.fetch_events(sport, date):
            start = _parse_scheduled(ev.get("scheduled"))
            if ev.get("id") is not None and start is not None:
                out.append({"id": ev["id"], "start": start,
                            "participants": ev.get("participants") or []})
        return out
    return events_for


def _sport_of(pick):
    """Uppercase sport; a blank sport is MLB, as in tracker._stat_map_for_sport."""
    return (pick.get("sport") or "").upper() or "MLB"


def capture_live(picks, now=None, *, tracker=None, bp=None, clv_fetch=None,
                 window_minutes=45, snapshots=None):
    """Live wiring: the same per-sport seams clv_fetch.build_closes_live uses, aimed at
    open picks. Runs `capture` once per sport in clv_fetch.CLOSE_SPORTS. MLB keeps its
    original wiring (no event-start fallback); NBA and NFL also time a pick with no
    game_time by its event's scheduled UTC start."""
    import importlib
    tracker = tracker or importlib.import_module("tracker")
    bp = bp or importlib.import_module("bettingpros")
    cf = clv_fetch or importlib.import_module("clv_fetch")
    now = now or datetime.now(AZ)

    snaps = snapshots if snapshots is not None else load_snapshots()
    report = []
    for sport in cf.CLOSE_SPORTS:
        mine = [p for p in picks if _sport_of(p) == sport]
        if not mine:
            continue
        # Game lines (#109) go to their own matcher; every other pick takes the
        # original prop path exactly as before.
        games = [p for p in mine if tracker.classify_bet(p) in GAME_LINE_KIND]
        if games:
            snaps, rows = capture_game_lines(
                games, now,
                events_for=make_events_for(sport, bp=bp),
                fetch_ladders=lambda ev, mk, _s=sport: bp.fetch_game_line_ladders(
                    ev, mk, sport=_s),
                market_for_kind=cf.GAME_LINE_MARKET.get(sport, {}).get,
                classify_bet=tracker.classify_bet,
                window_minutes=window_minutes,
                snapshots=snaps,
            )
            report.extend(rows)
            mine = [p for p in mine if tracker.classify_bet(p) not in GAME_LINE_KIND]
            if not mine:
                continue
        snaps, rows = capture(
            mine, now,
            normalize_name=tracker._normalize_name,
            two_way_at_line=cf.two_way_at_line,
            classify_bet=tracker.classify_bet,
            window_minutes=window_minutes,
            snapshots=snaps,
            event_start=None if sport == "MLB" else make_event_start(sport, bp=bp),
            **cf.sport_seams(sport, tracker=tracker, bp=bp),
        )
        report.extend(rows)
    for p in picks:
        if p.get("result") is None and _sport_of(p) not in cf.CLOSE_SPORTS:
            report.append((p.get("id"), "skip", f"sport {_sport_of(p)} has no close capture"))
    return snaps, report


def capture_observations_live(now=None, *, bp=None, window_minutes=45, path=None):
    """Live wiring for `capture_observations` over the observations file at `path`
    (default OBSERVATIONS_FILE). Reads only; the caller saves with
    `save_observation_closes`. No file yet = nothing to capture."""
    import importlib
    bp = bp or importlib.import_module("bettingpros")
    path = path or OBSERVATIONS_FILE
    if not os.path.exists(path):
        return {}, []
    import v3_scan
    store = v3_scan.load_store(path)
    now = now or datetime.now(timezone.utc)
    return capture_observations(
        store, now, window_minutes=window_minutes,
        fetch_offers=lambda sport, ev, mk: bp.fetch_raw_offers(ev, mk, sport=sport))
