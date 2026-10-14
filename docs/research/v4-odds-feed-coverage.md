# Can the existing odds feed price V4's markets?

Research ticket #90 on wayfinder map #86 (V4-Matchup, NFL + NBA). Probed 2026-10-13, 18:01–18:03 Arizona (2026-10-14 01:01–01:03 UTC), from the home PC (residential IP). I used the repo's own client (`bettingpros._live_get_json`, which scrapes the live key) and made about 40 read-only requests. Nothing was logged and no picks file was touched.

## TL;DR

- **Pinnacle (`book_id` 2) does not appear in any `/offers` response.** I checked NBA and NFL spreads, totals, moneylines, first-half lines and player props, plus MLB as a control. `/v3/books` still lists Pinnacle, but no market returns a price from it. This matches `betting-intel.md` (lines 762, 785, 808, 825, 842), where Pinnacle was missing in several sessions in a row from July onward. The "70% de-vigged Pinnacle" part of V4's fair price cannot be sourced from this feed.
- **The feed has no alt-line ladders.** Every book returns exactly one line per selection in every market probed. That held across all leagues, including BettingPros Consensus. I also tried four guessed query parameters to unlock alts and none had any effect. V4's "alt lines" bet type has no price source here.
- **A low-hold reference does exist for NFL.** The exchanges and prediction markets (Novig 60, ProphetX 38, Kalshi 68, Polymarket 73, Polymarket US 75) price NFL game lines at **0.0–1.0% hold**, against 3.6–6.1% for the retail books. That makes them the natural stand-in for Pinnacle.
- **NBA is thin right now.** Regular season opens 2026-10-20. For 2026-10-21 game lines, the exchanges are absent except Novig (7% hold), and NBA regular-season props are not posted yet. The preseason prop grid has only Underdog, Novig and Consensus.
- **Prices are fresh.** Each line carries an `updated` timestamp. Game-line quotes were 2–18 minutes old. One prop quote (theScore, NFL receiving yards) was 482 minutes stale.

## Coverage matrix (verified live, 2026-10-13)

| League | Market (BP `market_id`) | Event probed | Pinnacle? | Books priced | Low-hold (≤2%) books | Alt ladder? |
|---|---|---|---|---|---|---|
| NFL | Spread (3) | 22000 SEA@DEN 10-15; 22001 TEN@IND 10-18 | **No** | 18: Consensus, FanDuel, DK, Caesars, Fanatics, SugarHouse, BetRivers, BetMGM, bet365, PartyCasino, theScore, ProphetX, Fliff, Betr, Hard Rock, Novig, Kalshi, Polymarket | Novig 0.5%, ProphetX 0.9%, Kalshi 0.9%, Polymarket 1.0% | **No** (1 line/book) |
| NFL | Total (2) | 22000, 22001 | **No** | 19 (above + Polymarket US) | Novig 0.5%, Polymarket US 0.5%, ProphetX 0.9%, Kalshi 1.0%, Polymarket 1.0% | **No** |
| NFL | Moneyline (1) | 22000 | **No** | 18 | Polymarket 0.0%, Novig 0.6%, Kalshi 0.9%, ProphetX 0.9% | n/a |
| NFL | Passing yds (103) | 22000 | **No** | 19 incl. Underdog, PrizePicks, Sleeper | Kalshi 1.0%, Polymarket US 1.4% (n=2) | **No** |
| NFL | Receiving yds (105) | 22000 | **No** | 18 | Polymarket US 1.5% (n=6), Kalshi 1.5% (n=8) | **No** |
| NFL | Rushing yds (107) | 22001 (Sun) | **No** | 3: Consensus, Underdog, PrizePicks (5 days out) | none | **No** |
| NFL | Anytime TD (78) | 22000 | **No** | 15 | not measured (one-way market) | n/a |
| NBA | Spread (129) | 27891 ATL@ORL 10-21 (REG) | **No** | 13: retail + Fliff + Novig | none (Novig 7.2%) | **No** |
| NBA | Total (128) | 27891 | **No** | 13 | none (Novig 7.4%) | **No** |
| NBA | Moneyline (127) | 27891; 29131 NYK@TOR 10-13 (PRE) | **No** | 13–15 | not measured | n/a |
| NBA | 1H spread (163) | 29131 (PRE) | **No** | 5: Consensus, FanDuel, Fanatics, bet365, Novig | not measured | **No** |
| NBA | Points (156) | 29131 (PRE) | **No** | 3: Consensus, Underdog, Novig | none | **No** |
| NBA | Points / Rebounds (156/157) | 27891 (REG) | n/a | **0 offers**, not posted yet | — | — |
| MLB (control) | ML 122, total 175, K 285, hits 287 | 100945 CLE@TB | **No** | 14–18 | — | **No** |

Hold is the two-way overround where both sides are priced at the same number, averaged over the offers in that market. `n` is the number of player offers.

### Market IDs for V4 (verified live from `/v3/markets`, 2026-10-13)

**NBA:**
- Game lines: spread 129, total 128, moneyline 127.
- Halves and quarters: 1H spread 163, 1H total 153, 2H spread 166, 2H total 158, Q1–Q4 spread 164/167/168/165, Q1–Q4 total 154/159/161/155.
- Team total: 363.
- Player props: points 156, rebounds 157, assists 151, threes 162, steals 160, blocks 152, PRA 338, P+A 335, P+R 336, R+A 337, double-double 136, first basket 142.

**NFL:**
- Game lines: spread 3, total 2, moneyline 1.
- Halves and quarters: 1H spread 112, 1H total 97, 2H spread 115, 2H total 108, Q1–Q4 spread 113/116/117/114, Q1–Q4 total 98/109/110/99.
- Total points: 111.
- Player props: passing yds 103, passing TDs 102, attempts 333, completions 100, interceptions 101, rushing yds 107, rushing attempts 106, receiving yds 105, receptions 104, rush+rec yds 406, anytime TD 78, first TD 66, TDs 334.

### Book IDs missing from `bettingpros.BOOKS` (verified live from `/v3/books`)

| ID | Book |
|---|---|
| 15 | SugarHouse |
| 27 | PartyCasino |
| 39 | Fliff |
| 63 | Sleeper |
| 68 | Kalshi |
| 73 | Polymarket |
| 75 | Polymarket US |

Today they decode as `book-<id>`. Pinnacle (2) is still listed in `/v3/books`, so it is a known book that currently gets no prices.

## Freshness

Every line object carries `updated` (UTC), `main`, `is_off`, `active` and `metrics.pm_win_pct`.

- **Verified at about 18:00 Arizona:** game-line quotes were 2–18 minutes old on every book. Prop quotes were mostly 2–18 minutes old, but one outlier was 482 minutes old (theScore, NFL receiving yards). V4 should reject any quote older than a staleness bound, for example 60 minutes.
- **Not verified at about 15:00 Arizona** (the planned V4 NBA run). The probe ran 3 hours later. The NBA regular-season prop grid isn't open yet, so 3pm NBA prop freshness can't be measured until about 2026-10-20.
- **Correction to ADR 0010.** ADR 0010's context says the feed "exposes no timestamp". That is true of the *normalized* output of `fetch_offer_ladder` / `fetch_offers`. The raw line does carry `updated`, so the normalizers drop it. Capturing `updated` would give closes a real vintage.

## V3 code V4 can reuse as-is

All of these are pure functions with no I/O, in `.agents/skills/bet-tracker/value_engine.py`:

| Function | Line | Note |
|---|---|---|
| `american_to_prob` | 40 | |
| `prob_to_decimal` | 53 | |
| `multiplicative_devig` | 61 | Two-way ML and props |
| `power_devig` | 67 | Spreads and totals. Brackets the root for lopsided markets. |
| `devig_method` | 90 | Already sends `"alt …"`, `spread`, `total` to power, everything else to multiplicative. |
| `fair_two_way` | 107 | De-vigs a two-way pair of American prices. This is the building block for any reference book, not just Pinnacle. |
| `projected_clv` | 118 | |
| `ev_per_dollar` | 126 | |
| `gate_threshold` / `clears_gate` | 131 / 136 | 2% game lines, 3% props |
| `kelly_fraction` | 144 | |
| `units_from_clv` | 152 | Measurement mode (ADR 0009) flattens to 1u anyway. |
| `classify_steam` | 171 | Confirmation only |

Also reusable:
- `clv_fetch.two_way_at_line` (`clv_fetch.py:61`) and the `close_capture` flow, for consensus-based de-vig CLV on props.
- `bettingpros.fetch_events` (`bettingpros.py:248`) and `fetch_props` (`bettingpros.py:258`). Both already take `sport`.

Needs adapting before reuse:
- **`fetch_offers` and `fetch_offer_ladder`** (`bettingpros.py:193`, `208`) hard-code `sport=MLB` in the URL. The live probe needed `sport=NBA` / `sport=NFL`, which the API accepted, so make `sport` a parameter. These functions also drop `updated`.
- **`fetch_offer_ladder`** keeps only book 0. V4 needs the per-book two-way pairs to build an exchange reference.
- **`evaluate_market`** (`value_engine.py:207`) de-vigs whatever two-way prices it gets under the `pinnacle` key. It takes no pre-computed fair probability, so it cannot consume a 70/30 blended fair price. V4 should call `fair_two_way` and then `projected_clv` / `clears_gate` directly, or a variant of `evaluate_market` should accept `fair` as input.
- **`clv_fetch.STAT_MARKET`** (`clv_fetch.py:41`) is MLB-only. NBA and NFL need their own maps (IDs above).

## Gaps

1. **No Pinnacle.** This undermines the settled 70% de-vigged-Pinnacle blend as written. It also bears on GLOSSARY's Line-Value Edge and V3-Value definitions, which assume `book_id` 2.
2. **No alt-line ladders.** Each book returns only its main line. V4 has no feed to price alt spreads, totals or alt prop lines against, nor to measure their CLV. `fetch_offer_ladder`'s docstring says the consensus ladder "preserves EVERY alt line", but no live response today had more than one line per book, including MLB.
3. **NBA reference is thin.** The exchanges are absent from NBA game lines a week out, and the NBA regular-season prop grid is unposted. This needs re-probing around 2026-10-20 to 2026-10-22.
4. **Exchange sharpness is assumed, not verified.** Low hold on Novig, ProphetX, Kalshi and Polymarket is verified. That their prices are *sharp* (efficient and liquid) is not. ProphetX shows 14–17% hold on NFL props, which points to thin books there.
5. **No 3pm Arizona freshness sample** (see Freshness).

## Recommendation: where V4 gets its market fair price when Pinnacle is missing

Treat Pinnacle as missing by default and rename the blend's market leg to **"de-vigged market reference"**:

1. **Game lines (spread, total, ML).** Per side, take the median of the `fair_two_way`-de-vigged probabilities from books with two-way hold ≤ 2% at the same number. Today those are Novig, ProphetX, Kalshi, Polymarket and Polymarket US. Require at least 2 such books and quotes no older than 60 minutes.
   - Fallback: the median de-vigged price across all retail books at the consensus number, or BettingPros Consensus (book 0) de-vigged. Tag the pick `reference=retail`.
   - Keep the 70/30 weighting when the reference is exchange-based. Drop it to about 50/50 when the reference is retail. That second change is a weak lean and should be calibrated by CLV.
2. **Props.** Use the de-vigged Consensus (book 0) at the pick's number, which is what V3 and `close_capture` already do. Add low-hold exchange prices where Kalshi or Polymarket post that player's line. Model weight stays higher here, as the map already says.
3. **Alt lines.** Defer them out of V4's first slice, or price them model-only and leave them un-CLV-able until a ladder source exists. Don't log an alt line whose fair price can't be checked against any market.
4. **Log which reference was used** on every pick (`exchange` / `retail` / `consensus`), so the calibration loop can reweight by reference quality.

**How strong and how sure:**
- That the 70/30 blend's market leg must change because Pinnacle isn't in the feed: **strong, high confidence (about 90%).** Pinnacle was absent in every one of about 40 live calls across three leagues and every market type, and it has been absent in logged sessions since July.
- That exchange-median is the right replacement: **moderate, about 60% confidence.** The low hold is measured, but sharpness and liquidity are not. Two things would change my mind:
  - A study of exchange-reference CLV against realized closes over 30 or more picks showing it no better than retail consensus.
  - Pinnacle reappearing in `/offers`.

## Sources

- Live BettingPros API responses, 2026-10-13 18:01–18:03 Arizona, from `/v3/events`, `/v3/markets`, `/v3/books`, `/v3/offers` and `/v3/props`.
- Repo:
  - `.agents/skills/bet-tracker/bettingpros.py`
  - `.agents/skills/bet-tracker/value_engine.py`
  - `.agents/skills/bet-tracker/clv_fetch.py`
  - `.agents/skills/bet-tracker/betting-intel.md` (lines 762–842)
  - ADR 0006, 0007, 0009, 0010
