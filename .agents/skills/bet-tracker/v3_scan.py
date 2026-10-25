"""V3 Observation Scan: the deterministic morning run of the V3-Value engine (#108).

ADR 0011 runs V3 for one week as plain code, with no model call, before any V3 pick is
logged. Every morning this scans the board (BettingPros /offers for every not-started
event and every in-scope market), prices each retail sportsbook quote against the
Exchange Benchmark with `value_engine.scan_market`, and writes every price whose
projected CLV clears the market kind's gate (2% game lines, 3% props) to
`v3-observations.json`.

It never reads or writes picks.json. Observations never count toward stats, the
dashboard or the Daily Pick Cap (GLOSSARY.md: Observation Scan).

An observation is any row whose projected CLV clears `gate_threshold(kind)`, whatever
the ½-Kelly sizing says: ADR 0009 measurement mode sizes flat at 1u, so a +2.24% +260
price whose Kelly stake rounds to 0u is still a candidate. `units_kelly` is stored as
information only.

    python3 v3_scan.py --date YYYY-MM-DD [--sports NBA,NFL,MLB] [--apply] [--out PATH]

Without --apply it prints the result and writes nothing. With --apply it appends a run
row and every not-yet-seen observation to the output file. Re-running the same day
never duplicates a row and never overwrites a first-seen price. Exit status 2 when the
scan failed loudly (a sport with events returned zero offers on every market, which is
what a wrong market id or an outage looks like). Residential IP only (ADR 0006).
"""

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bettingpros as bp    # noqa: E402
import value_engine as ve   # noqa: E402

OBSERVATIONS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                 "v3-observations.json")

# (market_id, kind, stat label) per sport. Ids from /v3/markets?sport=..., 2026-10-24.
# A wrong id returns an empty list and looks like an outage, hence the per-market
# counts and the zero-offers failure in `scan`.
MARKETS = {
    "NBA": [
        (127, "moneyline", "moneyline"), (128, "total", "total"), (129, "spread", "spread"),
        (156, "prop", "points"), (157, "prop", "rebounds"), (151, "prop", "assists"),
        (335, "prop", "points + assists"), (336, "prop", "points + rebounds"),
        (337, "prop", "rebounds + assists"), (338, "prop", "points + rebounds + assists"),
        # threes (162), steals (160) and blocks (152) are skipped (#108).
    ],
    "NFL": [
        (1, "moneyline", "moneyline"), (2, "total", "total"), (3, "spread", "spread"),
        (103, "prop", "passing yards"), (100, "prop", "passing completions"),
        (333, "prop", "passing attempts"), (104, "prop", "receptions"),
        (105, "prop", "receiving yards"), (106, "prop", "rushing attempts"),
        (107, "prop", "rushing yards"), (406, "prop", "rushing + receiving yards"),
        # Low-count props (interceptions 101, passing TDs 102, touchdowns 334) and
        # fantasy points (253) are skipped, the NFL analogue of NBA threes/steals/blocks.
    ],
    "MLB": [
        (122, "moneyline", "moneyline"), (175, "total", "total"), (176, "spread", "run line"),
        (285, "prop", "strikeouts"), (405, "prop", "outs recorded"),
    ],
}

# Retail candidate names (ADR 0011). bettingpros.BOOKS lacks Fliff (39).
BOOK_NAMES = {
    10: "FanDuel", 12: "DraftKings", 13: "Caesars", 14: "Fanatics", 18: "BetRivers",
    19: "BetMGM", 24: "bet365", 33: "theScore Bet", 39: "Fliff", 45: "Betr", 49: "Hard Rock",
}


def _book_name(book_id):
    return BOOK_NAMES.get(book_id) or bp.BOOKS.get(book_id, f"book-{book_id}")


def _parse_utc(ts):
    """BettingPros 'YYYY-MM-DD HH:MM:SS' (UTC, no offset) -> aware datetime, else None."""
    if not isinstance(ts, str) or not ts.strip():
        return None
    try:
        dt = datetime.fromisoformat(ts.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def _iso_z(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def fetch_offer_pages(sport, event_id, market_id, get_json):
    """Every /offers page for one event and market -> (offers, fetch_ok).

    Paginates via `_pagination.total_pages` (the feed serves 10 offers a page). A page
    that fails returns what was fetched so far with fetch_ok False; never fabricated."""
    base = f"{bp.BP_API_BASE}/offers?sport={sport}&event_id={event_id}&market_id={market_id}"
    offers, page, total = [], 1, 1
    while page <= total:
        data = get_json(base if page == 1 else f"{base}&page={page}")
        if not data:
            return offers, False
        offers.extend(data.get("offers") or [])
        total = int((data.get("_pagination") or {}).get("total_pages") or 1)
        page += 1
    return offers, True


def _fmt_line(line):
    return f"{float(line):g}"


def _participant_and_bet(offer, kind, stat, side_label, line, event):
    """(participant, human-readable bet) for one observed side."""
    if kind == "prop":
        parts = offer.get("participants") or []
        player = (parts[0].get("name") if parts else None) or "?"
        return player, f"{player} {side_label} {_fmt_line(line)} {stat}"
    if kind == "total":
        game = f"{event.get('visitor')} @ {event.get('home')}"
        return game, f"{game} {side_label} {_fmt_line(line)}"
    if kind == "spread":
        return side_label, f"{side_label} {float(line):+g}"
    return side_label, f"{side_label} ML"


def observation_id(scan_date, event_id, market_id, participant, line, side, book_id):
    """Deterministic id from scan date, event, market, participant, line, side and book."""
    key = "|".join(str(x) for x in (scan_date, event_id, market_id, participant,
                                    "" if line is None else _fmt_line(line), side, book_id))
    return "v3obs-" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]


def scan(scan_date, sports, now, get_json=None, log=None):
    """Scan the board for `scan_date` -> {"run": run_row, "observations": [...]}.

    `now` must be timezone-aware; events starting at or before it are skipped. `log`
    receives one progress line per market (default: stderr)."""
    ve._require_aware(now)
    get_json = get_json or bp._live_get_json
    log = log or (lambda msg: print(msg, file=sys.stderr))
    scanned_at = _iso_z(now)
    observations = []
    for sport in sports:
        events = bp.fetch_events(sport, scan_date, get_json=get_json)
        for event in events:
            start = _parse_utc(event.get("scheduled"))
            if start is None or start <= now:
                continue
            for market_id, kind, stat in MARKETS[sport]:
                offers, _ok = fetch_offer_pages(sport, event["id"], market_id, get_json)
                gate = ve.gate_threshold(kind)
                for offer in offers:
                    parsed = ve.quotes_from_offer(offer, kind)
                    if not parsed["labels"]:
                        continue
                    for row in ve.scan_market(parsed["quotes"], kind, now):
                        if row["clv"] < gate:
                            continue
                        side = parsed["labels"][0 if row["side"] == "a" else 1]
                        participant, bet = _participant_and_bet(
                            offer, kind, stat, side, row["line"], event)
                        observations.append({
                            "id": observation_id(scan_date, event["id"], market_id,
                                                 participant, row["line"], side,
                                                 row["book_id"]),
                            "scan_date": scan_date, "scanned_at": scanned_at,
                            "sport": sport, "event_id": event["id"],
                            "event": f"{event.get('visitor')} @ {event.get('home')}",
                            "start_utc": _iso_z(start), "market_id": market_id,
                            "market": stat, "kind": kind, "participant": participant,
                            "bet": bet, "line": row["line"], "side": side,
                            "selection": row["side"], "book_id": row["book_id"],
                            "book": _book_name(row["book_id"]), "odds": row["odds"],
                            "p_best": round(row["p_best"], 6),
                            "fair_p": round(row["fair_p"], 6),
                            "projected_clv": round(row["clv"], 6), "gate": gate,
                            "units_kelly": row["units"],
                            "benchmark_operators": row["operators"],
                            "quote_updated": row["updated"],
                            "quote_age_min": round(row["quote_age_min"], 1),
                            "benchmark_max_age_min": round(row["benchmark_max_age_min"], 1),
                            "close": None,
                        })
    return {"run": {}, "observations": observations}
