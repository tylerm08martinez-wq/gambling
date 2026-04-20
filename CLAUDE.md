# Sports Betting — Decision Support

This folder is for analyzing sports bets and building a framework for making smarter wagering decisions.

## Purpose

Help Tyler identify +EV (positive expected value) betting opportunities across sports using data, line movement, and situational analysis.

## Approach

- Focus on **value**, not just picking winners — a bad line on a favorite is worse than a good line on an underdog
- Track all bets (win/loss, odds, stake, result) to measure actual vs. expected performance over time
- Use sharp money indicators, line movement, and public betting % to contextualize picks
- Avoid emotional bets (favorite teams, recency bias, chasing losses)

## Sports in Scope

- NFL / College Football
- NBA / College Basketball
- MLB
- Add others as needed

## Bet Types

- Moneyline
- Spread
- Totals (over/under)
- Player props
- Parlays (use sparingly — only when legs are correlated or independently strong)

## Skills

| Skill | Purpose |
|-------|---------|
| `/sports-betting` | V1-Trends: picks using ATS trends, expert consensus, situational angles, line movement |
| `/sports-betting-sharp` | V2-Sharp: picks using sharp money, steam moves, reverse line movement only — high selectivity |
| `/bet-tracker` | Log picks, record results, and compare ROI between V1 and V2 models |

All picks are stored in `.claude/skills/bet-tracker/picks.json`. Use `/bet-tracker stats` to see the full performance dashboard.

## Key Concepts to Apply

- **Closing line value (CLV):** Did the line move in your direction after you bet? Consistent CLV = good process
- **Kelly Criterion:** Size bets proportionally to edge — avoid overbetting
- **Bankroll:** Track as units, not dollars, to stay disciplined
- **Fade the public:** Heavy public sides often move lines away from value

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
