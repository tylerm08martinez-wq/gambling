# What NFL matchup data is available for free? (V4-Matchup research)

Ticket: #89 · Map: #86 · Researched: 2026-10-13 (home PC, residential IP)

## Bottom line

At $0, nflverse gives V4 strong **in-season** data for pace and pass rate over expected, weather (historical) plus a free forecast API, injuries and practice status, snap share, target and air-yards share, and **pressure**: per-QB and per-defender pressures from PFR, plus rushers and blitzers per play from FTN. The big gap is **coverage type (man/zone, shell) and routes run**. These exist only in the `pbp_participation` file, which nflverse says "does not update during the season" and ships after the Super Bowl. So coverage-vs-receiver can only be modeled from **last season's** tendencies, not current-week data. **Line win rates** (ESPN PRWR/PBWR) have no free structured feed.

## How this was checked

- **Verified live**: on 2026-10-13 I pulled release metadata from the GitHub API for `nflverse/nflverse-data` and downloaded the 2026 (or latest) files from this machine with stdlib Python. The column lists below are the real headers from those files, not copied from docs.
- **Read-only**: claims about cadence, licensing and history depth are quoted from nflreadr docs and were not tested by me.
  - [Data schedule](https://nflreadr.nflverse.com/articles/nflverse_data_schedule.html)
  - [load_ftn_charting](https://nflreadr.nflverse.com/reference/load_ftn_charting.html)
  - [load_participation](https://nflreadr.nflverse.com/reference/load_participation.html)
  - [NGS dictionary](https://nflreadr.nflverse.com/articles/dictionary_nextgen_stats.html)
- **Inferred**: anything else is marked as inferred where it appears.

Base download URL: `https://github.com/nflverse/nflverse-data/releases/download/<tag>/<file>`

### Release freshness observed on 2026-10-13

Week 5 ended with MNF on 2026-10-12.

| Release tag | Latest file | Asset updated (UTC) | Rows / weeks in file | Docs cadence (read-only) |
|---|---|---|---|---|
| `pbp` | `play_by_play_2026` | 2026-10-13 16:56 | 13,842 plays, wk 1–5 | "nightly basis after each game day" |
| `ftn_charting` | `ftn_charting_2026` | 2026-10-13 17:02 | 13,438 plays, wk 1–5 | "every day at 0, 6, 12, 18 UTC during the season"; charted "within 48 hours following each game" |
| `pfr_advstats` | `advstats_week_{def,pass,rec,rush}_2026` | 2026-10-13 23:03 | wk 1–4 full; wk 5 had only 31 def rows (~1 game) | 4x daily during season (lags the games by about 1–2 days in practice) |
| `nextgen_stats` | `ngs_{passing,receiving,rushing}` (all seasons in one file) | 2026-10-13 14:43 | wk 0–5 for 2026 | "every night (3–5 am ET) during the season" |
| `snap_counts` | `snap_counts_2026` | 2026-10-13 11:01 | wk 1–5 | 4x daily during season |
| `injuries` | `injuries_2026` | 2026-10-13 14:57 | wk 1–5 | "every day at 7AM UTC throughout the season" |
| `schedules` | `games` | 2026-10-14 00:06 | 1999–2026 incl. future weeks | "every 5 minutes during the season" |
| `depth_charts`, `weekly_rosters` | `*_2026` | 2026-10-13 ~15:00 | current | daily 7AM UTC |
| `pbp_participation` | **`pbp_participation_2025`** (no 2026 file) | 2026-02-10 | 45,184 plays, 2025 | "It does not update during the season!" |

## Edge families

### 1. Coverage (man/zone, shell) vs receiver

| | |
|---|---|
| Field(s) | `defense_man_zone_type` (`ZONE_COVERAGE`, `MAN_COVERAGE`), `defense_coverage_type` (`COVER_0/1/2/3/4/6`, `2_MAN`, ...), `route` (e.g. `QUICK OUT`, `HITCH/CURL`, `GO`, `SCREEN`, `IN/DIG`) |
| Source | `pbp_participation_<season>` (FTN from 2023 on, NGS before that) |
| Verified columns (2025 file) | `nflverse_game_id, old_game_id, play_id, possession_team, offense_formation, offense_personnel, defenders_in_box, defense_personnel, number_of_pass_rushers, players_on_play, offense_players, defense_players, n_offense, n_defense, ngs_air_yards, time_to_throw, was_pressure, route, defense_man_zone_type, defense_coverage_type, offense_names, defense_names, offense_positions, defense_positions, offense_numbers, defense_numbers` |
| Fill rate (2025) | Coverage fields 49% non-null (about all dropbacks): zone 15,020, man 7,035. `route` 42% non-null, and it records only the **targeted** receiver's route |
| Update timing | **Season-end only.** 2023+ data "is provided after all post-season games are completed". No 2026 file exists yet (verified) |
| History | 2016+ (pre-2023 from NGS; 2023+ from FTN) |
| License | CC-BY-SA 4.0. Attribution "FTN Data via nflverse" (2023+) or "NFL NextGenStats via nflverse" (≤2022) |
| Gaps | No current-season coverage. `route` is the targeted receiver's only, so there are no routes-run denominators and no per-defender coverage assignment. FTN's in-season `ftn_charting` has **no** coverage column (verified header below) |

**Modeling stance**: a defense's 2025 man/zone and shell rates, and receivers' 2025 splits vs man/zone, can be used as priors only. Coaching or coordinator changes break them. The ticket's hoped-for in-season coverage signal is not available at $0.

### 2. Pass-rush pressure vs QB

| | |
|---|---|
| Field(s), team and player | PFR weekly advanced stats. **QB side** (`advstats_week_pass`): `times_pressured, times_pressured_pct, times_blitzed, times_hurried, times_hit, times_sacked, passing_bad_throws, passing_drops`. **Defender side** (`advstats_week_def`): `def_pressures, def_times_blitzed, def_times_hurried, def_times_hitqb, def_sacks`, plus coverage-allowed stats `def_targets, def_completions_allowed, def_yards_allowed, def_passer_rating_allowed, def_adot` |
| Per-play, in-season | `ftn_charting`: `n_pass_rushers, n_blitzers, is_qb_out_of_pocket, is_qb_fault_sack, is_throw_away, is_interception_worthy`. pbp: `qb_hit, sack, qb_scramble` |
| Time to throw | NGS passing `avg_time_to_throw` (weekly; QBs with roughly 15+ attempts, inferred from the 2026 minimum) |
| Update timing | PFR 4x daily, but week 5 was only partly in by Tuesday evening (verified). FTN ≤48h. NGS nightly |
| History | PFR advstats 2018+ (read-only: nflreadr `load_pfr_advstats`). FTN 2022+ (verified file list). NGS 2016+ (verified) |
| License | PFR is scraped by nflverse with no explicit license. FTN is CC-BY-SA 4.0 |
| Gaps | `was_pressure` per play is participation-only, so it arrives at season end. PFR pressure is charted by PFR, with no tracking-based definition |

**Usable in-season**: offense pressure-allowed % vs defense pressure % (PFR) for QB yards and INT props and sack props. Weekly sample sizes are small, so shrink toward the prior.

### 3. Offensive/defensive line win rates

| | |
|---|---|
| Field(s) | None in nflverse. ESPN's Pass Rush / Pass Block / Run Stop / Run Block Win Rate (NGS tracking, "beat block within 2.5s") appear only in **ESPN articles** ([2025 leaderboard example](https://africa.espn.com/nfl/story/_/id/46138675/2025-nfl-win-rates-top-teams-players-rankings-pass-run-block)). There is no API or file, and refreshes are irregular |
| Proxy at $0 | PFR pressure allowed/generated (family 2). pbp `run_gap`/`run_location` with `yards_gained` and `epa`, for rush success by gap. NGS rushing `percent_attempts_gte_eight_defenders`, `rush_yards_over_expected`. FTN `n_defense_box` |
| Gaps | True win rates aren't available. Scraping ESPN articles is fragile and probably not worth it |

### 4. Route participation / target share

| | |
|---|---|
| Target share, air-yards share | pbp `receiver_player_id`, `air_yards`, `pass_attempt` (aggregate it yourself), and `stats_player_regpost_2026` (nightly). NGS receiving `targets, percent_share_of_intended_air_yards, avg_separation, avg_cushion, avg_intended_air_yards, avg_yac_above_expectation` (weekly; receivers with roughly 5+ targets, inferred from the 2026 minimum of 5.0) |
| Snap share | `snap_counts_2026`: `offense_snaps, offense_pct, defense_snaps, defense_pct, st_snaps, st_pct` with `player, position, team, opponent, week`. Updated 4x daily, wk 5 present (verified). History 2012+ (verified asset list) |
| Route participation (routes run / dropbacks) | **Not free in-season.** Participation `offense_players` per play would allow it, but only after the season ends. Proxy: `offense_pct` × team dropback rate |
| Gaps | No routes-run denominator, so true TPRR or YPRR isn't computable in-season. Snap share overstates route share for TEs and RBs |

### 5. Pace / pass rate over expected

| | |
|---|---|
| Field(s) | pbp `xpass`, `pass_oe` (99.6% non-null on 2026 run and pass plays, verified), `no_huddle`, `shotgun`, `qb_dropback`, `game_seconds_remaining`, `drive_play_count`, `drive_time_of_possession`, `score_differential`, `wp`, `vegas_wp`, `epa`, `cpoe`. FTN `is_no_huddle, is_motion, is_play_action, is_rpo, is_screen_pass` |
| Update timing | Nightly after each game day. 2026 wk 1–5 present on 2026-10-13 (verified) |
| History | pbp 1999+. `xpass`/`pass_oe` are from the nflfastR model (era coverage read-only; the 2026 fill is verified) |
| Gaps | None material. This is the strongest free family. Seconds per play has to be derived from game clock deltas |

### 6. Weather

| | |
|---|---|
| Historical | pbp `roof, surface, temp, wind, weather` (free-text, e.g. "Cloudy Temp: 77° F, Humidity: 79%, Wind: W 4 mph"). In 2026, numeric `temp`/`wind` are filled for 45 of 79 games: outdoor games only, so dome and closed-roof games are null by design (verified) |
| Schedule file | `games`: `roof, surface, temp, wind`, plus `spread_line, total_line, away_rest, home_rest, referee, div_game`. **`temp`/`wind` were blank for every 2026 game I checked (wk 5–6)**, so don't use the schedule file for weather |
| Forecast (pre-game) | **NWS `api.weather.gov`**: free, no key, needs a User-Agent header. `/points/{lat},{lon}` returned a `forecastHourly` URL live from this PC. **Open-Meteo**: free and keyless, but returned "service is overloaded" on my one test (transient, read-only claim) |
| Gaps | Stadium coordinates aren't in `games` (only `stadium_id`/`stadium`), so V4 needs a one-time static lat/lon table (~30 rows). Historical forecasts (what was predicted at bet time) aren't stored. Log your own |

### 7. Injuries / inactives

| | |
|---|---|
| Field(s) | `injuries_2026`: `season, season_type, game_type, team, week, gsis_id, position, full_name, report_primary_injury, report_secondary_injury, report_status (Out/Questionable/Doubtful), practice_primary_injury, practice_secondary_injury, practice_status (DNP/Limited/Full)` |
| Supporting | `depth_charts_2026`, `roster_weekly_2026` (status), `players` |
| Update timing | Daily 7AM UTC. Wk 5 present (verified). So the final Friday report usually lands the **next morning**, and Sunday inactives (~90 min before kickoff) are **not** covered in time |
| History | 2009+ (verified asset list) |
| Gaps | No game-day inactives feed. Same-day news (late scratches, snap limits) has to come from the LLM news step that the map already assigns to it |

## In-season `ftn_charting` header (verified)

The 2026 file has these columns:

```text
ftn_game_id, nflverse_game_id, season, week, ftn_play_id, nflverse_play_id, starting_hash, qb_location,
n_offense_backfield, n_defense_box, is_no_huddle, is_motion, is_play_action, is_screen_pass, is_rpo,
is_trick_play, is_qb_out_of_pocket, is_interception_worthy, is_throw_away, read_thrown, is_catchable_ball,
is_contested_ball, is_created_reception, is_drop, is_qb_sneak, n_blitzers, n_pass_rushers, is_qb_fault_sack,
date_pulled
```

There's no coverage, route or personnel column. FTN license (read-only, nflreadr docs): "released under the CC-BY-SA 4.0 Creative Commons license", with attribution to "FTN Data via nflverse".

**What CC-BY-SA means for us**: our use is internal modeling, and the dashboard reads only picks. If we ever publish FTN-derived tables (e.g., commit derived CSVs to this **public** repo), they need attribution and the same license. Safest is to gitignore cached raw and derived NFL data.

## Tooling

- **`nfl_data_py` is deprecated.** The repo was archived 2025-09-25: "deprecated in favour of nflreadpy… No further … maintenance".
- **`nflreadpy`** is the replacement. It has `load_pbp`, `load_ftn_charting`, `load_participation`, `load_nextgen_stats`, `load_snap_counts`, `load_injuries`, `load_depth_charts`, `load_schedules`, `load_player_stats` and more. It is Polars-based (`.to_pandas()` available), its cache is configurable via `NFLREADPY_CACHE*`, and it is labeled "Lifecycle: experimental". The README says "Most of the first version was written by Claude… use at your own risk."
- **Alternative**: hit the release URLs directly (CSV/parquet). This machine's `python3` has no pandas or pyarrow, so either install deps for V4 or use stdlib csv on the `.csv.gz` assets (that's how this research ran).
- **No residential-IP issue observed**: everything is GitHub release assets.

## Recommendation: NFL edge families V4 can model at $0

| Family | $0 verdict |
|---|---|
| Pace / PROE | **Yes**: in-season, nightly, rich history |
| Target / air-yards share + snap share (role/volume) | **Yes**: in-season. Route participation only via a snap% proxy |
| Injury redistribution | **Yes**: practice and report status daily. Late inactives come via the LLM news step |
| Pressure vs QB | **Yes, coarse**: PFR team/player pressures plus FTN rushers and blitzers. Partial lag of 1–2 days, so it fits a Wednesday-to-Sunday cycle |
| Weather | **Yes**: NWS forecast plus pbp history. Needs a static stadium lat/lon table |
| Coverage man/zone/shell vs receiver | **Prior-only**: last season's participation file. No in-season updates. Defer or treat as a weak prior |
| Line win rates | **No**: no free structured source. Use pressure and rush-gap proxies |

**Recommendation (strong, ~80% confidence):** build the V4 NFL projection on **volume × efficiency**. Volume comes from pace, PROE, and target and snap share, adjusted for injuries. Opponent adjustments come from **pressure** and **position-level defense allowed** (pbp EPA and yards allowed by target position, plus PFR coverage-allowed), with a weather haircut on passing and kicking. Leave **coverage-scheme matchups and line win rates out of v1**. What would change my mind: a free in-season coverage source turning up (e.g., nflverse resuming in-season participation), or the 2025-prior coverage splits showing a measurable lift in backtest despite going stale.

Data timing (moderate, ~70% confidence): PFR lags 1–2 days and FTN up to 48h, so NFL V4 runs should key off the **Wednesday–Saturday** data state for Sunday games, not Monday night.
