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

---

### 2026-04-25 — V2-Sharp Session

**Games scanned**: ~9 MLB · 4 NBA playoff · 3 NHL playoff · **Sharp signals found**: 0 confirmed · **Picks**: 0

**Signal observations**:
- Senators ML (Game 4 vs CAR, OTT down 0-3 at home) — line moved Senators +155 → +145 across one book. 10-cent move is below 15-cent steam threshold and is fully explainable by desperate-home-elimination dynamics + public chalk on the sweep narrative. Not confirmed sharp.
- Timberwolves +1.5 home vs Denver (MIN leads 2-1 in series) — counterintuitive line (home team leading the series getting points) is a possible Denver-sharp tell, but no public/money split data accessible to confirm RLM. Pass without confirmation.
- Diamondbacks vs Padres (Mexico City Series) — book pricing disparity (ARI -112 at one shop vs SD -130 elsewhere) is venue-related (Mexico City altitude/novelty) rather than steam. Not a confirmed sharp signal.
- Jalen Williams (Thunder, Grade 1 hamstring strain) — injury news public since Wednesday after Game 2; line of OKC -9.5 is fully baked. No unpriced-injury edge.
- Wembanyama OUT (Spurs Game 3) — already-resolved Friday game, not on today's slate.

**Calibration notes**:
- Same data-access wall as 2026-04-22 V2-Sharp: Action Network, BetQL, VSIN, Covers, SportsBettingDime, Cleatz all returned 403. The model's premise requires verifiable bet/money splits — cannot confirm RLM without them.

**Patterns reinforced or challenged**:
- Second consecutive V2-Sharp no-pick day driven by data access. Model is working as designed (sit out without confirmation), but the dependency on a single class of sources is a real systemic limitation. Worth exploring DocSports/sharp-report mirrors or direct sportsbook public-percentage feeds in next SKILL.md self-healing pass.
- Reinforced: never force a marginal RLM read on a 10-cent move. Steam threshold (≥15 cents ML / ≥1pt spread at multiple books) exists for a reason — the Senators move would have failed it on size alone even if confirmable.

---

### 2026-04-25 — V1-Trends Session

**Games researched**: ~14 across MLB (10), NBA playoffs (4), NHL playoffs (3) · **Picks**: 2 (both MLB, avg Score 6.0)

**Signal observations**:
- Garrett Crochet (BOS) at 7.88 ERA is the cleanest "broken pitcher" spot of the week — ranks 72nd of 73 qualified SPs, gave up 11 ER in 1.2 IP last start. Market has him at near-pickem (-116 BAL favorite) which is light pricing relative to a 3.80 ERA gap. This is functionally an ERA-mismatch trade but the broken-ace angle is distinct from the Lauer/Mahle/Littell template — name reputation seems to be holding the line tighter than warranted.
- Yankees-Astros lined up as a near-twin to yesterday's pick (Warren/McCullers): Weathers (3.18) vs Burrows (6.75), same script different cast. Sized down to 1u given 100% public on NYY across recent ticks and -154 juice eating most of the edge. Same chalk-trap risk that capped Apr 24 at 5.2.
- No qualifying NBA/NHL playoff picks. Hurricanes/Senators Under 5.5 (-105) was tempting (3-of-3 series Unders, elite goaltending both sides) but scored 4.8 on the rubric and didn't clear threshold. Stars +114 had an attractive price but injury picture (Hintz/Bastian out vs Zuccarello/Trenin out) was too symmetric. Thunder -9.5 was the kind of huge playoff number the V2-Sharp Apr 22 log explicitly flagged as low-signal.

**Calibration notes**:
- Orioles ML at Score 6.8 — depends on Crochet's collapse being real, not a one-off. Five-start sample (24 IP, 7.88 ERA, 11 ER game on Apr 13) is enough to call it a real regression, not noise. If he settles down for one start, this is toast.
- Yankees ML at Score 5.2 — same calibration as yesterday's logged 5.2: real mismatch, juice + 100% public makes it a thin lean. Watching whether back-to-back Yankees mismatches at -145+/-154 cash; both at 1u is the right size for chalk-trap exposure.

**Patterns reinforced or challenged**:
- ERA-mismatch pattern goes to its fifth test (Apr 17 D-Backs/Lauer W, Braves/Walker W; Apr 22 Angels/Lauer, Braves/Littell, Dodgers/Mahle pending; Apr 24 Guardians/Scherzer, Yankees/McCullers pending; Apr 25 Orioles/Crochet, Yankees/Burrows pending). Need to revisit promotion criteria once Apr 22-24 results resolve.
- New sub-pattern flagged: "broken ace, name still on the line" — Crochet's case is the first cleanly-isolated example. Watch for similar setups (former Cy Young/All-Star with bottom-decile current ERA priced tighter than peripherals warrant).
- Continued discipline on playoff NBA/NHL no-picks. V1 has now passed on three consecutive playoff slates without a basketball/hockey pick (Apr 22, Apr 24's 1u Blazers was the lone exception, Apr 25 none). The intel log caution from Apr 17 Hornets disaster is holding.

---

### 2026-04-26 — V2-Sharp Session

**Games scanned**: ~14 MLB · 4 NBA playoff · 2 NHL playoff · **Sharp signals found**: 1 confirmed · **Picks**: 1

**Signal observations**:
- Phillies @ Braves Under 8.5 — Cleanest RLM signal in weeks. 94% public tickets and 94.1% public money on Over, line moved Under -120 → -130 (10-cent move toward Under against overwhelming public). Sale (2.79 ERA, 1.00 WHIP) vs Nola (5.06 ERA, 1.46 WHIP). Phillies on 9-game losing streak. Multiple sources confirmed split. Logged at 2u, score 8.0.
- Yankees @ Astros investigated — VSIN flagged "low bets / high dollars" sharp split on Yankees (89% bets, 99% money), but line drifted from -154 (Saturday) to -132/-140 (Sunday). Movement direction is contradictory (sharps on Yankees but line moving toward Astros). Likely the Saturday number anchored on a different probable starter; Sunday correction may reflect Arrighetti's 2.45 ERA being stronger than Gil's 4.11. Discarded as ambiguous — direction conflict invalidates the signal.
- Rays @ Twins investigated — Sharps drove Rays from -135 to -145 (75% bets, 99% money on Rays). Public AND sharps on the same side, which is sharp confirmation but NOT RLM. Doesn't qualify under V2-Sharp criteria (which requires line moving against public).
- Reds vs Tigers investigated — VSIN reported Reds from -105 to -110 (sharp on Reds), but FanDuel research showed Tigers as -160 favorite, contradicting the direction. Conflicting source data, no clean RLM. Discarded.
- NHL slate down to 2 games (Bruins/Sabres G4, Lightning/Canadiens G4); no public/money split data accessible to confirm RLM. Both lines tight at -111 to -115. Pass.
- NBA slate (Cavs/Raptors G4, Knicks/Hawks G4, Lakers/Rockets G4, Pacers/Bucks G4-ish) — no actionable sharp split data. Pass on playoff basketball per the standing Apr 17 caution.

**Calibration notes**:
- Phillies/Braves Under at 8.0 — could have been higher (signal strength is 9/10 with 94% public on wrong side, well above the 70% threshold), but line value docked to ~5.5 because -130 is on the worse end of "acceptable" juice and we're entering after the steam already moved the number. Final 8.0 reflects strong-signal-but-late-entry.
- Yankees/Astros conflict shows the limit of multi-source synthesis: VSIN's "sharp on Yankees" reading and the actual closing-line drift toward Astros can't both be right. Default position when sources conflict directionally = pass.

**Patterns reinforced or challenged**:
- MLB total RLM (Under) with elite-vs-broken pitching matchup is a clean signal type. Different from prior V2-Sharp picks (White Sox ML, Hornets spread) — first totals-based RLM logged for V2.
- Reinforced: when public is at ≥90% and line moves against them, that's the strongest version of RLM and warrants a 2u sizing despite the late-entry juice penalty.
- Reinforced: VSIN MLB betting splits remained accessible today (unlike Action Network, BetQL, Covers, SportsBettingDime which continue to 403). VSIN + FanDuel Research + Sportsbettingdime article pages are the working source stack right now.


---

### 2026-04-26 — V1-Trends Session

**Games researched**: ~14 across MLB (8), NBA playoffs (4), NHL playoffs (2) · **Picks**: 2 (both MLB, avg Score 6.2)

**Signal observations**:
- Royals/Angels ERA mismatch (Lugo 1.15 vs Detmers 4.08) is the cleanest spot of the slate. Lugo holds the 2nd-lowest ERA in MLB. Multiple ATS trends align: Angels 0-7 covering RL in last 7 night games vs sub-.500 teams, Royals 6-3 SU L9 vs LAA, Royals 8-7 home. Line moved -142 → -122 over two days, which is a yellow flag (market correcting toward Angels) but the underlying mismatch is too large to dismiss. Sized at 1u given the line drift.
- Astros/Yankees presents an interesting INVERSE setup vs Apr 24/25 picks. Yesterday Yankees had the pitching edge (Warren 2.49 vs McCullers 6.20, Weathers 3.18 vs Burrows 6.75). Today the script flips: Arrighetti (2.45) vs Gil (4.11). Public is still 88%+ on Yankees from yesterday's chalk pattern but the edge has moved to Houston. Line drifted from NYY -154 (Sat) to -140 (Sun) — direction supports the pitching-edge flip read. Note: V2-Sharp investigated the same spot and discarded as ambiguous (VSIN flagged sharps on NYY at 99% money but line moved opposite direction). V1 takes the trend/situational side at +118; sized 1u to acknowledge the conflicting V2 read.
- Padres/Diamondbacks Mexico City Series — pricing distortions from altitude/venue make this hard to handicap; passed without confirmation.
- Red Sox/Orioles (Early 2.88 vs Bradish 3.96 with 1.76 WHIP) tempting at +119 but edge too small to clear threshold; passed.
- No qualifying NBA/NHL playoff picks. Cavs/Raptors had Quickley OUT-for-series injury edge but Cavs poor ATS as -3.5+ favorite (22-35-1) makes the spread risky; ML at -170 is heavy chalk. Avalanche -1.5 PL closeout spot is too rich a number on Kings desperation. Wemby remains questionable; stayed out per Apr 24 intel log on playoff NBA caution.

**Calibration notes**:
- Royals ML at Score 6.4 — line drift (-142 → -122) cost a point of confidence. If Lugo dominates and line was just market-correcting AL vs NL pricing, this is a strong play. If sharps were peeling away from KC for an unseen reason (lineup news, bullpen fatigue from sweep-attempt), the drop was warranted.
- Astros ML at Score 6.0 — pitching edge is real but V2 discarded same spot as ambiguous. Test of whether trend/contrarian-dog read holds despite the sharp-money signal pointing the other way. If this loses, document it as evidence that V2's discipline on conflicting signals is worth respecting even for V1 trend plays.

**Patterns reinforced or challenged**:
- ERA-mismatch pattern goes to its sixth test. Royals/Angels is a clean test (Lugo-elite vs Detmers-mediocre).
- New observation: when V1 and V2 disagree on the same game (V1 sees trend/value, V2 sees ambiguous-RLM), the model-on-model conflict itself is data. Astros pick will be the first explicit test of this divergence type.

