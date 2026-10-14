# V4-Matchup research: NBA injury and lineup sources and timing

- **Ticket:** #88, part of map #86 (V4-Matchup, NFL + NBA)
- **Researched:** 2026-10-13, from the home PC (residential IP). Arizona time (AZ) = UTC-7 all year.
- **Question:** Which free sources publish NBA injury status and starting lineups, when on game day (in AZ time), and how can a script read them reliably? Is ~3pm AZ the right time for the V4 NBA run?

**Gist:** The official NBA injury report PDF is the authoritative, script-readable source. It is published every 15 minutes, 24 hours a day. All game-day submissions are due by 2pm AZ at the latest. Questionable players are mostly resolved in the last ~60 minutes before the first tip. Confirmed starters are only due 30 minutes before tip. A ~3pm AZ run is right for **injury-driven** edges. It cannot see confirmed lineups, so it must price around players who are still Questionable.

Every claim below is tagged:
- **[LIVE]** means it was fetched from this machine on 2026-10-13.
- **[DOC]** means it was read from a primary source document.
- **[REPORTED]** means it is secondary or not yet verified.

---

## 1. League rules (primary source)

| Rule | Source |
|---|---|
| Teams must designate a participation status and a specific reason for any player whose participation may be affected, **by 5 p.m. local time the day before a game**. | [DOC] official.nba.com, "NBA Injury Report: 2025-26 Season" (no 2026-27 page exists yet; the `-2026-27-season/` URL returned 404 on 2026-10-13) |
| **Second game of a back-to-back:** the deadline is **1 p.m. local time on game day**. | [DOC] same page |
| **Game-day injury report:** due **between 11 a.m. and 1 p.m. local time**, or **between 8 and 10 a.m. local for tip-offs at 5 p.m. or earlier**. This does not apply to the second game of a back-to-back. | [DOC] same page |
| "Reports are updated on a continual basis throughout the day." | [DOC] same page |
| **Starting lineups:** "At least 30 minutes before the game is scheduled to begin, the scorers shall be supplied with the name and number of each player who will start the game." | [DOC] 2026-27 Official NBA Playing Rules, Rule 2, Section II (PDF linked from official.nba.com, `ak-static.cms.nba.com/.../2026/10/2026-27-Official-NBA-Playing-Rules.pdf`) |
| The public report was switched to a 15-minute refresh, and the 11am–1pm game-day resubmission was added as part of the league's betting-integrity changes. | [REPORTED] ESPN / Shams Charania, 2025-12-19. The 15-minute cadence is **confirmed [LIVE]** by the file listing in section 2. |

"Local time" is not defined on the page, so it is unclear whether it means the team's local time or the venue's. For a script this rarely matters: what counts is the **latest possible** submission, and that is a Pacific-time team (see the timeline).

## 2. Sources

| Source | Format | Update times | Reliability | How to parse | Status |
|---|---|---|---|---|---|
| **Official NBA injury report**, `https://ak-static.cms.nba.com/referee/injury/Injury-Report_{YYYY-MM-DD}_{hh}_{mm}{AM\|PM}.pdf` | PDF, multi-page table: Game Date, Game Time (ET), Matchup, Team, Player, Current Status, Reason | **Every 15 minutes, around the clock.** All 96 slots existed for 2026-03-02 (`12_00AM` … `11_45PM`). The time in the filename is **ET**. Each file covers **today's and tomorrow's** games, because day-before submissions show up early. | Authoritative: this is the league's own filing. Statuses are `Out / Doubtful / Questionable / Probable / Available`. `NOT YET SUBMITTED` marks a team that hasn't filed yet. | Build the URL for the most recent quarter-hour **in ET**. If you get a 403, step back 15 minutes, because the newest slot may not have posted yet. `pdftotext -layout` **misaligns** rows when a Reason wraps onto two lines (seen live: names and statuses drift apart). Use coordinate-based extraction instead: `pypdf` with a visitor function, or pdfplumber words bucketed by x-position. Also carry the Team/Matchup/Game-time values forward to rows that leave them blank. `pypdf` 6.10.0 is installed here; pdfplumber is not. | **[LIVE]** 200 for 2026-03-02 and 2026-03-18. A filename with no minutes (`_05PM`) worked in 2024-25 (2025-03-03 → 200) but returns **403** in 2025-26, so the format changed. **No reports for 2026-10-13 (preseason)**, so the 2026-27 regular season is not yet confirmed to use the same path. |
| **official.nba.com injury report page** | HTML | — | It holds the rules text only. The PDF links are not in the server HTML (0 report links found), so they are probably injected by JavaScript. | Don't scrape it. Build the PDF URL directly. | [LIVE] 200 |
| **ESPN league injuries**, `https://site.api.espn.com/apis/site/v2/sports/basketball/nba/injuries` (team view: `.../teams/{id}/injuries`; core API: `sports.core.api.espn.com/v2/sports/basketball/leagues/nba/teams/{id}/injuries`) | JSON. `injuries[]` is per team; each entry has `status`, `date` (UTC), `shortComment`/`longComment` (news blurb with attribution), `type.name`, `details.fantasyStatus` (e.g. `GTD`), `details.returnDate`, and `athlete` | Continuous. At the 00:59Z fetch, the newest entry was dated 00:39Z (about 20 minutes old), and several were within the hour. | **Coarse status.** Only `Day-To-Day` / `Out` were seen (112 / 21). Questionable, Doubtful and Probable are **not** distinguished, so it can't replace the official PDF. Its strength is the **news text**, which explains *why* and *how long*. That suits the "LLM is used only for news" role in the map. | `json.load`, then join on `athlete` name and team abbreviation. | **[LIVE]** 200 (all three URLs) |
| **ESPN game summary**, `https://site.api.espn.com/apis/site/v2/sports/basketball/nba/summary?event={id}` (event ids come from `.../scoreboard`) | JSON. Includes per-game `injuries`, `boxscore.players[].statistics[0].athletes[].starter` | The `starter` flags appear **only once the game is underway**. For a scheduled game, `boxscore.players` was empty. | Good for **checking afterwards** who actually started and played (useful for model training and resolution). It is **useless for pre-tip lineups**. | `json.load` | **[LIVE]** scheduled game 401898718: injuries present, no box players. In-progress game 401908944: 5 starters flagged per team. |
| **RotoWire NBA lineups**, `https://www.rotowire.com/basketball/nba-lineups.php` (free, no login) | Server-rendered HTML. Per game: `li.lineup__status` with class `is-expected` ("Expected Lineup") or `is-confirmed` ("Confirmed Lineup"); 5 × `li.lineup__player` (`lineup__pos`, `a[title]` = full name, class `is-pct-play-{0..100}`); a "MAY NOT PLAY" list with `span.lineup__inj` (`Ques`/`Out`/…); `data-lineup` / `data-out` RotoWire player-id lists | **Expected** lineups are up all day. They flip to **Confirmed** around tip. At 01:02Z (6:02pm AZ), the 3 games already underway showed 6 × Confirmed, and the 2 games tipping at 7pm AZ still showed 4 × Expected. | The only free source of **projected** starters before tip. It is a third party, so the HTML may change without notice. robots.txt `User-agent: *` does **not** disallow `/basketball/`; there is also an `llms.txt`. Terms of service were **not reviewed**: check them before relying on it unattended. | Regex or BeautifulSoup on the class names above. Treat `is-confirmed` as the only real lineup. | **[LIVE]** 200, 430 KB |
| **NBA CDN live data**, `cdn.nba.com/static/json/liveData/...` (scoreboard, boxscore, odds) and **stats.nba.com** | JSON | — | **Blocked from this machine with simple clients.** CDN returned 403 (Akamai "Access Denied") even with nba.com `Referer`/`Origin`. stats.nba.com timed out. | Not recommended at a $0, low-maintenance budget. | **[LIVE]** 403 / timeout |
| Team feeds and beat reporters (X/Twitter, team PR) | Free text | The fastest source, minutes after news breaks | No stable API. ESPN `shortComment` text and RotoWire already aggregate them with attribution. | Don't parse directly. | [REPORTED] (not probed) |

## 3. Observed game-day cadence (official PDF, measured)

[LIVE] measurement: I fetched the official PDF every 30 minutes and counted rows **for that date's games only**. The counts are approximate because of the PDF-layout issue above, but the trend is clear.

**2026-03-02 (EST, so AZ = ET − 2). Tips 7:00pm–10:30pm ET = 5:00pm–8:30pm AZ**

| ET slot | AZ | Not yet submitted | Out | Q/D/P |
|---|---|---|---|---|
| 6:00am – 12:30pm | 4:00am – 10:30am | 4 | 23 | 4 (unchanged all morning) |
| 1:00pm – 2:00pm | 11:00am – 12:00pm | 4 → 2 | 24 → 30 | 2–3 |
| 3:00pm – 4:30pm | 1:00pm – 2:30pm | 4 → 0 | 36 | 2 |
| 5:00pm | **3:00pm** | 0 | 36 | 2 |
| 6:30pm | 4:30pm | 0 | 37 | 0 |
| 9:00pm | 7:00pm | 0 | 38 (final) | 0 |

**2026-03-18 (EDT, so AZ = ET − 3). 9 games, tips 7:00pm–10:00pm ET = 4:00pm–7:00pm AZ**

| ET slot | AZ | Not yet submitted | Out | Q/D/P | Available |
|---|---|---|---|---|---|
| 6:00am – 12:00pm | 3:00am – 9:00am | 7 | 49 | 28 (unchanged) | 0 |
| 1:00pm – 2:00pm | 10:00am – 11:00am | 3–8 → 1 | 55 → 75 | 32–34 | 3–4 |
| 4:30pm | 1:30pm | 0 | 76 | 30 | 5 |
| 6:00pm | **3:00pm** | 0 | 76 | 25 | 10 |
| 7:00pm | 4:00pm | 0 | 88 | **1** | 24 |
| 8:00pm | 5:00pm | 0 | 90 (final) | 0 | 24 |

What this shows:
1. Nothing changes overnight or in the morning. The report "moves" once the game-day window opens: 11am–1pm local, which is 8am–2pm AZ depending on the team's time zone and the season.
2. All teams had filed by **2:30pm AZ** on both days.
3. **Outs are ~85–95% settled by 3pm AZ** (76/90 and 36/38).
4. **Questionable/Doubtful/Probable designations resolve in a burst right before the first tips.** On 2026-03-18, 24 of 25 resolved between 3:30 and 4:00pm AZ, and 12 extra Outs appeared in that half-hour.

## 4. Game-day timeline in Arizona time

Daylight-saving periods matter because AZ does not change its clocks:
- **EDT period** (season start → **2026-11-01**, and **2027-03-14** → season end): AZ = ET − 3, and AZ = Pacific time.
- **EST period** (2026-11-01 → 2027-03-14): AZ = ET − 2, and AZ = Pacific + 1.

| Event (AZ) | 4:00pm AZ tip (7pm ET, EDT; East home) | 5:00pm AZ tip (7pm ET, EST; East home) | 7:30pm AZ tip (West Coast home, e.g. 7:30pm PDT / 6:30pm PST) |
|---|---|---|---|
| Day-before designation deadline (5pm local, previous day) | 2:00pm AZ (East team) | 3:00pm AZ (East team) | 5:00pm AZ (PDT) / 6:00pm AZ (PST) |
| Game-day report window (11am–1pm local) | 8:00–10:00am AZ (East team); Pacific visitor 11am–1pm AZ | 9:00–11:00am AZ (East team); Pacific visitor 12–2pm AZ | 11am–1pm AZ (PDT) / **12–2pm AZ (PST)**, the latest possible deadline |
| Back-to-back second game deadline (1pm local) | 10:00am AZ | 11:00am AZ | 1:00pm AZ (PDT) / 2:00pm AZ (PST) |
| Official PDF "complete" (all teams filed), observed | ~1:30–2:30pm AZ | ~2:30pm AZ | same day, by ~2:30pm AZ |
| **V4 run at ~3:00pm AZ** | T − 60 min | T − 120 min | T − 270 min |
| Questionable players resolved (observed burst) | ~3:00–4:00pm AZ | ~4:00–5:00pm AZ | ~6:30–7:30pm AZ [inferred from the 30–60 minutes-before-tip pattern] |
| Starting lineups due to the scorer (Rule 2 §II) | **3:30pm AZ** | **4:30pm AZ** | **7:00pm AZ** |
| RotoWire flips Expected → Confirmed | ~3:30pm AZ | ~4:30pm AZ | ~7:00pm AZ (observed: still "Expected" at 6:02pm for a 7pm AZ tip) |

## 5. Recommendation: the V4 NBA run time

**Keep the V4-only NBA run at ~3:00pm AZ. Moderate strength, ~65% confidence.** Two conditions come with it:

1. **Data sources.**
   - Read the **official injury PDF**, using the latest 15-minute slot in ET and stepping back on 403. It is the status of record, and it is complete (zero "not yet submitted") by ~2:30pm AZ every day sampled.
   - Add **ESPN `/injuries` JSON** for the news text the LLM layer reads.
   - Add **RotoWire `nba-lineups.php`** for *expected* starters and minutes context.
   - Use **ESPN summary** only after the game, to verify starters and minutes.
2. **Price around Questionable players; don't wait for them.** At 3pm AZ, Outs are mostly settled, but in EDT months most Questionable designations are still open (25 open on 2026-03-18). For any prop or line where a Questionable player swings the projection, the run should either:
   - (a) fire only if the edge survives **both** the plays and sits scenarios, or
   - (b) skip it.

   Also exclude games that tip within ~45 minutes of the run finishing. That excludes nothing in EST months, where the first standard tip is 5pm AZ. In EDT months it leaves a 7pm ET (4pm AZ) tip only ~60 minutes, so check that the run finishes in under ~15 minutes.

Why not later:
- A run at T − 35 minutes before each tip cluster would see confirmed lineups and resolved Questionables. But that means several runs a day, at times that move with the slate and with DST.
- It also arrives after the news has broken, and books likely adjust within minutes [REPORTED, not measured here].

Why not earlier:
- Before ~1pm AZ the official report is often incomplete. On both sample days, nothing for that day's games changed before the 11am–1pm local window.
- Day-before Outs are already visible to the 9am run, so an earlier V4 pass adds little over the main 9am lane.

What would change my mind:
- If ADR 0010 closing-line data shows V4 picks made at 3pm consistently losing CLV on games where a Questionable player resolved, that would argue for a second **T − 35 min, confirmed-lineup pass**. That is currently a **weak lean, ~50%**, and should be deferred until there is measured evidence.

## 6. Open items / not verified

- **2026-27 regular-season PDF path is unconfirmed.** Preseason has no reports, and the 2026-10-13 slots all returned 403. The first regular-season day needs a one-line probe: request the latest slot and expect 200.
- **The meaning of "local time"** (the team's or the venue's) is not defined in the rule text.
- **RotoWire terms of service** have not been reviewed for automated use.
- **How fast books re-price props after an injury report change** was not measured. That is the real constraint on how much a later run could gain.
- **Q/D/P resolution for late West Coast games** is inferred, not sampled separately. The sample days' counts mix all tips because PDF extraction is approximate.
