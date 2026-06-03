// parseBet unit tests for the Live Peek module (issue #73).
// Run: node tests/parse-bet.test.mjs
//
// Asserts EXTERNAL behavior — the parsed shape of a bet string — never internal
// regex structure. The committed test target per the PRD (most logic, no network).
// Covers: the pitcher-parenthetical trap, both stat orderings, the N+ form,
// opponent-hint extraction, prop/game-line/moneyline classification, and that
// every current picks.json bet string classifies without throwing.

import assert from 'node:assert';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { parseBet, gradeOverUnder, fallbackLink, livePeek } from '../live-peek.js';

const __dirname = dirname(fileURLToPath(import.meta.url));
let passed = 0;
const check = (label, fn) => { fn(); passed++; if (process.env.VERBOSE) console.log('  ok:', label); };

// ── The pitcher-parenthetical trap — both real examples ────────────────────
check('Phillies total: pitcher paren stripped, total classified, line/side read', () => {
  const p = parseBet({ bet: 'Under 9 Phillies at Dodgers (Painter vs Yamamoto)', sport: 'MLB' });
  assert.strictEqual(p.kind, 'total');
  assert.strictEqual(p.side, 'under');
  assert.strictEqual(p.line, 9);
  // Pitcher names must NOT leak into team hints.
  assert.ok(!p.teamHints.join(' ').toLowerCase().includes('painter'), 'Painter leaked into hints');
  assert.ok(!p.teamHints.join(' ').toLowerCase().includes('yamamoto'), 'Yamamoto leaked into hints');
  // Opponent hint after "at" is the Dodgers.
  assert.ok(p.teamHints.some(h => /dodgers/i.test(h)), `expected Dodgers in hints, got ${JSON.stringify(p.teamHints)}`);
});

check('Aranda prop: pitcher paren stripped, prop classified, player/stat/side/line correct', () => {
  const p = parseBet({ bet: 'Jonathan Aranda Total Bases Over 1.5 vs Tigers (Madden)', sport: 'MLB' });
  assert.strictEqual(p.kind, 'prop');
  assert.strictEqual(p.player, 'Jonathan Aranda');
  assert.strictEqual(p.statKeyword, 'total bases');
  assert.strictEqual(p.statKey, 'totalBases');   // DIRECT boxscore field (ADR 0004), not derived
  assert.strictEqual(p.group, 'batting');
  assert.strictEqual(p.side, 'over');
  assert.strictEqual(p.line, 1.5);
  // "Madden" (pitcher) must not be a team hint; "Tigers" (opponent) must be.
  assert.ok(!p.player.toLowerCase().includes('madden'), 'Madden leaked into player');
  assert.ok(p.teamHints.some(h => /tigers/i.test(h)), `expected Tigers hint, got ${JSON.stringify(p.teamHints)}`);
});

// ── Both stat orderings ────────────────────────────────────────────────────
check('ordering A: "Player Stat Over N"', () => {
  const p = parseBet({ bet: 'Christian Yelich Hits Over 0.5 vs Giants (Roupp)', sport: 'MLB' });
  assert.strictEqual(p.kind, 'prop');
  assert.strictEqual(p.player, 'Christian Yelich');
  assert.strictEqual(p.statKey, 'hits');
  assert.strictEqual(p.side, 'over');
  assert.strictEqual(p.line, 0.5);
});

check('ordering B: "Player Over N Stat"', () => {
  const p = parseBet({ bet: 'Zack Wheeler OVER 5.5 strikeouts vs Cleveland Guardians', sport: 'MLB' });
  assert.strictEqual(p.kind, 'prop');
  assert.strictEqual(p.player, 'Zack Wheeler');
  assert.strictEqual(p.statKey, 'strikeOuts');
  assert.strictEqual(p.group, 'pitching');        // strikeouts read from the pitching line
  assert.strictEqual(p.side, 'over');
  assert.strictEqual(p.line, 5.5);
});

// ── The N+ form (means Over N-0.5) ─────────────────────────────────────────
check('N+ form: "Nico Hoerner 2+ Total Bases" → over 1.5', () => {
  const p = parseBet({ bet: 'Nico Hoerner 2+ Total Bases (Cubs vs Braves)', sport: 'MLB' });
  assert.strictEqual(p.kind, 'prop');
  assert.strictEqual(p.player, 'Nico Hoerner');
  assert.strictEqual(p.statKey, 'totalBases');
  assert.strictEqual(p.side, 'over');
  assert.strictEqual(p.line, 1.5);                // 2+ ⇒ Over 1.5
});

// ── Combined-stat props route to fallback, not a confident wrong grade (#4) ─
check('combined stat "Hits+Runs+RBIs" flagged combined, not graded as a single stat', () => {
  const p = parseBet({ bet: 'Aaron Judge Hits+Runs+RBIs Over 1.5 vs Red Sox', sport: 'MLB' });
  assert.strictEqual(p.kind, 'prop');
  assert.strictEqual(p.combined, true, 'expected combined:true');
  assert.strictEqual(p.statKey, null, 'combined stat must not resolve to a single statKey');
  assert.ok(/judge/i.test(p.player), `player should still parse, got ${JSON.stringify(p.player)}`);
});
check('combined stat with spaces "Runs + RBIs" also flagged combined', () => {
  const p = parseBet({ bet: 'Mookie Betts Runs + RBIs Over 1.5 vs Padres', sport: 'MLB' });
  assert.strictEqual(p.combined, true);
  assert.strictEqual(p.statKey, null);
});
check('N+ line ("2+ Total Bases") is NOT mistaken for a combined stat', () => {
  const p = parseBet({ bet: 'Nico Hoerner 2+ Total Bases (Cubs vs Braves)', sport: 'MLB' });
  assert.notStrictEqual(p.combined, true, 'N+ form must not be flagged combined');
  assert.strictEqual(p.statKey, 'totalBases');
  assert.strictEqual(p.line, 1.5);
});

// ── Opponent-hint extraction (vs / at / @) ─────────────────────────────────
check('opponent hint after "vs"', () => {
  const p = parseBet({ bet: 'Taj Bradley Over 5.5 Strikeouts vs Pittsburgh Pirates', sport: 'MLB' });
  assert.ok(p.teamHints.some(h => /pirates/i.test(h)), JSON.stringify(p.teamHints));
});
check('opponent hint after "@"', () => {
  const p = parseBet({ bet: 'Nathan Eovaldi Over 6.5 Strikeouts (Rangers @ Angels)', sport: 'MLB' });
  // paren stripped → no explicit vs/at/@ outside it → no opponent hint, but must still parse as prop
  assert.strictEqual(p.kind, 'prop');
  assert.strictEqual(p.player, 'Nathan Eovaldi');
});
check('opponent hint after "at" (game total)', () => {
  const p = parseBet({ bet: 'Under 8.5 Mariners at Royals (Kauffman Stadium)', sport: 'MLB' });
  assert.strictEqual(p.kind, 'total');
  assert.ok(p.teamHints.some(h => /royals/i.test(h)), JSON.stringify(p.teamHints));
});

// ── Classification: prop / total / moneyline / spread ──────────────────────
check('moneyline classified', () => {
  const p = parseBet({ bet: 'New York Mets ML vs New York Yankees', sport: 'MLB' });
  assert.strictEqual(p.kind, 'moneyline');
  assert.ok(p.teamHints.some(h => /mets/i.test(h)));
});
check('spread classified', () => {
  const p = parseBet({ bet: 'San Antonio Spurs +6.5 vs Oklahoma City Thunder (WCF Game 1)', sport: 'NBA' });
  assert.strictEqual(p.kind, 'spread');
});
check('total classified (over)', () => {
  const p = parseBet({ bet: 'Over 8.5 Giants vs Diamondbacks (at Chase Field)', sport: 'MLB' });
  assert.strictEqual(p.kind, 'total');
  assert.strictEqual(p.side, 'over');
  assert.strictEqual(p.line, 8.5);
});

// ── grader sanity (push/win/loss) ──────────────────────────────────────────
check('grader: value===line → push', () => assert.strictEqual(gradeOverUnder(5, 'over', 5), 'push'));
check('grader: over win', () => assert.strictEqual(gradeOverUnder(2, 'over', 1.5), 'win'));
check('grader: over loss (Aranda 0 vs Over 1.5)', () => assert.strictEqual(gradeOverUnder(0, 'over', 1.5), 'loss'));
check('grader: under win', () => assert.strictEqual(gradeOverUnder(3, 'under', 5.5), 'win'));
check('grader: null value → ungradeable', () => assert.strictEqual(gradeOverUnder(null, 'over', 1.5), 'ungradeable'));

// ── fallbackLink: prop → StatMuse, game-line → ESPN ────────────────────────
check('fallbackLink: prop → StatMuse', () => {
  const u = fallbackLink({ bet: 'Taj Bradley Over 5.5 Strikeouts vs Pittsburgh Pirates', sport: 'MLB', date: '2026-05-30' });
  assert.ok(u.includes('statmuse.com'), u);
});
check('fallbackLink: game-line → ESPN scoreboard', () => {
  const u = fallbackLink({ bet: 'Under 9 Phillies at Dodgers (Painter vs Yamamoto)', sport: 'MLB', date: '2026-05-31' });
  assert.ok(u.includes('espn.com') && u.includes('20260531'), u);
});

// ── Every current picks.json bet string classifies without throwing ────────
check('all current picks.json strings classify without throwing', () => {
  const raw = JSON.parse(readFileSync(join(__dirname, '..', '.agents', 'skills', 'bet-tracker', 'picks.json'), 'utf8'));
  const all = raw.picks || raw;
  const validKinds = new Set(['prop', 'total', 'moneyline', 'spread', 'other']);
  for (const pick of all) {
    let parsed;
    assert.doesNotThrow(() => { parsed = parseBet(pick); }, `threw on: ${pick.bet}`);
    assert.ok(validKinds.has(parsed.kind), `bad kind "${parsed.kind}" for: ${pick.bet}`);
    if (parsed.kind === 'prop') {
      assert.ok(parsed.player && parsed.player.length > 1, `empty player for prop: ${pick.bet}`);
      assert.ok(parsed.statKey, `missing statKey for prop: ${pick.bet}`);
    }
  }
  if (process.env.VERBOSE) console.log(`  swept ${all.length} picks`);
});

// ── livePeek orchestrator: combined stat degrades to fallback, never fetches (#4) ──
// A fake source that throws if touched — proves the combined-stat bet short-circuits to
// the deep-link fallback before any network grading is attempted.
const explodingSource = {
  findGame() { throw new Error('source.findGame should not be called for a combined stat'); },
  fetchBoxscore() { throw new Error('source.fetchBoxscore should not be called for a combined stat'); },
  findPlayerStat() { throw new Error('source.findPlayerStat should not be called for a combined stat'); },
};

const asyncChecks = [
  async () => {
    const res = await livePeek(
      { bet: 'Aaron Judge Hits+Runs+RBIs Over 1.5 vs Red Sox', sport: 'MLB', date: '2026-06-01', result: null },
      explodingSource,
    );
    assert.strictEqual(res.state, 'fallback', `combined stat should fall back, got ${res.state}`);
    assert.ok(res.url && res.url.includes('statmuse.com'), `prop fallback should be StatMuse, got ${res.url}`);
    passed++;
  },
];

const run = async () => {
  for (const fn of asyncChecks) await fn();
  console.log(`All parseBet tests passed (${passed} cases).`);
};
run().catch(err => { console.error(err); process.exit(1); });
