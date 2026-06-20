---
name: sports-betting-sharp
description: "V2-SHARP: Find today's best bets using sharp money, steam moves, and reverse line movement only — no ATS trends or expert consensus. High-selectivity model. Compare performance against sports-betting (v1-trends)."
argument-hint: [sport or "all"]
allowed-tools: WebSearch, WebFetch, Read, Write, Edit, Bash
---

# V2-Sharp — Today's Best Bets

## Data source — BettingPros API (datacenter-IP-tolerant)

All prop/odds/event research goes through the **BettingPros client** + **prop-edge extractor** (ADR 0006), never HTML scraping — scrapers 403 from the cloud routine's datacenter egress IP. Modules live in `.agents/skills/bet-tracker/`:

```bash
GAMBLING="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
BP="$GAMBLING/.agents/skills/bet-tracker/bettingpros.py"
PE="$GAMBLING/.agents/skills/bet-tracker/prop_edge.py"
```

**Fail-loud, never self-heal (replaces the old self-healing protocol):** with one authenticated API there is no stale URL to swap. If a BettingPros call returns empty/`[]`, the only causes are an outage or a rotated key — neither fixable by a SKILL edit. **Do not edit or commit any SKILL or source-list file. Do not fabricate a line.** Log zero picks and post `"BettingPros API unavailable — V2 sitting out"` to #bet-picks. (`/props` needs no key; `/events`/`/offers` use the public key the client resolves automatically.)

## Philosophy

Markets are efficient. The primary goal is **beating the closing line (positive CLV)** — if your entry price is better than where the line closes, you made a +EV bet regardless of outcome. ROI follows CLV over time.

**Edge priority (highest to lowest):**
1. **Props + cross-book gaps** — the extractor flags a Cross-Book Prop Gap (best line vs consensus ≥ 0.5 units); bet the stale book's price in the gap direction.
2. **Steam at 3+ books** — `/offers` carries each selection's `opening_line` plus every book's current line, so Steam = **3+ books currently moved off their opening line in the same direction** with no public catalyst. **Never chase steam** — if the book already moved, your entry is the new market price.
3. **Unpriced injury** — fast-closing window.
4. **Underdog/under value** — public overweights favorites and overs.

**Hard/Soft RLM are Manual-Run-only** (CONTEXT.md, ADR 0006): the BettingPros API exposes no public ticket/handle splits, and the sites that do 403 the datacenter IP. A Scheduled Run cannot source Public Ticket Data, so it cannot log an RLM pick — it uses Steam for the sharp game-line signal. A human on a residential IP may still research RLM on a Manual Run.

**Sport scope:**
- **MLB:** April – October
- **NBA:** October – June (playoffs through June)
- **NFL:** September – February
- **NHL:** Playoffs only (April – June) — totals and moneylines only, no props
- If today's date falls outside a sport's season, skip it entirely.

**Daily cap: 5 picks maximum across V1 and V2 combined, no more than 3 per model. No minimum.** Check Step 0. If already at 3 V2 picks: "V2 cap reached — sitting out." If at 5 total: "Daily cap reached — sitting out."

Selective by design. 0–2 picks/day is normal. "No signals today" is a valid output.

## Bet Types

Props are the **primary target**. Totals second. Spreads/ML/1H only with confirmed Steam (3+ books).

## Process

### 0. Performance Context — read before researching

```bash
GAMBLING="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
PICKS="$GAMBLING/.agents/skills/bet-tracker/picks.json"
[ -f "$PICKS" ] || { echo "❌ not in the gambling repo (cwd=$PWD, GAMBLING=$GAMBLING)"; exit 1; }
git -C "$GAMBLING" pull
```

From the settled v2-sharp picks, compute:
- **Today's V2 pick count** — if ≥ 3, stop: "V2 cap reached."
- **Today's combined pick count** — if ≥ 5, stop: "Daily cap reached."
- **Win rate by sport / edge type / score tier**; **open picks today** (do not duplicate).

Calibrate thresholds:
- Sport below 45% on 5+ settled → raise score threshold to 7.0 for that sport.
- Edge type below 40% on 5+ settled → downgrade its signal score by 1.
- Score 6.0–6.9 losing overall → raise minimum to 7.0.
- No settled picks → default thresholds.

Read **only the Active Intelligence section** at the top of `.agents/skills/bet-tracker/betting-intel.md` (stop before the Session Log archive — it's a long append-only history and reading it wastes tokens). Print a one-line context summary, e.g.:
`📊 Context: MLB 3-1 (75%), props 2-0 (100%) — no threshold changes | 1 pick logged today`

### 1. Prop Research — run FIRST (primary edge)

Fetch props and extract signalled candidates in one pipe (cross-book gaps + standalone prop_trend, biggest gap first):

```bash
python3 "$BP" props MLB | python3 "$PE"
```

Each candidate carries `primary_edge_type`, `side`, `bet_line`, `bet_book` (stale book), `gap`, `ev`, `trend_confirmed`, `player`. For NBA swap `MLB`→`NBA`.

**Flag as Signal A** when the extractor reports `cross_book_gap` (gap ≥ 0.5 with an identifiable stale book). **Prop Trend Confirmation (+0.5):** when `trend_confirmed` is true (the projection agrees with the gap side).

**Target prop types:** MLB pitcher strikeouts, batter hits, total bases, F5 total · NBA points/assists/rebounds on non-stars.

### 2. Game Line Research — always run, do not skip

Pull games and cross-book offers, and compute Steam from opening-vs-current:

```bash
python3 "$BP" events MLB "$(date +%F)"        # games + UTC scheduled + probable pitchers
python3 "$BP" offers <event_id> <market_id>   # per selection: opening_line + every book's current line
```

**Steam rule (Scheduled-Run sharp game-line signal):** for a selection, count books whose current line/odds have moved off `opening_line` in the same direction. **3+ books = Steam (Signal C); 4+ = mega steam.** 1–2 books = house noise, discard. No public catalyst (injury/lineup) may explain the move.

**RLM:** not available on a Scheduled Run (no Public Ticket Data). Do not log an RLM pick on a scheduled run; note "RLM unavailable — used Steam" if relevant.

### 3. CLV Check — mandatory for every qualifying pick

Pinnacle is available in the offers feed (`book_id` 2). For a qualifying signal:
1. Read Pinnacle's current line/odds for the same bet from `/offers`.
2. De-vig Pinnacle (strip vig from both sides → fair implied probability).
3. Convert your entry odds to implied probability.
4. Entry implied prob **lower** than Pinnacle fair = positive CLV ✓; higher = negative CLV, reconsider.

**CLV rules:** entry beats Pinnacle fair by ≥2% → full sizing · 1–2% → size down 0.5u · does not beat → cap 1u · Pinnacle absent for that market → note "CLV unverified", do not block.

### 4. Line Shopping — best-effort, not a gate

`/offers` lists every book's current line (names via the client's `BOOKS` map). Recommend the best line + book. If only one book surfaces, note "single-book verified — line shopping incomplete" as a risk; do not discard a confirmed signal for it.

### 5. Signals (need at least one)

| Signal | Requirement |
|--------|-------------|
| **A. Prop gap** | Extractor `cross_book_gap` (≥0.5 units, identifiable stale book). Bet the stale price in the gap direction. |
| **C. Steam (standard)** | 3+ books moved off `opening_line` same direction, no public catalyst. 1–2 books = discard. |
| **C+. Steam (mega)** | 4+ books — highest-confidence sharp signal. |
| **D. Unpriced injury** | Top-3 player out, line not adjusted; or teammate role increase boosting a prop. |
| **E. Underdog/under value** | Public-favored side, line hasn't moved, sharp indicators point the other way. |

**RLM (Hard/Soft)** remains a defined edge but is **Manual-Run-only** — never logged by a Scheduled Run.

**Discard if:** a public injury/lineup explains the move · only 1–2 books moved · line already past value (chasing) · a head-fake reversal · NBA playoff spread on divergence alone.

### 6. Score

**Overall = Signal × 0.7 + Line Value × 0.3.** Recommend only if **≥ 6.0**.

**Signal Strength:**
- Cross-book prop gap 1.0+: **9–10** · gap 0.5–0.9: **8–9**
- Prop Trend Confirmation (`trend_confirmed`): **+0.5** (cap 10)
- Steam mega (4+ books): **9–10** · Steam standard (3 books): **7–8** · 1–2 books: **0**
- Unpriced injury, line stale: **7–8**
- Underdog/under fade: **6–7**
- Single-book verified (line shopping incomplete): **−1 to signal score**

**Line Value:** Best line −100 to −110: **9** · −110 to −120: **7** · −120 to −140: **5** · worse than −140: **2** · +100 or better: **10** · +101 to +150: **9** · +151 to +250: **8**.

**CLV adjustment (after score):** beats Pinnacle fair ≥2% → no change · 1–2% → −0.5u · does not beat → cap 1u · unverified → note in output.

**Score ranges — use the midpoint** ("9–10" → 9.5). **Unit sizing:** ≥8.0 → 2u · 6.0–7.9 → 1u. **Hard cap 2u.**

### 7. Output

```
🔪 V2-Sharp Picks — [Date]
Signals investigated: X · Confirmed: Y · Picks: Z
V2 cap: [X/3 used] · Daily cap: [X/5 used across V1+V2]
```

If picks: ranked table **# | Bet | Type | Line@Book | Sport | Signal | Score**, then per pick:
- **Signal**: [details — gap size / steam book count + opening→current / timing]
- **Lines**: [book: line · …] → Best: [book]
- **CLV target**: Entry [X%] vs Pinnacle fair [X%] = [+/−]
- **Invalidation watch**: [what kills this pick]
- **Units**: 1u or 2u

If no picks: *"No sharp signals confirmed today. Sitting out is the play."* (or the BettingPros-unavailable notice if the feed was empty).

### 8. Auto-Log

Never append directly to `$PICKS` — log through the tracker CLI. Pull before logging; push only tracker-managed files:
`git -C "$GAMBLING" add .agents/skills/bet-tracker/picks.json .agents/skills/bet-tracker/rejected-candidates.json && git -C "$GAMBLING" commit -m "chore: log picks" && git -C "$GAMBLING" push origin main`

**game_time — from the BettingPros UTC `scheduled` field:**
- Use the event's `scheduled` value from `bettingpros.py events` (already UTC) for the *correct specific game* (cross-check teams + date).
- Convert UTC → **AZ (MST, UTC-7 year-round)**: `AZ = UTC − 7h`. No month/DST table — the source is unambiguous UTC.
- If the event can't be matched with confidence, omit `--game-time`.

**Signal → canonical `primary_edge_type`:** prop gap → `cross_book_gap` · prop trend → `prop_trend` · steam → `steam` · unpriced injury → `matchup_edge` · underdog/under fade → `underdog_fade`. (`hard_rlm`/`soft_rlm` are valid types but Manual-Run-only.)

```bash
python3 ".agents/skills/bet-tracker/tracker.py" log \
  --model v2-sharp \
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

Use `--run-type scheduled` for unattended runs. Scheduled runs must include `--primary-edge-type` and `--source-evidence-json`; candidates missing either are skipped or recorded as rejected, never hand-written into `picks.json`.

Tell user: "Logged X picks. V2 total: Y/3. Daily total: Z/5."

## Slack Format

Post to the `#bet-picks` channel: resolve the channel named exactly `bet-picks` via `slack_search_channels`, then `slack_send_message`. No markdown tables.

If picks:
```
🔪 *V2-Sharp | [Weekday Mon DD]*
_[X] investigated · [Y] picks · [Z/3] V2 cap · [W/5] daily cap_

[sport emoji] *[BET TYPE] · [SPORT]*
*[Bet]*  ·  💰 [Line] @ [Best Book]
📦 [X]u · Score [X.X] (🟢 7+, 🟡 6-6.9)
• [Signal — gap size / steam book count + opening→current]
• Lines: [book: line · …]
• CLV: Entry [X%] vs Pinnacle [X%] = [+/−]
⚠️ _[invalidation]_

(repeat per pick, ranked by score)

[1 punchy sentence]
```

If no picks:
```
🔪 *V2-Sharp | [Weekday Mon DD]*
No sharp signals today. Sitting out is the play.
[1 sentence on patience or fading the public — or "BettingPros API unavailable — V2 sitting out"]
```
