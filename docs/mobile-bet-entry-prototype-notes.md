# Mobile Bet Entry Prototype Notes

Question: Which mobile quick-bet flow keeps entry fastest without hiding the important betting context?

How to review:

```text
http://localhost:8090/dashboard.html?entryVariant=A
```

Variants:

- `A` - Fast sheet: closest to the current flow, with line/book context visible before entry.
- `B` - Preset ladder: amount-first flow with Kelly, half-Kelly, and 1% bankroll shortcuts.
- `C` - Review card: compact confirmation summary before amount entry.

Verdict:

```text
Variant B won. Promote the amount-first sheet with Kelly, half-Kelly, and 1% bankroll presets; remove the A/C branches and prototype switcher.
```
