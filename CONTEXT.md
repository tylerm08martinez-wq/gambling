# Betting Domain Glossary

## CLV (Closing Line Value)
The difference between your entry price and the closing line, expressed as implied probability. Positive CLV means you got a better price than the market settled at = good process. Benchmark: Pinnacle's de-vigged closing line. Consistently beating Pinnacle by 2%+ is the documented definition of a profitable edge.

## Measured CLV
A CLV value computed from Pinnacle's actual de-vigged closing line at game start. Distinct from Unmeasured CLV (`null` or placeholder `+0.00%`), where the Pinnacle close was never fetched. Most picks today have Unmeasured CLV — the Pinnacle-fetch workflow is unimplemented. Statistics over CLV should exclude Unmeasured CLV picks rather than treat them as zero.

## CLV Coverage
The percentage of settled picks with Measured CLV. ROI is not a mature trust signal until CLV Coverage is at least 90%.

## CLV-Positive +EV Candidate
A pre-game betting candidate whose current available line appears mispriced relative to a sharper market or auditable edge signal. Preferred over "high-ROI pick" before results exist.

## High-ROI Pick
A retrospective label for a settled pick or pick cohort that produced strong return on invested units. Avoid using this term for pre-game candidates.

## Cross-Book Prop Gap
A discrepancy of 0.5+ units on the same player prop across DK / FanDuel / BetMGM. Indicates sharp money already hit one book (the "sharp-hit book") and the other books haven't adjusted yet (the "stale books"). The edge is betting the stale price in the same direction the sharp-hit book moved.

## Handle/Ticket Divergence
A 20+ point gap between Handle % (dollars wagered) and Ticket % (number of bets) on the same side. Indicates large-dollar (sharp) action behind one side regardless of whether the line has moved. A soft RLM signal — requires one additional confirming factor to qualify for a pick.

## Hard RLM (Reverse Line Movement)
70%+ of public tickets on one side AND the line moves in the opposite direction. Confirms sharp money is on the other side. Requires actual line movement — ticket splits alone are insufficient. **Manual-Run-only:** its required [[Public Ticket Data]] is not exposed by the BettingPros API (verified 2026-06-01, ADR 0006) and the splits sites that publish it 403 the routine's datacenter IP, so Hard RLM cannot be a [[Scheduled Run]] Primary Edge — a human on a residential IP can still source it. Scheduled Runs use [[Steam Move]] for the sharp game-line signal instead.

## Prop Trend Confirmation
A +0.5 score bonus applied to Signal A (prop gap) when the player's season average is on the same side as the gap. E.g., pitcher averaging 7.2 Ks with the gap pointing Over at a 6.5 line.

## Pick
A model recommendation to wager on a specific bet, logged by the skill with a Pick Score, edge, line, and units. A Pick represents model output — not a confirmed wager.

## My Bet
A verified wager placed by the bettor on a specific Pick. Has a dollar stake confirmed by the bettor. Not every Pick becomes a My Bet. My Bet stats reflect real money outcomes; Pick stats reflect model performance.

## Pick Score
A 1–10 confidence rating assigned by the skill at the time a pick is logged, reflecting the strength of the edge signal. Higher scores indicate more confirming factors (cross-book gap size, steam book count, RLM %, quant convergence). Not a win probability estimate — it measures signal quality, not outcome certainty.

## Primary Edge
The betting signal that must independently satisfy its Signal Requirement before a pick can be logged.

## Primary Edge Type
The canonical, structured classification of a Primary Edge. The authoritative category used for dashboard filtering, grouping, and statistics. Distinct from the human-readable `primary_edge` text, which is freeform and meant for review context only. Canonical values: `cross_book_gap`, `clv_value`, `steam`, `hard_rlm`, `soft_rlm`, `ats_trend`, `quant_convergence`, `pitching_edge`, `prop_trend`, `matchup_edge`, `plus_money_start`, `underdog_fade`. Legacy picks without a Primary Edge Type fall back to parsing the freeform `primary_edge`.

## Source Evidence
Structured proof attached to a pick candidate showing which source supported the Primary Edge and whether that source was current, parseable, and usable.

## Expert/Model Consensus
Agreement between public-facing pick sites, projection models, or analysts. Supporting evidence only for Scheduled Runs, not a standalone Primary Edge.

## Market-Confirmed Primary Edge
A Primary Edge supported by current market price evidence such as CLV, cross-book gaps, hard RLM, steam, or line value.

## Line-Value Edge
The price currently available at a book beats the de-vigged Pinnacle (`book_id` 2) fair line by a threshold margin (≥2% for game lines, ≥3% for player props), expressed as projected CLV. Its canonical [[Primary Edge Type]] is `clv_value`. A [[Market-Confirmed Primary Edge]] computed purely from cross-book odds — it needs no [[Public Ticket Data]], so unlike [[Hard RLM]] it is sourceable on a [[Scheduled Run]] from the BettingPros `/offers` feed. The documented engine of [[V3-Value]].

## V3-Value
The third pick-generation model, after V1-Trends and V2-Sharp: a pure CLV/+EV engine that logs a [[Pick]] only when an available price beats the de-vigged Pinnacle fair line — a [[Line-Value Edge]]. Optimizes for [[CLV-Positive +EV Candidate]]s and is judged by CLV (CLV+ rate, average CLV) and [[Sharp Score]], never short-run win rate. Its originating Primary Edges are `clv_value` and [[Cross-Book Prop Gap]]; [[Steam Move]] and consensus win probability are confirmation-only.

## Scheduled Run
An unattended betting routine run that may log picks only when structured edge type and source evidence are present. Distinct from a Manual Run, which may capture incomplete candidates for human review.

## Daily Pick Cap
The maximum number of picks a Scheduled Run may log for one date: 7 total, no more than 3 from V1-Trends, no more than 3 from V2-Sharp, and no more than 3 from V3-Value, with no minimum.

## Rejected Candidate
A proposed bet that was not logged because its Primary Edge failed its Signal Requirement.

## Game-Line Bet
A bet whose outcome is determined entirely by the final game score: moneyline, run line / spread, and game total (Over/Under combined runs). Resolvable from the game's final score alone, with no per-player data. Contrast with [[Player Prop]].

## Player Prop
A bet on an individual player's statistical line (e.g. pitcher strikeouts, batter hits, total bases). Resolvable only from that player's boxscore stat line, never from the final score. The documented Primary Edge for this project. A Player Prop carries a stat type, a side (Over/Under, where an `N+` line means "at least N" = Over N−0.5), and a threshold. Auto-resolution must classify a pick as Game-Line Bet vs Player Prop *before* choosing how to resolve it — resolving a Player Prop as if it were a Game-Line Bet produces a silently wrong result.

## Player Prop Source
The per-sport adapter that supplies everything auto-resolution needs to settle a [[Player Prop]] from a finished game, behind one small interface: `find_game` (locate the final game for the bet's date/teams, returning an opaque game handle plus the final score), `fetch_boxscore` (turn that handle into the sport-agnostic per-player boxscore shape the resolver consumes — `teams.<side>.players[*].{person.fullName, stats.<group>.<key>}`), and the sport's `stat_map` (stat-keyword → boxscore group/key). MLB and NBA are the two adapters today: MLB's `fetch_boxscore` is effectively identity (the MLB Stats API already returns the shared shape), NBA's runs the ESPN boxscore adaptation (ADR 0005). The game handle is **opaque** — the resolver never inspects it; whatever a source's `find_game` produces is handed straight back to that same source's `fetch_boxscore`, so the `game_pk`-vs-`game_id` difference never reaches shared code. Adding a sport is registering one more Player Prop Source, not adding a branch to the resolver. The resolver is given its source registry as an argument, so a fake Player Prop Source is the test surface for the whole resolution loop.

## Live Peek
A read-only, client-side grade of a [[Pick]] computed in the dashboard at view time by calling the same public game-data APIs the nightly resolver uses (MLB Stats API, ESPN). Shown when the official result is not yet stored, so the bettor can see how a bet is going or how it went without waiting for settlement. **Never authoritative and never persisted:** it is not written to the pick record, and if it disagrees with the official nightly resolution, the resolution wins. Because it is disposable, a wrong value (postponed game, stat correction, parse miss) costs nothing. Only sports with a [[Player Prop Source]] adapter (MLB, NBA) produce a Live Peek; other sports, and any fetch failure, fall back to an external deep-link instead. A [[Game-Line Bet]] or [[Player Prop]] that is already settled needs no Live Peek — the stored result is shown directly.

## Public Ticket Data
The percentage of bets on each side of a market, used to identify the public side for RLM. **Not available to a [[Scheduled Run]]:** the BettingPros API exposes consensus *pricing* and a `pm_win_pct` probability, but no ticket%/handle% splits (verified 2026-06-01); the sites that publish them 403 the datacenter IP. Obtainable only on a Manual Run from a residential IP, which makes [[Hard RLM]] and [[Soft RLM]] Manual-Run-only signals.

## Line Movement Data
The opening line and current line for a market, used to confirm whether price moved against the public side.

## Freshness Marker
Evidence that source data belongs to the current game, current slate, or today's date.

## Sharp-Hit Book
The sportsbook that moved its prop line first, indicating it accepted a large sharp bet. Typically the book with lower limits and faster adjustment (BetMGM, Caesars). The direction it moved = the sharp side.

## Signal Requirement
The minimum source evidence needed before a betting signal can qualify as pick-worthy.

## Source Health
Whether a betting source is currently usable for research, based on availability, freshness, and parseability.

## Usable Source
A betting source whose current state is safe to use for research.

## Degraded Source
A betting source that can still provide research value but has a freshness, completeness, or parsing concern that should limit trust.

## Dead Source
A betting source that should be skipped because it is unavailable, blocked, stale beyond use, or not parseable.

## Sharp Score
A 0–100 process metric blending Win Rate (40pts), CLV (35pts), and ROI (25pts). A long-run signal, not a current snapshot. Becomes meaningful only once Pinnacle closing lines are recorded consistently — until then the CLV component is neutral by design and the score reflects Win Rate + ROI only.

## Soft RLM
Handle/Ticket divergence of 20+ points without confirmed line movement. Weaker than Hard RLM — requires one additional confirming factor (line movement, prop gap, or quant convergence) before qualifying for a pick. **Manual-Run-only** for the same reason as [[Hard RLM]]: depends on [[Public Ticket Data]] the cloud routine cannot reach.

## Stale Book
The sportsbook that has not yet adjusted its line after the sharp-hit book moved. The target for entering a prop gap bet (typically DraftKings or FanDuel, which accept higher limits and adjust more slowly).

## Steam Move
A rapid line shift of ≥1pt spread or ≥15c ML at 3+ books simultaneously with no public catalyst. 1-2 books = house positioning (noise). 4+ books = mega steam (highest-confidence signal). **Operationalized on a [[Scheduled Run]]** against the BettingPros `/offers` feed (ADR 0006): each selection carries an `opening_line` and every book's current line, so steam = **3+ books currently moved off their opening line in the same direction**. This is V2's Scheduled-Run sharp game-line signal, replacing the Manual-Run-only [[Hard RLM]].

## Relationships

- A **Usable Source** may support or drive a pick.
- A **Degraded Source** may support a pick but must not be the primary reason for a pick.
- A **Dead Source** must be skipped.
- A **Primary Edge** must satisfy its **Signal Requirement** before a pick can be logged.
- A **Rejected Candidate** is recorded separately from picks and must not affect betting statistics.
- A **Signal Requirement** determines whether available source evidence is sufficient for a specific betting signal.
- A **Hard RLM** signal requires usable **Public Ticket Data** and usable **Line Movement Data**.
- **Public Ticket Data** is unobtainable on a **Scheduled Run** (not in the BettingPros API; splits sites 403 the datacenter IP), so **Hard RLM** and **Soft RLM** are Manual-Run-only Primary Edges; a **Scheduled Run** uses **Steam Move** (opening-vs-current across 3+ books) for its sharp game-line signal.
- Usable **Line Movement Data** includes the opening line, current line, and a **Freshness Marker**.
- Usable **Public Ticket Data** includes the ticket percentage, public side, and a **Freshness Marker**.
- If a **Signal Requirement** is not met, that signal cannot qualify as the primary edge, but the pick may still qualify through a different signal whose requirement is met.
- A **CLV-Positive +EV Candidate** may become a **Pick** only after its **Primary Edge** satisfies its **Signal Requirement**.
- A **High-ROI Pick** can only be identified after settlement; it is not a valid pre-game target label.
- A **Scheduled Run** must include **Source Evidence** and a **Primary Edge Type** for every logged **Pick**.
- A **Scheduled Run** must obey the **Daily Pick Cap**.
- A **V3-Value** Scheduled Run logs only **Line-Value Edge** (`clv_value`) or **Cross-Book Prop Gap** picks; **Steam Move** and consensus win probability are confirmation-only, never a standalone Primary Edge.
- **Expert/Model Consensus** may support a **Pick**, but a **Scheduled Run** needs a **Market-Confirmed Primary Edge** before logging.
- ROI should not be treated as mature until **CLV Coverage** reaches at least 90%.
- A **Live Peek** is never authoritative and never persisted; the nightly resolution is the sole writer of a settled outcome. A Peek exists only for a **Pick** with no stored result, and only for sports that have a **Player Prop Source**.
