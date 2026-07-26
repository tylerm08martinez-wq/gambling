# Measurement Mode: Minimum Stakes, Flat Sizing, and a Pre-Registered Resume Condition

Until [[De-vigged CLV]] is positive across at least **100 Measured-CLV picks**, this project runs as a measurement program: **minimum real stakes ($1–2), flat 1u sizing, no bankroll deployment.** The resume condition is fixed here, in advance, and is not to be revised while a result is pending.

**Context:** after 81 graded picks over 74 days there is no measured edge, and — more importantly — no working instrument to detect one.

The record, corrected for a data defect found on 2026-07-25 (four picks logged with the bet in the `line` field, so their true prices were never recorded and they were paid out at an assumed −110):

| Slice | n | Record | Win% | ROI |
|---|---|---|---|---|
| All graded | 81 | 44-37 | 54.3% | +3.3% |
| **Known prices only** | **77** | **40-37** | **51.9%** | **−2.8%** |

The entire positive headline rested on those four assumed-price rows. On bets whose price is actually known, the book is slightly below the ~52.4% breakeven. The two largest samples are the negative ones: player props — the declared Primary Edge — at −12.6% (n=54), and `cross_book_gap`, its mechanism, at −9.9% (n=38).

De-vig CLV reads **+0.03% over 18 picks**: not negative, *absent*. And CLV Coverage is **22%** against the 90% CONTEXT.md already requires before ROI is treated as mature. That combination is the real finding — it is not "the strategy is losing", it is "a good strategy running badly and a bad strategy are currently indistinguishable, because the diagnostic is broken."

Detecting a true 55% from breakeven on results alone needs roughly 2,300 bets. CLV answers the same question far sooner, which is exactly why the framework designates it the process signal — but only if it is measured. Coverage is therefore the binding constraint on learning anything, and ADR 0010's closing-line capture exists to lift it.

Bankroll size makes this urgent rather than academic: at $10/unit on a $300 bankroll, the 2026-07-04 → 07-19 drawdown of ~18.7u was about 62% of the bankroll — from variance alone, on a strategy whose measured edge is zero. A bankroll that small can be destroyed by noise long before the sample is large enough to say anything.

**Considered Options:** keep betting normally and accept the variance; stop betting entirely and log paper picks; minimum real stakes with flat sizing; pause logging until the CLV pipeline is fixed.

Pure paper was rejected on one specific ground: paper picks drift. Without real fills, a logged price may be one that was never actually available — a stale line, a limit that would have been refused, a book that would have cut the account — which silently inflates both CLV and the record with no way to notice. Minimum stakes keep every logged price honest while making the bankroll irrelevant to the outcome. Pausing logging was rejected because it forfeits the sample; the whole point is to accumulate measured picks.

**Decision:** stake $1–2 per pick, flat 1u sizing on every pick regardless of score, and no bankroll deployment. Score gates whether to bet, never how much — it ran backwards over 81 picks (2u picks 46.3%, 1u picks 62.5%, r = −0.163, p = 0.18) and sizing on it cost ~6.5u against flat. Both betting skills now hard-cap at 1u.

**Resume condition, fixed in advance:** deploy meaningful stakes only when de-vig CLV is positive across **≥100 Measured-CLV picks**. Not win rate, not ROI, not a hot streak — CLV, on the de-vigged metric, at that sample size. Pre-registering this while the data is cold is the point: the failure mode being guarded against is a lucky fortnight being read as vindication after the fact.

**Consequences:** the project stops being a betting operation and becomes a measurement one until the evidence justifies otherwise, which is the honest reading of the current data. Nothing about the machinery changes — picks are still generated, logged, resolved and scored daily, so the sample grows at the same rate. What changes is that the outcome no longer costs anything material while the question is open. The cost is real: at ~1 pick/day, 100 measured picks is months away, and if closing-line capture underperforms it is longer still. That delay is the price of not having measured CLV for the first 81 picks. This ADR should be revisited when the resume condition is met, or if de-vig CLV is clearly *negative* across 100 picks — which would be an answer too, and a reason to stop rather than continue.
