---
name: sports-betting
description: "V1-TRENDS: Find today's best sports bets using ATS trends, expert consensus, situational angles, and line movement. Use when looking for today's best bets (trends-based model). Compare performance against sports-betting-sharp."
argument-hint: [sport or "all"]
allowed-tools: WebSearch, WebFetch, Read, Write
---

# V1-Trends — Today's Best Bets

## Goal
Identify value bets from props, ATS trends, situational spots, line movement, and expert consensus. **Props and totals are the primary targets** — moneylines only with confirmed sharp signal.

**Sport scope: MLB, NBA, NFL only.** Research only active seasons — do not waste tokens on sports not currently in season:
- **MLB:** April – October
- **NBA:** October – June (playoffs through June)
- **NFL:** September – February (preseason Aug, regular season Sep–Jan, playoffs through Feb)
- If today's date falls outside a sport's season, skip it entirely.

**Daily cap: 4 picks maximum across V1 and V2 combined.** Check Step 0 for today's count before researching. If already at 4, output "Daily cap reached — sitting out."

## Process

### 0. Performance Context — read before researching

Detect machine, then pull and read picks.json:
```bash
# Detect OS
if [ "$(uname)" = "Darwin" ]; then
  GAMBLING="/Users/tylermartinez/Projects/gambling"
else
  GAMBLING="C:/Users/metro/Claude/gambling"
fi
PICKS="$GAMBLING/.agents/skills/bet-tracker/picks.json"
git -C "$GAMBLING" pull
```

From the settled v1-trends picks, compute:
- **Today's pick count** — count all picks (v1-trends + v2-sharp) with today's date. If ≥ 4, stop: "Daily cap reached."
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

### 1a. Prop Research — run FIRST (2 WebSearch calls, free)

Issue both searches in one turn:
```
WebSearch: "[sport] player prop line gaps DraftKings FanDuel BetMGM [date]"
WebSearch: "[sport] best player props today sharp value [date]"
```

**Target prop types by sport:**
- **MLB:** pitcher strikeouts (K's), batter hits, total bases, first 5 innings total
- **NBA:** points, assists, rebounds on non-star players (books use simpler models on these)
- **NFL:** passing yards, rushing yards, receiving yards, receptions

**Flag as a prop candidate if:**
- Line gap ≥ 0.5 units across DK / FD / BetMGM, OR
- Prop line moved 0.5+ since open with no news explanation

If 2+ prop candidates found → skip Step 1b game line research entirely (early exit, save tokens).

### 1b. Game Line Research — only if props didn't yield 2+ candidates

Token budget: ≤2 WebFetch calls (props already used 0 fetches).

Issue searches in one turn:
```
WebSearch: "[sport] best bets picks today [date]"
WebSearch: "[sport] odds line movement [date]"
WebSearch: "[sport] injury report starter out [date]"
```

**Primary fetch (if needed):**
- `https://www.covers.com/picks/best-bets-today`

**Conditional fetch (only if primary lacks data):**
- `https://www.oddsshark.com/picks/best-bets`

Stop fetching once you have 3–5 candidate games with lines + at least one signal each.

**Fetch failure:** Skip failed URLs and use next source. If all fail, output: *"No qualifying picks today — data sources unavailable."* Do not fabricate picks.

**Stale URLs (do not fetch):**
- ~~actionnetwork.com/todays-picks~~ — 404

For each candidate game collect: matchup, sport, time, ML/spread/total + juice, opening vs current line, public % if available.

### 2. Line Shopping — best-effort, not a gate

Compare lines across DK / FD / BetMGM when the data is reachable:
> "DK: [line] · FD: [line] · MGM: [line] → Best: [book] at [line]"

If only one or two books are surfaced (common — most articles cite a single book), use what you have and **note "single-book verified — line shopping incomplete" as a risk on the pick.** Do NOT sit out solely because cross-book verification failed. A 0.5-point difference is a ~5% edge boost when reachable; missing it is a known cost, not a disqualifier.

Always recommend the best line you actually saw, with the book name. If lines are identical across all three, note it.

### 3. Identify Value Signals

**Priority order (highest edge first):**
1. **Prop gap** — ≥ 0.5 unit difference across books, or line moved 0.5+ with no news
2. **Model/expert convergence** — reputable model publishes quantified edge ≥6% (Dimers, BettingPros, RotoWire, DK Network, FanDuel Research), OR 2+ independent sources land on the same pick. Plus-money + model edge is the strongest retail-data signal.
3. **Season-trend prop edge** — pitcher avg ≥0.8 K below the K line (or ≥0.8 above for Over), batter on 5+ game hit streak with matchup edge, role-player avg ≥1.0 unit from line in the favorable direction. Cleanest retail-reachable prop signal.
4. **Total (over/under)** — structural inefficiency (injury to key offensive/defensive player, weather, pace mismatch)
5. **Reverse line movement** — public on A, line moves toward B (confirm 70%+ public, actual move required)
6. **ATS trend** — 5+ of last 7 ATS, situational angle (rest, travel, revenge, division)
7. **Unpriced injury** — major injury, line hasn't adjusted (or teammate usage boost)
8. **Moneyline** — only with confirmed RLM or steam; avoid heavy juice (worse than −130)

Avoid: chasing public consensus, parlays, juice worse than −130 without Confidence ≥ 8.

### 4. Score

**Confidence base: 4.** Add bonuses:
- Prop gap confirmed across books: +4
- Model/expert convergence (≥6% quant edge OR 2+ source agreement): +3
- Sharp money / RLM confirmed (70%+, line moved): +3
- Season-trend prop edge (≥0.8 unit from line in favorable direction): +2
- Strong ATS trend (5+ of last 7): +2
- Key injury advantage / unpriced usage boost: +2
- Favorable situational spot: +1
- Plus-money price (+100 or better) on a side a model likes: +1
- Conflicting signals: −2
- Single-book verified (no cross-book confirmation): −1

Cap at 10.

**Value (1–10):** based on edge — >8% EV: 10 · 5–8%: 8 · 3–5%: 6 · 1–3%: 4 · <1%: 2

**Overall = Confidence × 0.6 + Value × 0.4.** Recommend only if **≥ 6.0**.

**Unit sizing:** Score ≥ 8.0 → 2u · Score 6.0–7.9 → 1u · Below 6.0 → no pick.
**Hard cap: 2u maximum per pick. No exceptions.**

### 4. Output

Rank picks by score descending (highest confidence first) so top picks are easy to identify.

```
🎯 V1-Trends Picks — [Date]
X researched · Y props · Z game lines · [N] picks (ranked by score)
Daily cap: [X/4 used across V1+V2]
```

Per pick:
- **Type**: Prop / Total / Spread / ML
- **Edge**: [primary reason]
- **Lines**: DK [X] · FD [X] · MGM [X] → Best: [book]
- **Support**: [2-3 specific data points]
- **Risk**: [main counterargument]
- **Units**: 1u or 2u

If no picks: *"No qualifying picks today (threshold 6.5). Sitting out is the play."*

### 5. Auto-Log

Append each qualifying pick to `$PICKS` (set in Step 0 — create as `[]` if missing).

Before reading, pull latest: `git -C "$GAMBLING" pull`
After writing, push: `git -C "$GAMBLING" add .agents/skills/bet-tracker/picks.json && git -C "$GAMBLING" commit -m "chore: log picks" && git -C "$GAMBLING" push origin main`

**game_time rules — read carefully:**
- Source the start time from the game's own ESPN or MLB.com box score URL, not from a picks/odds page (odds sites sometimes list wrong or approximate times).
- Always verify the time is for the *correct specific game* being bet — cross-check the two teams and date.
- Convert to **AZ time (MST, UTC-7 year-round — Arizona does not observe DST)**:
  - EDT (summer, Mar–Nov): AZ = ET − 3 hours (e.g. 7:05 PM ET → 4:05 PM AZ)
  - EST (winter, Nov–Mar): AZ = ET − 2 hours (e.g. 7:05 PM ET → 5:05 PM AZ)
- If uncertain after checking two sources, set `null` rather than guess.

```json
{
  "id": "[YYYYMMDD]-[sport]-[short-label]",
  "date": "[YYYY-MM-DD]",
  "game_time": "[H:MM AM/PM AZ or null if unknown]",
  "model": "v1-trends",
  "sport": "[sport]",
  "bet_type": "prop|total|spread|moneyline|1H",
  "bet": "[description]",
  "line": "[odds @ best book]",
  "units": [1-2],
  "score": [0-10],
  "primary_edge": "[Prop gap / ATS trend / RLM / Steam / Injury / Situational]",
  "result": null,
  "units_won_lost": null,
  "closing_line": null,
  "clv": null
}
```

Tell user: "Logged X picks. Daily total: Y/4."

## Slack Format

Send to DM `U0ATA0A6NKB`. No markdown tables.

```
🎯 *V1-Trends | [Weekday Mon DD]*
_[X] picks · [Y]u at risk · [Z/4] daily cap used_

[sport emoji] *[BET TYPE] · [SPORT]*
*[Bet]*  ·  💰 [Line] @ [Best Book]
📦 [X]u · Score [X.X] (🟢 8+, 🟡 6.5-7.9)
• [edge]
• Lines: DK [X] · FD [X] · MGM [X]
⚠️ _[risk]_

(repeat per pick, ranked by score)

[1 punchy sentence]
```
