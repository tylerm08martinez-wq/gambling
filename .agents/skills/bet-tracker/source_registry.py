"""Canonical Source Registry parser (issue #58, Source Health / parent #47).

Single machine-readable source of truth for the V2-Sharp Step 2 (Game Line
Research) feed list, extracted out of `sports-betting-sharp/SKILL.md` prose.
Sources are role-keyed (primary_splits, secondary_splits, line_movement, stale)
and sport-aware. The skills and Source Health tooling read the registry through
`load_registry`.

Fail-loud by design: a malformed registry raises rather than silently returning
empty lists (an empty feed list would make the skill sit out for the wrong
reason). The parser also enforces the invariant that no URL appears in both an
active list and the stale/never-fetch list — a source cannot be live and dead at
once, and that contradiction must surface, not be swallowed.
"""

import json
from pathlib import Path

# The canonical registry file lives beside this parser.
REGISTRY_FILE = Path(__file__).with_name("source_registry.json")

# The active (fetchable) roles plus the stale never-fetch list. Every one of
# these keys must be present in a well-formed registry.
ACTIVE_ROLES = ("primary_splits", "secondary_splits", "line_movement")
REQUIRED_ROLES = ACTIVE_ROLES + ("stale",)


class RegistryError(ValueError):
    """Raised when the registry is malformed or violates an invariant."""


def _normalize_url(url):
    """Normalize a URL/identifier for cross-list comparison.

    Lowercase, strip the scheme and a leading ``www.``, and drop a trailing
    slash. Comparison is on the WHOLE path, not the host alone — so a specific
    page (``dknetwork.draftkings.com/draftkings-sportsbook-betting-splits``)
    and a bare-host stale entry (``dknetwork.draftkings.com``) are correctly
    distinct, while the literal same URL in two lists collides.
    """
    u = url.strip().lower()
    u = u.split("://", 1)[-1]  # drop scheme if present
    if u.startswith("www."):
        u = u[4:]
    return u.rstrip("/")


def load_registry(path=None):
    """Parse the registry and return the role-keyed source lists.

    Returns a dict with keys primary_splits, secondary_splits, line_movement,
    and stale, each mapping to a list of source entries (dicts).

    Raises RegistryError on invalid JSON, a missing/mis-typed role, or a URL
    that appears in both an active list and the stale list. Never returns
    empty lists in place of failing.
    """
    path = Path(path) if path is not None else REGISTRY_FILE
    try:
        raw = json.loads(path.read_text())
    except FileNotFoundError as e:
        raise RegistryError(f"registry file not found: {path}") from e
    except json.JSONDecodeError as e:
        raise RegistryError(f"registry is not valid JSON ({path}): {e}") from e

    if not isinstance(raw, dict):
        raise RegistryError(f"registry must be a JSON object, got {type(raw).__name__}")

    reg = {}
    for role in REQUIRED_ROLES:
        if role not in raw:
            raise RegistryError(f"registry missing required role: {role!r}")
        if not isinstance(raw[role], list):
            raise RegistryError(f"role {role!r} must be a list, got {type(raw[role]).__name__}")
        reg[role] = raw[role]

    _check_no_active_stale_collision(reg)
    return reg


def _entry_url(entry, role):
    """Pull the URL string out of a source entry, failing loud on bad shape."""
    if not isinstance(entry, dict) or "url" not in entry or not isinstance(entry["url"], str):
        raise RegistryError(f"role {role!r} has an entry without a string 'url': {entry!r}")
    return entry["url"]


def _check_no_active_stale_collision(reg):
    """A URL cannot be both live and never-fetch. Surface the contradiction."""
    stale_urls = {_normalize_url(_entry_url(e, "stale")) for e in reg["stale"]}
    for role in ACTIVE_ROLES:
        for entry in reg[role]:
            norm = _normalize_url(_entry_url(entry, role))
            if norm in stale_urls:
                raise RegistryError(
                    f"URL appears in both active role {role!r} and the stale list: {norm!r}"
                )
