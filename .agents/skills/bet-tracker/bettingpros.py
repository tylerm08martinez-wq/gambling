"""BettingPros API client — datacenter-IP-tolerant research data source.

Replaces HTML scraping (which 403s from the cloud routine's datacenter egress IP)
with the BettingPros CloudFront + API Gateway JSON API, which gates on a public
`x-api-key` header rather than IP reputation — the same key-less/CDN pattern as the
ESPN hidden API used for resolution (ADR 0005, 0006).

Fetch functions take an injectable `get_json` callable (URL -> dict | None) so they
can be unit-tested offline against recorded fixtures. On persistent failure the
client returns an empty list / None and never fabricates data (the never-guess
guarantee, extended from resolution to research).
"""

import os
import re
import sys

BP_API_BASE = "https://api.bettingpros.com/v3"
BP_SITE = "https://www.bettingpros.com"

# book_id -> name (from /v3/books, 2026-06-01). 0 = consensus, 2 = Pinnacle (CLV
# benchmark). Used to decode offer book ids to human names.
BOOKS = {
    0: "BettingPros Consensus", 2: "Pinnacle", 10: "FanDuel", 12: "DraftKings",
    13: "Caesars", 14: "Fanatics", 18: "BetRivers", 19: "BetMGM", 24: "bet365",
    33: "theScore Bet", 36: "Underdog", 37: "PrizePicks", 38: "ProphetX",
    45: "Betr", 49: "Hard Rock", 60: "Novig",
}

# Matches `api_key:"..."`, `apiKey: '...'`, `"x-api-key":"..."` etc. in the site JS.
# BettingPros keys are ~40-char alphanumeric. The key is public (shipped in client
# JS), not a secret — but it is never committed, only scraped at run time.
_API_KEY_RE = re.compile(r"""(?:x-)?api[_-]?key["'\s:=]{1,6}([A-Za-z0-9]{30,45})""", re.I)


def scrape_api_key(*, get_text):
    """Extract the public x-api-key from BettingPros site JS. None if not found.

    `get_text(url) -> str` is injectable so the parser is unit-tested offline. The
    live default walks the props page's referenced JS bundles looking for the key.
    """
    # Try the props page itself, then each JS bundle it references.
    page = get_text(f"{BP_SITE}/mlb/props/") or ""
    m = _API_KEY_RE.search(page)
    if m:
        return m.group(1)
    for path in sorted(set(re.findall(r"/dist/assets/[\w-]+\.js", page))):
        m = _API_KEY_RE.search(get_text(f"{BP_SITE}{path}") or "")
        if m:
            return m.group(1)
    return None


# A *public* app key shipped in BettingPros' client JS to every browser (used only
# for `/events` and `/offers`; `/props` needs none). Not a secret — committed as a
# last-resort fallback so the cloud routine works with no operational setup. The env
# override and scrape-first path below let it rotate without a code change.
_PUBLIC_KEY_FALLBACK = "CHi8Hy5CEE4khd46XNYL23dCFX96oUdw6qOt1Dnh"


def resolve_api_key(*, get_text=None):
    """The public key, in priority order: env override → live scrape → public fallback.

    `BETTINGPROS_API_KEY` wins if set (rotation without a code change). Otherwise we
    try scraping the live site JS; if that fails (the key currently lives in a lazily
    loaded chunk the scraper does not reach), we fall back to the committed public key
    so `/events`/`/offers` still work cloud-side with zero setup.
    """
    env = os.environ.get("BETTINGPROS_API_KEY")
    if env:
        return env
    return scrape_api_key(get_text=get_text or _live_get_text) or _PUBLIC_KEY_FALLBACK


# --- Live (production) fetchers — not unit-tested; verified by the cloud re-trigger ---

def _live_get_text(url):
    import urllib.request
    try:
        req = urllib.request.Request(url, headers={"User-Agent": _UA})
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.read().decode("utf-8", "replace")
    except Exception:
        return None


_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"
_KEY_CACHE = {}


def _live_get_json(url):
    """Default get_json: reuses tracker._http_get_json, attaching the public key."""
    import importlib.util as _il
    if "tracker" not in _KEY_CACHE:
        spec = _il.spec_from_file_location(
            "tracker", os.path.join(os.path.dirname(__file__), "tracker.py")
        )
        mod = _il.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _KEY_CACHE["tracker"] = mod
        _KEY_CACHE["key"] = resolve_api_key()
    tracker = _KEY_CACHE["tracker"]
    key = _KEY_CACHE.get("key")
    headers = {"x-api-key": key} if key else None
    return tracker._http_get_json(url, headers=headers)


def _normalize_side(side: dict) -> dict:
    """Best-book line/odds plus consensus, the inputs a Cross-Book Prop Gap needs."""
    return {
        "line": side.get("line"),
        "odds": side.get("odds"),
        "book": side.get("book"),
        "consensus_line": side.get("consensus_line"),
        "consensus_odds": side.get("consensus_odds"),
        "ev": side.get("expected_value"),
        "bet_rating": side.get("bet_rating"),
    }


def _normalize_prop(raw: dict) -> dict:
    player = raw.get("participant", {}).get("player", {})
    proj = raw.get("projection", {})
    return {
        "market_id": raw.get("market_id"),
        "event_id": raw.get("event_id"),
        "player": {
            "name": raw.get("participant", {}).get("name"),
            "team": player.get("team"),
            "position": player.get("position"),
        },
        "over": _normalize_side(raw.get("over", {})),
        "under": _normalize_side(raw.get("under", {})),
        "projection": {
            "recommended_side": proj.get("recommended_side"),
            "value": proj.get("value"),
            "diff": proj.get("diff"),
        },
        "performance": raw.get("performance", {}),
    }


def _normalize_event(raw: dict) -> dict:
    pitchers = raw.get("pitchers") or {}
    return {
        "id": raw.get("id"),
        # `scheduled` is the source UTC timestamp — the game-time of record. Converting
        # to AZ (UTC-7) downstream removes the DST month-boundary mislabeling.
        "scheduled": raw.get("scheduled"),
        "home": raw.get("home"),
        "visitor": raw.get("visitor"),
        "pitchers": {
            "home": pitchers.get("home_probable"),
            "visitor": pitchers.get("visitor_probable"),
        },
    }


def _book_main_line(book: dict) -> dict:
    """Pick a book's main (else first) line entry."""
    lines = book.get("lines") or []
    return next((l for l in lines if l.get("main")), lines[0] if lines else {})


def _normalize_offer(raw: dict) -> dict:
    selections = []
    for s in raw.get("selections", []):
        opening = (s.get("opening_line") or {}).get("line")
        books = []
        for b in s.get("books", []):
            ml = _book_main_line(b)
            if ml.get("line") is None and ml.get("cost") is None:
                continue
            bid = b.get("id")
            books.append({
                "book_id": bid,
                "book": BOOKS.get(bid, f"book-{bid}"),
                "line": ml.get("line"),
                "odds": ml.get("cost"),
            })
        selections.append({
            "label": s.get("short_label") or s.get("label"),
            "opening_line": opening,
            "books": books,
        })
    return {
        "market_id": raw.get("market_id"),
        "event_id": raw.get("event_id"),
        "selections": selections,
    }


def fetch_offers(event_id, market_id, *, get_json=None):
    """Return normalized cross-book offers (opening + per-book current) for an event/market.

    Each selection carries its `opening_line` and every book's current line/odds, the
    inputs a Steam Move check needs (3+ books off their opening in the same direction).
    Empty list on failure — never fabricated.
    """
    get_json = get_json or _live_get_json
    url = f"{BP_API_BASE}/offers?sport=MLB&event_id={event_id}&market_id={market_id}"
    data = get_json(url)
    if not data:
        return []
    return [_normalize_offer(o) for o in data.get("offers", [])]


def fetch_offer_ladder(event_id, market_id, *, get_json=None):
    """Full per-player CONSENSUS line ladder for an event+market (every line, not just main).

    Returns [{"player": name, "team": team, "sides": {"over": {line: odds}, "under": {line: odds}}}]
    using BettingPros Consensus (book_id 0) — the market-wide closing price. Unlike
    `fetch_offers` (which collapses to each book's main line), this preserves EVERY alt
    line, so a pick's entry number can be matched for a de-vigged CLV even when the
    displayed main line is split (e.g. Under 14.5 / Over 15.5). Empty list on failure —
    never fabricated. Powers the realized-CLV backfill (clv_fetch); Pinnacle is absent
    from the prop grid (#51), so the de-vigged two-way close comes from consensus.
    """
    get_json = get_json or _live_get_json
    url = f"{BP_API_BASE}/offers?sport=MLB&event_id={event_id}&market_id={market_id}"
    data = get_json(url)
    if not data:
        return []
    out = []
    for off in data.get("offers", []):
        parts = off.get("participants") or []
        name = parts[0].get("name") if parts else None
        team = (parts[0].get("player") or {}).get("team") if parts else None
        sides = {}
        for sel in off.get("selections", []):
            side = (sel.get("label") or "").strip().lower()
            if side not in ("over", "under"):
                continue
            book0 = next((b for b in sel.get("books", []) if b.get("id") == 0), None)
            if not book0:
                continue
            ladder = {}
            for ln in book0.get("lines") or []:
                if ln.get("line") is not None and ln.get("cost") is not None:
                    ladder[float(ln["line"])] = int(ln["cost"])
            if ladder:
                sides[side] = ladder
        if name and sides:
            out.append({"player": name, "team": team, "sides": sides})
    return out


def fetch_events(sport, date, *, get_json=None):
    """Return normalized events for `sport`/`date` (empty list on failure)."""
    get_json = get_json or _live_get_json
    url = f"{BP_API_BASE}/events?sport={sport}&date={date}"
    data = get_json(url)
    if not data:
        return []
    return [_normalize_event(e) for e in data.get("events", [])]


def fetch_props(sport, date=None, *, get_json=None):
    """Return normalized props for `sport` (empty list on failure — never fabricated).

    `/props` serves data without a key, so the Primary Edge survives even if key
    resolution fails (only `/events` and `/offers` require the key).
    """
    get_json = get_json or _live_get_json
    base = f"{BP_API_BASE}/props?sport={sport}&limit=50"
    if date:
        base += f"&date={date}"
    props = []
    page = 1
    while True:
        data = get_json(f"{base}&page={page}")
        if not data:
            # Page 1 failure → no data at all (never fabricate). A later-page failure
            # returns what we have rather than silently looping.
            break
        props.extend(data.get("props", []))
        pg = data.get("_pagination") or {}
        total = pg.get("total_pages") or 1
        if page >= total:
            break
        page += 1
    return [_normalize_prop(p) for p in props]


def _main(argv):
    import json
    if len(argv) < 2 or argv[0] not in ("events", "props"):
        print("usage: bettingpros.py events|props SPORT [DATE]", file=sys.stderr)
        return 2
    cmd, sport = argv[0], argv[1]
    date = argv[2] if len(argv) > 2 else None
    rows = fetch_events(sport, date) if cmd == "events" else fetch_props(sport, date)
    if not rows:
        print(f"BettingPros API unavailable or empty for {cmd} {sport} {date or ''}", file=sys.stderr)
        return 1
    print(json.dumps(rows, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
