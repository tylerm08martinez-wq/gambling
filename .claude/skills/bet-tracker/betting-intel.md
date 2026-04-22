# Betting Intelligence Log

Cumulative observations from V1-Trends, V2-Sharp, and Bet Tracker sessions. All three skills read this at the start and append new insights at the end. Use this to calibrate scores, prioritize signals, and avoid repeating mistakes.

---

## How to Use This Log (for skills)

**On read:** Scan all sections before making any picks or analysis. Apply relevant patterns to today's games. If a sport, team, edge type, or market condition matches a logged observation, adjust confidence accordingly.

**On write:** After presenting picks or resolving results, append a dated entry to the Session Log. Be specific — name teams, lines, signals, and outcomes. Vague observations don't help future decisions.

---

## Edge Type Patterns

*Running observations about which signal types are working or failing.*

<!-- Format: [Date] [Model] — [Signal type] — [Observation] -->

---

## Sport-Specific Observations

*Patterns that apply to specific sports or leagues.*

<!-- Format: [Date] [Sport] — [Observation] -->

---

## Market & Line Movement Notes

*Observations about books, juice levels, and line movement behavior.*

<!-- Format: [Date] — [Observation] -->

---

## Score Calibration Notes

*Cases where model scores were too high or too low vs. actual outcomes.*

<!-- Format: [Date] [Model] — [Bet] scored [X], outcome was [win/loss] — [What the score missed] -->

---

## Active Patterns (High Confidence)

*Patterns seen 3+ times with consistent results. Apply these proactively.*

None yet — will populate as data accumulates.

---

## Patterns to Avoid

*Situations that have repeatedly produced bad outcomes.*

None yet — will populate as data accumulates.

---

## Session Log

*Dated entries from each skill run — most recent at bottom.*

### 2026-04-18 — V2-Sharp Session

**Games scanned**: 15 MLB · **Sharp signals found**: 3 investigated · **Picks**: 1

**Signal observations**:
- Money/ticket RLM on White Sox ML (+140) — 67% public tickets on Athletics, 65% of money flipped to CWS; Fedde (3.38 ERA) vs Severino (5.59 ERA) reinforces sharp side. Cleanest signal of the day.
- Cardinals ML (+125) investigated — 55% HOU tickets, 75% STL money split looks like RLM but public lean only 55% (below 60% threshold), HOU has clear OPS advantage (.799 vs .695), no confirmed line movement. Discarded.
- Rangers ML (+118) investigated — 78% money on TEX but ticket split was essentially 49/51, and the line moved against Rangers (opened +122, sitting +119 = not RLM). Discarded.

**Calibration notes**:
- White Sox at score 7.75 — would have been higher if opening line movement confirmed; signal held primarily on ticket/money divergence + pitching edge.

**Patterns reinforced or challenged**:
- MLB money-ticket divergence remains primary signal type. Second session with a MLB pick using this method. Intel log shows 2-for-2 yesterday; tracking whether the edge holds.

---

### 2026-04-22 — V2-Sharp Session

**Games scanned**: ~15 MLB + 3 NHL playoff + 2 NBA playoff · **Sharp signals found**: 0 confirmed · **Picks**: 0

**Signal observations**:
- Stars @ Wild Game 3 investigated — Hintz (Stars C) out, but injury long-known (since March 6) and fully priced; Wild -134 home. No unpriced injury edge.
- Wild Zuccarello status investigated — day-to-day for Game 3 after Myers elbow (Game 1). Too uncertain to price; no line move against Wild to confirm sharps leaning Stars.
- Thunder -17.5 vs Suns (Game 2) — massive public number after 35-pt Game 1 rout. No RLM data available; huge laying-points spots rarely produce clean sharp signals.
- MLB slate (Braves/Nats, Guardians/Astros, Angels/BJs, etc.) — primary sharp-tracking sources (Action Network, VSIN, SportsBettingDime, BetQL) all returned 403. Unable to verify public/money splits or opening line movement. Cannot confirm signals without data — correct action is to pass.

**Calibration notes**:
- Data-access failures on sharp-tracking sites are becoming routine. Consider adding alternative sources (DocSports steam plays, sharp-report mirrors) in SKILL.md self-healing section.

**Patterns reinforced or challenged**:
- No-pick days are the model working as designed. V2-Sharp's premise is that fewer, cleaner signals beat volume. Sitting out beats forcing a marginal RLM.

---

### 2026-04-17 — Bet Tracker Results

**Resolved today**: 3 picks (2-1-0)

**Result observations**:
- D-Backs -1.5 RL vs TOR (+146, V1-Trends) — Won 6-3, needed to win by 2+, won by 3. Soroka dominant (4th win of season). High-ERA opponent + RLM signal = clean result.
- Braves ML vs PHI (-118, V1-Trends) — Won 9-0. Walker was cooked before the first pitch. RLM + ERA mismatch was the right read; this wasn't close.
- Hornets -3 vs ORL (-110, V2-Sharp) — Lost 90-121, down by 31. Play-in game, RLM fired but the game wasn't competitive. Hornets may have been low-motivation after clinching the spot; Magic were desperate.

**Intelligence updates**:
- RLM in MLB went 2-for-2 today with strong margins. Both faded heavy public sides (96% on TOR, 79% on PHI). Early signal that RLM is a reliable primary edge in baseball.
- RLM in NBA play-in failed badly (-31). Play-in games are single-elimination with high emotional variance — desperation and motivation distort normal line movement reads. Reduce confidence on RLM in play-in contexts.
- V1-Trends 2-0, V2-Sharp 0-1 on day 1. Too early to draw conclusions but V1 benefited from stronger situational context (ERA mismatches, not just line movement).

**Log maintenance**:
- No active patterns promoted yet — need 3+ consistent results per edge type.

