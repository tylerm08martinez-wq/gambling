"""V3 Observation Scan: the deterministic morning run of the V3-Value engine (#108).

ADR 0011 runs V3 for one week as plain code, with no model call, before any V3 pick is
logged. Every morning this scans the board (BettingPros /offers for every not-started
event and every in-scope market), prices each retail sportsbook quote against the
Exchange Benchmark with `value_engine.scan_market`, and writes every price whose
projected CLV clears the market kind's gate (2% game lines, 3% props) to
`v3-observations.json`.

It never reads or writes the picks ledger. Observations never count toward stats, the
dashboard or the Daily Pick Cap (GLOSSARY.md: Observation Scan).

An observation is any row whose projected CLV clears `gate_threshold(kind)`, whatever
the ½-Kelly sizing says: ADR 0009 measurement mode sizes flat at 1u, so a +2.24% +260
price whose Kelly stake rounds to 0u is still a candidate. `units_kelly` is stored as
information only.

    python3 v3_scan.py --date YYYY-MM-DD [--sports NBA,NFL,MLB] [--apply] [--out PATH]

Without --apply it prints the result and writes nothing. With --apply it appends a run
row and every not-yet-seen observation to the output file. Re-running the same day
never duplicates a row and never overwrites a first-seen price.

Run status and exit code: `ok` (0) only for a clean board; `degraded` (3) when any
request failed but the scan finished; `failed` (2) when the scan stopped early (past
--deadline-sec, default 300s, or after 5 consecutive failed requests), crashed, or a
sport with events returned zero offers on every market (what a wrong market id or an
outage looks like). Every outcome, a crash included, still writes its run row under
--apply. Residential IP only (ADR 0006).
"""

import argparse
import hashlib
import json
import os
import sys
import time
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


DEFAULT_DEADLINE_SEC = 300       # the scan runs before V1/V2; it must never delay them
MAX_CONSECUTIVE_FAILURES = 5     # this many failed requests in a row = the feed is down


class _StopScan(Exception):
    """Raised between fetches when the scan must stop (deadline or a dead feed)."""


class _Fetcher:
    """Wraps get_json: counts failed requests and enforces the stop conditions.

    Checked before every request: the wall-clock deadline (`clock` is monotonic
    seconds, injectable for tests) and the consecutive-failure limit. A request that
    returns nothing is a failure; any successful response resets the streak."""

    def __init__(self, get_json, deadline_sec, clock, max_consecutive):
        self.get_json, self.clock = get_json, clock
        self.deadline_sec, self.max_consecutive = deadline_sec, max_consecutive
        self.started = clock()
        self.requests = self.failures = self.streak = 0

    def __call__(self, url):
        elapsed = self.clock() - self.started
        if self.deadline_sec is not None and elapsed > self.deadline_sec:
            raise _StopScan(f"deadline of {self.deadline_sec:g}s exceeded after "
                            f"{self.requests} requests; scan stopped early")
        self.requests += 1
        data = self.get_json(url)
        if data:
            self.streak = 0
            return data
        self.failures += 1
        self.streak += 1
        if self.streak >= self.max_consecutive:
            raise _StopScan(f"{self.streak} consecutive failed requests "
                            f"(last: {url}); scan stopped early")
        return data


def _has_benchmark(quotes, kind, now):
    """True if any line in this market has an Exchange Benchmark, retail quote or not."""
    lines = {None} if kind == "moneyline" else {
        q.get("line") for q in quotes if q.get("book_id") in ve.BENCHMARK_BOOKS}
    return any(ve.exchange_benchmark(quotes, line, kind, now) for line in lines)


def _run_row(scan_date, scanned_at, sports, errors, failures=0, **counts):
    status = "failed" if errors else ("degraded" if failures else "ok")
    row = {"scan_date": scan_date, "scanned_at": scanned_at, "sports": list(sports)}
    row.update(counts)
    row.update(fetch_failures=failures, errors=errors, status=status)
    return row


def failed_run(scan_date, sports, now, error):
    """The run row for a scan that crashed before it could count anything."""
    return _run_row(scan_date, _iso_z(now), sports, [error], events_by_sport={},
                    events_started=0, markets_scanned=0, markets_with_benchmark=0,
                    markets_scored=0, candidates=0, offers_by_market={})


def scan(scan_date, sports, now, get_json=None, log=None,
         deadline_sec=DEFAULT_DEADLINE_SEC, clock=None,
         max_consecutive_failures=MAX_CONSECUTIVE_FAILURES):
    """Scan the board for `scan_date` -> {"run": run_row, "observations": [...]}.

    `now` must be timezone-aware; events starting at or before it are skipped. `log`
    receives one progress line per market (default: stderr).

    Run status: `ok` only for a clean board; `degraded` when any request failed but
    the scan finished; `failed` when it stopped early (past `deadline_sec`, or after
    `max_consecutive_failures` failed requests in a row) or hit a zero-offer / no-event
    condition. Observations collected before an early stop are kept: they are real
    prices.

    Counts: `markets_scanned` is every /offers market (one per player for props);
    `markets_with_benchmark` those with an Exchange Benchmark at any line;
    `markets_scored` those where a fresh retail price was priced against it."""
    ve._require_aware(now)
    fetch = _Fetcher(get_json or bp._live_get_json, deadline_sec,
                     clock or time.monotonic, max_consecutive_failures)
    log = log or (lambda msg: print(msg, file=sys.stderr))
    scanned_at = _iso_z(now)
    observations, errors = [], []
    events_by_sport, offers_by_market = {}, {}
    counts = {"events_started": 0, "markets_scanned": 0, "markets_with_benchmark": 0,
              "markets_scored": 0}
    try:
        for sport in sports:
            _scan_sport(sport, scan_date, now, fetch, log, scanned_at, observations,
                        errors, events_by_sport, offers_by_market, counts)
        if sports and not any(events_by_sport.values()):
            errors.append(f"no events for any of {', '.join(sports)} on {scan_date} "
                          "(events feed outage?)")
    except _StopScan as stop:
        errors.append(str(stop))
        log(f"  STOPPED: {stop}")
    run = _run_row(scan_date, scanned_at, sports, errors, fetch.failures,
                   events_by_sport=events_by_sport, candidates=len(observations),
                   offers_by_market=offers_by_market, requests=fetch.requests, **counts)
    return {"run": run, "observations": observations}


def _scan_sport(sport, scan_date, now, fetch, log, scanned_at, observations, errors,
                events_by_sport, offers_by_market, counts):
    events = bp.fetch_events(sport, scan_date, get_json=fetch)
    events_by_sport[sport] = len(events)
    upcoming = []
    for event in events:
        start = _parse_utc(event.get("scheduled"))
        if start is None or start <= now:
            counts["events_started"] += 1
        else:
            upcoming.append((event, start))
    sport_offers = 0
    for market_id, kind, stat in MARKETS[sport]:
        gate = ve.gate_threshold(kind)
        market_offers = 0
        for event, start in upcoming:
            offers, _ok = fetch_offer_pages(sport, event["id"], market_id, fetch)
            market_offers += len(offers)
            for offer in offers:
                parsed = ve.quotes_from_offer(offer, kind)
                if not parsed["labels"]:
                    continue
                counts["markets_scanned"] += 1
                counts["markets_with_benchmark"] += _has_benchmark(parsed["quotes"], kind, now)
                rows = ve.scan_market(parsed["quotes"], kind, now)
                counts["markets_scored"] += 1 if rows else 0
                for row in rows:
                    if row["clv"] >= gate:
                        observations.append(_observation(
                            row, parsed["labels"], offer, kind, stat, gate, event, start,
                            sport, market_id, scan_date, scanned_at))
        offers_by_market[f"{sport}:{market_id}"] = market_offers
        sport_offers += market_offers
        if upcoming:
            log(f"  {sport} market {market_id} ({stat}): {market_offers} offers "
                f"across {len(upcoming)} events")
    if upcoming and sport_offers == 0:
        errors.append(f"{sport}: zero offers on every market across {len(upcoming)} "
                      "not-started events (wrong market ids or a feed outage)")


def _observation(row, labels, offer, kind, stat, gate, event, start, sport, market_id,
                 scan_date, scanned_at):
    side = labels[0 if row["side"] == "a" else 1]
    participant, bet = _participant_and_bet(offer, kind, stat, side, row["line"], event)
    return {
        "id": observation_id(scan_date, event["id"], market_id, participant, row["line"],
                             side, row["book_id"]),
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
    }


# ==================================================================================
# the observations file
# ==================================================================================
def merge(store, result):
    """Fold one scan result into the {"runs", "observations"} store; returns the store.

    Appends the run row (stamped with `new_observations`) and every observation whose
    id isn't already stored. A stored observation is never touched: its first-seen
    price is the one the review measures."""
    store.setdefault("runs", [])
    store.setdefault("observations", [])
    seen = {o.get("id") for o in store["observations"]}
    added = 0
    for obs in result["observations"]:
        if obs["id"] in seen:
            continue
        seen.add(obs["id"])
        store["observations"].append(obs)
        added += 1
    store["runs"].append(dict(result["run"], new_observations=added))
    return store


def load_store(path):
    if not os.path.exists(path):
        return {"runs": [], "observations": []}
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict) or not isinstance(data.get("runs"), list) \
            or not isinstance(data.get("observations"), list):
        raise ValueError(f"{path} is not a {{runs, observations}} observations file")
    return data


def save_store(path, store):
    """Atomic write: a crash mid-write never leaves a truncated observations file."""
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(store, f, indent=1)
        f.write("\n")
    os.replace(tmp, path)


# ==================================================================================
# CLI
# ==================================================================================
EXIT_CODES = {"ok": 0, "failed": 2, "degraded": 3}


def main(argv=None, get_json=None, now=None, clock=None):
    ap = argparse.ArgumentParser(description="V3 Observation Scan (ADR 0011, #108)")
    ap.add_argument("--date", required=True, help="slate date, YYYY-MM-DD")
    ap.add_argument("--sports", default="NBA,NFL,MLB", help="comma list (default NBA,NFL,MLB)")
    ap.add_argument("--apply", action="store_true", help="write to --out (default: print only)")
    ap.add_argument("--out", default=OBSERVATIONS_FILE, help="observations file path")
    ap.add_argument("--deadline-sec", type=float, default=DEFAULT_DEADLINE_SEC,
                    help=f"stop the scan after this many seconds (default {DEFAULT_DEADLINE_SEC})")
    args = ap.parse_args(argv)
    try:
        datetime.strptime(args.date, "%Y-%m-%d")
    except ValueError:
        ap.error(f"--date must be YYYY-MM-DD, got {args.date!r}")
    sports = [s.strip().upper() for s in args.sports.split(",") if s.strip()]
    if not sports or any(s not in MARKETS for s in sports):
        ap.error(f"--sports must be from {sorted(MARKETS)}, got {args.sports!r}")

    now = now or datetime.now(timezone.utc)
    print(f"V3 Observation Scan {args.date} at {_iso_z(now)} ({', '.join(sports)})",
          file=sys.stderr)
    try:
        result = scan(args.date, sports, now, get_json=get_json,
                      deadline_sec=args.deadline_sec, clock=clock)
    except Exception as exc:   # a crash still leaves a failed run row for the review
        error = f"scan crashed: {type(exc).__name__}: {exc}"
        print(f"ERROR: {error}", file=sys.stderr)
        result = {"run": failed_run(args.date, sports, now, error), "observations": []}
    run = result["run"]
    if args.apply:
        store = merge(load_store(args.out), result)
        save_store(args.out, store)
        run = store["runs"][-1]
    print(json.dumps({"run": run, "observations": result["observations"]}, indent=1))
    for err in run["errors"]:
        print(f"ERROR: {err}", file=sys.stderr)
    print(f"status={run['status']} markets_scanned={run['markets_scanned']} "
          f"with_benchmark={run['markets_with_benchmark']} scored={run['markets_scored']} "
          f"candidates={run['candidates']} fetch_failures={run['fetch_failures']}"
          + (f" new={run['new_observations']} -> {args.out}" if args.apply else " (dry run)"),
          file=sys.stderr)
    return EXIT_CODES.get(run["status"], 2)


if __name__ == "__main__":
    sys.exit(main())
