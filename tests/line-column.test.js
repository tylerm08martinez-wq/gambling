'use strict';
const assert = require('assert');

// Extracted from the inline IIFEs in dashboard.html ~lines 1853 and 2592.
// Both Pick Log and My Bets Log use identical logic; one function covers both.
function renderLineCell(line, actualOdds) {
  const loggedMatch = (line || '').match(/([+-]?\d{2,4})/);
  const loggedNum = loggedMatch ? parseInt(loggedMatch[1]) : null;
  if (actualOdds != null && actualOdds !== loggedNum) {
    const a = actualOdds;
    return `<span style="font-weight:600">${a > 0 ? '+' : ''}${a}</span> <span style="color:var(--muted);font-size:10px;text-decoration:line-through">${loggedNum != null ? (loggedNum > 0 ? '+' : '') + loggedNum : ''}</span>`;
  }
  return line || '—';
}

// actual_odds set and differs from logged → dual-display
const dual = renderLineCell('+120 @ FanDuel', 115);
assert.ok(dual.includes('+115'), `Expected actual odds "+115" in: ${dual}`);
assert.ok(dual.includes('+120'), `Expected logged odds "+120" in: ${dual}`);
assert.ok(dual.includes('line-through'), `Expected struck-through logged odds in: ${dual}`);
assert.ok(dual.includes('font-weight:600'), `Expected bold actual odds in: ${dual}`);

// actual_odds is null → returns original line string unchanged
assert.strictEqual(renderLineCell('+120 @ FanDuel', null), '+120 @ FanDuel');

// actual_odds matches logged odds exactly → returns original line string unchanged
assert.strictEqual(renderLineCell('+120 @ FanDuel', 120), '+120 @ FanDuel');

// positive actual odds render with leading '+'
const posActual = renderLineCell('-110 @ DraftKings', 115);
assert.ok(posActual.includes('+115'), `Positive actual odds should have leading "+": ${posActual}`);

// negative actual odds render without '+'
const negActual = renderLineCell('+120 @ FanDuel', -115);
assert.ok(negActual.includes('-115'), `Negative actual odds should not have "+": ${negActual}`);
assert.ok(!negActual.includes('+-115'), `Negative actual odds must not have "+-115": ${negActual}`);

// empty line fallback
assert.strictEqual(renderLineCell('', null), '—');
assert.strictEqual(renderLineCell(null, null), '—');

console.log('All line-column rendering tests passed.');
