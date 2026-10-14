# Can we test NFL projections for free before going live? (V4-Matchup research)

Ticket: #98 · Map: #86 · Sibling: #89 ([v4-nfl-free-data](https://github.com/tylerm08martinez-wq/gambling/blob/main/docs/research/v4-nfl-free-data.md)) · Researched: 2026-10-13 (home PC, residential IP)

## Bottom line

**Yes, and the gate can be stronger than the NBA's.** The 2025 NFL season can be backtested for $0 against both actual box scores and real sportsbook lines.

1. **Actuals and point-in-time inputs.** nflverse `stats_player_week_2025` has every weekly stat line V4 needs. Rebuilding pre-week inputs from weeks `< w` gives no look-ahead on stats. The one soft spot is injuries: nflverse keeps only **one row per player-week**, with the final game status and practice status, and has no report date. So it's usable as "the Friday status", but not as a Wednesday-to-Friday progression.
2. **Historical prop lines: free source found.** The BettingPros `/v3` API, which this repo already uses (ADR 0006), returns the **2025 (and 2024) NFL player props**. Each prop has a consensus line, the best line per side, the **opening line**, each book's **last pre-kickoff line** across about 17 books, and the **actual result**. The Odds API historical props are **paid-only**. No free GitHub or Kaggle prop-line dataset turned up. **There's no Pinnacle on NFL props in the sample checked**, so a de-vigged sharp close isn't available. The market benchmark is the multi-book consensus close.
3. **Baseline.** On the same 2025 player-weeks (weeks 4–18), the **consensus closing line already beats the season-to-date average** on all four markets tested (by 2–7 MAE points of yards). So "beat a season average" is a **weak gate** for NFL. The real bar is **beating the consensus line's MAE, and over/under side accuracy vs the closing line**.

## How this was checked

- **Verified live (2026-10-13, this PC, stdlib `python3 -I`, no pandas):** I downloaded nflverse release assets (`stats_player_week_2025`, `injuries_2025`, `snap_counts_2025`, `schedules/games`) and read the real headers and row counts. I called the BettingPros `/v3/events`, `/v3/props`, `/v3/offers` and `/v3/markets` for NFL 2025 and 2024, then ran the baseline comparisons below. All data was kept in `%TEMP%`. **Nothing downloaded is committed.**
- **Read-only (docs, not tested):** nflreadr dictionaries, The Odds API docs, OddsPapi blog claims, and web search for datasets. Each is marked where it's used.
- **Inferred:** marked inline.

## (a) Reconstructing 2025 weekly stat lines with point-in-time inputs

### Actuals: `stats_player/stats_player_week_2025` (verified)

- URL: `https://github.com/nflverse/nflverse-data/releases/download/stats_player/stats_player_week_2025.csv.gz` (also `.parquet`). Asset last updated 2026-08-13.
- 19,422 rows. Weeks 1–18 REG (about 900–1,100 rows each), plus 19–22 POST. Keyed by `player_id` (GSIS), `season`, `week`, `season_type`, `game_id`, `team`, `opponent_team`.
- Columns for prop markets: `completions, attempts, passing_yards, passing_tds, passing_interceptions, carries, rushing_yards, rushing_tds, receptions, targets, receiving_yards, receiving_tds`. There are volume and share fields for inputs too: `target_share, air_yards_share, wopr, receiving_air_yards, passing_air_yards, passing_epa, rushing_epa, receiving_epa, passing_cpoe`.
- **Note: `release` tag `player_stats` also exists** (older naming). Use `stats_player`, which is current.
- **Survivorship caveat (verified):** a player only gets a row if he recorded a stat. 222 of 2,215 WR/TE games with ≥50% offensive snaps had no stats row when matched by name and week. That gap is partly name mismatches and partly zero-stat games. A backtest must define its population **before** the game: injury status not Out, plus pre-week snap share. It must not use "has a stats row this week", which leaks whether he played. Missing rows should be read as 0 when the player was active per `snap_counts`.

### Point-in-time inputs

| Input | File (release tag) | Dating | Point-in-time verdict |
|---|---|---|---|
| Rolling volume, efficiency, shares | `stats_player_week_2025`, `pbp/play_by_play_2025` | `week`, `game_id`; schedule `gameday` for dates | **Clean**: use only `week < w` |
| Snap share | `snap_counts/snap_counts_2025` (`offense_snaps, offense_pct`, plus `game_id`, `pfr_player_id`) | `week`, `game_id` | **Clean** for `week < w`. Keyed on PFR id, so join via `players` id map, not names |
| Injury and practice status | `injuries/injuries_2025` | **`week` only** | **Partial.** Columns verified: `season, season_type, game_type, team, week, gsis_id, position, full_name, first_name, last_name, report_primary_injury, report_secondary_injury, report_status, practice_primary_injury, practice_secondary_injury, practice_status`. The nflreadr dictionary documents a `date_modified` field (read-only), but **it isn't in the 2025 file** (verified). There's one row per player-week, so the Wed/Thu/Fri practice progression is collapsed into a single status. `report_status` (Out 1,382 / Questionable 1,283 / Doubtful 120) is the **final** pre-game designation, normally published on Friday, so it's legitimately pre-game. Of 1,217 REG Questionable rows, 49% have a stats row that week. That's the uncertainty a model faces, so no leak. Out had **0** stats rows, which is consistent |
| Game environment | `schedules/games` (`gameday, gametime, spread_line, total_line, away_moneyline, home_moneyline, over_odds, under_odds, roof, temp, wind, away_rest, home_rest`) | `gameday` | `spread_line`/`total_line` are filled for all 285 2025 games (verified). The nfldata `DATASETS.md` says only "The spread line for the game" and doesn't say whether it's opening or closing (read-only). **Treat it as approximately closing**, so it's **look-ahead-ish** for a Wednesday projection. Fine as a team-total input for a "Sunday morning" backtest, not for an early-week one |
| Weather | pbp `temp, wind` (actual) | game | **Look-ahead**: these are observed conditions, not forecasts. Historical forecasts aren't stored (#89). Use them only with a "perfect forecast" caveat, or skip the weather haircut in the backtest |
| Depth charts / rosters | `depth_charts_2025`, `weekly_rosters` | weekly snapshot | Not checked here (inferred to be weekly snapshots; #89 lists cadence) |

**Simplest clean backtest timestamp: "Sunday morning, week w".** Inputs are stats, snaps and pbp from weeks `< w`, the final injury report for week `w`, and the schedule spread and total. That matches when V4's 9am run would fire on game day.

## (b) Free historical NFL player-prop lines / closing lines

| Source | Props? | 2025 coverage | Free? | Verdict |
|---|---|---|---|---|
| **BettingPros `/v3/props` + `/v3/offers`** (public `x-api-key` already in `bettingpros.py`) | **Yes** | **Verified**: `season=2025&week=N` (and `date=YYYY-MM-DD`) return scored props. Receiving-yards props per week: wk1 266, wk5 176, wk9 181, wk18 139. **2024 wk5: 155** | Free (undocumented API) | **Use** |
| The Odds API historical | Yes (from 2023-05-03) | Yes | **No**: "Historical data is only available on paid usage plans" ([docs](https://the-odds-api.com/historical-odds-data/)); 10 credits per region per market per event | Paid only |
| OddsPapi `/historical-odds` | Claims props history on the free tier ([blog](https://oddspapi.io/blog/?p=3871)) | Their own example starts collection 2026-06-02 for the 2026 season. **2025 depth unknown** | Free tier 250 or 1,000 req/mo (their posts conflict) | Unverified. Not needed |
| Kaggle "NFL scores and betting data" (tobycrabtree) | No, game lines only | to 2024 | CC BY-NC-SA | Not props |
| GitHub `mackman08/nfl-prop-data` | Current-week props CSV only (`odds/nfl_player_props_latest.csv`) | No 2025 history. Repo created 2026-09-21, **no license** | n/a | Not usable |
| SportsDataIO / FantasyData | Yes (props from 2020) | Yes | Paid | Out of budget |

### What BettingPros gives per prop (verified on 2025 wk5, event 21607 LV @ IND, market 105)

- `/v3/props?sport=NFL&season=2025&week=5&market_id=105` returns, per player:
  - `over/under.line`, `odds` and `book`: the best price
  - `consensus_line`, `consensus_odds`
  - `projection.value`: BettingPros' own projection
  - `scoring.actual`, `is_push`
- `/v3/offers?sport=NFL&market_id=105&event_id=21607` returns:
  - `opening_line {line, cost, book_id, created}`, e.g. created `2025-10-05 15:13:32`
  - each book's main line with an `updated` timestamp. **All 388 lines carried `updated` 2025-10-05 17:05 UTC**, minutes after the 13:00 ET (17:00 UTC) kickoff. So the stored line is the **last pre-kickoff snapshot, a closing line** (inferred from the timestamp, one game checked). Line history between open and close is **not** exposed.
- Books present: 0 (consensus), 10 FanDuel, 12 DraftKings, 13 Caesars, 14 Fanatics, 18 BetRivers, 19 BetMGM, 33 theScore, 36 Underdog, 37 PrizePicks, 38 ProphetX, 49 Hard Rock, 60 Novig, plus ids 15/27/39/63. **No Pinnacle (id 2)** on this NFL prop.
- Market ids (verified via `/v3/markets?sport=NFL`): 100 pass completions, 101 INTs, 102 pass TDs, 103 pass yards, 104 receptions, 105 receiving yards, 106 rush attempts, 107 rush yards, 333 pass attempts.
- **Licensing:** this is an undocumented internal API, and the site is "© 2018–2026 BettingPros.com. All rights reserved." I couldn't retrieve the full terms text (read-only gap). **Treat it as internal research only.** Fetch at backtest time into an ignored cache, and **never commit pulled lines to this public repo.** This is the same stance as ADR 0006's use of the API.
- **Caveat on `projection.value`:** I can't verify it was frozen pre-game (it may be recomputed). Don't use it as a baseline without more evidence.

## (c) Baseline to beat, and metric

### Season-to-date vs last-N (verified; nflverse only, 2025 REG, player-weeks with ≥3 prior games and a prop-relevant prior average)

| Market | n | Season avg | Last 3 | Last 5 | Season median | EWMA 0.85 |
|---|---|---|---|---|---|---|
| receiving_yards | 1,167 | 27.10 | 28.92 | 27.64 | **26.64** | 27.13 |
| receptions | 1,185 | 1.84 | 1.94 | 1.88 | **1.81** | 1.84 |
| rushing_yards | 605 | **26.30** | 28.43 | 26.68 | 26.54 | 26.32 |
| carries | 497 | 4.30 | 4.31 | 4.26 | 4.44 | **4.21** |
| passing_yards | 387 | **64.38** | 69.40 | 67.12 | 64.86 | 64.58 |
| attempts | 404 | 7.99 | 7.95 | 8.05 | 7.99 | **7.82** |

(Values are MAE.) The season average is about as good as any naive average. Last-3 is consistently worst. The season average is biased **high** on yards (actual minus average is −3.9 receiving yards and −6.4 passing yards). That's partly selection: players filtered on a high prior average regress toward the mean.

### Market line vs season average on the same player-weeks (verified; BettingPros-listed props, 2025 weeks 4–18, ≥3 prior games)

| Market | n | MAE consensus close | MAE season avg | Over rate vs close | Side acc. of season avg vs close |
|---|---|---|---|---|---|
| receiving_yards | 2,736 | **18.69** | 20.39 | 47.4% | 47.7% |
| rushing_yards | 1,192 | **19.10** | 20.11 | 47.6% | 51.7% |
| passing_yards | 405 | **55.53** | 62.81 | 51.6% | 43.7% |
| receptions | 2,516 | **1.46** | 1.53 | 46.8% | 51.6% |

- The closing consensus beats the season average on every market. A model that only beats the season average can still lose to the market.
- Unders hit about 52–53% vs the close on receiving and rushing yards and receptions. That's consistent with the known "public overs" tilt in AGENTS.md (one season, not tested for significance).
- Name-matching nflverse to BettingPros by normalized display name dropped about 4–5% (the skipped counts include players with <3 prior games). A real backtest should map ids (BettingPros uses FantasyPros ids; inferred, not verified).

### Recommended gate

- **Metric 1 (point accuracy):** MAE per market vs actuals, on a population fixed pre-game.
- **Metric 2 (what matters for betting):** for player-weeks with a BettingPros line, the **side hit rate vs the consensus closing line at the actual odds**, giving simulated flat-1u ROI. Report it only where the model's edge clears a threshold, at the price that was actually available. This is the NFL analogue of CLV under measurement mode.
- **Bar:** the model must beat the **season-to-date average** on MAE (the map's existing gate), **and** match or beat the **consensus-close MAE**, **and** show a simulated side hit rate above about 52.4% (−110 break-even) on fired picks. The last two are the real test.

## Recommendation

**Strong, ~80% confidence:** run the NFL V4 gate as a **2025-season walk-forward backtest at a "Sunday morning" timestamp**:

- Inputs: nflverse stats, snaps and pbp from weeks `< w`, plus the week-`w` final injury status.
- Scored against nflverse actuals and against **BettingPros consensus closing lines**, fetched at run time into a gitignored cache.
- Go live only if the model beats both the season average and the closing-line MAE, and its fired picks clear about 52.4% vs the close.

What would change my mind:

- BettingPros' `updated` timestamps turning out to be post-game (it would then stop being a close). Spot-check 3–5 more games before relying on it.
- BettingPros closing the historical props endpoint.

**Moderate, ~65% confidence:** skip the weather haircut and the early-week (Wednesday) timestamp in the backtest. Historical forecasts and dated practice reports don't exist for free, so those components can only be validated live under measurement mode.

## Effects on other tickets

- **#86 map, "Gate before going live":** for NFL, upgrade from "beat a season-average baseline" to "beat the season average **and** the consensus closing line". The same BettingPros check is worth running for NBA (inferred, not tested).
- **Spread/total projections ticket:** nflverse `games` has `spread_line`/`total_line` and moneylines for all 2025 games, so the team-level model half of the 70/30 blend can be backtested for free too (open vs close unspecified).
- **Resolution/CLV ticket:** BettingPros `/v3/offers` exposes opening and last pre-kick lines per book for NFL props. It's a candidate closing-line source for V4 NFL prop CLV (ADR 0010). Pinnacle doesn't appear on NFL props, so de-vigged CLV needs a different benchmark: consensus or best-of-books.
