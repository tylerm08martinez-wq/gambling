# V3-Value Benchmarks Against Low-Hold Exchanges, Not Pinnacle

V3-Value's fair price is now the **Exchange Benchmark**: the median de-vigged two-way price across low-hold exchange venues quoting the same line. It replaces the de-vigged Pinnacle line that ADR 0007 built V3 on. V3 also runs for one week as a deterministic **Observation Scan** that writes candidates outside the ledger, before any V3 pick is logged.

**Context:** a readiness review on 2026-10-24 pulled 135 live `/offers` markets across NBA, NFL and MLB, game lines and props. Pinnacle (book 2) appeared in none of them. `/books` still lists it, but `&book_id=2` returns `[]`, and betting-intel.md shows it missing since about July. ADR 0007's spine is unbuildable, and ADR 0006's "Pinnacle present" is stale.

The fallback ADR 0007 allowed, de-vigged retail consensus, is an exchange detector rather than an edge detector. It flagged 58 prices on the 2026-10-25 board, and all 58 were exchanges or prediction markets. Their hold is about 1%, so they beat a de-vigged retail price by construction. Inverting the comparison gave the expected shape of a real value engine: of 2,620 retail sportsbook prices, 25 beat the low-hold exchange fair price at all and 2 cleared the gate.

The same review found engine defects that would mis-state projected CLV regardless of benchmark. Moneylines were always de-vigged multiplicatively, which inflates longshots and flipped one +809 price from −13.9% to +14.6%. Prices were compared across different line numbers. The prop gate was chosen by searching the market label for the word "prop", so "points" or "PRA" got the 2% game-line gate.

**Considered Options:**
- **Exchange Benchmark (chosen).** Uses data already on the feed, matches the framework the V4 odds research proposed in #99, and the inverted test produced a plausible candidate rate.
- **Retail consensus excluding the candidate book.** Rejected: this is the fallback that flagged only exchanges.
- **Paid feed carrying Pinnacle.** Deferred, not rejected. It restores ADR 0007 as written, but costs money and no current provider has been verified to carry Pinnacle. Revisit if the Exchange Benchmark fails its review.
- **Shelve V3.** Rejected for now: the inverted test is promising enough to measure for a week at no stake.

**Decision:**
- **Benchmark venues:** Novig (60), Kalshi (68), Polymarket (73) and Polymarket US (75), and ProphetX (38). Polymarket and Polymarket US are **one operator**.
- **Quote eligibility:** a venue's quote counts only if it is two-way at the same line number, its two-way hold is at most 3%, and its `updated` time is within 60 minutes of the scan.
- **Minimum:** at least 2 distinct operators must qualify, or the market has no benchmark and is skipped. No fallback to retail consensus.
- **Candidates:** retail sportsbooks only: FanDuel (10), DraftKings (12), Caesars (13), Fanatics (14), BetRivers (18), BetMGM (19), bet365 (24), theScore Bet (33), Fliff (39), Betr (45), Hard Rock (49). Exchanges, DFS and pick'em venues, and the skins SugarHouse (15) and PartyCasino (27), are never candidates.
- **De-vig:** power method for every game line (moneyline, spread, total). Multiplicative for player props, unchanged.
- **Gates:** unchanged at 2% for game lines and 3% for player props. The market kind is passed to the engine explicitly and never inferred from a label.
- **Line numbers:** a candidate is compared only with benchmark quotes at the identical line. A spread of +2.5 is never compared with a fair price at +3.

**Observation week:** V3 runs at 09:00 AZ for seven consecutive days, starting the first morning the scan is live, as plain code with no model call. It writes candidates to `v3-observations.json` and never to `picks.json`. Observations never count toward stats, the dashboard or the Daily Pick Cap. Close capture snapshots each observation's market before start, so every candidate gets a realized CLV against both the exchange close and the retail consensus close.

**Pre-registered review the day after the seventh scan.** V3 is promoted to logging picks under ADR 0009 measurement mode only if all of these hold:
1. The scan completed on at least 6 of the 7 days.
2. Candidates averaged between 0.3 and 5 per day.
3. At least 80% of candidates received a measured close.
4. Mean realized CLV against the exchange close is above zero.

Passing is a sanity check, not evidence of edge: a week yields roughly 5 to 20 candidates, and about 30 are needed to tell a 2% edge from zero. If the review fails, V3 stays off and the paid-feed option is reopened. These conditions are not to be revised while the week is running.

**Consequences:** this supersedes ADR 0007's Pinnacle benchmark and its consensus fallback; ADR 0007's thresholds, sizing and CLV-first evaluation stand. Moneyline closes captured after this change are de-vigged with the power method. Stored CLV values are not rewritten. V4's market blend weights and the alt-lines question stay open in #99 and #103; this ADR settles only V3.
