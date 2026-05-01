---
name: sports-betting-sharp
description: "V2-SHARP: Find today's best sports bets using sharp money, steam moves, and reverse line movement only — no ATS trends or expert consensus. High-selectivity model. Compare performance against sports-betting (v1-trends)."
argument-hint: [sport or "all"]
allowed-tools: WebSearch, WebFetch
---

# Sports Betting Research — Today's Best Bets (V2: Sharp Money Model)

## Philosophy
Sports betting markets are efficient. Publicly available trends, expert consensus, and situational angles are already priced into lines. The only reliable edges are:
1. **Following sharp/professional money** — bettors who beat the market long-term
2. **Line shopping** — finding the best number across books
3. **Injury info not yet priced in** — a narrow, fast-closing window

This model is deliberately selective. Fewer picks, higher bar. If there are no strong sharp signals today, the output is: *"No strong value found today."* That is a valid and useful result.

## Inputs
- **Sport filter**: `$ARGUMENTS` — specific sport or blank for all
- **Today's date**: Always use today's date when searching

## Process

### 0. Read Betting Intelligence Log

Read the **Active Intelligence** section of `.claude/skills/bet-tracker/betting-intel.md` (skip the session log). Apply all listed signals, avoids, source notes, and calibration rules before evaluating any signals today.

### 1. Find Steam Moves & Sharp Action

These are the only signals worth searching for. Run in parallel:

```
WebSearch: "steam move today [date] sports betting"
WebSearch: "sharp money [sport] today [date] reverse line movement"
WebSearch: "line movement sharp action [date] NBA/MLB/NHL"
WebSearch: "consensus vs line movement sports [date]"
```

Also fetch these specific sources known for tracking sharp action:
- `https://www.actionnetwork.com/game-picks` (look for "Sharp" or "Steam" badges)
- `https://www.sportsbettingdime.com/sharp-money-report/`
- `https://www.docsports.com/free-sports-picks/steam-plays.html`

### 2. Identify Valid Sharp Signals

Only proceed with a bet if it shows **at least one** of these confirmed signals:

#### Signal A — Reverse Line Movement (RLM)
- Public betting % is **60%+ on one side**
- The line has moved **toward the other side** since open
- Example: 70% of bets on Lakers, but line moves from Lakers −4.5 → −3.5 (sharps on Celtics +3.5)

#### Signal B — Steam Move
- Line moves **≥1 point (spread) or ≥15 cents (ML)** within a short window
- Movement occurs at **multiple books simultaneously**
- No obvious public catalyst (no breaking injury news, no viral narrative)
- This indicates a sharp syndicate placed large coordinated bets

#### Signal C — Unpriced Injury
- A key starter (top-3 player on the team) is ruled out or downgraded
- Line has **not yet adjusted** by the expected amount
- Window closes fast — only flag if the line still has value at current number
- Search: `"[Player] injury [date]"` + check current line vs expected impact

**If none of these signals are confirmed: do not recommend a bet.** Output "No sharp signals found today" and stop.

### 3. Line Shop for Best Number

For every confirmed signal, find the best available line:

```
WebSearch: "[Team] spread odds comparison today"
WebSearch: "[matchup] best line DraftKings FanDuel BetMGM"
```

Record the line at each major book (DraftKings, FanDuel, BetMGM, Caesars, PointsBet). Even half-point differences matter significantly over time.

### 4. Verify — Eliminate False Positives

Before flagging a pick, check for explanations that invalidate the signal:

- Is the line movement explained by a **public injury report**? (Then it's not sharp action — it's the market adjusting)
- Is one book an **outlier** while others haven't moved? (Then it may be a single book balancing action, not a steam move)
- Has the line **already moved past value**? (If sharp action was early and the line has fully moved, the edge is gone)
- Is there a **scheduling or motivation factor** that explains public fade? (Then it may be public money, not sharps)

Discard any signal with a clean alternative explanation.

### 5. Score Each Pick

Scoring is intentionally strict. Most days should produce 0–2 picks.

#### Signal Strength (1–10)
| Confirmed Signal | Score |
|------------------|-------|
| Steam move confirmed at 3+ books | 9–10 |
| RLM with 70%+ public on wrong side | 8–9 |
| RLM with 60–70% public on wrong side | 6–7 |
| Unpriced injury, line clearly stale | 7–8 |
| Single signal, some ambiguity | 4–5 |
| No clean signal confirmed | 0 — do not recommend |

#### Line Value (1–10)
Compare current line to fair value estimate:
- Use implied probability from the odds
- For spreads: is this the best available number across books?
- For moneylines: is the juice reasonable (avoid anything worse than −130)?

| Juice/Value | Score |
|-------------|-------|
| Best line in market, −100 to −110 | 9–10 |
| Near-best line, −110 to −120 | 7–8 |
| Acceptable, −120 to −130 | 5–6 |
| Worse than −130 | 2–3 — reconsider |

**Overall Score = (Signal Strength × 0.7) + (Line Value × 0.3)**

Only recommend bets with Overall Score ≥ 6.0.

### 6. Present Results

---

## Today's Sharp Picks — [Date]

**Model**: V2-Sharp · **Signal threshold**: RLM / Steam / Unpriced injury only
**Games scanned**: X · **Sharp signals found**: Y · **Picks**: Z

---

> If no picks: **"No sharp signals confirmed today. Sitting out is a valid play."**

---

### Sharp Plays

| # | Bet | Line | Best Book | Sport | Signal | Strength | Line Value | Score |
|---|-----|------|-----------|-------|--------|----------|------------|-------|
*(populate with today's confirmed sharp picks)*

---

### Pick Breakdowns

For each pick:

**[#]. [Bet]** · [Line @ Book] · [Sport]
- **Signal**: [RLM / Steam / Unpriced injury — specific details]
- **Public split**: [X% of bets on opponent] → line moved [direction]
- **Line movement**: Opened [X], now [Y] at [time]
- **Best line available**: [Book @ line] vs [Book @ line]
- **What would invalidate this**: [Specific thing to watch before tip]
- **Unit size**: 1u / 2u (max 2u for this model — high selectivity means size up on confirmed signals)

---

### Signals Investigated But Discarded
- **[Matchup]**: [Why it was discarded — e.g., "RLM explained by Embiid injury report, not sharp action"]

---

### 📝 Log Your Picks
After presenting picks, ask: **"Which of these are you betting? I'll log them to the tracker."**

For each confirmed bet, run:
```bash
python ".claude/skills/bet-tracker/tracker.py" log \
  --model v2-sharp \
  --sport "[sport]" \
  --bet "[Full bet description including opponent — e.g. 'D-Backs -1.5 RL vs TOR']" \
  --line [odds] \
  --units [1 or 2] \
  --score [overall_score] \
  --edge "[RLM / Steam / Unpriced injury — one line with specifics]" \
  --line-num [spread or RL number, 0 for ML, total number for over/under]
```

Confirm the logged pick ID to the user.

---

### 📓 Update Betting Intelligence Log

After logging picks, append a new entry to `.claude/skills/bet-tracker/betting-intel.md` under **Session Log**. Use this format:

```
### [YYYY-MM-DD] — V2-Sharp Session

**Games scanned**: X · **Sharp signals found**: Y · **Picks**: Z

**Signal observations**:
- [Signal type] on [matchup] — [what made it clean or ambiguous]
- [Any false positives investigated and discarded — name the reason]

**Calibration notes** (if any picks were close calls):
- [Bet] at score [X] — [what nearly crossed/missed the threshold and why]

**Patterns reinforced or challenged**:
- [Match with existing log patterns, or new pattern emerging]
```

If no picks were made: `[Date] — V2-Sharp: No sharp signals confirmed. [X] signals investigated, discarded because [brief reason].`

After results come in (via `/bet-tracker`), revisit calibration notes and add outcome context if the result was surprising.

---

## Slack Message Format

**Delivery method**: Use the `mcp__Slack__slack_send_message` MCP tool with `channel_id: "U0ATA0A6NKB"`. Do NOT use curl + webhook — the sandbox egress proxy blocks `hooks.slack.com` (returns 403 `host_not_allowed`).

When sending results via Slack DM to `U0ATA0A6NKB`, use this phone-friendly format. NO markdown tables.

If picks found:
Line 1: 🔪 *V2-Sharp Picks | [Weekday Mon DD]*
Line 2 (italic): [X] signals investigated · [Y] confirmed · [Z] picks

Then a divider line, then for each pick:
[sport emoji] *PICK N — [SPORT]*
*[Bet description]*
💰 [Line] @ [Book]
📦 [X] unit(s) · Score [X.X] 🟢  (🟢 if 7+, 🟡 if 5-6.9)
• Signal: [RLM/Steam/Unpriced injury — specific details]
• Public split: [X]% on opponent, line moved [direction]
• Best line: [Book @ line]
⚠️ _[what would invalidate this pick]_

Divider line, then:
🔍 *Investigated but discarded:* [matchup] — [reason]

Finish with 1-2 punchy entertaining sentences about the sharp action — like a sharp friend texting you.

If no picks found:
🔪 *V2-Sharp | [Weekday Mon DD]*
No sharp signals confirmed today. Sitting out is the play.
[1-2 fun sentences about patience being profitable, or roasting the public.]

## Self-Healing
If sharp-tracking sources change URLs or go behind paywalls, update this SKILL.md with working alternatives. Key sites to keep current: ActionNetwork, SportsBettingDime, DocSports steam reports.
