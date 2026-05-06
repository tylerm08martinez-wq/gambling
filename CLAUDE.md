# Sports Betting — Decision Support

This folder is for analyzing sports bets and building a framework for making smarter wagering decisions.

## Purpose

Help Tyler identify +EV (positive expected value) betting opportunities across sports using data, line movement, and situational analysis.

## Approach

- Focus on **value**, not just picking winners — a bad line on a favorite is worse than a good line on an underdog
- Track all bets (win/loss, odds, stake, result) **and closing line value (CLV)** — CLV is the process signal; ROI is the outcome signal; both should trend positive
- Primary edge: **player props + cross-book line gaps** — books set props with less precision and adjust them slower than game lines
- Secondary edge: **RLM (70%+ threshold)** and **steam moves confirmed at 3+ books simultaneously** — single-book moves are noise
- Avoid emotional bets (favorite teams, recency bias, chasing losses)

## Sports in Scope

- NFL / College Football
- NBA / College Basketball
- MLB
- Add others as needed

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
| `/bet-tracker` | Log picks, record results, and compare ROI between V1 and V2 models |

All picks are stored in `.claude/skills/bet-tracker/picks.json`. Use `/bet-tracker stats` to see the full performance dashboard.

## Key Concepts

- **Closing line value (CLV):** Compare your bet line vs. the closing line (both converted to implied probability). Positive CLV = you got a better price than the market settled at = good process. Consistent positive CLV long-term means the model has real edge, regardless of short-term win/loss variance. Tracked automatically in `picks.json`.
- **Props + cross-book gaps:** Books set prop lines with less precision. A 0.5+ unit gap across DK / FanDuel / BetMGM means sharps have already hit one book — target the stale price before it closes.
- **RLM threshold is 70%+:** Below 70% public lean is too noisy. 70%+ with line moving the wrong way is a genuine sharp signal.
- **Steam requires 3+ books:** A line move at 1-2 books is a single book adjusting. A simultaneous move at 3+ books is a sharp syndicate.
- **Kelly Criterion:** Size bets proportionally to edge — avoid overbetting
- **Bankroll:** Track as units, not dollars, to stay disciplined

## Automation

Both models run automatically every day at **9am Arizona time** via remote triggers in Anthropic's cloud (PC does not need to be on).

| Trigger | ID |
|---------|-----|
| V1-Trends Daily | `trig_01Nb7FSHC71b7mKnubppSJUp` |
| V2-Sharp Daily | `trig_016TZJHhwzkiWPA3czAc5sUq` |

Results are sent to Tyler's Slack DM each morning. Picks are committed to this repo automatically — run `git pull` after getting the Slack message to sync locally.

Manage triggers: https://claude.ai/code/scheduled

## GitHub Repo

Private repo: `https://github.com/tylerm08martinez-wq/gambling`
All picks are version-controlled here. The remote triggers clone this repo, run research, append to `picks.json`, and push.

## Notes

- Tyler's bankroll and unit size tracked in `bet-log.md`
- Output sharp picks or analysis to this folder; finalized strategy frameworks → Second Brain `decisions/`
