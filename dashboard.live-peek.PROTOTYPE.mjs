// ============================================================================
// PROTOTYPE — throwaway. Validates the Live Peek fetch-and-grade pipeline
// against the LIVE MLB Stats API before folding the logic into dashboard.html.
// Run:  node dashboard.live-peek.PROTOTYPE.mjs
// Question it answers: does parse -> find game -> fetch boxscore -> map stat ->
// grade actually work end-to-end for the two real picks? (ADR 0007 / CONTEXT Live Peek)
// Delete me once the answer is captured in NOTES.
// ============================================================================

// --- resolver stat-map (mirror of ADR 0004; total bases is a DIRECT boxscore field) ---
const STAT_MAP = {
  'total bases': 'totalBases',
  'strikeouts':  'strikeOuts',   // pitching
  'hits':        'hits',
  'rbi':         'rbi',
  'rbis':        'rbi',
  'runs':        'runs',
  'home runs':   'homeRuns',
  'doubles':     'doubles',
  'triples':     'triples',
  'walks':       'baseOnBalls',
  'stolen bases':'stolenBases',
};
// which boxscore group each stat lives in
const PITCHING_STATS = new Set(['strikeOuts']);
const STAT_KEYS = Object.keys(STAT_MAP).sort((a, b) => b.length - a.length); // longest first

// ---------------------------------------------------------------------------
// 1. CLASSIFY + PARSE
// ---------------------------------------------------------------------------
function parseBet(pick) {
  const bet = pick.bet || '';
  // strip the trailing "(...)" pitcher/venue parenthetical so it can't be mistaken for teams
  const core = bet.replace(/\s*\([^)]*\)\s*$/, '').trim();

  const ouMatch = core.match(/\b(over|under)\b\s+([\d.]+)/i);
  const side = ouMatch ? ouMatch[1].toLowerCase() : null;
  const line = ouMatch ? parseFloat(ouMatch[2]) : (pick.line_num ?? null);

  // opponent / teams = text after vs|at|@
  const oppMatch = core.match(/\b(?:vs\.?|at|@)\s+(.+)$/i);
  const opponent = oppMatch ? oppMatch[1].trim() : null;

  // does the bet name a player stat keyword?
  const lc = core.toLowerCase();
  const statKeyword = STAT_KEYS.find(k => lc.includes(k)) || null;

  if (statKeyword) {
    // PROP: isolate the player name by removing opp clause, the over/under clause, and the stat keyword
    let s = core;
    if (oppMatch) s = s.replace(/\s+(?:vs\.?|at|@)\s+.+$/i, '');
    s = s.replace(new RegExp(statKeyword, 'i'), ' ');
    s = s.replace(/\b(over|under)\b\s+[\d.]+/i, ' ');
    s = s.replace(/\b\d+\+/g, ' '); // N+ form
    const player = s.replace(/\s+/g, ' ').trim();
    return {
      kind: 'prop', player, statKeyword,
      statKey: STAT_MAP[statKeyword],
      group: PITCHING_STATS.has(STAT_MAP[statKeyword]) ? 'pitching' : 'batting',
      side: side || 'over', line,
      teamHints: opponent ? splitTeams(opponent) : [],
    };
  }

  // GAME-LINE: total if it has Over/Under, else spread/ml (not fetched in this proto)
  // teams = core minus the leading "Over/Under N"
  let teamsText = core.replace(/^\s*(over|under)\s+[\d.]+\s*/i, '');
  teamsText = teamsText.replace(/\b(?:vs\.?|at|@)\b/gi, ' ');
  return {
    kind: side ? 'total' : 'other',
    side, line,
    teamHints: splitTeams(teamsText),
  };
}
function splitTeams(t) {
  return t.split(/\s+(?:vs\.?|at|@|and|,)\s+|\s+/i)
    .map(x => x.trim()).filter(Boolean)
    // keep only "team-like" tokens (Capitalized words), drop stray junk
    .filter(x => /^[A-Z]/.test(x));
}

// ---------------------------------------------------------------------------
// 2. MLB Stats API — find game + boxscore
// ---------------------------------------------------------------------------
async function mlbFindGame(date, teamHints) {
  const url = `https://statsapi.mlb.com/api/v1/schedule?sportId=1&date=${date}`;
  const r = await fetch(url, { headers: { 'User-Agent': 'live-peek-proto' } });
  const j = await r.json();
  const games = (j.dates?.[0]?.games) || [];
  const hintLc = teamHints.map(h => h.toLowerCase());
  const match = games.find(g => {
    const names = [g.teams.away.team.name, g.teams.home.team.name].map(n => n.toLowerCase());
    return hintLc.some(h => names.some(n => n.includes(h)));
  });
  return match ? {
    gamePk: match.gamePk,
    status: match.status.detailedState,
    away: match.teams.away.team.name, awayR: match.teams.away.score,
    home: match.teams.home.team.name, homeR: match.teams.home.score,
  } : null;
}
async function mlbBoxscore(gamePk) {
  const url = `https://statsapi.mlb.com/api/v1/game/${gamePk}/boxscore`;
  const r = await fetch(url, { headers: { 'User-Agent': 'live-peek-proto' } });
  return r.json();
}
function findPlayerStat(box, playerName, group, statKey) {
  const wantLast = playerName.toLowerCase().split(/\s+/).pop();
  for (const sideKey of ['away', 'home']) {
    const players = box.teams[sideKey].players || {};
    for (const pid of Object.keys(players)) {
      const pl = players[pid];
      const full = (pl.person?.fullName || '').toLowerCase();
      if (full === playerName.toLowerCase() || full.split(/\s+/).pop() === wantLast) {
        const val = pl.stats?.[group]?.[statKey];
        return { matchedName: pl.person.fullName, value: val ?? null,
                 hasStatGroup: !!pl.stats?.[group] };
      }
    }
  }
  return null;
}

// ---------------------------------------------------------------------------
// 3. GRADE
// ---------------------------------------------------------------------------
function gradeOverUnder(value, side, line) {
  if (value == null || line == null) return 'ungradeable';
  if (value === line) return 'push';
  const over = value > line;
  return (side === 'over') === over ? 'win' : 'loss';
}

// ---------------------------------------------------------------------------
// 4. THE STATE MACHINE — what 🔍 will do per pick
// ---------------------------------------------------------------------------
async function livePeek(pick) {
  const log = (...a) => console.log('   ', ...a);
  console.log(`\n🔍  ${pick.bet}`);
  console.log(`    [${pick.sport} · ${pick.date} · stored result=${pick.result ?? 'null'}]`);

  // STATE A: settled -> show stored, no fetch
  if (pick.result) {
    log(`STATE: SETTLED → inline panel from stored data (no fetch)`);
    if (pick.final_score) {
      const nums = (pick.final_score.match(/\d+/g) || []).map(Number);
      const total = nums.reduce((a, b) => a + b, 0);
      log(`final: ${pick.final_score}  (total ${total})`);
      if (pick.line_num != null) {
        const g = gradeOverUnder(total, /under/i.test(pick.bet) ? 'under' : 'over', pick.line_num);
        log(`→ ${pick.bet.match(/over|under/i)?.[0] || ''} ${pick.line_num}  ${g.toUpperCase()}  (stored: ${pick.result.toUpperCase()})`);
      }
    }
    return;
  }

  // STATE B: unsettled. MLB/NBA -> fetch & grade. Else -> deep-link.
  if (pick.sport !== 'MLB' && pick.sport !== 'NBA') {
    log(`STATE: UNSETTLED, ${pick.sport} (no adapter) → deep-link fallback`);
    return;
  }
  if (pick.sport === 'NBA') {
    log(`STATE: UNSETTLED NBA → ESPN adapter (not built in this proto) → would fetch`);
    return;
  }

  const parsed = parseBet(pick);
  log(`PARSE:`, JSON.stringify(parsed));

  const game = await mlbFindGame(pick.date, parsed.teamHints);
  if (!game) { log(`✗ no game matched hints ${JSON.stringify(parsed.teamHints)} → fallback link`); return; }
  log(`GAME: pk=${game.gamePk} [${game.status}]  ${game.away} ${game.awayR} @ ${game.home} ${game.homeR}`);

  if (parsed.kind === 'prop') {
    const box = await mlbBoxscore(game.gamePk);
    const hit = findPlayerStat(box, parsed.player, parsed.group, parsed.statKey);
    if (!hit) { log(`✗ player "${parsed.player}" not found → fallback link`); return; }
    log(`PLAYER: ${hit.matchedName}  ${parsed.statKey}=${hit.value}`);
    const grade = gradeOverUnder(hit.value, parsed.side, parsed.line);
    const live = !/final/i.test(game.status);
    log(`→ ${parsed.player} ${hit.value} ${parsed.statKeyword}  ${parsed.side} ${parsed.line}  ${grade.toUpperCase()}${live ? '  ⏳ IN PROGRESS' : ''}`);
  } else if (parsed.kind === 'total') {
    const total = (game.awayR ?? 0) + (game.homeR ?? 0);
    const grade = gradeOverUnder(total, parsed.side, parsed.line);
    const live = !/final/i.test(game.status);
    log(`→ total ${total}  ${parsed.side} ${parsed.line}  ${grade.toUpperCase()}${live ? '  ⏳ IN PROGRESS' : ''}`);
  } else {
    log(`kind=${parsed.kind} not fetched in proto → fallback link`);
  }
}

// ---------------------------------------------------------------------------
// RUN
// ---------------------------------------------------------------------------
import { readFileSync } from 'node:fs';
const all = JSON.parse(readFileSync(new URL('./.agents/skills/bet-tracker/picks.json', import.meta.url)));
const picks = all.picks || all;

const targets = picks.filter(p =>
  p.bet?.includes('Aranda') || p.bet?.includes('Phillies at Dodgers'));

console.log('=== LIVE PEEK PROTOTYPE — two real examples ===');
for (const p of targets) await livePeek(p);

// quick parse-only sanity sweep over ALL picks to catch parser blowups
console.log('\n=== PARSE-ONLY SWEEP (classification across all picks) ===');
for (const p of picks) {
  const parsed = p.result ? { kind: 'SETTLED' } : parseBet(p);
  console.log(`  ${(p.kind || parsed.kind).padEnd(8)} | ${p.bet}`);
  if (!p.result && parsed.kind === 'prop')
    console.log(`           ↳ player="${parsed.player}" stat=${parsed.statKey} ${parsed.side} ${parsed.line} hints=${JSON.stringify(parsed.teamHints)}`);
}
