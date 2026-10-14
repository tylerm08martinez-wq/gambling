# Free NBA data for V4-Matchup's first edge families

Research ticket: #87. Map: #86. Researched 2026-10-13 from the home PC (residential IP).

**Question:** for V4-Matchup's first NBA edge families (injury redistribution of minutes and usage, opponent defense by position and play type, pace, rest/back-to-back/travel, blowout risk), which free sources cover each one? For each: endpoint, granularity, update timing, rate limits, residential vs datacenter reachability, and history depth. All of 2025-26 is needed for the accuracy gate. Also note what exists for primary-defender matchups and referees.

**Short answer:** `stats.nba.com` (the backend `nba_api` wraps) plus `cdn.nba.com` covers every first edge family, with full 2025-26 history, and answered from this PC with no auth. The official NBA injury-report PDFs supply point-in-time injury history, and ESPN's injuries JSON supplies the live feed. There's one catch: **Synergy play-type defense and season matchup tables are season-to-date aggregates only and ignore date filters**, so backtesting with them on 2025-26 would leak future data.

## How claims were checked

- **[live]**: I requested the endpoint from this machine on 2026-10-13 (Python `urllib`, browser `User-Agent` and `Referer: https://www.nba.com/`, no `x-nba-stats-*` headers, no API key) and inspected the JSON.
- **[read]**: from a primary written source (cited inline). I didn't test it.
- **[inferred]**: my reasoning, not stated by any source.

Reference game for the per-game probes: `0022501194` (MEM @ HOU, 2026-04-12, the last 2025-26 regular-season game day).

## Edge family to source map

`S` = `https://stats.nba.com/stats`. All `S` endpoints take `LeagueID=00&Season=2025-26&SeasonType=Regular%20Season` unless noted. The `nba_api` class name is in brackets.

| Edge family | Source / endpoint | Granularity | Point-in-time? | Update timing | History depth | Rate limit | Residential / datacenter |
|---|---|---|---|---|---|---|---|
| **Injury: who is out (live)** | ESPN `site.api.espn.com/apis/site/v2/sports/basketball/nba/injuries` | Per player: `status` (Out / Day-To-Day…), `date`, `details.returnDate`, fantasy GTD flag, comments | Current snapshot only | Updated through the day; preseason 2026-27 entries dated 2026-10-12 **[live]** | **None.** Current list only; the core-API per-athlete injury history returned 404 **[live]** | None documented | 200 residential **[live]**. ESPN's site API already works from the cloud per ADR 0005/0006 **[read]** |
| **Injury: official report (live + history)** | `ak-static.cms.nba.com/referee/injury/Injury-Report_YYYY-MM-DD_HH[_MM]AM/PM.pdf` | Per player per game: status (Out/Doubtful/Questionable/Probable) + reason | **Yes**, one file per publish time | Multiple publishes per day. **Filename format changed mid-season:** `_05PM` / `_01PM` style through at least 2025-12-15; `_05_00PM` / `_05_15PM` / `_11_30AM` (15-minute slots) from at least 2026-01-15 **[live]** | All 2025-26 game days probed returned 200 (2025-10-21 through 2026-04-12); a 2022-01-15 file also exists **[live]** | None observed | 200 residential **[live]**. Wrong-format URLs return **403, not 404**, so "403" means "no such file" and isn't a block |
| **Injury: who actually played (backtest truth)** | `S/leaguegamelog?PlayerOrTeam=P` [LeagueGameLog]; `cdn.nba.com/static/json/liveData/boxscore/boxscore_{gameId}.json` | Player-game rows (MIN, all box stats); CDN box has `status`, `played`, `starter`, `position` per player | Yes (per game) | Within hours after final; CDN live in-game | 26,651 player-game rows covering 2025-10-21 to 2026-04-12 **[live]** | See stats.nba.com row below | 200 residential **[live]** |
| **Usage redistribution** | `S/leaguedashplayerstats?MeasureType=Usage` [LeagueDashPlayerStats]; per game `S/boxscoreadvancedv3?GameID=` [BoxScoreAdvancedV3] (`usagePercentage`, `possessions`, `pace`); `S/playbyplayv3` [PlayByPlayV3] for on/off; pbpstats API for lineup/WOWY | Season or date-range dashboard; per player-game advanced | **Yes.** Dashboards honour `DateFrom`/`DateTo` (verified: `DateTo=12/01/2025` returned ATL GP=22, not 82) **[live]** | Post-game | Full 2025-26 **[live]** | As below | 200 residential **[live]** |
| **Opponent defense by position** | Build from `leaguegamelog` player rows × positions from `S/playerindex` [PlayerIndex] (`G`, `F`, `C`, `G-F`, `F-C`…). Alternatives: `S/leaguedashptdefend` [LeagueDashPtDefend] (defender FG% allowed vs expected, has `PLAYER_POSITION`); `leaguedashteamstats?MeasureType=Opponent&PlayerPosition=` | Player-game → aggregate any window | **Yes** if built from game logs **[inferred]**; ptdefend accepts `DateFrom`/`DateTo` params **[live: accepted]** | Post-game | Full 2025-26 | As below | 200 residential **[live]** |
| **Opponent defense by play type** | `S/synergyplaytypes?PlayerOrTeam=T&TypeGrouping=defensive&PlayType=…&SeasonYear=2025-26` [SynergyPlayTypes] | Team (or player) × play type (Isolation, PRBallHandler, PRRollman, Postup, Spotup, Handoff, Cut, OffScreen, Transition, Putbacks, Misc): POSS, PPP, percentile | **No.** `DateTo` silently ignored (GP stays 80) **[live]** | Season-to-date; refreshes daily during the season **[inferred]** | 2025-26 and 2024-25 both return 30 teams **[live]** | As below | 200 residential **[live]** |
| **Pace** | `S/leaguedashteamstats?MeasureType=Advanced` [LeagueDashTeamStats] (`PACE`, `E_PACE`, `OFF/DEF_RATING`); per game `boxscoreadvancedv3`; pbpstats `api.pbpstats.com/get-games/nba` (Home/Away possessions per game) | Team season/date-range; team-game | **Yes** (`DateTo`) **[live]** | Post-game | Full 2025-26 (2,460 team-games) **[live]** | stats as below; pbpstats one call took 10.7 s | 200 residential **[live]** |
| **Rest / back-to-back / travel** | `S/scheduleleaguev2` [ScheduleLeagueV2] or `cdn.nba.com/static/json/staticData/scheduleLeagueV2.json` | Every game: `gameId`, UTC/local tip times, arena, city/state | Yes (schedule is fixed ahead of time) | 2026-27 schedule already published (CDN meta 2026-10-13) **[live]** | 2025-26 via `Season=2025-26`, 2026-27 via CDN **[live]** | n/a | 200 residential **[live]**. Travel distance needs a static arena-coordinates table (not in the feed) **[inferred]** |
| **Blowout risk** | Inputs: team game log `PLUS_MINUS` / final margin (`leaguegamelog?PlayerOrTeam=T`); `playbyplayv3` for score-by-time and garbage-time minutes; the market spread from BettingPros/Pinnacle (ADR 0006) | Team-game; event-level PBP | Yes | Post-game | Full 2025-26 **[live]** | As below | 200 residential **[live]** |
| *Later:* **Primary-defender matchups** | Per game `S/boxscorematchupsv3?GameID=` [BoxScoreMatchupsV3]: offensive player × defender `matchupMinutes`, `partialPossessions`, `percentageDefenderTotalTime`, `switchesOn`, points, FGA… Season roll-up `S/leagueseasonmatchups` [LeagueSeasonMatchups] | Player-pair per game | Per game: yes. Season roll-up: **no** (`DateTo` ignored, same 4,782 rows) **[live]** | Post-game | Full 2025-26 **[live]** | As below | 200 residential **[live]** |
| *Later:* **Referee crews** | Pre-game: `official.nba.com/referee-assignments/` (HTML, "posted at approximately 9:00am ET each game day", crew chief / referee / umpire / alternate) **[live]**. History: `S/boxscoresummaryv3` `officials[]` and CDN boxscore `officials[]` (personId, name, `OFFICIAL1..3`) **[live]** | Crew per game | Assignment page shows today only; history comes from box scores | ~9am ET game day (= 6am Arizona), so it's ready before the 9am AZ run | History per game for all of 2025-26 **[live]** | n/a | 200 residential **[live]** |

### Shared notes on `stats.nba.com`

- **Auth / headers:** no key needed. A browser `User-Agent` plus `Referer`/`Origin` of `nba.com` worked; the `x-nba-stats-token` headers weren't needed on 2026-10-13 **[live]**.
- **Rate limit:** there's no published limit. 25 back-to-back requests (no sleep) all returned 200 in 11.5 s **[live]**. An `nba_api` contributor reports reverse-engineering "once every 600ms" as safe, and says over-requesting leads to temporary blocks **[read: swar/nba_api#176]**. Plan for 1 request/s with backoff.
- **Datacenter:** "The NBA blocks all cloud hosting providers. This is a reason that integration tests are not run from the CI build" (nba_api contributor) **[read: swar/nba_api#176; duplicates #498 (AWS EC2), #510 (Lambda), #419 (GCP)]**. Not tested from the Anthropic cloud here. Treat it as **residential-only**, same as BettingPros (ADR 0006). The 9am and 3pm V4 runs already sit on the home PC, so this costs nothing new.
- **Deprecated v2 box scores:** `boxscoresummaryv2` for the reference game returns a frozen pre-game state (status "8:30 pm ET", empty `Officials`) **[live]**. **Use the `*v3` endpoints.** `nba_api` latest release is v1.11.4 (2026-02-20) **[read: GitHub releases API]**; it isn't installed on this PC.
- **Bulk cost for the gate:** the whole season of player box scores is **one** `leaguegamelog` call (4.5 MB, 2.8 s) **[live]**. Per-game advanced, matchup and PBP data is ~1,230 games × 3 endpoints ≈ 3,700 calls, roughly 1–1.5 hours at 1 req/s, done once and cached **[inferred]**.

### Basketball-Reference and pbpstats (fallbacks)

- **Basketball-Reference:** pages return 200 residential **[live]**. Hard limit: "more than 20 requests per minute" puts the session in "jail" for up to a day; there's no API, because data agreements bar downloads **[read: sports-reference.com/bot-traffic.html]**. `robots.txt` disallows `/play-index/*.cgi` and others **[live]**. It adds nothing the NBA endpoints lack for these families, so it's a fallback only.
- **pbpstats:** `api.pbpstats.com/get-games/nba` and `/get-totals/nba` returned 200 with per-game possessions and season totals **[live]**. The API is undocumented: the docs cover the Python parsing library (lineups on floor, possession start/end, loaders for stats.nba.com / data.nba.com / live), not the hosted API or its terms **[read: pbpstats.readthedocs.io]**. It was slow (10.7 s). Treat it as a convenience for lineup/WOWY, not a dependency.

## Gaps and risks

1. **Look-ahead leakage in Synergy and season matchups (high impact on #93).** `synergyplaytypes` and `leagueseasonmatchups` ignore `DateFrom`/`DateTo`. Using 2025-26 season values to project 2025-26 games inflates backtest accuracy. Options:
   (a) use **2024-25** play-type defense as the prior for 2025-26 backtests (verified available);
   (b) build play-type-like and matchup features point-in-time from per-game `boxscorematchupsv3` / `playbyplayv3`;
   (c) from 2026-27 on, **snapshot Synergy daily** so the live model has its own history.
   Position defense, pace, usage and rest are all point-in-time safe.
2. **No free injury *history* from ESPN.** The backtest's "who sat" truth comes from box scores (who played). The *pre-game* knowledge state (status at 3pm, say) comes only from the NBA PDFs, which need PDF parsing and two filename formats. A gate that simulates pre-game knowledge needs the PDFs. A gate using actual minutes as "perfect injury news" overstates live accuracy **[inferred]**.
3. **Unofficial, unannounced APIs.** stats.nba.com has changed headers, deprecated v2 endpoints, and blocked cloud IPs without notice. The fail-loud pattern from ADR 0006 should apply (no picks, Slack message) **[inferred]**.
4. **Residential-only.** If V4 ever needs to move to the cloud, every stats.nba.com source likely breaks. ESPN injuries is the only piece known to be cloud-tolerant.
5. **Travel distance** needs a hand-maintained 30-arena coordinates table (plus neutral sites such as international games); the schedule gives city/arena names only.
6. **Synergy refresh timing and the exact injury-report publish cadence** weren't measured here (only that both filename formats exist). Check them during build.

## Recommendation

**Use stats.nba.com (via `nba_api` v1.11.x or a thin client in the existing HTTP client) plus the CDN schedule/boxscore JSON as V4's NBA data layer; ESPN injuries for the live injury feed; NBA injury-report PDFs for injury history. Keep Basketball-Reference and pbpstats as fallbacks only.** Strength: **strong**. Confidence: **high (~85%)**. Every family was fetched live with full 2025-26 depth at $0, and the residential constraint is one the project already accepts. What would change my mind: stats.nba.com starting to block or throttle this residential IP during the bulk backfill, or the injury PDFs proving too irregular to parse reliably (then fall back to box-score truth for the gate and ESPN-only live).

**For the accuracy gate (#93):** **strongly** recommend (confidence high, ~80%) that the gate run point-in-time only: features computed with `DateTo` = the day before each game, and Synergy/matchup inputs taken from 2024-25 rather than 2025-26. Otherwise the gate measures leakage, not skill.

**For the projection shape (#92):** **moderate** recommendation (confidence moderate, ~65%) to make the first model **minutes × per-minute-rate**, adjusted by position-DvP, pace and rest, with blowout risk applied as a minutes haircut keyed off the market spread. Play-type defense comes in as a second-stage adjustment once daily Synergy snapshots exist. These are the inputs that are point-in-time clean today. It would change if a cheap leakage-free play-type reconstruction from PBP turns out to be easy.
