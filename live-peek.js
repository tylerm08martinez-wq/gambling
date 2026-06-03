// ============================================================================
// live-peek.js — read-only, non-authoritative "second grader" for the dashboard.
//
// 🔍 on a Pick computes a Live Peek (CONTEXT.md → Live Peek; ADR 0007):
//   - settled pick      → render the stored result + final_score, NO network call
//   - unsettled MLB prop → fetch the boxscore from statsapi.mlb.com, grade inline,
//                          label it "live peek — official grade posts tonight"
//   - everything else    → a single clean deep-link fallback (StatMuse / ESPN)
//
// This logic is folded in from the validated throwaway prototype
// (dashboard.live-peek.PROTOTYPE.mjs / .NOTES.md) with its fold-in fixes applied:
//   1. same-last-name collision across the two teams is REFUSED, not guessed (ADR 0004)
//   2. fetch() WITHOUT credentials — MLB sends `Access-Control-Allow-Origin:*` together
//      with `Allow-Credentials:true`; sending credentials would invalidate the `*`
//   3. NBA/other sports → deep-link fallback (NBA inline grading is issue #74/#75)
//   4. read-only: NEVER writes picks.json — the nightly Python resolver stays the sole
//      writer of any settled outcome (ADR 0007)
//
// Pure functions (parseBet, gradeOverUnder, fallbackLink, inferKind, settledSummary)
// are exported for Node unit tests. The async orchestrator (livePeek) and the DOM
// renderer (renderLivePeek) are the dashboard's entry points.
// ============================================================================

// --- resolver stat-map (mirror of ADR 0004; total bases is a DIRECT boxscore field,
//     NOT derived from hit components) ---------------------------------------
export const STAT_MAP = {
  'total bases':  'totalBases',
  'strikeouts':   'strikeOuts',   // pitching group
  'hits allowed': 'hits',         // pitcher "hits allowed" → pitching.hits
  'hits':         'hits',
  'rbis':         'rbi',
  'rbi':          'rbi',
  'runs':         'runs',
  'home runs':    'homeRuns',
  'doubles':      'doubles',
  'triples':      'triples',
  'walks':        'baseOnBalls',
  'stolen bases': 'stolenBases',
};

// Which boxscore group a mapped statKey lives in. Most live in `batting`;
// strikeouts (and "hits allowed") are read from the pitcher's `pitching` line.
const PITCHING_STAT_KEYWORDS = new Set(['strikeouts', 'hits allowed']);

// Longest keyword first so "total bases" wins over "bases", "hits allowed" over "hits".
const STAT_KEYS = Object.keys(STAT_MAP).sort((a, b) => b.length - a.length);

// Combined-stat props (e.g. "Hits+Runs+RBIs", "Runs + RBIs") are a SUM of several
// boxscore fields. We don't grade them inline — substring-matching one keyword would
// produce a confident WRONG peek (grading "Hits+Runs+RBIs" as just `hits`). Detect the
// "+" that joins stat words and route the bet to the fallback instead (review #4, #75).
// Matches a stat keyword immediately followed (allowing spaces) by "+" and another word,
// or a word "+" then a stat keyword — i.e. the "+" is a stat conjunction, not an "N+" line.
const COMBINED_STAT_RE = /[a-z]\s*\+\s*[a-z]/i;

// ---------------------------------------------------------------------------
// 1. CLASSIFY + PARSE
//    parseBet returns a discriminated result:
//      { kind:'prop',  player, statKeyword, statKey, group, side, line, teamHints }
//      { kind:'total', side, line, teamHints }
//      { kind:'moneyline'|'spread'|'other', side, line, teamHints }
//    It strips the trailing "(...)" pitcher/venue parenthetical BEFORE extracting
//    teams/players so a pitcher name is never mistaken for a team.
// ---------------------------------------------------------------------------
export function parseBet(pick) {
  const bet = (pick && pick.bet) || '';

  // Drop the trailing "(...)" pitcher/venue parenthetical (e.g. "(Painter vs Yamamoto)",
  // "(Madden)", "(at Coors Field)") so its contents can't pollute team/player extraction.
  const core = bet.replace(/\s*\([^)]*\)\s*$/, '').trim();
  const lc = core.toLowerCase();

  // Over/Under token + number (works for both "Stat Over N" and "Over N Stat").
  const ouMatch = core.match(/\b(over|under)\b\s+([\d.]+)/i);
  let side = ouMatch ? ouMatch[1].toLowerCase() : null;
  let line = ouMatch ? parseFloat(ouMatch[2]) : null;

  // "N+" form means "at least N" = Over N-0.5.
  const plusMatch = core.match(/\b(\d+(?:\.\d+)?)\+/);
  if (line == null && plusMatch) {
    side = 'over';
    line = parseFloat(plusMatch[1]) - 0.5;
  }
  // Fall back to the stored numeric line if the text had none.
  if (line == null && pick && pick.line_num != null) line = pick.line_num;

  // Opponent / teams hint = text after vs|at|@ (on the de-parenthesized core).
  const oppMatch = core.match(/\b(?:vs\.?|at|@)\s+(.+)$/i);
  const opponent = oppMatch ? oppMatch[1].trim() : null;

  // Does the bet name a player-stat keyword?
  const statKeyword = STAT_KEYS.find(k => lc.includes(k)) || null;

  if (statKeyword) {
    // COMBINED-STAT GUARD (review #4): a "+" joining stat words (e.g. "Hits+Runs+RBIs",
    // "Runs + RBIs") is a SUM the inline grader can't compute from one boxscore field.
    // Grading it as the single matched keyword would be a confident wrong peek, so flag
    // it as combined → the orchestrator degrades to the StatMuse fallback. The "N+" line
    // form ("2+ Total Bases") is digit+, not letter+letter, so it does NOT trip this.
    if (COMBINED_STAT_RE.test(core)) {
      return {
        kind: 'prop',
        combined: true,             // signals "don't grade inline — fall back"
        statKeyword,                // kept so fallbackLink can build a sensible query
        statKey: null,
        side: side || 'over',
        line,
        teamHints: oppMatch ? splitTeams(opponent) : [],
        player: core
          .replace(/\s+(?:vs\.?|at|@)\s+.+$/i, '')
          .replace(/\b(over|under)\b\s+[\d.]+/i, ' ')
          .replace(/\b\d+(?:\.\d+)?\+/g, ' ')
          .replace(/[a-z]+(?:\s*\+\s*[a-z]+)+/i, ' ')   // strip the combined-stat phrase
          .replace(/\s+/g, ' ').trim(),
      };
    }
    // PROP: isolate the player name by stripping the opponent clause, the over/under
    // clause, the "N+" token, and the stat keyword from the core.
    let s = core;
    if (oppMatch) s = s.replace(/\s+(?:vs\.?|at|@)\s+.+$/i, '');
    s = s.replace(new RegExp(escapeRe(statKeyword), 'i'), ' ');
    s = s.replace(/\b(over|under)\b\s+[\d.]+/i, ' ');
    s = s.replace(/\b\d+(?:\.\d+)?\+/g, ' ');           // N+ form
    const player = s.replace(/\s+/g, ' ').trim();

    const statKey = STAT_MAP[statKeyword];
    const group = PITCHING_STAT_KEYWORDS.has(statKeyword) ? 'pitching' : 'batting';
    return {
      kind: 'prop',
      player,
      statKeyword,
      statKey,
      group,
      side: side || 'over',
      line,
      teamHints: opponent ? splitTeams(opponent) : [],
    };
  }

  // GAME-LINE. Classify total vs moneyline vs spread.
  const isMoneyline = /\b(ml|moneyline)\b/i.test(core);
  const spreadMatch = core.match(/([+-]\d+(?:\.\d+)?)/);
  let kind;
  if (side) kind = 'total';
  else if (isMoneyline) kind = 'moneyline';
  else if (spreadMatch) kind = 'spread';
  else kind = 'other';

  // teams = core minus leading "Over/Under N", the ml/spread tokens, and vs/at/@ joins.
  let teamsText = core
    .replace(/^\s*(over|under)\s+[\d.]+\s*/i, '')
    .replace(/\b(ml|moneyline)\b/gi, ' ')
    .replace(/[+-]\d+(?:\.\d+)?/g, ' ')
    .replace(/\b(?:vs\.?|at|@)\b/gi, ' ');

  return {
    kind,
    side,
    line,
    teamHints: splitTeams(teamsText),
  };
}

// Convenience: just the classification, for callers that only need the bet type.
export function inferKind(pick) {
  return parseBet(pick).kind;
}

function escapeRe(s) {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

// Split an opponent/teams string into "team-like" tokens (drop stray junk, keep
// Capitalized words and ALL-CAPS abbreviations like "CLE"/"PHI").
function splitTeams(t) {
  return (t || '')
    .split(/\s+(?:vs\.?|at|@|and|,)\s+|\s+/i)
    .map(x => x.trim())
    .filter(Boolean)
    .filter(x => /^[A-Z]/.test(x));
}

// ---------------------------------------------------------------------------
// 2. GRADE (pure)
//    value === line → push; either null → ungradeable.
// ---------------------------------------------------------------------------
export function gradeOverUnder(value, side, line) {
  if (value == null || line == null) return 'ungradeable';
  if (value === line) return 'push';
  const over = value > line;
  return (side === 'over') === over ? 'win' : 'loss';
}

// ---------------------------------------------------------------------------
// 3. MLB Player Prop Source adapter (thin async wrappers over statsapi.mlb.com).
//    Mirrors the Python Player Prop Source interface (CONTEXT.md):
//      findGame(date, teamHints) → opaque { gamePk, status, scores }
//      fetchBoxscore(gamePk)     → shared boxscore shape
//      findPlayerStat(box, ...)  → matched player's stat, refusing ambiguous matches
//    All fetches are plain (no credentials) so MLB's `ACAO:*` stays valid.
// ---------------------------------------------------------------------------
const MLB_BASE = 'https://statsapi.mlb.com/api/v1';

export function makeMlbSource(fetchImpl = fetch) {
  async function getJson(url) {
    // No `credentials:'include'` — see header note (ADR 0007 fold-in #2).
    const r = await fetchImpl(url);
    if (!r.ok) throw new Error(`MLB API ${r.status} for ${url}`);
    return r.json();
  }

  return {
    async findGame(date, teamHints) {
      const j = await getJson(`${MLB_BASE}/schedule?sportId=1&date=${encodeURIComponent(date)}`);
      const games = (j.dates && j.dates[0] && j.dates[0].games) || [];
      const hintLc = (teamHints || []).map(h => h.toLowerCase());
      const match = games.find(g => {
        const names = [g.teams.away.team.name, g.teams.home.team.name].map(n => n.toLowerCase());
        return hintLc.some(h => names.some(n => n.includes(h)));
      });
      if (!match) return null;
      return {
        gamePk: match.gamePk,
        status: match.status.detailedState,
        away: match.teams.away.team.name, awayR: match.teams.away.score,
        home: match.teams.home.team.name, homeR: match.teams.home.score,
      };
    },

    async fetchBoxscore(gamePk) {
      return getJson(`${MLB_BASE}/game/${gamePk}/boxscore`);
    },

    findPlayerStat,
  };
}

// findPlayerStat: locate the player's stat across both teams. A full-name match is
// taken immediately. Otherwise fall back to last-name matching — but if the SAME
// last name appears on more than one player across the two teams, REFUSE (return a
// collision sentinel) rather than guess (ADR 0004 skip-on-collision).
export function findPlayerStat(box, playerName, group, statKey) {
  const wantFull = (playerName || '').toLowerCase().trim();
  const wantLast = wantFull.split(/\s+/).pop();

  const lastNameHits = [];
  for (const sideKey of ['away', 'home']) {
    const players = (box.teams && box.teams[sideKey] && box.teams[sideKey].players) || {};
    for (const pid of Object.keys(players)) {
      const pl = players[pid];
      const full = ((pl.person && pl.person.fullName) || '').toLowerCase();
      if (!full) continue;
      if (full === wantFull) {
        // Exact full-name match wins outright — no collision risk.
        return statHit(pl, group, statKey);
      }
      if (full.split(/\s+/).pop() === wantLast) {
        lastNameHits.push(pl);
      }
    }
  }

  if (lastNameHits.length === 0) return null;                 // unmatched → fallback
  if (lastNameHits.length > 1) return { collision: true };    // ambiguous → refuse
  return statHit(lastNameHits[0], group, statKey);
}

function statHit(pl, group, statKey) {
  const val = pl.stats && pl.stats[group] && pl.stats[group][statKey];
  return {
    matchedName: pl.person.fullName,
    value: (val == null ? null : val),
    hasStatGroup: !!(pl.stats && pl.stats[group]),
  };
}

// ---------------------------------------------------------------------------
// 4. FALLBACK LINK builder (pure).
//    Prop      → StatMuse single-answer query.
//    Game-line → ESPN scoreboard for that sport + date.
// ---------------------------------------------------------------------------
const ESPN_LEAGUE = {
  MLB: 'mlb', NBA: 'nba', NFL: 'nfl', NHL: 'nhl',
  CFB: 'college-football', 'COLLEGE FOOTBALL': 'college-football',
  CBB: 'mens-college-basketball', NCAAB: 'mens-college-basketball',
};

export function fallbackLink(pick) {
  const parsed = parseBet(pick);
  const date = (pick && pick.date) || '';
  const sport = ((pick && pick.sport) || '').toUpperCase();

  if (parsed.kind === 'prop') {
    // StatMuse answers a single natural-language stat query cleanly.
    const q = [parsed.player, parsed.statKeyword, date].filter(Boolean).join(' ');
    return `https://www.statmuse.com/${sport === 'NBA' ? 'nba' : 'mlb'}/ask/${encodeURIComponent(q.replace(/\s+/g, ' ').trim())}`;
  }

  // Game-line → ESPN scoreboard for the date (YYYYMMDD).
  const league = ESPN_LEAGUE[sport] || 'mlb';
  const ymd = date.replace(/-/g, '');
  return `https://www.espn.com/${league}/scoreboard/_/date/${ymd}`;
}

// ---------------------------------------------------------------------------
// 5. SETTLED summary (pure) — how a stored result landed, from the pick record.
//    No network. Used to render the inline panel for already-settled picks.
// ---------------------------------------------------------------------------
export function settledSummary(pick) {
  const result = (pick.result || '').toLowerCase();
  const parsed = parseBet(pick);
  let detail = '';

  if (parsed.kind === 'total' && pick.final_score) {
    const nums = (pick.final_score.match(/\d+/g) || []).map(Number);
    const total = nums.reduce((a, b) => a + b, 0);
    const line = parsed.line != null ? parsed.line : pick.line_num;
    if (line != null) {
      const margin = total - line;
      detail = `total ${total} vs ${parsed.side || (/under/i.test(pick.bet) ? 'under' : 'over')} ${line}`
        + (margin !== 0 ? ` (${margin > 0 ? '+' : ''}${margin.toFixed(1)})` : ' (push)');
    } else if (pick.final_score) {
      detail = pick.final_score;
    }
  } else if (parsed.kind === 'prop' && pick.prop_result) {
    detail = pick.prop_result
      + (pick.line_num != null ? ` (needed ${pick.line_num}${pick.prop_margin != null ? `, margin ${pick.prop_margin >= 0 ? '+' : ''}${pick.prop_margin}` : ''})` : '');
  } else if (pick.final_score) {
    detail = pick.final_score;
  }

  return {
    result,                          // 'win' | 'loss' | 'push' | 'void'
    finalScore: pick.final_score || null,
    detail,                          // human "how it landed" string
  };
}

// ---------------------------------------------------------------------------
// 6. THE ORCHESTRATOR — livePeek(pick) → structured result object (rendering is
//    separate). Read-only: never writes the pick record.
//
//    settled                       → { state:'settled', ... }            (no fetch)
//    unsettled, sport !== MLB      → { state:'fallback', url, reason }    (NBA deferred)
//    unsettled MLB prop/total      → parse → findGame → grade inline
//      any miss / throw            → { state:'fallback', url, reason }    (degrade safely)
// ---------------------------------------------------------------------------
export async function livePeek(pick, source = makeMlbSource()) {
  // STATE A: settled → stored panel, no fetch.
  if (pick && pick.result) {
    return { state: 'settled', pick, ...settledSummary(pick) };
  }

  const sport = ((pick && pick.sport) || '').toUpperCase();

  // STATE B: unsettled, non-MLB → deep-link fallback (NBA inline grading is a later slice).
  if (sport !== 'MLB') {
    return { state: 'fallback', url: fallbackLink(pick), reason: `no inline grader for ${sport || 'unknown sport'}` };
  }

  // STATE C: unsettled MLB → parse → findGame → grade. Any miss/throw degrades to fallback.
  try {
    const parsed = parseBet(pick);

    if (parsed.kind !== 'prop' && parsed.kind !== 'total') {
      // Spread / moneyline inline grading is out of scope (PRD) → fallback.
      return { state: 'fallback', url: fallbackLink(pick), reason: `${parsed.kind} not graded inline` };
    }

    if (parsed.combined) {
      // Combined-stat prop (e.g. "Hits+Runs+RBIs") — no single boxscore field to grade
      // against; degrade to the StatMuse fallback rather than peek a wrong number (#4).
      return { state: 'fallback', url: fallbackLink(pick), reason: 'combined-stat prop not graded inline' };
    }

    const game = await source.findGame(pick.date, parsed.teamHints);
    if (!game) {
      return { state: 'fallback', url: fallbackLink(pick), reason: 'no matching game' };
    }
    // MLB detailedState is "Game Over"/"Completed Early" for a window after the last
    // out before it becomes "Final" — all three are terminal, not in-progress.
    const live = !/final|game over|completed/i.test(game.status);

    if (parsed.kind === 'total') {
      const total = (game.awayR || 0) + (game.homeR || 0);
      const grade = gradeOverUnder(total, parsed.side, parsed.line);
      return {
        state: live ? 'live' : 'peek',
        kind: 'total', game, parsed,
        value: total, grade,
        detail: `total ${total} ${parsed.side} ${parsed.line} → ${grade.toUpperCase()}`,
      };
    }

    // prop
    const box = await source.fetchBoxscore(game.gamePk);
    const hit = source.findPlayerStat(box, parsed.player, parsed.group, parsed.statKey);
    if (!hit) {
      return { state: 'fallback', url: fallbackLink(pick), reason: `player "${parsed.player}" not found` };
    }
    if (hit.collision) {
      // Same last name across the two teams → refuse, don't guess (ADR 0004).
      return { state: 'fallback', url: fallbackLink(pick), reason: 'ambiguous player match (same last name)' };
    }
    if (hit.value == null) {
      return { state: 'fallback', url: fallbackLink(pick), reason: 'stat not available yet' };
    }
    const grade = gradeOverUnder(hit.value, parsed.side, parsed.line);
    return {
      state: live ? 'live' : 'peek',
      kind: 'prop', game, parsed,
      player: hit.matchedName,
      value: hit.value, grade,
      detail: `${hit.matchedName} ${hit.value} ${parsed.statKeyword} ${parsed.side} ${parsed.line} → ${grade.toUpperCase()}`,
    };
  } catch (err) {
    // Fetch failure / unexpected shape → degrade to the deep-link, never a wrong answer.
    return { state: 'fallback', url: fallbackLink(pick), reason: `error: ${err && err.message ? err.message : err}` };
  }
}

// ---------------------------------------------------------------------------
// 7. DOM RENDERER — turns a livePeek result into the inline "Game Result" panel.
//    Async: shows a loading line, then resolves into settled / peek / fallback.
//    Read-only and self-contained; never mutates the pick.
// ---------------------------------------------------------------------------
const GRADE_COLOR = { win: '#36c275', loss: '#e5675f', push: '#c9a23a', ungradeable: '#8a93a6' };

function esc(v) {
  return String(v == null ? '' : v).replace(/[&<>"']/g, ch =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]));
}

function fallbackAnchor(url, label) {
  return `<a href="${esc(url)}" target="_blank" rel="noopener" onclick="event.stopPropagation()" `
    + `style="display:inline-block;margin-top:6px;font-size:11px;color:var(--accent);text-decoration:none;border-bottom:1px dashed var(--border)">${esc(label)}</a>`;
}

function panelHtml(result) {
  if (result.state === 'settled') {
    const color = GRADE_COLOR[result.result] || 'var(--text)';
    const landed = result.detail ? ` — <span style="color:var(--muted)">${esc(result.detail)}</span>` : '';
    return `<div style="margin-top:8px;font-size:12px">`
      + `<span style="font-weight:700;color:${color};text-transform:uppercase">${esc(result.result || '—')}</span>${landed}`
      + (result.finalScore ? `<div style="font-size:11px;color:var(--muted);margin-top:2px">${esc(result.finalScore)}</div>` : '')
      + `</div>`;
  }

  if (result.state === 'peek' || result.state === 'live') {
    const color = GRADE_COLOR[result.grade] || 'var(--text)';
    const liveTag = result.state === 'live' ? '⏳ ' : '';
    const score = result.game ? `${esc(result.game.away)} ${result.game.awayR ?? ''} @ ${esc(result.game.home)} ${result.game.homeR ?? ''}` : '';
    return `<div style="margin-top:8px;font-size:12px">`
      + `<span style="font-weight:700;color:${color}">${esc(result.detail)}</span>`
      + (score ? `<div style="font-size:11px;color:var(--muted);margin-top:2px">${esc(score)} [${esc(result.game.status)}]</div>` : '')
      + `<div style="font-size:10px;color:var(--muted);margin-top:4px;font-style:italic">${liveTag}live peek — official grade posts tonight</div>`
      + `</div>`;
  }

  // fallback
  const isProp = parseBet(result.pickForFallback || {}).kind === 'prop';
  const label = isProp ? 'Look up stat on StatMuse →' : 'See scoreboard on ESPN →';
  // Review #5: show a friendly line instead of the raw `reason` (e.g. "error: Failed to
  // fetch"). The deep-link stays; `reason` is preserved only as a hover/debug aid (title).
  const dbg = result.reason ? ` title="${esc(result.reason)}"` : '';
  return `<div style="margin-top:8px;font-size:12px"${dbg}>`
    + `<div style="font-size:11px;color:var(--muted);margin-bottom:2px">couldn't load live result — check StatMuse/ESPN</div>`
    + fallbackAnchor(result.url, label)
    + `</div>`;
}

// renderLivePeek(pick, mountEl): replace mountEl's contents with the Live Peek panel.
// For settled picks this is synchronous-fast (no fetch); for unsettled MLB it shows a
// "checking…" line, then resolves. Safe to call repeatedly.
export async function renderLivePeek(pick, mountEl, source = makeMlbSource()) {
  if (!mountEl) return;
  // Settled → render immediately, no network.
  if (pick && pick.result) {
    mountEl.innerHTML = panelHtml({ state: 'settled', ...settledSummary(pick) });
    return;
  }
  mountEl.innerHTML = `<div style="margin-top:8px;font-size:11px;color:var(--muted)">checking live peek…</div>`;
  let result;
  try {
    result = await livePeek(pick, source);
  } catch (err) {
    result = { state: 'fallback', url: fallbackLink(pick), reason: 'peek failed' };
  }
  // The fallback renderer needs the pick to decide StatMuse vs ESPN label.
  if (result.state === 'fallback') result.pickForFallback = pick;
  mountEl.innerHTML = panelHtml(result);
}
