---
name: bet-tracker
description: Track and compare sports betting pick performance between V1-Trends and V2-Sharp models. Log results, view stats, and see which model is winning long-term. Use when logging a bet result, checking ROI, or comparing model performance.
argument-hint: [log | result | stats]
allowed-tools: Read, Write, WebSearch, Bash
---

# Bet Tracker

All data logic (stats, math, formatting) is handled by `tracker.py`. This skill orchestrates:
1. Auto-resolving open picks via web search
2. Calling `tracker.py` for all data operations
3. Writing the Daily Recap and intel log (the creative/analytical parts Claude does better)

**Script location:** `.claude/skills/bet-tracker/tracker.py`
**Data files:** `picks.json`, `betting-intel.md` — both in the same directory.

---

## Action: `log`

Ask the user for:
1. Model (`v1-trends` or `v2-sharp`)
2. Sport
3. Bet description — always include the opponent (e.g. "D-Backs -1.5 RL vs TOR", "Braves ML vs PHI", "Curry 4+ 3PM vs LAL", "Under 5.5 — Stars vs Wild")
4. Odds/line (e.g. -110, +146)
5. Units (1, 2, or 3)
6. Pick score from skill output (if available)
7. Primary edge
8. For spread/RL bets: the spread number (e.g. 1.5 for a -1.5 RL). For ML: 0. For totals: the total number.

Then run:
```bash
python ".claude/skills/bet-tracker/tracker.py" log \
  --model <model> \
  --sport "<sport>" \
  --bet "<full bet with opponent>" \
  --line <odds> \
  --units <units> \
  --score <score_or_omit> \
  --edge "<primary edge>" \
  --line-num <spread_number>
```

Confirm the logged pick to the user.

---

## Action: `result <id> <win|loss|push>`

Look up the pick by ID, then run:
```bash
python ".claude/skills/bet-tracker/tracker.py" resolve <id> <outcome> \
  --final-score "<score>" \
  --game-margin <int> \
  --line-num <float> \
  [--prop-result "<stat line>"] \
  [--prop-margin <int>]
```

- `--game-margin`: actual whole-number game margin, positive = our team won by X (e.g. won 6-3 → 3; lost 90-121 → -31)
- `--line-num`: the spread number for cover check display (e.g. 3 for -3 spread; 0 for ML)
- `--prop-result`: for player props, the stat line (e.g. "3/9 from three")
- `--prop-margin`: actual stat minus threshold (e.g. needed 4, got 3 → -1)

Then run `tracker.py stats` and show the output.

---

## Action: `stats` (default — no argument)

### Step 1: Auto-resolve open picks

Run `tracker.py open` to get a JSON list of open picks.

For each open pick where `date <= today`, web search for the result in parallel:
- Team bets: `"[teams] final score [date]"`
- Player props: `"[player name] [stat] [date] [opponent]"`

Determine win/loss/push from the result. Then for each resolved pick, run:
```bash
python ".claude/skills/bet-tracker/tracker.py" resolve <id> <outcome> \
  --final-score "<score>" \
  --game-margin <int> \
  --line-num <float>
```

If a result can't be found (game postponed, future game), skip and leave open.

### Step 2: Run the dashboard

```bash
python ".claude/skills/bet-tracker/tracker.py" stats
```

Print the full output verbatim.

### Step 3: Daily Recap

Write a punchy 3-5 sentence summary of **newly resolved picks only** (skip this if nothing was resolved today). Tone: sharp bettor talking to a friend — confident, a little sarcastic on losses, genuinely excited on wins. Cover:
- Biggest winner and how dominant
- Worst beat (blowout or near-miss)
- Any pattern that showed up (e.g. "RLM 2-for-2 in MLB again")
- One concrete takeaway

Example:
> "Braves didn't just win — they made 9-0 look like a formality. D-Backs did exactly what a +146 dog should: won clean, covered by a run. The Hornets? Lost by 31 in a play-in. That wasn't a game, it was a crime scene. RLM is 2-for-2 in baseball and 0-for-1 in NBA play-ins — trust it on the diamond, be skeptical when elimination pressure enters the picture."

### Step 4: Auto-write to betting-intel.md

After every stats run where picks were resolved, append a session entry to `betting-intel.md` under **Session Log**. Do this automatically.

Format:
```
### [YYYY-MM-DD] — Bet Tracker Results

**Resolved**: X picks ([W]-[L]-[P])

**Observations**:
- [Specific pick] ([edge], [model]) — [outcome], margin [X]. [What this confirms or challenges]
- [Flag near-misses and blowouts]

**Pattern updates**:
- [Edge type trending up/down — note it. Promote to Active Patterns at 3+ consistent results]
- [Score calibration flags]
```

Only write specific, actionable observations. If nothing notable: `[Date] — X picks resolved [W-L]. No notable updates.`

Also update top-level sections of `betting-intel.md` when warranted:
- **Active Patterns** — promote at 3+ consistent results for an edge type
- **Patterns to Avoid** — promote at 3+ consistent failures
- **Score Calibration Notes** — flag big mismatches between score and outcome

---

## Notes
- `tracker.py` handles all math and formatting — never compute ROI or units manually
- Minimum 20 settled picks per model for statistically meaningful comparisons
- The model with higher ROI after 50+ picks is the stronger methodology
