# Canonical Edge Type Taxonomy

The dashboard and tracker classify picks by edge using a canonical, structured **Primary Edge Type** field. The human-readable `primary_edge` text is retained for review context but is not the authoritative category.

**Context:** ADR-0001 established a dual-field approach (readable `primary_edge` + structured fields like `primary_edge_type`) but left the canonical taxonomy unspecified. The dashboard's Edge filter and Edge Breakdown view were parsing the freeform `primary_edge` text, which produced a category for every minor wording change (e.g. "E-Rod elite home SP (3-0…" and "Sharp vs public split: 9…" appearing as truncated, distinct edges).

**Considered Options:** parse freeform `primary_edge` text (current, brittle); replace freeform with structured-only (clean but loses review context); keep both with structured as canonical (chosen).

**Decision:** the canonical Primary Edge Type values are: `cross_book_gap`, `steam`, `hard_rlm`, `soft_rlm`, `ats_trend`, `quant_convergence`, `pitching_edge`, `prop_trend`, `matchup_edge`, `plus_money_start`, `underdog_fade`. New picks must populate `primary_edge_type` with one of these values. Dashboard categorization (filter dropdown, Edge Breakdown grouping) reads `primary_edge_type` and falls back to parsing freeform `primary_edge` only for legacy picks without a structured type.

**Consequences:** existing picks logged before this ADR have null `primary_edge_type` and continue to be categorized via the legacy text-parsing path until backfilled. Adding a new edge type requires updating the canonical list in this ADR, the `tracker.py` validation, and the dashboard. The two-field design means logging must keep readable and structured fields in sync, but loose phrasing in `primary_edge` no longer fragments the dashboard taxonomy.
