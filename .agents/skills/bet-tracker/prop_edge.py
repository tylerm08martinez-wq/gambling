"""Prop-edge extractor — pure functions over a normalized BettingPros prop.

Translates one normalized prop (the shape `bettingpros.fetch_props` returns) into a
betting candidate carrying the detected signal, the side/line/book to bet, and the
canonical `primary_edge_type` (CONTEXT.md). No I/O — fully table-testable.

Signals (slice 2 of #48):
- **Cross-Book Prop Gap** — the best available line differs from the consensus line by
  ≥ GAP_THRESHOLD units. A lower line favors the over (a lower bar to clear); a higher
  line favors the under. The stale book offering that line is the bet target.
- **Prop Trend Confirmation** — the model's `projection.recommended_side` agrees with
  the gap side (a confirming bonus, not a standalone scheduled-run edge).
"""

GAP_THRESHOLD = 0.5
# BettingPros bet_rating is 1–5; ≥4 is a strong model lean. Used only for a standalone
# prop_trend edge when no cross-book gap exists.
STRONG_RATING = 4


def _no_signal(prop):
    return {
        "market_id": prop.get("market_id"),
        "event_id": prop.get("event_id"),
        "player": prop.get("player"),
        "primary_edge_type": None,
        "side": None,
        "bet_line": None,
        "bet_book": None,
        "gap": 0.0,
        "ev": None,
        "trend_confirmed": False,
    }


def extract_prop_edge(prop: dict) -> dict:
    """Return a candidate for `prop` (primary_edge_type None when nothing qualifies)."""
    over, under = prop.get("over", {}), prop.get("under", {})
    consensus = over.get("consensus_line")
    line = over.get("line")
    candidate = _no_signal(prop)
    if consensus is None or line is None:
        return candidate

    rec = (prop.get("projection") or {}).get("recommended_side")
    gap = round(abs(line - consensus), 2)
    if gap >= GAP_THRESHOLD:
        # Lower best line than consensus → over edge; higher → under edge.
        side = "over" if line < consensus else "under"
        chosen = over if side == "over" else under
        candidate.update(
            primary_edge_type="cross_book_gap",
            side=side,
            bet_line=chosen.get("line"),
            bet_book=chosen.get("book"),
            gap=gap,
            ev=chosen.get("ev"),
            # Prop Trend Confirmation: the model's pick agrees with the gap side.
            trend_confirmed=(rec == side),
        )
        return candidate

    # No cross-book gap. A strongly-rated projection stands alone as a prop_trend edge.
    chosen = over if rec == "over" else under if rec == "under" else None
    if chosen is not None and (chosen.get("bet_rating") or 0) >= STRONG_RATING:
        candidate.update(
            primary_edge_type="prop_trend",
            side=rec,
            bet_line=chosen.get("line"),
            bet_book=chosen.get("book"),
            ev=chosen.get("ev"),
            trend_confirmed=True,
        )
    return candidate


def select_edges(props):
    """Map a list of normalized props to the candidates that carry a signal,
    biggest cross-book gap first (then prop_trend). The skill's research entry point."""
    cands = [extract_prop_edge(p) for p in props]
    signalled = [c for c in cands if c["primary_edge_type"]]
    return sorted(signalled, key=lambda c: (c["gap"], c["trend_confirmed"]), reverse=True)


if __name__ == "__main__":
    import json
    import sys
    props = json.load(sys.stdin)
    json.dump(select_edges(props), sys.stdout, indent=1)
