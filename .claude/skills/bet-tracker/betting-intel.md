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

---

### 2026-04-27 — V2-Sharp Session

**Games scanned**: 3 NBA playoff · 2 NHL playoff · ~12 MLB · **Sharp signals investigated**: 4 · **Picks**: 0

**Signal observations**:
- Phoenix Suns +375 ML vs OKC (Game 4) — 12% public tickets, 44.5% money handle on PHX. Money/ticket divergence is sharp-style, but spread moved OKC -9.5 → -10.5 (with public), not against. No RLM confirmation. Discarded.
- Minnesota +380 ML vs Denver (Game 5) — 56.2% money on MIN vs 76.3% public on DEN. Fully explained by Edwards (knee) + DiVincenzo (Achilles) both ruled OUT — public injury info, line already adjusted. Not sharp action. Discarded.
- Pittsburgh ML vs Philadelphia (Game 5) — Line bounced -134 → -137 (~3 cents, below 15-cent steam threshold). Single book noise, not coordinated steam. Discarded.
- Penguins-Flyers Under 5.5/6 — 70% money on Under, but total moved 6 → 5.5 with the money (no RLM). Public Under bias rather than sharp signal. Discarded.

**Calibration notes**:
- Phoenix money/handle split was tempting (mirrors 4/18 White Sox pattern), but NBA playoff context with team down 0-3 lacks the pitching-mismatch confirmation that made the WSOX play clean. Big-dog handle on +375 likely reflects one whale taking a value swing, not a syndicate position. Held the line at the 6.0 threshold.

**Patterns reinforced or challenged**:
- Money/ticket divergence on big underdog ML in NBA playoffs is NOT equivalent to MLB money/ticket divergence. MLB pattern is supported by pitching mismatch; NBA elimination-game dog handle can be single-whale lottery tickets. Note for future: require RLM confirmation (line moving against public) for NBA money-split signals before flagging.

---

### 2026-04-27 — V1-Trends Session

**Games researched**: ~14 across MLB (10), NBA playoffs (3), NHL playoffs (2) · **Picks**: 3 (all MLB, avg Score 6.1)

**Signal observations**:
- Three ERA-mismatch spots logged: Guardians ML -145 (Messick 1.76 vs Matz 4.81), Angels ML -120 (Kochanowicz 3.10 vs Kay 5.57), Padres ML -110 (Vasquez 1.88 vs Boyd 5.79). Seventh test of the ERA-mismatch pattern. Average ERA gap ~2.6 runs across the three picks.
- Padres was sized down to lean (5.5) explicitly because the intel log earlier in the day flagged Vasquez xERA 4.32 = regression candidate. Demonstrates intel log being applied to score calibration as designed.
- Guardians H2H wrinkle: Matz 1.71 lifetime ERA vs CLE in 31.2 IP. Treated as a small-sample concern (~5 starts spread across 2016/2019/2021), not enough to override 2026 ERA mismatch but enough to drop confidence by ~1 point.
- Angels: Kochanowicz 1.80 ERA across his four April starts is the cleanest in-form signal. Kay coming off 8 ER in 3.2 IP last start = broken-pitcher angle layered on top.

**No-pick rationales**:
- Pirates/Cardinals — Pirates were attractive on ERA gap (May 5.84) but Pittsburgh is using opener-bulk (Montgomery 1 inning, Dotel as bulk reliever). Removes the clean SP ERA-edge read; passed.
- Yankees @ Rangers — Schlittler 1.77-1.95 ERA vs deGrom 2.13 ERA is functionally a coin flip on the mound. Yankees lineup advantage real but -175 juice eats the edge. Pass.
- Marlins @ Dodgers — Yamamoto 2.48 ERA but Dodgers -295 is unbettable chalk territory.
- NBA playoffs all skipped per standing playoff caution: Wolves +10.5 has Edwards/DiVincenzo OUT but injuries are public and priced (V2-Sharp Apr 27 logged this same read). Thunder -10.5 sweep number too rich + Jalen Williams OUT. Pistons -2.5 a coin flip with no edge.
- NHL playoffs both skipped: Flyers/Pens G5 has PIT desperate at home but no pricing edge. Vegas/Mammoth G4 a coin flip at -115.

**Calibration notes**:
- Guardians ML at Score 6.5 — flagged as "best of slate" if Matz H2H magic is noise (more likely than not given his 4.81 season ERA). If he posts a quality start vs CLE again, this loses and the H2H concern was real.
- Angels ML at Score 6.4 — depends on Kochanowicz holding April form. If Kay catches the Angels' offensive funk (17 R in 7 G), score was overconfident.
- Padres ML at Score 5.5 — explicit test of "did intel log save us from a bad bet" or "did it cause us to size down on a winner." Vasquez peripherals favor regression but Boyd 5.79 ERA is bad regardless.

**Patterns reinforced or challenged**:
- ERA-mismatch pattern at seventh test. Three more data points coming today. Need to revisit promotion criteria after Apr 22-26 results all resolve.
- First explicit instance of intel log directly altering a pick's size (Padres at 1u lean instead of 1u play). Document outcome: did the warning prove correct?
- Continued discipline on playoff NBA/NHL no-picks. V1 has now passed on five consecutive playoff slates without taking a clean basketball/hockey play (Apr 22, 24's Blazers was the lone NBA pick, 25, 26, 27).

---

### 2026-04-28 — V1-Trends Session

**Games researched**: ~15 across MLB (12), NBA playoffs (3), NHL playoffs (3) · **Picks**: 2 (both MLB, avg Score 5.7)

**Signal observations**:
- Brewers ML -112 vs Arizona — Kelly 9.31 ERA is the broken-ace template (returning from IL, 8 ER in 4.1 IP last start vs CWS) but the sample is only 2 starts so the headline number is noisier than past picks (Crochet 7.88 over 5 starts, Lauer 7.82 over multiple). Light juice (-112) on the home favorite is the value driver. ARI is 19-8 ATS this year — strong counter-signal on the team-level trend, kept score at 6.0 not higher.
- Astros ML +114 @ Baltimore — Teng (2.16) vs Baz (5.08) is a clean 3-run ERA edge with HOU as plus-money road dog. Public heavy on BAL run line. Direct echo of Apr 26 Astros ML +118 vs NYY pick (Arrighetti 2.45 vs Gil 4.11, also score 6.0). Different from Apr 24-25 Yankees picks where NYY had the pitcher edge — this template flips back to Houston this week. Sized to 1u lean given HOU 11-18 SU/ATS trend offsets the pitching edge.
- Yankees @ Rangers (Schlittler 1.77 vs deGrom 2.13) is the cleanest game on the slate but pitcher edge is symmetric — both elite. -175 NYY juice eats whatever lineup edge exists. Same chalk-trap risk that capped Apr 24/25 NYY at 5.2; today it doesn't even clear that bar.
- Mets -185 vs Nationals (Holmes 2.10 vs Littell 7.56) had a massive ERA gap but line moved -175 → -194 already, eating the value. Same Littell broken-ace was logged as part of Apr 22 Braves/Littell pick at -149 (pending result). Skip due to juice.
- Cubs -125 @ Padres (Cabrera 2.73 vs Buehler 5.75) is a real 3-run ERA gap but model only gives 53% Cubs vs implied 55.6% — near breakeven, name-pitcher-recovering risk on Buehler similar to Kelly. Skip per chalk-trap discipline.

**Calibration notes**:
- Brewers ML at Score 6.0 — depends on whether Kelly's 9.31 is real collapse or 1-bad-start noise. Veterans with proven track records (Career ~3.50 ERA) often regress toward mean fast. Watch for any Arizona lineup news that could suggest sharps know something.
- Astros ML at Score 5.4 — explicit second test of "Apr 26 Astros template" (contrarian +money dog with pitching edge over public NYY chalk). Apr 26 result still pending; today is essentially the same setup with a different ace pitcher. If both lose, document as evidence that "contrarian +money dog" is a thinner edge than the rubric suggests.

**Patterns reinforced or challenged**:
- ERA-mismatch pattern at eighth and ninth tests today. Two more data points; need to revisit promotion criteria after the Apr 22-27 backlog of pending picks resolves.
- Continued discipline on playoff NBA/NHL no-picks. V1 has now passed on six consecutive playoff slates without a basketball/hockey play (other than Apr 24's lone Blazers).
- Chalk-trap discipline held: skipped Yankees -175, Mets -185, Reds -200, Dodgers -295, Cubs -125. Heavy juice on legitimate mismatches keeps getting cut.

---

### 2026-04-29 — V1-Trends Session

**Games researched**: ~14 across MLB (10), NBA playoffs (3 G5s), NHL playoffs (3) · **Picks**: 3 (all MLB, avg Score 6.3)

**Signal observations**:
- Cubs/Padres ERA-mismatch is the cleanest spot of the slate — Waldron 12.46 ERA / 2.31 WHIP over 8.2 IP, Padres staff at 8.13 ERA over the last 7 days (worst in MLB) and 15% K rate (lowest in MLB). Apr 28 intel log skipped Cubs/Padres at -125 with Buehler (5.75) due to "name-pitcher recovery" risk; today's Waldron has no such overhang and the gap is ~8 runs vs ~3. Picked at -118 / score 6.5.
- Royals ML +102 with Wacha (2.51) vs Severino (5.17, 7.11 home ERA at hitter-friendly Sutter Health). Plus money on better-pitcher side compounded by ballpark factor. Inverse of Apr 26 Royals/Angels -122 pick (line had drifted toward the better side then; today the better side is plus money).
- Diamondbacks ML +110 — E-Rod (2.89) vs Sproat (6.45) on paper, but E-Rod allowed 8 ER over last 2 starts so the headline edge overstates current form. Saved by ARI 19-8 ATS team-level trend (strongest in the slate). Sized to 1u lean given E-Rod regression risk.
- Astros ML +104 vs BAL (Lambert 3.27 vs Bassitt 6.75) is the third consecutive day of the contrarian-Astros-pitching-edge template (Apr 26 +118 win pending, Apr 28 +114 pending). Skipped today to avoid concentration on a still-pending pattern test — wait for results before adding a third leg.

**No-pick rationales**:
- Tigers/Braves — Skubal (2x Cy Young, 2.72 ERA) vs JR Ritchie (2.57 ERA in 7 IP MLB sample) is a name-vs-unproven setup, but Braves are 21-9 (best record in MLB) and -144 juice on Detroit eats most of the headline edge. Passed.
- Yankees @ Rangers — Warren/Elmer Rodriguez (TBD) vs Eovaldi (5.79 ERA) looks like a pitching edge but starter uncertainty + -154+ juice keeps this in chalk-trap territory. Continued discipline on heavy NYY juice.
- Mets/Nats — Holmes 2.10 vs Littell 7.56 was the headline mismatch but line moved -175 → -194, eating the value. Same Apr 28 pass logic.
- Phillies/Giants — Sanchez 2.94 ERA but 1.60 WHIP is a major red flag (44 hits in 33.2 IP); -149 juice on a starter with that kind of baserunner traffic is a fade signal not a play.
- Mariners/Twins — Kirby (2.97) vs Bradley (2.91) is symmetric, no edge.
- Blue Jays/Red Sox — Both starters >6.50 ERA (Lauer 6.75, Bello 9.00); Bello 1-4 ATS as BOS dog this year is a clean fade signal but Lauer's 6.75 isn't reliably better. Coin flip at the margin, passed.
- All NBA G5s skipped per standing playoff caution: Pistons -9.5 / Magic, Cavs -8.5 / Raptors, Lakers -4.5 / Rockets (Durant OUT priced in, Reaves Q). No clean injury or RLM edges.
- All NHL games skipped: Lightning -1.5 / Canadiens, Penguins / Flyers G6 (-122 toss-up), Vegas / Mammoth — no clean pricing edges.

**Calibration notes**:
- Cubs ML at Score 6.5 — depends on Waldron's 12.46 ERA being real and not 1-bad-start noise. Sample is 8.2 IP so it's small, but knuckleballer is also a high-variance archetype. If he throws a quality start, this is toast and we'll have evidence that the small-sample-on-bad-pitcher edge is thinner than the rubric suggests.
- Diamondbacks ML at Score 6.0 — first explicit test of "ATS-trend-strong-enough-to-override-pitcher-regression" setup. If E-Rod posts another 4+ ER outing and ARI loses, document as evidence that team-level ATS trends shouldn't outweigh in-form pitcher quality.
- Royals ML at Score 6.4 — Severino's 7.11 home ERA at Sutter Health is the value driver. If Severino throws a quality start, ballpark-factor edge was overweighted.

**Patterns reinforced or challenged**:
- ERA-mismatch pattern at tenth (or higher) test today (Cubs/Padres-Waldron, Royals/Athletics-Severino, Diamondbacks/Brewers-Sproat all variants of the template). Need to revisit promotion criteria once the Apr 22-28 backlog of pending picks resolves.
- Continued discipline on playoff NBA/NHL no-picks. V1 has now passed on seven consecutive playoff slates without a basketball/hockey play (other than Apr 24 Blazers).
- Chalk-trap discipline held: skipped Yankees -154+, Mets -194, Dodgers -225, Tigers -144. Heavy juice on legitimate mismatches keeps getting cut even when the underlying matchup is real.

---

### 2026-04-30 — V2-Sharp Session

**Games scanned**: ~12 MLB · 3 NBA playoff Game 6s · 2 NHL playoff Game 6s · **Sharp signals investigated**: 6 · **Picks**: 0

**Signal observations**:
- D-Backs @ Brewers (ML) — Money/ticket divergence (60% public bets MIL, 62% money on ARI) but line held firm at MIL -120/-125 across the cycle. No actual line movement against public to confirm RLM. Adding to that, the run-line splits flip the other way (sharps 68% on MIL +1.5), which signals a coherent "close game" sharp position rather than a clean ML steam play. Same direction-conflict pattern flagged on Apr 26 Yankees/Astros = pass.
- Nuggets @ Timberwolves Game 6 — Line moved DEN -6.5 → -5.5 (1pt toward MIN) which is a steam-sized move, but no accessible public/money splits to confirm whether move was sharp or simply public homedog buying after MIN went down 3-1 → 3-2. Edwards (knee) + DiVincenzo (Achilles) injuries are publicly known and already priced (logged as such on Apr 27). Cannot confirm sharp catalyst for the move. Pass without confirmation.
- Celtics @ 76ers Game 6 — Opened BOS -5.5 (-115), drifted to BOS -6.5 (-218 to -245 ML). Line moved with the public chalk side; not RLM. Discarded.
- Knicks @ Hawks Game 6 — Mixed line direction across books (NYK -2 open, current -1.5 to -2.5). No clean steam direction. Discarded.
- Orioles vs Astros (DH) — Public hammering Astros (multiple snapshots at 100%), line moved HOU -120 → -122 (with public). Not RLM. Discarded.
- Cardinals @ Pirates — Public and money both on PIT (Skenes 77% bets / 71% money on -1.5; ML moved toward PIT as Skenes start firmed up). Sharp/public alignment, not RLM. Same pattern as Apr 26 Rays/Twins discard — sharp confirmation ≠ RLM under V2-Sharp criteria.
- Stars @ Wild Game 6 — Line drifted MIN -102 → -125 across books with no accessible splits. Could be public homedog momentum + sharps; can't confirm direction. Discarded.

**Calibration notes**:
- Brewers/D-Backs at score ~5.0–5.5 ceiling absent line movement. The Apr 18 White Sox playbook (money/ticket divergence + pitching edge) needed a confirmed line shift OR pitching mismatch to clear the bar. Today's Soroka vs Woodruff is too even on the mound for the divergence to stand alone.
- Nuggets/Wolves -1pt move would qualify as steam if confirmed at multiple books with public/money splits showing public on DEN. Without those splits the move is uncategorizable. Marking as "would have been investigated harder if VSIN/Action Network were accessible" — same data-access issue logged on Apr 22, 25.

**Patterns reinforced or challenged**:
- Third V2-Sharp no-pick day in the last six sessions (Apr 22, 25, 30). Selectivity working as designed.
- Reinforced Apr 26 rule: when split data conflicts directionally (e.g., sharps on Side A ML but Side B run line), default to pass. Today's D-Backs/Brewers fit this exactly.
- Reinforced Apr 27 rule: NBA playoff line moves without verified public-side data are NOT actionable as sharp signals — could equally be public homedog buying or whale lottery tickets. Nuggets/Wolves -1pt move is a textbook example of why we need splits, not just movement.
- Reinforced data-access pattern: Action Network, BetQL, Covers, Scores&Odds, OddsShark, SportsBettingDime, FanDuel Research all 403'd today. VSIN article also 403'd (in contrast to Apr 26 when VSIN was the working source). Working source stack continues to shrink.

---

### 2026-05-06 — V1-Trends Session

**Games researched**: ~12 across MLB (9), NBA playoffs (1), NHL playoffs (1) · **Picks**: 3 (all MLB, avg Score 6.5)

**Signal observations**:
- Three ERA-mismatch spots identified: Cardinals ML +103 (Pallante 3.73 vs Sproat 6.75), Guardians ML +116 (Cantillo 3.67 vs Ragans 5.29), Red Sox ML ~+100 (Gray 4.30 vs Flaherty 5.90). ERA-mismatch pattern now at its 11th–13th test depending on how unresolved Apr picks settled.
- Dodgers -220 vs HOU (Glasnow 2.56 vs McCullers 6.32) was the largest ERA gap on the slate (~3.8 runs) but chalk-trap discipline held — skipped at -220. Same discipline applied Apr 24–29 on heavy chalk.
- Cardinals and Guardians are both road underdogs with better pitchers. The "plus-money better pitcher" template (seen on Apr 29 Royals ML +102) is getting a second and third test today.
- Red Sox ML included as a borderline lean (score 6.0) — the ERA gap (1.6 runs) is the smallest of the three picks and Flaherty's small sample (29 IP) adds uncertainty.
- Spurs/MIN Game 2 (-9.5) skipped per standing NBA playoff caution. MIN won G1 as +10.5 road dogs; no sharp confirmation available.
- BUF/MTL NHL total (DK opened 6.5, now 5.5) investigated for V1 totals angle but no situational edge strong enough to clear threshold — playoff debut game, total movement explained by defensive context.

**Calibration notes**:
- Cardinals ML at Score 7.0 — hinges on Sproat's 6.75 ERA being real over only 2 starts. If Sproat settles down (veteran regression-to-mean), this is toast. If the sample reflects a broken pitcher, it cashes easily.
- Guardians ML at Score 6.4 — Ragans is 1-4 and struggling all season, but KC home field is real. If Ragans finds his Apr 2025 form for one start, the ERA signal is overweighted.
- Red Sox ML at Score 6.0 — borderline inclusion. Flaherty's 1.79 WHIP is the red flag, not just ERA. Watch: if Flaherty walks batters early and BOS capitalizes, this is the right call; if he throws a clean 5 innings, the score was inflated.

**Patterns reinforced or challenged**:
- ERA-mismatch pattern now extended to 11-13 tests (pending prior unresolved). First session with three ERA-mismatch picks simultaneously — watching whether three concurrent picks dilutes the edge or compounds it.
- "Plus-money better pitcher as road dog" sub-template getting its clearest back-to-back test (Cardinals +103, Guardians +116). If both hit, worth promoting to a named sub-pattern.
- Chalk-trap discipline held: Dodgers -220 skipped despite the largest ERA gap on the slate. Consistent with Apr 24–29 discipline.

---

### 2026-05-06 — V2-Sharp Session

**Games scanned**: ~12 MLB · 1 NBA playoff · 1 NHL playoff · **Sharp signals found**: 0 confirmed · **Picks**: 0

**Signal observations**:
- BUF/MTL total (DK opened 6.5, now 5.5) — 1-goal drop is steam-sized, but could not confirm at 3+ books. Playoff defensive tightening is a clean public explanation for the opener setting it at 5.5 rather than the H2H historical 6.5. Over is -130, Under is +106 — the book still sees heavy public action on the Over (consistent with the H2H history of 6+ goals in 8 straight). Without public/money splits confirming the public is on the Over and the line moved the opposite way, this does not qualify as RLM. Discarded.
- Spurs/MIN Game 2 (-9.5) — MIN won G1 as +10.5 road dogs. No public/money split data accessible. Standing intel log caution on NBA playoff spreads applies. Discarded.
- MLB full slate — Action Network, BetQL, VSIN, Covers, FanDuel Research all 403. No public/money splits accessible. Cannot confirm RLM on any MLB game. Discarded by default.

**Calibration notes**:
- BUF/MTL total would have been worth investigating harder if public splits were available. A 1-goal drop against what should be a public Over (6+ goals in 8 straight H2H) would be a meaningful signal if confirmed. Data-access wall blocked further investigation.

**Patterns reinforced or challenged**:
- Seventh consecutive session where data-access failures on sharp-tracking sites (Action Network, BetQL, VSIN, Covers) result in 0 V2 picks. Model is working as designed — sitting out beats guessing.
- NHL total moves require the same verification standard as MLB ML moves: need public/money splits AND confirmation at 3+ books. A single-source 1-goal drop is insufficient even if steam-sized on paper.

---

### 2026-05-15 — V1-Trends Session

**Games researched**: ~10 across MLB (8), NBA playoffs (2 G6s), NHL playoffs (1 G5) · **Picks**: 1 (MLB, Score 5.5)

**Signal observations**:
- Kelly (ARI) has 9.92 xERA / 7.62 ERA over 5 starts — extreme broken-pitcher spot. One improved last start (7 IP, 1 ER vs NYM) lowered ERA from 9.95 to 7.62 but did not change underlying peripherals. xERA is the reliable predictor; picking COL ML +106 on xERA mismatch (Kelly 9.92 vs Freeland 5.18) at Coors.
- Yankees vs Mets (Schlittler 1.35 ERA vs Holmes 1.86 ERA): symmetric elite pitching matchup, no mismatch. Line moved -140/-145 toward -160 (public AND sharp aligned on NYY). Not a V1 pick — no ERA gap and chalk territory.
- Spurs -4.5 to -5.5 road favorites vs Wolves Game 6: 73% bets + 84% money on Spurs = public AND sharp money aligned on same side (not RLM). Standing playoff NBA/NHL caution applied. Skipped.
- Cavaliers -3.5 (-120) vs Pistons Game 6: Robinson/Huerter/LeVert all questionable, but Robinson missed Game 5 already — injuries public and priced into line. -120 juice reduces value further. Skipped.
- NHL: Canadiens/Sabres Game 5 was May 14; no NHL game on May 15.

**Calibration notes**:
- COL ML at Score 5.5 — borderline inclusion, below usual 6.0+ bar, due to Kelly's one improved start. If Kelly reverts to peripherals (5+ ER) and COL wins, xERA-over-recent-ERA methodology is validated. If Kelly replicates his last start, revisit whether one good outing is enough to disqualify the broken-pitcher angle entirely.

**Patterns reinforced or challenged**:
- ERA-mismatch (xERA variant) pattern extended. First time using xERA as primary signal when ERA and xERA diverge sharply post-one-improvement-start.
- Continued discipline on playoff NBA/NHL no-picks. V1 has now passed on eight consecutive playoff slates without a basketball/hockey play (other than Apr 24 Blazers injury-based).

---

### 2026-05-15 — V2-Sharp Session

**Games scanned**: ~10 MLB · 2 NBA playoff G6s · **Sharp signals found**: 0 confirmed · **Picks**: 0

**Signal observations**:
- Spurs/Wolves G6: 73% bets, 84% money on Spurs — public AND sharp aligned on same side. Not RLM; no contrarian sharp value.
- Yankees/Mets: Line moved -140/-145 to -160 WITH the public (60% on NYY). Both public and sharp on NYY — not RLM.
- All MLB sharp-tracking sources (Action Network, VSIN, BetQL, SportsBettingDime, Covers) returned 403 — consistent with 8+ consecutive sessions.
- No unpriced injuries identified.

**Patterns reinforced or challenged**:
- Eighth+ consecutive V2-Sharp no-pick driven by data-access failures. Model working as designed.
- Reinforced: when money % > ticket % (84 > 73 on Spurs), sharps are MORE bullish than public — this is sharp confirmation on the chalk side, not a contrarian RLM signal.

