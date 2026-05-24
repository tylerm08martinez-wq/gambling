# Validate Primary Edge Before Logging Picks

Scheduled pick logging must validate the structured **Primary Edge** before writing to `picks.json`. The human-readable `primary_edge` text remains for dashboard readability and betting review, but validation uses structured edge type and source evidence fields because parsing freeform edge descriptions would be brittle and would let bad or stale source evidence quietly enter the tracker.

**Considered Options:** parse `primary_edge` text directly; replace `primary_edge` with structured fields only; keep readable `primary_edge` and add structured validation fields.

**Decision:** keep readable `primary_edge` and add structured fields such as `primary_edge_type`, `source_evidence`, `validation_status`, and `validation_notes`. Run validation at the `tracker.py log` write boundary so every normal path into `picks.json` is protected.

**Consequences:** automated scheduled runs reject candidates whose **Primary Edge** fails its **Signal Requirement** and cannot override validation. Manual runs may show rejected candidates for review and may override only with a written reason, which is stored in `validation_notes`. Rejected candidates are recorded outside `picks.json` so they can be audited without affecting betting statistics.
