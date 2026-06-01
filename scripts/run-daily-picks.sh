#!/bin/bash
# run-daily-picks — runs the V1-Trends + V2-Sharp betting routine on the HOME PC
# (residential IP), because BettingPros (the cross-book props source = Primary Edge)
# 403s from datacenter/cloud IPs (ADR 0006). Schedule this ~9am AZ via launchd
# (macOS) or Task Scheduler (Windows git-bash). The skills handle their own
# tracker.py logging, git push, and #bet-picks Slack post.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

LOG="$PROJECT_DIR/scripts/.run-daily-picks.log"
echo "=== $(date '+%Y-%m-%d %H:%M %Z') run-daily-picks ===" | tee -a "$LOG"

# Fail loud if the BettingPros props feed isn't reachable from THIS host — if it
# 403s here too, this machine's IP is also blocked and there is nothing to run.
if ! python3 "$PROJECT_DIR/.agents/skills/bet-tracker/bettingpros.py" props MLB >/dev/null 2>&1; then
  echo "❌ BettingPros props unreachable from this host — aborting (is this a residential IP?)" | tee -a "$LOG"
  exit 1
fi

git pull --rebase origin main 2>&1 | tee -a "$LOG"

# The routine prompt: execute both skills exactly as written. Mirrors the retired
# cloud trigger's prompt. Requires the `claude` CLI + Slack MCP configured on this host.
PROMPT='You are the Daily Bet Picks agent. Generate today'\''s V1-Trends and V2-Sharp betting picks by executing the project'\''s two betting skills exactly as written, then confirm the results pushed to GitHub. The repo is the current working directory. Always use python3.

1. Read .agents/skills/sports-betting/SKILL.md in full and execute every step in order (Step 0 context pull, research via the BettingPros client/extractor, logging via tracker.py with --run-type scheduled + --primary-edge-type + --source-evidence-json, git push, Slack post to #bet-picks).
2. Then read .agents/skills/sports-betting-sharp/SKILL.md in full and execute it the same way (run AFTER V1 so it respects the shared daily cap).
3. Verify both pushes landed on origin/main; retry any missing push. Print a summary of V1/V2 pick counts and cap usage. 0 picks is a valid outcome.

Do NOT fabricate games/lines/odds. Do NOT lower the bar to fill the card. Do NOT edit picks.json by hand. Do NOT commit anything but tracker-managed files.'

claude -p "$PROMPT" 2>&1 | tee -a "$LOG"

echo "=== done $(date '+%H:%M %Z') ===" | tee -a "$LOG"
