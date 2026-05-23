---
name: sports-betting-sharp
description: "V2-SHARP: Find today's best bets using sharp money, steam moves, and reverse line movement only — no ATS trends or expert consensus. High-selectivity model. Compare performance against sports-betting (v1-trends)."
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

Markets are efficient. The primary goal is **beating the closing line (positive CLV)** — if your entry price is better than where the line closes, you made a +EV bet regardless of outcome. ROI follows CLV over time (2–5% CLV edge ≈ 15–25% annual ROI boost). Consistently beating Pinnacle's de-vigged close by 2%+ is the documented definition of a profitable edge.

**Edge priority (highest to lowest):**
1. **Props + cross-book gaps** — books price props loosely; 0.5+ unit gaps mean sharps hit one book first. Bet the stale price at the lagging book in the direction the sharp-hit book moved.
2. **RLM at 70%+ with Handle/Ticket divergence** — splits show # of bets, not dollar handle. A 20+ point gap between Handle % and Ticket % is a soft RLM signal (sharps behind one side regardless of line movement). Require confirmed line movement OR a second confirming factor to qualify.
3. **Steam at 3+ books simultaneously** — single-book moves are noise. **Never chase steam** — if the book already moved, your entry is the new market price, not the edge.
4. **Unpriced injury** — fast-closing window
5. **Underdog/under value** — public overweights favorites and overs; sharps consistently find value on dogs and unders

**Sport scope:**
- **MLB:** April – October
- **NBA:** October – June (playoffs through June)
- **NFL:** September – February
- **NHL:** Playoffs only (April – June) — totals and moneylines only, no props
- If today's date falls outside a sport's season, skip it entirely.

**Daily cap: 3 picks maximum for V2-Sharp.** Check Step 0. If already at 3 V2 picks, output "V2 cap reached — sitting out." Total combined cap across V1 + V2 is 5 picks per day.

Selective by design. 0–2 picks/day is normal. "No signals today" is a valid output.

**Long-run calibration targets:** 55%+ win rate on spread/total bets; 5–7% ROI over 500+ bets.

## Bet Types

Props are the **primary target** — biggest accessible edge. Totals second. Spreads/ML/1H only with confirmed RLM 70%+ or steam 3+ books.

## Process

### 0. Performance Context — read before researching

Detect machine, then pull and read picks.json:
```bash
if [ "$(uname)" = "Darwin" ]; then
  GAMBLING="/Users/tylermartinez/Projects/gambling"
else
  GAMBLING="C:/Users/metro/Claude/gambling"
fi
PICKS="$GAMBLING/.agents/skills/bet-tracker/picks.json"
git -C "$GAMBLING" pull
```

From the settled v2-sharp picks, compute:
- **Today's V2 pick count** — count v2-sharp picks with today's date. If ≥ 3, stop: "V2 cap reached."
- **Today's combined pick count** — count all picks (v1 + v2) with today's date. If ≥ 5, stop: "Daily cap reached."
- **Win rate by sport** — which sports are hitting vs. losing
- **Win rate by edge type** — which signal types are profitable
- **Win rate by score tier** — are 7+ picks outperforming 6-6.9?
- **Open picks today** — do not duplicate any already-logged pick

Use this to **calibrate thresholds**:
- If a sport is below 45% win rate on 5+ settled picks → raise score threshold to 7.0 for that sport
- If an edge type is below 40% win rate on 5+ settled picks → downgrade its signal score by 1 point
- If score 6.0–6.9 picks are losing overall → raise minimum threshold to 7.0
- If no settled picks yet → proceed with default thresholds

Read `.agents/skills/bet-tracker/betting-intel.md` for session observations and active patterns.

Print a one-line context summary before researching, e.g.:
`📊 Context: MLB 3-1 (75%), RLM 4-2 (67%), props 2-0 (100%) — no threshold changes | 1 pick logged today`

---

### 1. Prop Research — run FIRST (primary edge)

Fetch these URLs directly — do not WebSearch for prop data:

**Primary fetch (MLB + NBA):**
- `https://www.rotowire.com/betting/mlb/player-props-plus-proj.php` — shows DK/FD/BetMGM/Caesars lines side-by-side vs. RotoWire projections. Gaps visible at a glance.
- `https://www.rotowire.com/betting/nba/player-props-plus-proj.php` — same for NBA

**Secondary fetch (cross-book line shopping):**
- `https://www.oddstrader.com/mlb/player-props/` — free cross-book comparison grid
- `https://www.oddstrader.com/nba/player-props/`

**Tertiary fetch (public splits on props):**
- `https://playerprops.ai/trends` — ticket % and money % on props; confirms which direction the public is on

**Target prop types by sport:**
- **MLB:** pitcher strikeouts, batter hits, total bases, first 5 innings total
- **NBA:** points, assists, rebounds on non-star players
- **NFL:** passing yards, rushing yards, receiving yards, receptions

**Flag as Signal A if:**
- Gap ≥ 0.5 units across DK / FD / BetMGM, **AND you can identify the sharp side** (the book with lower limits / faster adjustment — typically BetMGM or Caesars — moved first; the bet goes at DK or FD at the stale price in the same direction)
- OR prop line moved 0.5+ since open with no news

**Prop Trend Confirmation (+0.5 bonus on Signal A score):**
When a cross-book gap is found, check RotoWire's season average for that player. If the season average is on the same side as the gap (e.g., pitcher averaging 7.2 Ks with line at 6.5 and gap pointing Over), add +0.5 to the Signal A score. This replaces the former standalone Signal H.

---

### 2. Game Line Research — always run, do not skip

Fetch both in one turn:

**Public splits (primary):**
- `https://cleatz.com/public-betting/mlb/` (also `/nba/`, `/nhl/`) — Handle % + Ticket % aggregated from multiple books, 15-min refresh. **This is the primary RLM confirmation source.**
- `https://dknetwork.draftkings.com/draftkings-sportsbook-betting-splits/` — DK's own Handle % + Ticket % (largest U.S. book by volume)

**Secondary split sources:**
- `https://www.wunderdog.com/mlb-baseball/public-consensus` — public consensus %
- `https://contests.covers.com/consensus/topconsensus/all/overall` — cross-sport public sentiment overview

**Line movement (confirmed working):**
- `https://www.vegasinsider.com/[sport]/odds/las-vegas/` — opening vs. current lines across 8+ books
- Compare opening line to current line per matchup. Line moving against the obvious public side = RLM proxy.

**RLM confirmation rule:**
- **Hard RLM:** 70%+ public on tickets, line moved opposite direction. Strongest version.
- **Soft RLM:** 20+ point gap between Handle % and Ticket % (e.g., 30% tickets / 60% handle on Team A) = sharp money behind Team A even without confirmed line movement. Requires one additional confirming factor (line movement, prop gap, or quant convergence) to qualify for a pick.
- Ticket count alone with no line movement = discard.

**No data fallback:** If CLEATZ and DK Network both fail AND searches return no split data, output: *"No sharp signals today — data sources unavailable."* Do not fabricate signals.

**Stale URLs (confirmed blocked — never fetch):**
- actionnetwork.com · sportsbettingdime.com · docsports.com · sportsinsights.com · betql.com · covers.com · vsin.com · sportsbookreview.com · oddsshark.com · winnersandwhiners.com · dknetwork.draftkings.com (API endpoint — use CLEATZ instead if this 403s)

---

### 3. CLV Check — mandatory for every qualifying pick

After identifying a signal that meets the threshold, verify CLV before logging:

1. Fetch Pinnacle's current line on the same bet via `https://www.oddstrader.com` (aggregates Pinnacle alongside DK/FD/BetMGM)
2. De-vig Pinnacle's line: strip the vig from both sides to get fair implied probability
3. Convert your entry odds to implied probability
4. If your implied probability is **lower** than Pinnacle's fair probability = positive CLV ✓
5. If your implied probability is **higher** = negative CLV, reconsider the pick

**CLV rules:**
- Entry beats Pinnacle fair line by ≥2%: full unit sizing per score
- Entry beats Pinnacle fair line by 1–2%: size down 0.5u from score recommendation
- Entry does not beat Pinnacle fair line: flag as "CLV marginal" and drop to 1u regardless of score
- Pinnacle line unavailable: note "CLV unverified" in the pick — do not block the pick

---

### 4. Line Shopping — best-effort, not a gate

Compare DK / FD / BetMGM lines when reachable:
> "DK: [line] · FD: [line] · MGM: [line] → Best: [book] at [line]"

If only one or two books are surfaced, use what you have and note "single-book verified — line shopping incomplete" as a risk. Do NOT discard a confirmed signal solely because cross-book verification failed. Missing line shopping is a known cost, not a disqualifier.

---

### 5. Signals (need at least one)

| Signal | Requirement |
|--------|-------------|
| **A. Prop gap/steam** | 0.5+ unit gap across DK/FD/MGM with identifiable sharp side, OR prop line moved 0.5+ since open with no news. Bet the stale price in the direction of the sharp-hit book. |
| **B. RLM (hard)** | 70%+ public on tickets, line moved opposite. Prefer 75%+ due to ticket/handle discrepancy. |
| **B-soft. RLM (soft)** | 20+ pt Handle/Ticket divergence without confirmed line movement. Requires one additional confirming factor. |
| **C. Steam (standard)** | ≥1pt spread or ≥15c ML move at **3+ books simultaneously**, no public catalyst. 1-2 books = noise, discard. |
| **C+. Steam (mega)** | Same as C but **4+ books simultaneously** — highest-confidence sharp signal. |
| **D. Unpriced injury** | Top-3 player out, line not adjusted; or teammate role increase boosting prop. |
| **E. Underdog/under value** | Public % heavily on favorite/over (65%+), line hasn't moved to reflect it, sharp indicators point the other way. |
| **F. Late move** | Significant line move in final 2–3 hours before game time (higher limits, fresher info — weight more than early steam). |
| **G. Quant convergence** | 2+ **methodologically independent** sources agree on the same side with ≥6% edge. Sources must use different methodologies (e.g., Dimers simulation model + RotoWire statistical projection + BettingPros top-leaderboard expert with audited positive track record). Two cappers using the same data = one signal, not two. |

**Discard if any of these are true:**
- A public injury report or lineup news explains the move
- Only one book moved (house positioning, not sharp action)
- Line already past value at time of entry (chasing steam)
- Scheduling factor or divisional familiarity explains the public side
- **Head fake pattern**: initial small-limit move one way, then reversal — discard immediately
- **NBA playoff spread**: money/ticket divergence alone does not qualify as RLM — big-dog handle on plus-money NBA playoff teams frequently reflects single-whale lottery action, not syndicate positioning. Require confirmed line movement (line moved against 70%+ public) before logging any NBA playoff spread pick.

---

### 6. Score

**Overall = Signal × 0.7 + Line Value × 0.3.** Recommend only if **≥ 6.0**.

**Signal Strength:**
- Cross-book prop gap 1.0+, or prop moved 1.0+: **9–10**
- Cross-book prop gap 0.5–0.9, or prop moved 0.5–0.9: **8–9** *(upgraded from 7–8)*
- Prop Trend Confirmation (season avg on same side as gap): **+0.5 bonus** (cap 10)
- RLM 75%+ confirmed with Handle/Ticket divergence 20+ pts: **8–9** · RLM 75%+ confirmed, no divergence data: **7–8** · RLM 70–74% confirmed: **7–8** · Below 70%: **0** · Ticket splits only, no line move and no divergence: **0**
- Soft RLM (divergence 20+ pts, no line move) + one confirming factor: **6–7**
- Steam mega (4+ books): **9–10** · Steam standard (3 books): **7–8** · 1–2 books: **0**
- Late move (final 2–3h, 3+ books): **+2 bonus** on top of steam/RLM score *(upgraded from +1)*
- Unpriced injury, line stale: **7–8**
- Underdog/under fade (public 65%+, sharp indicators opposite): **6–7**
- Quant convergence (G): 2 independent sources ≥6% edge: **7–8** · 3+ independent sources agree: **8–9**
- Single-book verified (line shopping incomplete): **−1 to final signal score**
- Head fake pattern detected: **discard, score 0**

**Line Value:**
- Best line, −100 to −110: **9** · −110 to −120: **7** · −120 to −140: **5** · Worse than −140: **2**
- Positive odds (+100 or better): **10** · (+101 to +150): **9** · (+151 to +250): **8** · Better than +250: **7**

**CLV adjustment (applied after score):**
- Beats Pinnacle fair line ≥2%: no change
- Beats Pinnacle fair line 1–2%: −0.5u from recommendation
- Does not beat Pinnacle fair line: cap at 1u regardless of score
- CLV unverified: no change, note in output

**Score ranges — always use the midpoint** (e.g. "9–10" → 9.5, "7–8" → 7.5).

**Unit sizing:** Score ≥ 8.0 → 2u · Score 6.0–7.9 → 1u.
**Hard cap: 2u maximum per pick. No exceptions.**

---

### 7. Output

```
🔪 V2-Sharp Picks — [Date]
Signals investigated: X · Confirmed: Y · Picks: Z
V2 cap: [X/3 used] · Daily cap: [X/5 used across V1+V2]
```

If picks: table with **# | Bet | Type | Line@Book | Sport | Signal | Score** (ranked by score descending), then per-pick:
- **Signal**: [specific details — include timing: early/late and book count]
- **Lines**: DK [X] · FD [X] · MGM [X] → Best: [book]
- **CLV target**: Entry [X%] vs Pinnacle fair [X%] = [+/− CLV]
- **Invalidation watch**: [what would kill this pick]
- **Units**: 1u or 2u

If no picks: *"No sharp signals confirmed today. Sitting out is the play."*

---

### 8. Auto-Log

Append each qualifying pick to `$PICKS` (set in Step 0 — create as `[]` if missing).

Before reading, pull latest: `git -C "$GAMBLING" pull`
After writing, push: `git -C "$GAMBLING" add .agents/skills/bet-tracker/picks.json && git -C "$GAMBLING" commit -m "chore: log picks" && git -C "$GAMBLING" push origin main`

**game_time rules — read carefully:**
- Source the start time from the game's own ESPN or MLB.com box score URL, not from a picks/odds page.
- Always verify the time is for the *correct specific game* being bet — cross-check the two teams and date.
- Convert to **AZ time (MST, UTC-7 year-round — Arizona does not observe DST)**:
  - EDT (summer, Mar–Nov): AZ = ET − 3 hours
  - EST (winter, Nov–Mar): AZ = ET − 2 hours
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

Tell user: "Logged X picks. V2 total: Y/3. Daily total: Z/5."

---

## Slack Format

Send to DM `U0ATA0A6NKB`. No markdown tables.

If picks:
```
🔪 *V2-Sharp | [Weekday Mon DD]*
_[X] investigated · [Y] picks · [Z/3] V2 cap · [W/5] daily cap_

[sport emoji] *[BET TYPE] · [SPORT]*
*[Bet]*  ·  💰 [Line] @ [Best Book]
📦 [X]u · Score [X.X] (🟢 7+, 🟡 6-6.9)
• [Signal — specific, timing, book count]
• Lines: DK [X] · FD [X] · MGM [X]
• CLV: Entry [X%] vs Pinnacle [X%] = [+/−]
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
