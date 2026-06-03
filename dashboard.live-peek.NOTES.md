# Live Peek prototype — verdict

**Question:** Does a client-side fetch-and-grade pipeline (parse bet → find game →
fetch boxscore → map stat → grade vs line/side) actually work end-to-end against the
live MLB Stats API for the real Pick Log examples — clean enough to replace the
generic Google search behind 🔍?

**Answer: YES.** Run `node dashboard.live-peek.PROTOTYPE.mjs`. Both real cases passed:

- `Under 9 Phillies at Dodgers (Painter vs Yamamoto)` (settled) → correctly **bypasses
  fetch**, renders from stored data, grades total 10 vs Under 9 = LOSS (matches stored).
- `Jonathan Aranda Total Bases Over 1.5 vs Tigers (Madden)` (the "even worse" case,
  stored `result=null`) → parsed cleanly, found game pk=822974 (Final, DET 10 @ TB 9),
  read `batting.totalBases=0`, graded **Over 1.5 → LOSS**. The nightly resolver had left
  this ungraded; the peek answers it instantly. This is the whole value prop.

## Validated
- **CORS open** on `statsapi.mlb.com` (schedule + boxscore) and `site.api.espn.com` —
  `Access-Control-Allow-Origin: *`. Browser fetch from GitHub Pages works, no proxy.
- **Parser** strips the trailing pitcher parenthetical (no "Painter vs Yamamoto" /
  "Madden" pollution), handles both stat orderings (`Total Bases Over 1.5` AND
  `Over 5.5 Strikeouts`), the `N+` form, and pulls the opponent hint after vs/at/@.
- **`batting.totalBases` is a direct boxscore field** — no derivation needed (confirms ADR 0004/0007).
- Parse-only sweep over all 44 picks: zero blowups; all 3 unsettled props parsed correctly.

## Fold into the real dashboard.html implementation
1. **Mirror the resolver's safety:** same-last-name collision → **skip, don't guess**
   (ADR 0004). The proto takes the first last-name match; the real peek must refuse an
   ambiguous match so it never shows a confidently-wrong number.
2. **`fetch()` without `credentials:'include'`** — MLB sends `ACAO:*` + `Allow-Credentials:true`;
   including credentials would invalidate the `*`.
3. **NBA/ESPN adapter not built here** — port ADR 0005 ESPN boxscore logic to JS for NBA props.
   Until then NBA unsettled → deep-link fallback.
4. **Game-line total path** (sum the two final scores) is trivial and validated by
   inspection; no unsettled total existed in current data to live-run.
5. Keep it **read-only / never writes picks.json** (ADR 0007). Label in-progress games
   "⏳ live peek — official grade posts tonight".
6. Fallback links: prop → StatMuse single-answer query; game-line → ESPN scoreboard for the date.

**Status:** throwaway. Delete `dashboard.live-peek.PROTOTYPE.mjs` + this file once the
logic is folded into `dashboard.html`.
