#!/bin/bash
# capture-closes — snapshot two-way closing lines for picks about to start.
#
# Runs on a SHORT interval (every ~15 min) through the day, unlike the once-daily jobs.
# Each pass captures only picks inside the window and keeps whichever snapshot lands
# closest to first pitch, so games starting at 10:40am and 7:10pm are both caught
# without needing a schedule per game.
#
# HOME PC ONLY: BettingPros 403s datacenter IPs (ADR 0006), same constraint as the
# morning picks run.
#
# Writes .agents/skills/bet-tracker/closing_lines.json locally and does NOT commit —
# at a 15-minute cadence that would be commit spam. The morning run picks the file up
# and commits it alongside the CLV backfill, which is also the only consumer (backfill
# is residential-only too, so nothing in the cloud needs this file).
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR" || exit 1

LOG="$PROJECT_DIR/scripts/.capture-closes.log"

# Only run during plausible game hours (AZ). Outside them every pass is a guaranteed
# no-op that still costs a BettingPros round trip. 'MST7' not 'America/Phoenix' —
# git-bash ships no zoneinfo DB and named zones silently fall back to UTC.
HOUR=$(TZ='MST7' date +%H)
if [ "$HOUR" -lt 8 ] || [ "$HOUR" -gt 21 ]; then
  exit 0
fi

out=$(timeout 300 python3 "$PROJECT_DIR/.agents/skills/bet-tracker/tracker.py" \
        capture-closes --window-minutes 45 --apply 2>&1)
rc=$?

# Log only when something happened or something broke. A quiet no-op pass every 15
# minutes for 13 hours a day would bury the signal in its own noise.
if [ $rc -ne 0 ] || echo "$out" | grep -q "📸"; then
  {
    echo "=== $(TZ='MST7' date '+%Y-%m-%d %H:%M') capture-closes (exit $rc) ==="
    echo "$out"
  } >> "$LOG"
fi

# A persistent failure here degrades CLV coverage silently — the exact class of
# slow-rotting breakage that hid the 53-day picks outage. Surface it through the same
# sentinel the session health check reads.
if [ $rc -ne 0 ]; then
  echo "capture-closes failed at $(TZ='MST7' date '+%Y-%m-%d %H:%M') (exit $rc) — CLV coverage will degrade. See scripts/.capture-closes.log" \
    > "$PROJECT_DIR/scripts/.CAPTURE-FAILED"
else
  rm -f "$PROJECT_DIR/scripts/.CAPTURE-FAILED"
fi

exit 0
