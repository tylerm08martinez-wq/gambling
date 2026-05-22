#!/bin/bash
# resolve-and-push — auto-resolve open picks, show stats, commit, push
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
TRACKER="$PROJECT_DIR/.agents/skills/bet-tracker/tracker.py"
PICKS="$PROJECT_DIR/.agents/skills/bet-tracker/picks.json"
INTEL="$PROJECT_DIR/.agents/skills/bet-tracker/betting-intel.md"

cd "$PROJECT_DIR"

echo "🔍 Resolving open picks..."
python3 "$TRACKER" auto-resolve

echo ""
echo "📊 Updated stats:"
python3 "$TRACKER" stats

echo ""
echo "📦 Staging changes..."
git add "$PICKS" "$INTEL" 2>/dev/null || git add "$PICKS"

if git diff --cached --quiet; then
  echo "✅ Nothing to commit — no picks resolved."
  exit 0
fi

DATE=$(date '+%Y-%m-%d')
git commit -m "Auto-resolve picks $DATE"

echo ""
echo "🚀 Pushing..."
git pull --rebase origin main
git push origin main

echo ""
echo "✅ Done."
