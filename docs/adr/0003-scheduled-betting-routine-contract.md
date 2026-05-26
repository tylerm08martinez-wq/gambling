# Scheduled Betting Routine Contract

Scheduled betting runs must optimize for **CLV-Positive +EV Candidates**, not pre-game "high-ROI picks." ROI is a retrospective scoreboard; the scheduled routine's job is to log only auditable candidates whose current market price appears mispriced.

**Considered Options:** keep scheduled runs prompt-only and rely on agent judgment; require perfect source evidence for every edge before logging; require structured edge type plus at least one usable current source for every scheduled pick, with stricter evidence rules for high-risk edge types; cap the slate at 4 total picks; cap the slate at 5 total picks with no per-model limit; cap the slate at 5 total picks with a 3-pick per-model cap.

**Decision:** scheduled runs must log through `tracker.py log --run-type scheduled` and must include a canonical `primary_edge_type` plus structured `source_evidence`. The minimum scheduled contract is one usable, fresh, named source supporting the primary edge. Edge-specific requirements may be stricter; Hard RLM already requires usable public ticket data and usable line movement data. Expert/model consensus may support a scheduled pick, but it is not a standalone Primary Edge; scheduled picks need market confirmation such as CLV, cross-book gaps, hard RLM, steam, or line value. The daily cap is 5 total picks, with no more than 3 V1-Trends picks and no more than 3 V2-Sharp picks. There is no minimum pick count.

**Trust Metric:** every pick should capture pre-bet price evidence at log time, and every settled pick should attempt Measured CLV at resolution. ROI is not considered a mature trust signal until CLV Coverage reaches at least 90% of settled picks.

**Follow-up:** nightly resolver hardening is required to make the trust metric reliable, especially for props, totals, and measured CLV. This ADR does not claim that resolution coverage is complete.

**Consequences:** scheduled runs will produce fewer but more auditable picks. Missing structured evidence becomes a rejected candidate rather than a logged pick. Manual runs remain available for human-reviewed exceptions, but scheduled runs cannot override validation. The cap leaves room for rare strong slates while preventing either model from flooding the card. The routine may continue logging picks before CLV automation is perfect, but ROI claims must remain provisional until the CLV coverage threshold is met.
