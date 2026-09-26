@AGENTS.md

# Gambling — Claude-specific additions

Shared rules for every coding agent live in `AGENTS.md` (imported above). Only Claude Code-specific rules go here.

## Development Workflow — Claude skills

**Support tools (not part of the chain):**

- `/zoom-out` — run *before* `/to-prd` when about to work in unfamiliar code, so the PRD is grounded.
- `/improve-codebase-architecture` — periodic codebase health audit (HTML report); recommendations *feed* `/to-prd`; run between feature cycles, not during one.
- `/write-a-skill` → `/skill-optimizer` — for building new skills, not code features.
