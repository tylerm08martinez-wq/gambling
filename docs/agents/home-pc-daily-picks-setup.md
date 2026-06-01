# Set up automatic Daily Bet Picks on the home PC

**For the agent running on Tyler's home PC.** The Daily Bet Picks routine was moved off the Anthropic cloud because its data source (BettingPros cross-book props — the Primary Edge) 403s from datacenter IPs and only works from a residential IP (ADR 0006). Your job: make `scripts/run-daily-picks.sh` fire automatically ~9:00am America/Phoenix (AZ, UTC-7, no DST), verify it, then disable the old cloud trigger.

Detect this machine's OS and follow the matching section. Do **not** invent a new research process — the script just runs the two skills as written.

## 1. Preconditions (verify first, fix if missing)
- `python3`, `git`, and the `claude` CLI are on PATH.
- Git can push to `origin main` non-interactively (cached credential / token / SSH key).
- **Slack MCP is configured** in Claude Code on this machine (the skills post to `#bet-picks`; without it picks still log+push but the Slack post no-ops).
- This host is on a **residential** connection. Confirm BettingPros is reachable:
  ```bash
  python3 .agents/skills/bet-tracker/bettingpros.py props MLB | python3 -c "import sys,json;print('props:',len(json.load(sys.stdin)))"
  ```
  Expect ~1500. If it 403s/errors, this IP is also blocked — stop and tell Tyler.

## 2. Smoke-test the runner once (attended)
```bash
bash scripts/run-daily-picks.sh
```
Watch `scripts/.run-daily-picks.log`. Confirm: both skills ran, picks logged via `tracker.py` (or a clean fail-loud sit-out), pushed to `origin main`, and posted to `#bet-picks`. If the headless `claude -p` blocks on anything, the `--dangerously-skip-permissions` flag in the script should prevent it — if not, investigate before scheduling. The script self-guards against double-runs via `scripts/.last-run-date` (delete it to force a re-test).

## 3. Schedule ~9:00am AZ

**Compute the local time** that equals 9:00am AZ on this machine (AZ is UTC-7 year-round; adjust for this PC's timezone + its DST).

### Windows (Task Scheduler, runs the .sh via git-bash)
Create a daily task. Program: the git-bash binary (e.g. `C:\Program Files\Git\bin\bash.exe`); Arguments: `-lc "cd /c/path/to/gambling && bash scripts/run-daily-picks.sh"`. Set the trigger to the local time matching 9:00am AZ, "Run whether user is logged on or not", and (optional) a wake timer so the PC wakes for it. Verify with: Task Scheduler → Run, then check the log + `#bet-picks`.

### macOS (launchd)
Write `~/Library/LaunchAgents/com.tyler.daily-picks.plist` with `ProgramArguments` = `["/bin/bash","/Users/.../gambling/scripts/run-daily-picks.sh"]`, a `StartCalendarInterval` at the local hour matching 9am AZ, and `StandardOut/ErrorPath` to a log. `launchctl load` it. Optionally `pmset repeat wake` so the Mac wakes before the run.

## 4. After a real scheduled run posts picks
Disable the retired cloud trigger so it stops posting "BettingPros API unavailable" each morning — ask Tyler to confirm, then it can be turned off at https://claude.ai/code/routines (trigger `trig_01SkNEk48CK981znKJPaHb47`), or have an agent with RemoteTrigger access set `enabled: false`.

## Guardrails
- The skills own their git pull/commit/push of tracker files — don't commit anything else.
- Never hand-edit `picks.json`; always go through `tracker.py` (`python3`).
- 0 picks is a valid outcome (V2 especially). Fail-loud + sit-out is correct when the feed is empty — never fabricate.
