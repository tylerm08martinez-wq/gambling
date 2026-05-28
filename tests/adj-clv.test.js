'use strict';
const assert = require('assert');

// Verbatim from dashboard.html ~lines 1170-1179
function impliedProb(odds) {
  return odds > 0 ? 100 / (odds + 100) : Math.abs(odds) / (Math.abs(odds) + 100);
}

function adjClv(pick, actualOdds) {
  const closingMatch = (pick.closing_line || '').match(/([+-]?\d{2,4})/);
  if (!closingMatch || actualOdds == null) return null;
  const closingOdds = parseInt(closingMatch[1]);
  if (!closingOdds) return null;
  return ((impliedProb(closingOdds) - impliedProb(actualOdds)) / impliedProb(actualOdds) * 100).toFixed(2);
}

// --- impliedProb ---

// positive odds: 100 / (120 + 100) = 0.4545...
assert.ok(Math.abs(impliedProb(120) - (100 / 220)) < 0.0001);

// negative odds: 110 / (110 + 100) = 0.5238...
assert.ok(Math.abs(impliedProb(-110) - (110 / 210)) < 0.0001);

// --- adjClv ---

// null when closing_line absent
assert.strictEqual(adjClv({ line: '+120 @ FanDuel' }, 115), null);

// null when closing_line unparseable
assert.strictEqual(adjClv({ closing_line: 'OFF' }, 115), null);

// null when actualOdds is null
assert.strictEqual(adjClv({ closing_line: '-110' }, null), null);

// null when actualOdds is undefined
assert.strictEqual(adjClv({ closing_line: '-110' }, undefined), null);

// correct result when both are valid
// closing -110 (~52.38%), actual -110 → CLV = 0.00%
assert.strictEqual(adjClv({ closing_line: '-110 @ close' }, -110), '0.00');

// positive adj CLV: actual odds better than closing (you got +120, closed at +100)
// impliedProb(100)=0.5, impliedProb(120)=0.4545 → (0.5-0.4545)/0.4545*100 ≈ +10.00
const posAdj = parseFloat(adjClv({ closing_line: '+100' }, 120));
assert.ok(posAdj > 0, `Expected positive adj CLV, got ${posAdj}`);

// negative adj CLV: actual odds worse than closing (you got -120, closed at +100)
// impliedProb(100)=0.5, impliedProb(-120)=0.5455 → (0.5-0.5455)/0.5455*100 ≈ -8.33
const negAdj = parseFloat(adjClv({ closing_line: '+100' }, -120));
assert.ok(negAdj < 0, `Expected negative adj CLV, got ${negAdj}`);

console.log('All impliedProb / adjClv tests passed.');
