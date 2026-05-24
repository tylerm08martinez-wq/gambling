# Betting Domain Glossary

## CLV (Closing Line Value)
The difference between your entry price and the closing line, expressed as implied probability. Positive CLV means you got a better price than the market settled at = good process. Benchmark: Pinnacle's de-vigged closing line. Consistently beating Pinnacle by 2%+ is the documented definition of a profitable edge.

## Cross-Book Prop Gap
A discrepancy of 0.5+ units on the same player prop across DK / FanDuel / BetMGM. Indicates sharp money already hit one book (the "sharp-hit book") and the other books haven't adjusted yet (the "stale books"). The edge is betting the stale price in the same direction the sharp-hit book moved.

## Handle/Ticket Divergence
A 20+ point gap between Handle % (dollars wagered) and Ticket % (number of bets) on the same side. Indicates large-dollar (sharp) action behind one side regardless of whether the line has moved. A soft RLM signal — requires one additional confirming factor to qualify for a pick.

## Hard RLM (Reverse Line Movement)
70%+ of public tickets on one side AND the line moves in the opposite direction. Confirms sharp money is on the other side. Requires actual line movement — ticket splits alone are insufficient.

## Prop Trend Confirmation
A +0.5 score bonus applied to Signal A (prop gap) when the player's season average is on the same side as the gap. E.g., pitcher averaging 7.2 Ks with the gap pointing Over at a 6.5 line.

## Primary Edge
The betting signal that must independently satisfy its Signal Requirement before a pick can be logged.

## Rejected Candidate
A proposed bet that was not logged because its Primary Edge failed its Signal Requirement.

## Public Ticket Data
The percentage of bets on each side of a market, used to identify the public side for RLM.

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

## Soft RLM
Handle/Ticket divergence of 20+ points without confirmed line movement. Weaker than Hard RLM — requires one additional confirming factor (line movement, prop gap, or quant convergence) before qualifying for a pick.

## Stale Book
The sportsbook that has not yet adjusted its line after the sharp-hit book moved. The target for entering a prop gap bet (typically DraftKings or FanDuel, which accept higher limits and adjust more slowly).

## Steam Move
A rapid line shift of ≥1pt spread or ≥15c ML at 3+ books simultaneously with no public catalyst. 1-2 books = house positioning (noise). 4+ books = mega steam (highest-confidence signal).

## Relationships

- A **Usable Source** may support or drive a pick.
- A **Degraded Source** may support a pick but must not be the primary reason for a pick.
- A **Dead Source** must be skipped.
- A **Primary Edge** must satisfy its **Signal Requirement** before a pick can be logged.
- A **Rejected Candidate** is recorded separately from picks and must not affect betting statistics.
- A **Signal Requirement** determines whether available source evidence is sufficient for a specific betting signal.
- A **Hard RLM** signal requires usable **Public Ticket Data** and usable **Line Movement Data**.
- Usable **Line Movement Data** includes the opening line, current line, and a **Freshness Marker**.
- Usable **Public Ticket Data** includes the ticket percentage, public side, and a **Freshness Marker**.
- If a **Signal Requirement** is not met, that signal cannot qualify as the primary edge, but the pick may still qualify through a different signal whose requirement is met.
