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
STAMP="$PROJECT_DIR/scripts/.last-run-date"

# --- Failure alerting -------------------------------------------------------
# A scheduled run that aborts (feed 403, claude crash, push fail) would otherwise
# be silent — the skills only post to #bet-picks on SUCCESS. This trap fires on any
# non-zero exit so a failed morning is never silent.
#
# Mechanism, in order of robustness:
#   1. Slack incoming webhook (plain curl, no deps) — put the URL in
#      ~/.config/bet-picks/slack-webhook (one line, outside the repo, never commit it).
#   2. Fallback: claude -p Slack MCP post — works for feed/push failures, but NOT if
#      claude itself is the thing that broke. That's why the webhook is preferred.
notify_failure() {
  local msg="$1"
  local hook_file="$HOME/.config/bet-picks/slack-webhook"
  if [ -f "$hook_file" ]; then
    curl -s -X POST -H 'Content-type: application/json' \
      --data "{\"text\":\"$msg\"}" "$(cat "$hook_file")" >/dev/null 2>&1 && return 0
  fi
  claude -p "Post exactly this message to the #bet-picks Slack channel and nothing else: $msg" \
    --dangerously-skip-permissions >/dev/null 2>&1 || true
}
on_exit() {
  local rc=$?
  if [ "$rc" -ne 0 ]; then
    notify_failure "🚨 Daily Bet Picks FAILED on $(hostname) at $(date '+%Y-%m-%d %H:%M %Z') (exit $rc). No picks posted today — check scripts/.run-daily-picks.log."
  fi
}
trap on_exit EXIT
# ---------------------------------------------------------------------------

echo "=== $(date '+%Y-%m-%d %H:%M %Z') run-daily-picks ===" | tee -a "$LOG"

# Idempotence guard: don't run twice for the same AZ date (the skills also dedup
# via their Step 0, but this avoids wasted headless runs on a re-fire).
# NOTE: use POSIX 'MST7' (Mountain Standard, 7h west of UTC, no DST = Arizona),
# NOT 'America/Phoenix' — git-bash/MSYS2 ships no zoneinfo DB, so named zones
# silently fall back to UTC. With UTC the guard rolls over at 5pm AZ and a second
# same-day run after 5pm sails past the guard (burned 2026-06-01).
TODAY="$(TZ='MST7' date +%F)"
if [ -f "$STAMP" ] && [ "$(cat "$STAMP")" = "$TODAY" ]; then
  echo "✅ Already ran for $TODAY — skipping." | tee -a "$LOG"; exit 0
fi

# Fail loud if the BettingPros props feed isn't reachable from THIS host — if it
# 403s here too, this machine's IP is also blocked and there is nothing to run.
if ! python3 "$PROJECT_DIR/.agents/skills/bet-tracker/bettingpros.py" props MLB >/dev/null 2>&1; then
  echo "❌ BettingPros props unreachable from this host — aborting (is this a residential IP?)" | tee -a "$LOG"
  exit 1
fi

git pull --rebase origin main 2>&1 | tee -a "$LOG"

# Backfill realized CLV on YESTERDAY's now-settled player props from the BettingPros
# consensus close. This MUST run here (residential IP) — BettingPros 403s the datacenter,
# so it can't live in the nightly cloud resolver (ADR 0006). The nightly resolver settled
# yesterday's picks at 11pm; their closing lines are now frozen and matchable. Idempotent:
# only fills picks with a null closing_line, leaves un-matchable ones Unmeasured.
YESTERDAY="$(TZ='MST7' date -v-1d +%F 2>/dev/null || TZ='MST7' date -d 'yesterday' +%F)"
echo "ℹ️  Backfilling realized CLV for $YESTERDAY..." | tee -a "$LOG"
if python3 "$PROJECT_DIR/.agents/skills/bet-tracker/tracker.py" \
     backfill-clv --date "$YESTERDAY" --apply 2>&1 | tee -a "$LOG" | grep -q "Backfilled"; then
  git add .agents/skills/bet-tracker/picks.json
  git commit -m "chore: backfill realized CLV for $YESTERDAY" 2>&1 | tee -a "$LOG" || true
  git push origin main 2>&1 | tee -a "$LOG" || true
fi

# The routine prompt: execute the betting skills exactly as written. Mirrors the
# retired cloud trigger's prompt. Requires the `claude` CLI + Slack MCP on this host.
#
# V3-Value (CLV/+EV de-vig model, ADR 0007) is GATED OFF by default — it is still
# incubating in the experiments lab. Activate by exporting V3_VALUE_ENABLED=1 in the
# scheduler's environment, but ONLY after BOTH prerequisites are met:
#   1. its autoeval loop is green (the engine de-vigs correctly), and
#   2. a runnable copy exists on THIS host — either graduated into ~/.claude/skills
#      or forked to .agents/skills/sports-betting-value/ (the path referenced below).
# Until then V3 logs nothing live, so a mis-computed pick can't pollute the CLV ledger.
if [ "${V3_VALUE_ENABLED:-0}" = "1" ]; then
  V3_STEP='3. Then read .agents/skills/sports-betting-value/SKILL.md in full and execute it the same way (run AFTER V1 and V2 so it respects the shared daily cap: 7 total, 3 per model). It logs with --model v3-value and --primary-edge-type clv_value.
'
  echo "ℹ️  V3-Value ENABLED for this run." | tee -a "$LOG"
else
  V3_STEP=''
  echo "ℹ️  V3-Value gated OFF (export V3_VALUE_ENABLED=1 after the autoeval pass + a host copy exists)." | tee -a "$LOG"
fi

PROMPT_HEAD='You are the Daily Bet Picks agent. Generate today'\''s betting picks by executing the project'\''s betting skills exactly as written, then confirm the results pushed to GitHub. The repo is the current working directory. Always use python3.

1. Read .agents/skills/sports-betting/SKILL.md in full and execute every step in order (Step 0 context pull, research via the BettingPros client/extractor, logging via tracker.py with --run-type scheduled + --primary-edge-type + --source-evidence-json, git push, Slack post to #bet-picks).
2. Then read .agents/skills/sports-betting-sharp/SKILL.md in full and execute it the same way (run AFTER V1 so it respects the shared daily cap).
'
PROMPT_TAIL='Finally, verify all pushes landed on origin/main; retry any missing push. Print a summary of pick counts and cap usage. 0 picks is a valid outcome.

Do NOT fabricate games/lines/odds. Do NOT lower the bar to fill the card. Do NOT edit picks.json by hand. Do NOT commit anything but tracker-managed files.'

PROMPT="${PROMPT_HEAD}${V3_STEP}${PROMPT_TAIL}"

# Headless/unattended: no TTY to approve tool prompts, so skip permission prompts.
# Safe here — this is your own machine running your own repo's skills, which have
# their own guardrails (never hand-edit picks.json, fail-loud, tracker-only commits).
claude -p "$PROMPT" --dangerously-skip-permissions 2>&1 | tee -a "$LOG"

echo "$TODAY" > "$STAMP"
echo "=== done $(date '+%H:%M %Z') ===" | tee -a "$LOG"
