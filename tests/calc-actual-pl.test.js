'use strict';
const assert = require('assert');

// Verbatim from dashboard.html ~lines 1181-1194
function calcActualPL(pick, stake, actualOdds) {
  if (!pick.result || pick.result === null || stake == null) return null;
  let odds;
  if (actualOdds != null) {
    odds = actualOdds;
  } else {
    const oddsMatch = (pick.line || '').match(/([+-]?\d{2,4})/);
    odds = oddsMatch ? parseInt(oddsMatch[1]) : -110;
  }
  if (pick.result === 'win') return odds > 0 ? stake * (odds / 100) : stake * (100 / Math.abs(odds));
  if (pick.result === 'loss') return -stake;
  if (pick.result === 'push') return 0;
  return null;
}

// win with positive odds (+120)
assert.strictEqual(calcActualPL({ result: 'win', line: '+120 @ FanDuel' }, 100, null), 120);

// win with negative odds (-110)
assert.ok(Math.abs(calcActualPL({ result: 'win', line: '-110 @ DraftKings' }, 110, null) - 100) < 0.001);

// loss
assert.strictEqual(calcActualPL({ result: 'loss', line: '-110 @ DraftKings' }, 50, null), -50);

// push
assert.strictEqual(calcActualPL({ result: 'push', line: '-110 @ DraftKings' }, 50, null), 0);

// null result (unsettled)
assert.strictEqual(calcActualPL({ result: null, line: '+120 @ FanDuel' }, 100, null), null);

// no result field at all
assert.strictEqual(calcActualPL({ line: '+120 @ FanDuel' }, 100, null), null);

// actualOdds override used when provided (different from pick.line)
// pick.line says +120 but actual was +115
assert.ok(Math.abs(calcActualPL({ result: 'win', line: '+120 @ FanDuel' }, 100, 115) - 115) < 0.001);

// actualOdds override with negative odds
assert.ok(Math.abs(calcActualPL({ result: 'win', line: '+120 @ FanDuel' }, 110, -115) - (110 * 100 / 115)) < 0.001);

// fallback to pick.line when actualOdds is null
assert.strictEqual(calcActualPL({ result: 'win', line: '+200 @ BetMGM' }, 50, null), 100);

// fallback to pick.line when actualOdds is undefined
assert.strictEqual(calcActualPL({ result: 'win', line: '+200 @ BetMGM' }, 50, undefined), 100);

console.log('All calcActualPL tests passed.');
