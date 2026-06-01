---
name: sports-betting
description: "V1-TRENDS: Find today's best sports bets using ATS trends, expert consensus, situational angles, and line movement. Use when looking for today's best bets (trends-based model). Compare performance against sports-betting-sharp."
argument-hint: [sport or "all"]
allowed-tools: WebSearch, WebFetch, Read, Write, Bash
---

# V1-Trends — Today's Best Bets

## Goal
Identify value bets from props, ATS trends, situational spots, line movement, and expert consensus. **Props and totals are the primary targets** — moneylines only with confirmed sharp signal.

**Sport scope: MLB, NBA, NFL only.** Research only active seasons — do not waste tokens on sports not currently in season:
- **MLB:** April – October
- **NBA:** October – June (playoffs through June)
- **NFL:** September – February (preseason Aug, regular season Sep–Jan, playoffs through Feb)
- If today's date falls outside a sport's season, skip it entirely.

**Daily cap: 5 picks maximum across V1 and V2 combined, with no more than 3 V1 picks and no more than 3 V2 picks. No minimum picks.** Check Step 0 for today's count before researching. If already at 5 total or 3 V1 picks, output "Daily cap reached — sitting out."

## Data source — BettingPros API (datacenter-IP-tolerant)

All prop/odds/event research goes through the **BettingPros client** and **prop-edge extractor** (ADR 0006), not HTML scraping — scrapers 403 from the cloud routine's datacenter egress IP. The two modules live in `.agents/skills/bet-tracker/`:

```bash
GAMBLING="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
BP="$GAMBLING/.agents/skills/bet-tracker/bettingpros.py"
PE="$GAMBLING/.agents/skills/bet-tracker/prop_edge.py"
```

**Fail-loud, never self-heal:** if a BettingPros call returns empty/`[]`, the data is unavailable — **do not edit or commit any SKILL file, do not swap in a scraper, do not fabricate a line.** Log zero picks and post `"BettingPros API unavailable — V1 sitting out"` to #bet-picks. (`/props` needs no key; `/events`/`/offers` use the public key the client resolves automatically.)

## Process

### 0. Performance Context — read before researching

Locate the repo root, then pull and read picks.json:
```bash
# Derive the repo root portably — works on macOS, Windows git-bash, and the
# remote routine's Linux clone. Do NOT hard-code machine paths here.
GAMBLING="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
PICKS="$GAMBLING/.agents/skills/bet-tracker/picks.json"
# Fail loud if cwd isn't the gambling repo — never operate on the wrong picks.json.
[ -f "$PICKS" ] || { echo "❌ not in the gambling repo (cwd=$PWD, GAMBLING=$GAMBLING)"; exit 1; }
git -C "$GAMBLING" pull
```

From the settled v1-trends picks, compute:
- **Today's pick count** — count all picks (v1-trends + v2-sharp) with today's date. If ≥ 5 total or ≥ 3 v1-trends picks, stop: "Daily cap reached."
- **Win rate by sport** — which sports are hitting vs. losing
- **Win rate by edge type** — which signal types (ATS trend, RLM, Steam, Injury, Prop gap, Situational) are profitable
- **Win rate by score tier** — are higher-scored picks actually outperforming lower ones?
- **Open picks today** — list any picks already logged for today (do not duplicate)

Use this to **calibrate confidence** during scoring:
- If a sport is below 45% win rate on 5+ settled picks → raise the score threshold to 7.0 for that sport
- If an edge type is below 40% win rate on 5+ settled picks → reduce its Confidence bonus by 1 point
- If no settled picks yet → proceed with default thresholds

Print a one-line context summary before researching, e.g.:
`📊 Context: MLB 5-2 (71%), ATS trend 4-3 (57%), props 3-1 (75%) — no threshold changes | 1 pick logged today`

### 1a. Prop Research — run FIRST (primary edge)

Fetch today's props and extract the signalled candidates in one pipe (the extractor keeps only props with a Cross-Book Prop Gap or standalone prop_trend, biggest gap first):

```bash
python3 "$BP" props MLB | python3 "$PE"
```

Each candidate carries `primary_edge_type` (`cross_book_gap` or `prop_trend`), `side`, `bet_line`, `bet_book` (the stale book to bet), `gap`, `ev`, `trend_confirmed`, and `player`. For NBA, swap `MLB`→`NBA`.

**Target prop types by sport** (use to prioritise among candidates):
- **MLB:** pitcher strikeouts (K's), batter hits, total bases, first 5 innings total
- **NBA:** points, assists, rebounds on non-star players

If 2+ qualifying prop candidates found → skip Step 1b game line research entirely (early exit).

### 1b. Game Line Research — only if props didn't yield 2+ candidates

Pull today's games and a cross-book odds snapshot:

```bash
python3 "$BP" events MLB "$(date +%F)"            # games + UTC scheduled + probable pitchers
python3 "$BP" offers <event_id> <market_id>       # cross-book lines + opening_line per selection
```

For each candidate game collect: matchup, sport, the BettingPros UTC `scheduled` time, best line + book, and the opening-vs-current movement across books. A reputable model/expert edge may be gathered via `WebSearch` as *supporting* evidence only — it is never a standalone scheduled-run Primary Edge (see Step 3).

**Data unavailable:** if both props and events come back empty, output the fail-loud message above and sit out. Never fabricate picks.

### 2. Line Shopping — best-effort, not a gate

The `/offers` snapshot already lists every book's current line. Recommend the best line you actually saw, with the book name (decoded via the client's `BOOKS` map). If only one book is surfaced, note "single-book verified — line shopping incomplete" as a risk; do NOT sit out solely for that.

### 3. Identify Value Signals

**Priority order (highest edge first):**
1. **Prop gap** (`cross_book_gap`) — ≥ 0.5 unit best-line-vs-consensus gap from the extractor; bet the stale book's line
2. **Season-trend prop edge** (`prop_trend`) — the extractor's standalone prop_trend (strong projection/rating), or pitcher avg ≥0.8 K from the K line in the favorable direction
3. **Total (over/under)** (`matchup_edge`) — structural inefficiency (injury, weather, pace mismatch)
4. **Reverse line movement** (`hard_rlm`) — **Manual-Run-only** (Public Ticket Data is unavailable to a Scheduled Run, CONTEXT.md). Do not log on a scheduled run.
5. **ATS trend** (`ats_trend`) — situational angle. **Supporting evidence only on a Scheduled Run** — never a standalone scheduled Primary Edge.
6. **Unpriced injury** (`matchup_edge`) — major injury, line hasn't adjusted
7. **Moneyline** (`plus_money_start`) — only with a market-confirmed edge; avoid juice worse than −130

**Scheduled-run gate (Market-Confirmed Primary Edge — ADR 0003):** on `--run-type scheduled`, every logged pick's Primary Edge must be market-confirmed (cross-book gap, prop_trend with current price, steam, or line value). An `ats_trend` or expert/model-consensus-only candidate with no current market confirmation is recorded as a **Rejected Candidate**, never logged as a pick.

### 4. Score

**Confidence base: 4.** Add bonuses:
- Prop gap confirmed (extractor `cross_book_gap`): +4
- Prop trend confirmed (extractor `prop_trend` / season trend ≥0.8 unit): +2
- Model/expert convergence (≥6% quant edge OR 2+ source agreement) **with market confirmation**: +3
- Total structural inefficiency: +2
- Strong ATS trend (5+ of last 7) — supporting only: +1
- Key injury advantage / unpriced usage boost: +2
- Favorable situational spot: +1
- Plus-money price (+100 or better) on a side a model likes: +1
- Conflicting signals: −2
- Single-book verified (no cross-book confirmation): −1

Cap at 10.

**Value (1–10):** based on edge — >8% EV: 10 · 5–8%: 8 · 3–5%: 6 · 1–3%: 4 · <1%: 2

**Overall = Confidence × 0.6 + Value × 0.4. Recommend only if ≥ 6.0.**

**Unit sizing:** Score ≥ 8.0 → 2u · Score 6.0–7.9 → 1u · Below 6.0 → no pick.
**Hard cap: 2u maximum per pick. No exceptions.**

### 4b. Output

Rank picks by score descending (highest confidence first) so top picks are easy to identify.

```
🎯 V1-Trends Picks — [Date]
X researched · Y props · Z game lines · [N] picks (ranked by score)
Daily cap: [X/5 used across V1+V2] · V1 cap: [Y/3 used]
```

Per pick:
- **Type**: Prop / Total / Spread / ML
- **Edge**: [primary reason]
- **Lines**: [book: line · …] → Best: [book]
- **Support**: [2-3 specific data points]
- **Risk**: [main counterargument]
- **Units**: 1u or 2u

If no picks: *"No qualifying picks today (threshold 6.0). Sitting out is the play."*

### 5. Auto-Log

Never append directly to `$PICKS`. All qualifying picks must be logged through the tracker CLI so duplicate checks, validation, rejected-candidate logging, and write-boundary guardrails apply.

Before reading, pull latest: `git -C "$GAMBLING" pull`
After logging, push only tracker-managed changes: `git -C "$GAMBLING" add .agents/skills/bet-tracker/picks.json .agents/skills/bet-tracker/rejected-candidates.json && git -C "$GAMBLING" commit -m "chore: log picks" && git -C "$GAMBLING" push origin main`

**game_time — from the BettingPros UTC `scheduled` field:**
- Use the event's `scheduled` value from `bettingpros.py events` (already UTC) for the *correct specific game* (cross-check the two teams and date).
- Convert UTC → **AZ (MST, UTC-7 year-round — Arizona does not observe DST)**: `AZ = UTC − 7h`. No month/DST table — the source timestamp is unambiguous UTC.
- If the event can't be matched with confidence, omit `--game-time` rather than guess.

**Signal → canonical `primary_edge_type`:** prop gap → `cross_book_gap` · prop trend/season trend → `prop_trend` · total inefficiency / unpriced injury → `matchup_edge` · ATS trend (manual only) → `ats_trend` · RLM (manual only) → `hard_rlm` · plus-money ML → `plus_money_start` · multi-source quant w/ market confirm → `quant_convergence`.

```bash
python3 ".agents/skills/bet-tracker/tracker.py" log \
  --model v1-trends \
  --sport "<sport>" \
  --bet "<full bet description incl opponent>" \
  --line "<odds @ best book>" \
  --units <1|2> \
  --score <score> \
  --edge "<human-readable primary edge>" \
  --primary-edge-type <canonical_edge_type> \
  --source-evidence-json '<json list of usable current source evidence>' \
  --line-num <spread_or_total_number_or_0> \
  --game-time "<H:MM AM/PM AZ>" \
  --run-type manual
```

Use `--run-type scheduled` for unattended/scheduled runs. Scheduled runs must include `--primary-edge-type` and `--source-evidence-json` and a **Market-Confirmed Primary Edge**; candidates missing either, or whose only edge is `ats_trend`/consensus, are recorded as rejected, not hand-written into `picks.json`.

Tell user: "Logged X picks. V1 total: Y/3. Daily total: Z/5."

## Slack Format

Post to the `#bet-picks` channel: use `slack_search_channels` to resolve the channel named exactly `bet-picks` to its ID, then `slack_send_message` to it. No markdown tables.

```
🎯 *V1-Trends | [Weekday Mon DD]*
_[X] picks · [Y]u at risk · [Z/5] daily cap used_

[sport emoji] *[BET TYPE] · [SPORT]*
*[Bet]*  ·  💰 [Line] @ [Best Book]
📦 [X]u · Score [X.X] (🟢 8+, 🟡 6.0-7.9)
• [edge]
• Lines: [book: line · …]
⚠️ _[risk]_

(repeat per pick, ranked by score)

[1 punchy sentence]
```

If no picks (or data unavailable):
```
🎯 *V1-Trends | [Weekday Mon DD]*
No qualifying picks today (threshold 6.0). Sitting out is the play.
[1 sentence — or "BettingPros API unavailable — V1 sitting out" if the feed was empty]
```
