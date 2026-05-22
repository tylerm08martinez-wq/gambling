---
name: sports-betting-sharp
description: "V2-SHARP: Find today's best sports bets using sharp money, steam moves, and reverse line movement only — no ATS trends or expert consensus. High-selectivity model. Compare performance against sports-betting (v1-trends)."
argument-hint: [sport or "all"]
allowed-tools: WebSearch, WebFetch, Read, Write, Edit, Bash
---

# V2-Sharp — Today's Best Bets

## Self-Healing (mandatory — run every session)

When any data source fails (403, 404, timeout, redirect loop):

1. **Immediately move it to the stale list** in this SKILL.md — add it to the "never fetch" line in Step 2. Do this before continuing research, not after.
2. **Find a working replacement** — try the next source in the list, or run `WebSearch: "MLB betting splits public money percentage today"` and identify a site that's actively publishing split data. Fetch it to confirm it loads.
3. **Add the working replacement** to the primary sources list in Step 2, above the stale list.
4. **Continue research** with whatever working sources remain — never sit out solely because one source failed.

**High-value pick standard is non-negotiable.** Self-healing means adapting data sources, not lowering the signal bar. If all sources genuinely fail and no signal can be confirmed, sitting out is still correct — but that should be rare after patching.

## Philosophy
Markets are efficient. The primary goal is **beating the closing line (positive CLV)** — if your entry price is better than where the line closes, you made a +EV bet regardless of outcome. ROI follows CLV over time (2–5% CLV edge ≈ 15–25% annual ROI boost).

**Edge priority (highest to lowest):**
1. **Props + cross-book gaps** — books price props loosely; 0.5+ unit gaps mean sharps hit one book first
2. **RLM at 70%+** — splits show # of bets, not dollar handle. Require line movement confirmation; never rely on splits alone.
3. **Steam at 3+ books simultaneously** — single-book moves are noise. **Never chase steam** — if the book already moved, your entry is the new market price, not the edge.
4. **Unpriced injury** — fast-closing window
5. **Underdog/under value** — public overweights favorites and overs; sharps consistently find value on dogs and unders

**Sport scope: MLB, NBA, NFL only.** Research only active seasons — do not waste tokens on sports not currently in season:
- **MLB:** April – October
- **NBA:** October – June (playoffs through June)
- **NFL:** September – February (preseason Aug, regular season Sep–Jan, playoffs through Feb)
- If today's date falls outside a sport's season, skip it entirely.

**Daily cap: 4 picks maximum across V1 and V2 combined.** Check Step 0. If already at 4, output "Daily cap reached — sitting out."

Selective by design. 0–2 picks/day is normal. "No signals today" is a valid output.

**Long-run calibration targets:** 55%+ win rate on spread/total bets; 5–7% ROI over 500+ bets.

## Bet Types
Props are the **primary target** — biggest accessible edge. Totals second. Spreads/ML/1H only with confirmed RLM 70%+ or steam 3+ books.

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

From the settled v2-sharp picks, compute:
- **Today's pick count** — count all picks (v1-trends + v2-sharp) with today's date. If ≥ 4, stop: "Daily cap reached."
- **Win rate by sport** — which sports are hitting vs. losing
- **Win rate by edge type** — which signal types (RLM, Steam, Prop gap, Injury, etc.) are profitable
- **Win rate by score tier** — are 7+ picks outperforming 6-6.9?
- **Open picks today** — do not duplicate any already-logged pick

Use this to **calibrate thresholds**:
- If a sport is below 45% win rate on 5+ settled picks → raise score threshold to 7.0 for that sport
- If an edge type is below 40% win rate on 5+ settled picks → downgrade its signal score by 1 point
- If score 6.0–6.9 picks are losing overall → raise minimum threshold to 7.0
- If no settled picks yet → proceed with default thresholds

Print a one-line context summary before researching, e.g.:
`📊 Context: MLB 3-1 (75%), RLM 4-2 (67%), props 2-0 (100%) — no threshold changes | 1 pick logged today`

### 1. Prop Research — run FIRST (2 WebSearch calls, counts toward token budget)

Issue both searches in one turn:
```
WebSearch: "[sport] player prop steam line movement sharp [date]"
WebSearch: "[sport] player prop DraftKings FanDuel BetMGM line gap [date]"
```

**Target prop types by sport:**
- **MLB:** pitcher strikeouts, batter hits, total bases, first 5 innings total
- **NBA:** points, assists, rebounds on non-star players
- **NFL:** passing yards, rushing yards, receiving yards, receptions

**Flag as Signal A if:**
- Gap ≥ 0.5 units across DK / FD / BetMGM, OR
- Prop line moved 0.5+ since open with no news

**Early exit:** If 2+ prop signals found → skip game line research entirely. Props are the highest edge — don't waste tokens on game lines when you already have confirmed signals.

### 2. Game Line Research — only if props yielded < 2 signals

Issue both searches in one turn:
```
WebSearch: "[sport] sharp money reverse line movement [date]"
WebSearch: "[sport] betting splits public money percentage [date]"
```

**Line movement fetch (confirmed working):**
- `https://www.vegasinsider.com/[sport]/odds/las-vegas/` — shows opening vs. current lines across 8+ books
- Compare opening line to current line per matchup. A line moving against the obvious public side = RLM proxy. Use this to confirm or deny any movement reported in WebSearch results.

**Split data — WebSearch only (direct-fetch sites are blocked):**
Split sites (SBR, OddsShark, ActionNetwork, Covers, VSIN, BetQL, etc.) all return 403/404. Do NOT attempt to fetch them. Instead:
- Use WebSearch results: sports media, Reddit r/sportsbook, sharp cappers on X, and podcast recaps often publish split % in plain text
- Search: `"[team] [date] betting percentage public money"` — look for quoted numbers like "73% of bets on..."
- If no splits found in search results, infer direction from line movement alone: heavy public team (clear headliner favorite) + line moved against them = credible RLM

**Early exit:** Stop as soon as 2+ qualifying signals are found.

**No data fallback:** If VegasInsider fetch fails AND searches return no split data, output: *"No sharp signals today — data sources unavailable."* Do not fabricate signals.

**Stale URLs (confirmed blocked — never fetch):**
- actionnetwork.com · sportsbettingdime.com · docsports.com · sportsinsights.com · dknetwork.draftkings.com · betql.com · covers.com · vsin.com · sportsbookreview.com · oddsshark.com · winnersandwhiners.com

### 3. Line Shopping — best-effort, not a gate

Compare DK / FD / BetMGM lines when reachable:
> "DK: [line] · FD: [line] · MGM: [line] → Best: [book] at [line]"

If only one or two books are surfaced (common with public sources), use what you have and **note "single-book verified — line shopping incomplete" as a risk on the pick.** Do NOT discard a confirmed signal solely because cross-book verification failed. A 0.5-point gap is a ~5% edge boost when reachable; missing it is a known cost.

### 4. Signals (need at least one)

| Signal | Requirement |
|--------|-------------|
| **A. Prop gap/steam** | 0.5+ unit gap across DK/FD/MGM, OR prop line moved 0.5+ since open with no news |
| **B. RLM** | 70%+ public on # of bets, line moved opposite. Must confirm with actual line movement — splits alone not sufficient. Prefer 75%+ due to bet-count vs. handle discrepancy |
| **C. Steam (standard)** | ≥1pt spread or ≥15c ML move at **3+ books simultaneously**, no public catalyst. 1-2 books = noise, discard |
| **C+. Steam (mega)** | Same as C but **4+ books simultaneously** — highest-confidence sharp signal |
| **D. Unpriced injury** | Top-3 player out, line not adjusted; or teammate role increase boosting prop |
| **E. Underdog/under value** | Public % heavily on favorite/over (65%+), line hasn't moved to reflect it, and sharp indicators point the other way |
| **F. Late move** | Significant line move in final 2–3 hours before game time (higher limits, fresher info — weight more than early steam) |
| **G. Quant convergence** | Reputable model publishes quantified edge ≥6% (Dimers, BettingPros, RotoWire, DK Network, FanDuel Research), OR 2+ independent sources land on the same pick. Plus-money entry strengthens further. Retail proxy for "someone smart already hit this." |
| **H. Season-trend prop edge** | Pitcher avg ≥0.8 K from line in favorable direction over 5+ starts, batter ≥1.0 unit from line over 10+ games, role-player ≥1.0 unit from line over 8+ games. Trend must align with the bet side. |

**Discard if any of these are true:**
- A public injury report or lineup news explains the move
- Only one book moved (house positioning, not sharp action)
- Line already past value at time of entry (chasing steam)
- Scheduling factor or divisional familiarity explains the public side
- **Head fake pattern**: initial small-limit move one way, then reversal — discard immediately

### 5. Score

**Overall = Signal × 0.7 + Line Value × 0.3.** Recommend only if **≥ 6.0**.

**Signal Strength:**
- Cross-book prop gap 1.0+, or prop moved 1.0+: **9–10**
- Cross-book prop gap 0.5–0.9, or prop moved 0.5–0.9: **7–8**
- RLM 75%+ (confirmed with line move): **8–9** · RLM 70–74%: **7–8** · Below 70%: **0** · Splits only, no line move: **0**
- Steam mega (4+ books): **9–10** · Steam standard (3 books): **7–8** · 1–2 books: **0**
- Late move (final 2–3h, 3+ books): **+1 bonus** on top of steam/RLM score
- Unpriced injury, line stale: **7–8**
- Underdog/under fade (public 65%+, sharp indicators opposite): **6–7**
- Quant convergence (G): single source ≥6% edge: **6–7** · 2+ sources agree: **7–8** · 3+ sources agree: **8–9**
- Season-trend prop edge (H): ≥0.8 unit from line: **6–7** · ≥1.5 unit from line: **7–8**
- **Stacking bonus**: if G and H both fire on the same pick, add +1 to the higher score (cap 9)
- Single-book verified (line shopping incomplete): **−1 to final signal score**
- Head fake pattern detected: **discard, score 0**

**Line Value:**
- Best line, −100 to −110: **9** · −110 to −120: **7** · −120 to −140: **5** · Worse than −140: **2**
- Positive odds (+100 or better): **10** · (+101 to +150): **9** · (+151 to +250): **8** · Better than +250: **7**

**Score ranges — always use the midpoint** (e.g. "9–10" → 9.5, "7–8" → 7.5).

**Unit sizing:** Score ≥ 8.0 → 2u · Score 6.0–7.9 → 1u.
**Hard cap: 2u maximum per pick. No exceptions.**

### 6. Output

```
🔪 V2-Sharp Picks — [Date]
Signals investigated: X · Confirmed: Y · Picks: Z
Daily cap: [X/4 used across V1+V2]
```

If picks: table with **# | Bet | Type | Line@Book | Sport | Signal | Score** (ranked by score descending), then per-pick:
- **Signal**: [specific details — include timing: early/late and book count]
- **Lines**: DK [X] · FD [X] · MGM [X] → Best: [book]
- **CLV target**: beating [closing line estimate] = +EV confirmation
- **Invalidation watch**: [what would kill this pick]
- **Units**: 1u or 2u

If no picks: *"No sharp signals confirmed today. Sitting out is the play."*

### 7. Auto-Log

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
  "model": "v2-sharp",
  "sport": "[sport]",
  "bet_type": "prop|total|spread|moneyline|1H",
  "bet": "[description]",
  "line": "[odds @ best book]",
  "units": 1,
  "score": [0-10],
  "primary_edge": "[Prop gap / Prop steam / RLM / Steam / Injury / Underdog fade]",
  "result": null,
  "units_won_lost": null,
  "closing_line": null,
  "clv": null
}
```

Tell user: "Logged X picks. Daily total: Y/4."

## Slack Format

Send to DM `U0ATA0A6NKB`. No markdown tables.

If picks:
```
🔪 *V2-Sharp | [Weekday Mon DD]*
_[X] investigated · [Y] picks · [Z/4] daily cap used_

[sport emoji] *[BET TYPE] · [SPORT]*
*[Bet]*  ·  💰 [Line] @ [Best Book]
📦 [X]u · Score [X.X] (🟢 7+, 🟡 6-6.9)
• [Signal — specific, timing, book count]
• Lines: DK [X] · FD [X] · MGM [X]
⚠️ _[invalidation]_

(repeat per pick, ranked by score)

[1 punchy sentence]
```

If no picks:
```
🔪 *V2-Sharp | [Weekday Mon DD]*
No sharp signals today. Sitting out is the play.
[1 sentence on patience or fading the public]
```
