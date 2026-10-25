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
#      The only channel that reaches you off-machine.
#   2. Windows toast — no secret required, but only visible at this console.
#   3. scripts/.LAST-RUN-FAILED sentinel — always written; cleared on next success.
# NOTE (2026-07-25): the old fallback here was `claude -p` posting to Slack. That is
# useless by construction — `claude` is the single most likely thing to be broken, and
# on 2026-06-03 it was: the CLI began failing with "Credit balance is too low" and the
# alert path died with it. 48 consecutive failed runs went unreported for 53 days.
# Every channel below is therefore independent of the claude binary.
notify_failure() {
  local msg="$1"
  local delivered=0

  # 1. Slack incoming webhook — preferred; the only channel that reaches you off-machine.
  local hook_file="$HOME/.config/bet-picks/slack-webhook"
  if [ -s "$hook_file" ]; then
    curl -sf -m 15 -X POST -H 'Content-type: application/json' \
      --data "{\"text\":$(printf '%s' "$msg" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))')}" \
      "$(tr -d '[:space:]' < "$hook_file")" >/dev/null 2>&1 && delivered=1
  fi

  # 2. Windows toast — visible on this host without any secret to configure.
  powershell.exe -NoProfile -Command "
    [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType=WindowsRuntime] > \$null
    \$t=[Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent(
         [Windows.UI.Notifications.ToastTemplateType]::ToastText02)
    \$t.GetElementsByTagName('text').Item(0).AppendChild(\$t.CreateTextNode('Daily Bet Picks FAILED')) > \$null
    \$t.GetElementsByTagName('text').Item(1).AppendChild(\$t.CreateTextNode('$(printf '%s' "$msg" | tr -d "'" | cut -c1-160)')) > \$null
    [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('Daily Bet Picks').Show(
      [Windows.UI.Notifications.ToastNotification]::new(\$t))
  " >/dev/null 2>&1 && delivered=1

  # 3. Sentinel file — last resort, always works, and gives any later run/dashboard
  #    something durable to read. Cleared on the next successful run.
  printf '%s\n' "$msg" > "$PROJECT_DIR/scripts/.LAST-RUN-FAILED"

  [ "$delivered" -eq 1 ] || echo "⚠️  all remote alert channels failed; wrote scripts/.LAST-RUN-FAILED" | tee -a "$LOG"
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

# Shared lock with capture-closes.sh (every 15 min, including 09:00): it writes
# closing_lines.json, which the pull below autostashes and the backfill commit stages.
# Held for the pull + backfill + commit/push only, then released BEFORE the long claude
# step so captures for 9:15-10:00 starts (NFL Sunday 10am kickoffs) are not skipped.
# capture-closes waits for nothing (flock -n); this side waits up to 10 minutes, longer
# than capture's own 300s timeout. No flock (stock macOS) = run unlocked, as before.
TRACKER_LOCK="$PROJECT_DIR/scripts/.tracker.lock"
if command -v flock >/dev/null 2>&1; then
  exec 9>"$TRACKER_LOCK"
  if ! flock -w 600 9; then
    echo "❌ scripts/.tracker.lock still held after 10 min — aborting before git pull" | tee -a "$LOG"
    exit 1
  fi
else
  echo "⚠️  flock not found — pull/backfill run without scripts/.tracker.lock" | tee -a "$LOG"
fi

# --autostash is load-bearing, not defensive: capture-closes.sh deliberately
# leaves closing_lines.json uncommitted (see its header), and the CLV backfill
# below dirties picks.json. This pull therefore ALWAYS runs against a dirty
# tree by design. Without --autostash it aborts with "cannot pull with rebase:
# You have unstaged changes" and takes the whole run with it - which is exactly
# what happened every day from 2026-07-27 to 2026-08-21.
git pull --rebase --autostash origin main 2>&1 | tee -a "$LOG"

# Backfill realized CLV on YESTERDAY's now-settled player props from the BettingPros
# consensus close. This MUST run here (residential IP) — BettingPros 403s the datacenter,
# so it can't live in the nightly cloud resolver (ADR 0006). The nightly resolver settled
# yesterday's picks at 11pm; their closing lines are now frozen and matchable. Idempotent:
# only fills picks with a null closing_line, leaves un-matchable ones Unmeasured.
YESTERDAY="$(TZ='MST7' date -v-1d +%F 2>/dev/null || TZ='MST7' date -d 'yesterday' +%F)"
echo "ℹ️  Backfilling realized CLV for $YESTERDAY..." | tee -a "$LOG"
if python3 "$PROJECT_DIR/.agents/skills/bet-tracker/tracker.py" \
     backfill-clv --date "$YESTERDAY" --apply 2>&1 | tee -a "$LOG" | grep -q "Backfilled"; then
  # closing_lines.json rides along: capture-closes writes it locally every ~15 min but
  # deliberately doesn't commit (that cadence would be commit spam), so this is where
  # the captured closes get durably recorded alongside the CLV they produced.
  git add .agents/skills/bet-tracker/picks.json .agents/skills/bet-tracker/closing_lines.json
  git commit -m "chore: backfill realized CLV for $YESTERDAY" 2>&1 | tee -a "$LOG" || true
  # Push failures used to be swallowed by `|| true`, which stranded the 2026-07-16 and
  # 2026-07-19 CLV commits on local main for over a week while the dashboard — which
  # reads origin/main via the GitHub Contents API — served stale CLV. Alert instead.
  if ! git push origin main 2>&1 | tee -a "$LOG"; then
    notify_failure "⚠️ Daily Bet Picks: CLV backfill for $YESTERDAY committed locally but PUSH FAILED on $(hostname). Dashboard is serving stale CLV until this is pushed."
  fi
fi

# Release the tracker lock (see above) before the long-running claude step.
exec 9>&-

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
V3_SKILL="$PROJECT_DIR/.agents/skills/sports-betting-value/SKILL.md"
if [ "${V3_VALUE_ENABLED:-0}" = "1" ]; then
  # Fail loud on a missing skill file instead of handing the agent a path that doesn't
  # exist (#108): alert, skip only the V3 step, and let V1/V2 run.
  if [ -f "$V3_SKILL" ]; then
    V3_STEP='3. Then read .agents/skills/sports-betting-value/SKILL.md in full and execute it the same way (run AFTER V1 and V2 so it respects the shared daily cap: 7 total, 3 per model). It logs with --model v3-value and --primary-edge-type clv_value.
'
    echo "ℹ️  V3-Value ENABLED for this run." | tee -a "$LOG"
  else
    V3_STEP=''
    echo "❌ V3_VALUE_ENABLED=1 but $V3_SKILL does not exist — V3 step SKIPPED." | tee -a "$LOG"
    notify_failure "🚨 Daily Bet Picks: V3_VALUE_ENABLED=1 on $(hostname) but .agents/skills/sports-betting-value/SKILL.md is missing. V3 was skipped; V1/V2 continue."
  fi
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

# --- V3 Observation Scan (ADR 0011, #108) -----------------------------------
# Deterministic, no model call, independent of V3_VALUE_ENABLED. Writes candidates to
# v3-observations.json, never picks.json. It runs as an `if` condition so a failure
# (exit 2 = zero offers on every market / no events; anything else = a crash) can't
# abort the picks run under `set -e`: it alerts and V1/V2 carry on. The file is
# committed even after a failed scan, because the failed run row is what the
# week-end review (#110) counts. Only that one path is committed.
V3_OBS=".agents/skills/bet-tracker/v3-observations.json"
echo "ℹ️  V3 Observation Scan for $TODAY..." | tee -a "$LOG"
if python3 "$PROJECT_DIR/.agents/skills/bet-tracker/v3_scan.py" --date "$TODAY" --apply 2>&1 | tee -a "$LOG"; then
  echo "✅ V3 Observation Scan completed." | tee -a "$LOG"
else
  echo "❌ V3 Observation Scan FAILED — continuing with V1/V2." | tee -a "$LOG"
  notify_failure "⚠️ Daily Bet Picks: V3 Observation Scan for $TODAY FAILED on $(hostname). V1/V2 picks continue. Check scripts/.run-daily-picks.log."
fi
# Push the observations commit. A rejected push (origin moved since the morning pull)
# gets one rebase + retry. A failed retry must never leave the checkout mid-rebase on a
# detached HEAD: `claude -p` would then log and commit picks there. So any failure
# aborts the rebase and checks HEAD is back on main.
# Returns 0 pushed; 1 push failed but HEAD is on main (alerted, picks continue);
# 2 HEAD could not be restored to main (alerted; the caller must stop the run).
v3_push_observations() {
  # TODO(#112): take scripts/.tracker.lock around this retry once #112 lands
  if git push origin main 2>&1 | tee -a "$LOG"; then
    return 0
  fi
  if git pull --rebase --autostash origin main 2>&1 | tee -a "$LOG" \
     && git push origin main 2>&1 | tee -a "$LOG"; then
    return 0
  fi
  git rebase --abort 2>/dev/null || true
  if [ "$(git symbolic-ref -q --short HEAD || true)" != "main" ]; then
    git checkout -q main 2>/dev/null || true
  fi
  if [ "$(git symbolic-ref -q --short HEAD || true)" != "main" ]; then
    notify_failure "🚨 Daily Bet Picks: V3 observations push retry left $(hostname) OFF main (HEAD: $(git rev-parse --short HEAD 2>/dev/null || echo '?')). Run STOPPED before the picks agent — fix the checkout by hand."
    return 2
  fi
  notify_failure "⚠️ Daily Bet Picks: V3 observations for $TODAY committed locally but PUSH FAILED (after a rebase retry) on $(hostname). HEAD is on main; picks continue."
  return 1
}
if [ -f "$V3_OBS" ] && [ -n "$(git status --porcelain -- "$V3_OBS")" ]; then
  git add -- "$V3_OBS"
  git commit -m "chore: V3 observation scan for $TODAY" -- "$V3_OBS" 2>&1 | tee -a "$LOG" || true
  v3_push_rc=0
  v3_push_observations || v3_push_rc=$?
  if [ "$v3_push_rc" -eq 2 ]; then
    echo "❌ HEAD is not on main after the V3 push retry — stopping before claude -p." | tee -a "$LOG"
    exit 1
  fi
fi
# ---------------------------------------------------------------------------

# Headless/unattended: no TTY to approve tool prompts, so skip permission prompts.
# Safe here — this is your own machine running your own repo's skills, which have
# their own guardrails (never hand-edit picks.json, fail-loud, tracker-only commits).
claude -p "$PROMPT" --dangerously-skip-permissions 2>&1 | tee -a "$LOG"

# --- Success heartbeat ------------------------------------------------------
# Without this, "0 picks today" (a valid outcome), "the agent crashed", and "the PC
# was asleep" are indistinguishable from outside the log — which is how 48 failed runs
# hid for 53 days. A run that reaches here genuinely completed, so record proof:
# a machine-readable status file, and clear the failure sentinel.
UNPUSHED="$(git rev-list --count origin/main..main 2>/dev/null || echo '?')"
PICKS_TODAY="$(python3 -c "
import json
try:
    d=json.load(open('.agents/skills/bet-tracker/picks.json'))
    p=d['picks'] if isinstance(d,dict) and 'picks' in d else d
    print(sum(1 for x in p if str(x.get('date',''))[:10]=='$TODAY'))
except Exception:
    print('?')
" 2>/dev/null || echo '?')"

rm -f "$PROJECT_DIR/scripts/.LAST-RUN-FAILED"
cat > "$PROJECT_DIR/scripts/.last-run-status.json" <<JSON
{"date":"$TODAY","completed_at":"$(date '+%Y-%m-%dT%H:%M:%S%z')","host":"$(hostname)","status":"ok","picks_logged":"$PICKS_TODAY","unpushed_commits":"$UNPUSHED"}
JSON

if [ "$UNPUSHED" != "0" ] && [ "$UNPUSHED" != "?" ]; then
  notify_failure "⚠️ Daily Bet Picks completed on $(hostname) but $UNPUSHED commit(s) are UNPUSHED — dashboard will serve stale data."
fi

echo "$TODAY" > "$STAMP"
echo "=== done $(date '+%H:%M %Z') — picks_logged=$PICKS_TODAY unpushed=$UNPUSHED ===" | tee -a "$LOG"
