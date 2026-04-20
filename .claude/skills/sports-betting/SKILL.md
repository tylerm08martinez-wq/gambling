---
name: sports-betting
description: "V1-TRENDS: Find today's best sports bets using ATS trends, expert consensus, situational angles, and line movement. Use when looking for today's best bets (trends-based model). Compare performance against sports-betting-sharp."
argument-hint: [sport or "all"]
allowed-tools: WebSearch, WebFetch
---

# Sports Betting Research — Today's Best Bets (V1: Trends Model)

## Goal
Research today's games across all major sports, identify value bets where the odds offer positive expected value, and deliver a ranked list of picks with reasoning.

## Inputs
- **Sport filter**: `$ARGUMENTS` — specific sport (NBA, NFL, MLB, NHL, NCAAB, NCAAF, soccer) or "all" / blank for everything
- **Today's date**: Always use today's date when searching for games and odds

## Process

### 0. Read Betting Intelligence Log

Before researching any games, read `.claude/skills/bet-tracker/betting-intel.md`.

Extract and apply:
- **Active Patterns**: Treat these as confirmed priors — if a pattern applies to a game today, adjust that game's confidence score up or down accordingly and note it in the pick breakdown.
- **Patterns to Avoid**: If today's pick matches a logged failure pattern, flag it explicitly and reduce the score by 1–2 points.
- **Edge Type Patterns**: If certain signal types have been underperforming, downweight them in scoring.
- **Sport-Specific Observations**: Apply any relevant sport/league notes to today's candidates.
- **Score Calibration Notes**: If past scores have been inflated/deflated for certain edge types, recalibrate.

If the log is empty or has no relevant entries, proceed normally.

### 1. Find Today's Games & Odds

Search for today's lines across major sports. Use multiple searches in parallel:

```
WebSearch: "NBA odds today [date] best bets picks"
WebSearch: "MLB odds today [date] best bets"
WebSearch: "NHL odds today [date] picks"
WebSearch: "NFL odds today [date]" (if applicable)
WebSearch: "soccer odds today [date] best bets"
```

Also fetch odds aggregators for raw lines:
- `https://www.actionnetwork.com/todays-picks`
- `https://www.covers.com/picks/best-bets-today`
- `https://www.oddsshark.com/picks/best-bets`

For each game found, collect:
- **Teams / matchup**
- **Sport and league**
- **Game time**
- **Moneyline** (both sides)
- **Spread** (ATS line + juice)
- **Over/Under** (total + juice)
- **Opening line vs current line** (line movement)
- **Public betting %** (if available)
- **Sharp/professional money side** (if available)

### 2. Research Contextual Factors

For each promising game, search for relevant factors:

```
WebSearch: "[Team] injury report today"
WebSearch: "[Team] recent form last 5 games"
WebSearch: "[Team] vs [Team] head to head"
WebSearch: "[matchup] expert picks consensus today"
```

Key factors to evaluate:
- **Injuries**: Missing starters, key players listed as out/doubtful
- **Rest/fatigue**: Back-to-back games, travel schedule
- **Recent form**: Last 5–10 games ATS, home vs away splits
- **Head-to-head**: Historical matchup results and ATS record
- **Weather**: Outdoor sports — wind speed, rain, temperature
- **Motivation**: Playoff implications, rivalry games, revenge spots
- **Line movement**: Which direction the line moved and why (sharp vs public)

### 3. Identify Value Bets

A value bet exists when the implied probability from the odds is **lower** than your estimated true probability. Prioritize:

#### 🎯 Strong Value Indicators
- **Reverse line movement**: Public money is on Team A but line moves toward Team B (sharps on B)
- **Steam moves**: Line moves significantly at multiple books simultaneously (sharp syndicate action)
- **Line move against public**: 60%+ public bets on one side, but line moves the other way
- **Key number crosses**: Line moves through 3, 7, 10 in football — critical hook numbers
- **Injury impact not yet priced in**: Major injury reported but line hasn't adjusted

#### ⚠️ Avoid
- Chasing public consensus without line value
- Betting heavily juiced lines (−130 or worse) without strong conviction
- Same-game parlays (high vig, correlated legs)
- Betting > 3 units on any single game

### 4. Score Each Pick

Rate every candidate bet on two dimensions:

#### Confidence Score (1–10)
| Signal | Points |
|--------|--------|
| Sharp money indicator confirmed | +3 |
| Reverse line movement present | +2 |
| Strong ATS trend (5+ of last 7) | +2 |
| Key injury advantage | +2 |
| Favorable weather/situational spot | +1 |
| Expert consensus 60%+ aligned | +1 |
| Conflicting signals or unclear edge | −2 |
| Line already moved significantly | −1 |

#### Value Score (1–10) — based on implied vs estimated probability
| Edge | Score |
|------|-------|
| >8% positive EV estimated | 10 |
| 5–8% positive EV | 8 |
| 3–5% positive EV | 6 |
| 1–3% positive EV | 4 |
| Near breakeven (<1%) | 2 |

**Overall Score = (Confidence × 0.6) + (Value × 0.4)**

### 5. Present Results

Sort picks by Overall Score, highest first. Only include bets with Overall Score ≥ 5.0.

---

## Today's Best Bets — [Date]

**Market snapshot**: X games researched across Y sports · Z picks meet value threshold

---

### 🏆 Top Picks

| # | Bet | Line | Book | Sport | Conf | Value | Score | Rec |
|---|-----|------|------|-------|------|-------|-------|-----|
| 1 | Team A −3.5 | −110 | DraftKings | NBA | 🟢 8/10 | 🟢 8/10 | 8.0 | ✅ **Strong** |
| 2 | Over 214.5 | −108 | FanDuel | NBA | 🟢 7/10 | 🟡 6/10 | 6.6 | ✅ **Play** |
| 3 | Team B ML | +145 | BetMGM | MLB | 🟡 6/10 | 🟡 6/10 | 6.0 | ⚠️ **Lean** |

**Color key:** 🟢 7–10 · 🟡 4–6 · 🔴 0–3

---

### 📋 Pick Breakdowns

For each top pick, provide:

**[#]. [Bet Description]** · [Line] · [Sport/League]
- **Edge**: [Primary reason this is a value bet — sharp action, injury, trend, etc.]
- **Supporting factors**: [2–3 bullet points with specific data]
- **Risk**: [Main counterargument or risk factor]
- **Line movement**: [Opened at X, now at Y — moved toward/away from public]
- **Suggested book**: [Where best line is available]
- **Unit size**: 1u / 2u / 3u based on confidence

---

### 📊 Summary Stats
- **Total picks**: X
- **Strong plays (Score 8+)**: X
- **Value plays (Score 6–7.9)**: X
- **Leans (Score 5–5.9)**: X
- **Sports covered**: [list]

### ❌ Games Researched But Skipped
- **[Matchup]**: [1-line reason — e.g., "No edge, public side, line moved too far"]

### 💡 Bankroll Notes
- **1 unit** = your standard flat bet size (e.g., 1–2% of bankroll)
- Never bet more than 3 units on a single game
- Avoid parlays unless specifically noted as correlated value

### 📝 Log Your Picks
After presenting picks, ask the user: **"Which of these are you betting? I'll log them to the tracker."**

For each confirmed bet, run:
```bash
python ".claude/skills/bet-tracker/tracker.py" log \
  --model v1-trends \
  --sport "[sport]" \
  --bet "[Full bet description including opponent — e.g. 'Braves ML vs PHI']" \
  --line [odds] \
  --units [1/2/3] \
  --score [overall_score] \
  --edge "[primary edge — e.g. ATS trend, RLM, injury]" \
  --line-num [spread or RL number, 0 for ML, total number for over/under]
```

Confirm the logged pick ID to the user.

---

### 📓 Update Betting Intelligence Log

After logging picks, append a new entry to `.claude/skills/bet-tracker/betting-intel.md` under **Session Log**. Use this format:

```
### [YYYY-MM-DD] — V1-Trends Session

**Games researched**: X across [sports]
**Picks made**: X (Score X.X avg)

**Signal observations**:
- [Edge type] was [strong/weak/absent] today — [brief reason]
- [Any market behavior worth noting — e.g. "public hammering favorites across NBA, lines holding firm"]

**Calibration notes** (if any picks were close calls or borderline):
- [Bet] at score [X] — [what tipped it in/out, what to watch for in results]

**Patterns reinforced or challenged**:
- [Any match with existing patterns, or new pattern emerging]
```

Only add entries that contain real observations. If nothing notable happened (e.g. no games found, or routine picks with no signal nuance), write a one-liner: `[Date] — V1-Trends: X picks logged, no notable observations.`

After results come in (via `/bet-tracker`), revisit calibration notes and add outcome context if the result was surprising.

---

## Self-Healing
If any URLs return 404s or paywalls, update this SKILL.md with working alternatives. Preferred free sources: ActionNetwork free tier, Covers.com, ESPN BET, OddsShark, The Lines.
