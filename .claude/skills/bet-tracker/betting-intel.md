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

### 2026-04-22 — V1-Trends Session

**Games researched**: 12 across MLB, NBA playoffs, NHL playoffs · **Picks**: 3 (all MLB, avg Score 6.8)

**Signal observations**:
- Three clean ERA-mismatch spots in MLB today where the bad starter has 7+ ERA (Lauer 7.13, Littell 7.11, Mahle 7.23). This is the same pattern that went 2-0 on Apr 17 (Braves ML 9-0, D-Backs RL 6-3).
- No qualifying NHL or NBA playoff picks — Pistons -8.5 intentionally skipped given Hornets -3 play-in blowup taught us to reduce confidence on line-movement reads in high-variance playoff contexts.
- Braves ML at -149 with 84% public is heavy chalk. Historically risky but ERA/rotation edges are real — sized down to 1u to account for juice and trap risk.

**Calibration notes**:
- Angels ML at Score 7.6 — Soriano's 0.28 ERA is unsustainable but the full-season ERA gap to Lauer is still ~7 runs. Even regression to mean keeps the mismatch dominant. Watch if Lauer actually survives 4+ innings.
- Dodgers -1.5 RL — Freeman absence is the main downgrade vs what would be a slam-dunk mismatch otherwise. Monitoring whether Freeman-out games still cover -1.5 with Ohtani.

**Patterns reinforced or challenged**:
- MLB ERA-mismatch pattern getting a third test today (after 2-0 on Apr 17). If 4-of-5 or better across the next 2 weeks, promote to Active Patterns.
- No-pick in playoff basketball/hockey when line-movement reads are ambiguous. V1 should not force picks — intel log from Apr 18 V2-Sharp session emphasized this too.

---

### 2026-04-24 — V1-Trends Session

**Games researched**: ~15 across MLB, NBA playoffs, NHL playoffs · **Picks**: 3 (2 MLB, 1 NBA; avg Score 6.5)

**Signal observations**:
- Clean ERA-mismatch in CLE/TOR — Williams (2.12 ERA) vs Scherzer (7.16 ERA). Same template as Apr 17 (Braves/Lauer, D-Backs/Lauer) and Apr 22 (Angels/Lauer, Braves/Littell, Dodgers/Mahle). Fourth test for this pattern — if it hits, consider promoting to Active Patterns.
- Wemby concussion protocol created a clean injury edge on POR +2.5. Market already repriced series odds (-2000 → -550), but line may not have fully adjusted to his likely absence. Sized down to 1u given Apr 22 intel log caution on playoff basketball.
- Yankees/Astros at -145 is a borderline lean — mismatch is real (Warren 2.49 vs McCullers 6.20) but juice ate most of the value. Logged at 1u.

**Skipped**:
- Phillies/Braves (ATL -145) — intel log warns on heavy Braves chalk; Painter (4.42 ERA) vs Holmes (3.42 ERA) not a strong mismatch.
- Mariners/Cardinals (-160) — Kirby edge real but Mariners 1-8 on road in 2026 is too red-flag for heavy juice.
- Nats/White Sox — Mikolas 9.15 ERA but 2-0 lifetime vs CWS and Hudson is untested as starter; no clear edge.
- Oilers/Ducks Game 3 — coin flip after Ducks won Game 2 6-4; no edge at Oilers -137.

**Calibration notes**:
- Guardians ML at Score 7.4 — rests heavily on Scherzer's collapse being real (velocity decline + .368 xwOBA). If TOR hits HRs early, model underweights Scherzer's Hall-of-Fame mental toughness.
- Blazers +2.5 at Score 6.8 — if Wemby plays and looks normal, pick is toast. Watching inactives list.

**Patterns reinforced or challenged**:
- ERA-mismatch pattern goes to its fourth test. Need 4-of-5 hits across next 2 weeks to promote.
- First playoff NBA injury-edge play since Hornets RLM disaster on Apr 17 (-31 loss). This is injury-based, not RLM-based, so the intel log caution doesn't apply directly — but keeping it at 1u.

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

