# Sports Betting — Decision Support

Analyze sports bets; identify +EV opportunities using data, line movement, and situational analysis.

## Approach

- Value over winners — a bad line on a favorite is worse than a good line on an underdog.
- Track all bets (win/loss, odds, stake, result) **and CLV** — CLV is the process signal, ROI the outcome signal; both should trend positive.
- Primary edge: **player props + cross-book line gaps** — books set props with less precision and adjust slower than game lines.
- Secondary edge: **RLM (70%+ threshold)** and **steam confirmed at 3+ books simultaneously** — single-book moves are noise.
- No emotional bets (favorite teams, recency bias, chasing losses).
- **Long-run calibration targets:** 55%+ win rate on spread/total bets; 5–7% ROI over 500+ bets.

## Sports in Scope

NFL / College Football, NBA / College Basketball, MLB, NHL. Add others as needed.

## Bet Types

| Priority | Type | Notes |
|----------|------|-------|
| 🥇 Primary | Player props | Cross-book gaps and prop steam are the most accessible retail edge |
| 🥇 Primary | Alternate lines | Cross-book gaps common here too |
| 🥈 Secondary | Spread / Moneyline / Total | Only with confirmed RLM (70%+) or 3+ book steam |
| 🥈 Secondary | 1st half / 1st quarter | Same signals as game lines |
| ⚠️ Use sparingly | Parlays | Only when legs have confirmed independent signals |

## Skills

| Skill | Purpose |
|-------|---------|
| `/sports-betting` | V1-Trends: picks using ATS trends, expert consensus, situational angles, line movement |
| `/sports-betting-sharp` | V2-Sharp: props + cross-book gaps first; RLM (70%+) and steam (3+ books) for game lines — high selectivity |
| `/bet-tracker` | Log picks, record results, compare ROI between V1 and V2 |

## Development Workflow (engineering changes)

**Money-scoring system** — worst bug class is silent mis-resolution (lost bet scored as win, or CLV computed against the wrong line). Green tests and a clean diff can both pass while a bet is scored wrong; the workflow exists to catch that.

**Tier the work:**

- **Trivial, at the keyboard** (typo, one-line tweak, obvious fix): just commit. No PRD, no issue.
- **Logic-touching OR delegated to an AFK agent**: run the full chain — the PRD/issue is the agent's prompt; verbosity is the price of unattended execution.

**The full chain:**

```
/grill-with-docs   → only if the data source or domain model isn't already nailed down in an ADR.
                     Forces decisions up front instead of surfacing mid-build as a ready-for-human blocker.
/to-prd            → spec the work, publish to the issue tracker
/to-issues         → slice into tracer-bullet vertical issues (prove the path end-to-end on one case, then widen)
[implement]        → /tdd for new logic; one issue → one branch → one PR
/review            → reviews the diff (reasons about code, not behavior)
/verify            → REQUIRED for anything touching resolution, determine_outcome, scoring, or CLV.
                     /review and /code-review inspect the diff; /verify runs the resolver against a real
                     finished game and watches the actual outcome. Tests cover cases you thought of —
                     /verify catches the ones you didn't.
```

**Non-negotiable:** any change touching resolution / scoring / CLV ends with `/verify`, not just `/review`.

**Support tools (not part of the chain):**

- `/zoom-out` — run *before* `/to-prd` when about to work in unfamiliar code, so the PRD is grounded.
- `/improve-codebase-architecture` — periodic codebase health audit (HTML report); recommendations *feed* `/to-prd`; run between feature cycles, not during one.
- `/write-a-skill` → `/skill-optimizer` — for building new skills, not code features.

**Hygiene:** close or delete abandoned branches/draft PRs — the chain doesn't sweep rot.

## File Paths — Critical

**Active skill path:** `.agents/skills/bet-tracker/`
- `picks.json` — single source of truth for all picks
- `actual_bets.json` — single source of truth for My Bets verified wagers, stakes, and bankroll settings
- `tracker.py` — CLI (always invoke with `python3`, never `python`)
- `SKILL.md` — skill instructions
- `betting-intel.md` — session observations and pattern notes

**Stale path (do not use):** `.claude/skills/bet-tracker/` — old copy, ignore. If `.claude/skills/bet-tracker/actual_bets.json` reappears, run:
```bash
python3 ".agents/skills/bet-tracker/tracker.py" migrate-actual-bets
```

**Dashboard picks GitHub path** (hard-coded in `dashboard.html`):
```text
.agents/skills/bet-tracker/picks.json
```
Dashboard reads picks via the GitHub Contents API, not `raw.githubusercontent.com` (raw CDN can lag after a push). If the skill path changes, update `PICKS_FILE_PATH` in `dashboard.html`.

**My Bets GitHub path** (hard-coded in `dashboard.html`):
```text
.agents/skills/bet-tracker/actual_bets.json
```
My Bets tab writes this file via the GitHub Contents API. Read-only without a GitHub token; do not reintroduce localStorage or `.claude` as source-of-truth fallbacks.

> **⚠️ Gotcha (burned 2026-05-22, and again via raw CDN cache 2026-05-25):** after any file reorganization, verify `PICKS_FILE_PATH` in `dashboard.html` matches the active path and the GitHub Contents API returns fresh data. A stale path or raw CDN cache makes the dashboard look out of date even after a successful push.

## Data File

All picks live in `.agents/skills/bet-tracker/picks.json` — single source of truth, read/written by:
- `/sports-betting` and `/sports-betting-sharp` when logging picks (pull before read, push after write)
- Nightly auto-resolve agent (pushes results to GitHub every night at 11pm Phoenix)
- `/bet-tracker` for stats and manual result entry (pull before read, push after write)
- `scripts/resolve-and-push.sh` — one-command local resolution + push

**Never edit picks.json manually** — always go through the skills or the nightly agent.

## Dashboard

Live (auto-deployed via GitHub Pages), fetches picks directly from GitHub, auto-refreshes every 5 min:
```
https://tylerm08martinez-wq.github.io/gambling/dashboard.html
```
Tabs:
- **Overview** — KPI strip, cumulative P&L, win rate by sport, bet type breakdown, score distribution
- **V1 vs V2** — side-by-side model comparison with H2H stats and units P&L by sport
- **Edge Breakdown** — picks and performance by edge type and sport
- **Pick Log** — filterable full pick history with results and P&L

## Key Concepts

- **CLV:** compare bet line vs. closing line (both as implied probability). Positive CLV = better price than market settled at = good process; consistent positive CLV long-term means real edge regardless of short-term variance.
- **Props + cross-book gaps:** books set prop lines with less precision. A 0.5+ unit gap across DK / FanDuel / BetMGM means sharps already hit one book — target the stale price before it closes.
- **RLM threshold: 70%+ with line move confirmation.** Splits show # of bets, not dollar handle — 80/20 on tickets may be 55/45 on dollars. Always require actual line movement to confirm RLM.
- **Steam requires 3+ books simultaneously.** 1–2 books = noise; 4+ books = "mega sharp" signal.
- **Never chase steam:** if the book already moved, you're entering at the new market price, not the edge.
- **Late moves carry more weight:** moves in the final 2–3 hours before game time reflect higher limits and fresher info.
- **Head fakes:** sharps make small bets to move a line, then bet the other side when limits rise. Move followed by reversal = manipulation, not signal.
- **Underdog/under value:** public systematically overweights favorites and overs — sharps consistently find value on dogs and unders.
- **Kelly Criterion:** size bets proportionally to edge; avoid overbetting. Use fractional Kelly (half-Kelly) to reduce volatility.
- **Bankroll:** track as units, not dollars, to stay disciplined.

## Automation

| Routine | Schedule | Purpose | ID |
|---------|----------|---------|-----|
| Daily Bet Picks (V1 + V2) | 9am Arizona | V1 + V2 research; log picks, commit/push to GitHub, post summary to Slack #bet-picks | **home PC** (`scripts/run-daily-picks.sh`) |
| Nightly Bet Tracker — Auto-Resolve Picks | 11pm Arizona | Look up final scores, calculate CLV, commit results to GitHub | `trig_01SwKt54TorHpUVWSbsrnP2m` (cloud) |

Nightly auto-resolve runs in Anthropic's cloud (datacenter-tolerant APIs — MLB Stats + ESPN, ADR 0004/0005). Daily Bet Picks runs on the **home PC** via local scheduler, not cloud: its research data (BettingPros cross-book props — the Primary Edge) is **403-blocked from datacenter IPs** (ADR 0006, 2026-06-01 acceptance test), so it must run from a residential IP. PC must be powered/awake ~9am AZ. Old cloud trigger `trig_01SkNEk48CK981znKJPaHb47` is disabled.

Manage routines: https://claude.ai/code/routines

## GitHub Repo

Public repo: `https://github.com/tylerm08martinez-wq/gambling` — all picks version-controlled; nightly agent resolves results and pushes to main automatically; dashboard reads directly from GitHub, no manual sync.

## Agent skills

- **Issue tracker:** GitHub Issues. See docs/agents/issue-tracker.md.
- **Triage labels:** default five-role vocabulary (needs-triage, needs-info, ready-for-agent, ready-for-human, wontfix). See docs/agents/triage-labels.md.
- **Domain docs:** single-context repo — one CONTEXT.md at root, ADRs in docs/adr/. See docs/agents/domain.md.
