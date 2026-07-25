#!/bin/bash
# session-health-check — surface a broken daily-picks runner the moment a Claude Code
# session opens in this repo.
#
# WHY THIS EXISTS: the 9am picks job failed 48 times over 53 days (2026-06-03 →
# 2026-07-25) and nobody noticed, because a failed run is *silent from the outside* —
# the skills only post to Slack on SUCCESS, and the failure alert used to route through
# the very `claude` binary that was broken. The log said "Credit balance is too low"
# every morning and no human ever read it.
#
# This is the cheapest possible backstop: you cannot open this project without being
# told the runner is down. It reads only local state (no network, no API), so it can
# never itself be the thing that's broken.
#
# Exit code is always 0 — a health check must never block a session from starting.
set -uo pipefail

cd "$(git rev-parse --show-toplevel 2>/dev/null)" 2>/dev/null || exit 0

STATUS="scripts/.last-run-status.json"
SENTINEL="scripts/.LAST-RUN-FAILED"
PICKS=".agents/skills/bet-tracker/picks.json"
STALE_HOURS=36          # ~1.5 daily cycles: one missed morning is noise, two is a fault

now=$(date +%s)

# 1. An explicit failure from the last run always wins.
if [ -f "$SENTINEL" ]; then
  echo "🚨 [gambling] DAILY PICKS RUNNER FAILED"
  echo "   $(head -c 300 "$SENTINEL")"
  echo "   → see scripts/.run-daily-picks.log; clear scripts/.LAST-RUN-FAILED once fixed."
  exit 0
fi

# 2. No heartbeat at all, or a stale one. Distinguishes "never completed since the
#    heartbeat was added" from "completed, but not recently".
if [ ! -f "$STATUS" ]; then
  echo "⚠️  [gambling] no run heartbeat yet ($STATUS missing) — the 9am picks job has"
  echo "   not completed successfully since the heartbeat was added. First clean run"
  echo "   will create it."
else
  mtime=$(stat -c %Y "$STATUS" 2>/dev/null || stat -f %m "$STATUS" 2>/dev/null || echo 0)
  age_h=$(( (now - mtime) / 3600 ))
  if [ "$mtime" -gt 0 ] && [ "$age_h" -ge "$STALE_HOURS" ]; then
    echo "⚠️  [gambling] daily picks heartbeat is ${age_h}h old (threshold ${STALE_HOURS}h)."
    echo "   Last: $(head -c 200 "$STATUS")"
    echo "   → is the PC awake at 9am AZ? check scripts/.run-daily-picks.log"
  fi
fi

# 3. Unpushed commits mean the dashboard is serving stale data — this stranded two CLV
#    backfills for over a week when the credential store was broken.
if git rev-parse --abbrev-ref '@{u}' >/dev/null 2>&1; then
  unpushed=$(git rev-list --count '@{u}'..HEAD 2>/dev/null || echo 0)
  [ "${unpushed:-0}" -gt 0 ] && \
    echo "⚠️  [gambling] $unpushed unpushed commit(s) — dashboard reads origin, so it is stale."
fi

# 4. Open picks whose game date has passed and that the nightly resolver never settled.
#    Zombies silently shrink the settled denominator every stat is computed over.
if [ -f "$PICKS" ]; then
  python3 - "$PICKS" <<'PY' 2>/dev/null || true
import json, sys
from datetime import date, timedelta
try:
    raw = json.load(open(sys.argv[1], encoding="utf-8"))
    picks = raw["picks"] if isinstance(raw, dict) and "picks" in raw else raw
except Exception:
    sys.exit(0)
cutoff = str(date.today() - timedelta(days=2))
stale = [p for p in picks if p.get("result") is None and str(p.get("date", ""))[:10] < cutoff]
if stale:
    print(f"⚠️  [gambling] {len(stale)} pick(s) unresolved >2 days after game date:")
    for p in stale[:5]:
        print(f"     {p.get('date')}  {p.get('id')}")
    if len(stale) > 5:
        print(f"     … and {len(stale) - 5} more")
    print("   → python3 .agents/skills/bet-tracker/tracker.py auto-resolve")
PY
fi

exit 0
