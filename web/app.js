/* App controller: series selection, match ingestion, roster corrections, metric cards. */

(function () {
'use strict';

const { el, renderSection } = window.MWOModules;

const state = {
  seriesId: null,
  series: null,
  seriesList: [],
  modules: [],
  // 'summary' | 'matches' | 'A' | 'B' — a team letter doubles as both the tab id
  // and the ?team= query param, so no separate "kind" bookkeeping is needed.
  activeTab: 'summary',
};

const $ = (id) => document.getElementById(id);

/* ------------------------------------------------------------------ http */

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(body.detail || `${response.status} ${response.statusText}`);
  }
  return body;
}

function banner(message, kind = 'error') {
  const node = $('banner');
  if (!message) { node.hidden = true; return; }
  node.className = `banner ${kind}`;
  node.textContent = message;
  node.hidden = false;
  if (kind === 'info') setTimeout(() => { node.hidden = true; }, 4000);
}

/* ------------------------------------------------------------------ series */

// The series picker is a custom trigger + popover, not a native <select> — a
// <select>'s options can't hold their own delete button, and each row here needs one.
async function loadSeriesList(selectId = null) {
  const { series } = await api('/api/series');
  state.seriesList = series;
  if (selectId !== null) state.seriesId = selectId;
  renderSeriesTrigger();
  renderSeriesMenu();
  return series;
}

function renderSeriesTrigger() {
  const current = state.seriesList.find((s) => s.id === state.seriesId);
  $('series-trigger-label').textContent = current
    ? `${current.name} (${current.match_count})`
    : 'No series yet';
}

function renderSeriesMenu() {
  const menu = $('series-menu');
  menu.replaceChildren();

  if (!state.seriesList.length) {
    menu.append(el('div', { class: 'series-menu-empty', text: 'No series yet — create one below.' }));
    return;
  }

  for (const item of state.seriesList) {
    const isActive = item.id === state.seriesId;
    menu.append(el('div', {
      class: `series-row${isActive ? ' active' : ''}`,
      role: 'option',
      'aria-selected': isActive ? 'true' : 'false',
      onclick: () => selectSeries(item.id),
    },
      el('span', { class: 'series-row-label' },
        `${item.name} `,
        el('span', { class: 'series-row-count', text: `(${item.match_count})` }),
      ),
      el('button', {
        class: 'series-row-delete', type: 'button', title: `Delete "${item.name}"`,
        onclick: (event) => {
          event.stopPropagation(); // don't also trigger the row's onclick (selecting it)
          deleteSeriesById(item.id, item.name, item.match_count);
        },
      }, '×'),
    ));
  }
}

function setSeriesMenuOpen(open) {
  $('series-menu').hidden = !open;
  $('series-trigger').setAttribute('aria-expanded', open ? 'true' : 'false');
}

async function selectSeries(id) {
  setSeriesMenuOpen(false);
  if (id === state.seriesId) return;
  state.seriesId = id;
  state.activeTab = 'summary';
  renderSeriesTrigger();
  renderSeriesMenu();
  $('ingest-log').replaceChildren();
  await refreshSeries();
}

async function ensureSeries() {
  const list = await loadSeriesList();
  if (!list.length) {
    const created = await api('/api/series', {
      method: 'POST',
      body: JSON.stringify({ name: 'My Series', match_ids: '' }),
    });
    state.seriesId = created.series.id;
    await loadSeriesList(state.seriesId);
  } else if (state.seriesId === null) {
    state.seriesId = list[0].id;
    renderSeriesTrigger();
    renderSeriesMenu();
  }
}

async function refreshSeries() {
  if (state.seriesId === null) return;
  state.series = await api(`/api/series/${state.seriesId}`);
  renderSeries();
  await renderMetrics();
}

/* ------------------------------------------------------------------ matches */

async function addMatches() {
  const input = $('match-input');
  const raw = input.value.trim();
  if (!raw) { banner('Enter at least one match ID.'); return; }

  const button = $('add-matches-btn');
  button.disabled = true;
  button.textContent = 'Fetching…';
  banner(null);

  try {
    const result = await api(`/api/series/${state.seriesId}/matches`, {
      method: 'POST',
      body: JSON.stringify({
        match_ids: raw,
        force_refresh: $('force-refresh').checked,
      }),
    });
    renderIngestLog(result.ingest);
    if (result.ingest.every((r) => r.status === 'error')) {
      banner('No matches could be fetched — see the details below.', 'error');
    } else {
      input.value = '';
    }
    state.series = result.series;
    renderSeries();
    await renderMetrics();
  } catch (error) {
    banner(error.message);
  } finally {
    button.disabled = false;
    button.textContent = 'Add matches';
  }
}

function renderIngestLog(results) {
  const log = $('ingest-log');
  log.replaceChildren();
  for (const result of results || []) {
    const failed = result.status === 'error';
    log.append(el('div', { class: `ingest-line ${failed ? 'err' : 'ok'}` },
      el('span', { class: 'mark', text: failed ? '✗' : '✓' }),
      el('span', { class: 'id', text: result.match_id }),
      el('span', { class: 'detail', text: `${result.status} — ${result.detail}` }),
    ));
  }
}

async function removeMatch(matchId) {
  state.series = (await api(`/api/series/${state.seriesId}/matches/${matchId}`, {
    method: 'DELETE',
  })).series;
  renderSeries();
  await renderMetrics();
}

/* ------------------------------------------------------------------ render: series */

function renderSeries() {
  const series = state.series;
  if (!series) return;

  $('match-count').textContent = `${series.matches.length} match${series.matches.length === 1 ? '' : 'es'}`;

  // match chips
  const chips = $('match-chips');
  chips.replaceChildren();
  for (const match of series.matches) {
    chips.append(el('span', { class: 'chip' },
      match.match_id,
      el('span', { class: 'meta', text: match.map || 'unknown map' }),
      el('button', {
        title: 'Remove from series',
        onclick: () => removeMatch(match.match_id),
      }, '×'),
    ));
  }

  $('teams-panel').hidden = series.matches.length === 0;
  renderTabBar();

  // warnings
  const warnings = $('warnings');
  warnings.replaceChildren();
  for (const warning of series.warnings || []) {
    warnings.append(el('div', { class: 'warning', text: warning }));
  }

  // team names
  $('team-a-name').value = series.team_a_name;
  $('team-b-name').value = series.team_b_name;

  renderReviewStrip(series);
  renderRoster('A', series.rosters.A);
  renderRoster('B', series.rosters.B);
}

function renderReviewStrip(series) {
  const strip = $('review-strip');
  const items = series.needs_review || [];
  strip.replaceChildren();
  strip.hidden = items.length === 0;
  if (!items.length) return;

  strip.append(el('h3', { text: `${items.length} player${items.length === 1 ? '' : 's'} worth checking` }));
  strip.append(el('p', {
    class: 'review-note',
    text: 'These were placed on thin evidence — a single appearance, or conflicting sides. Correct any that are wrong; corrections are pinned and steer the rest of the inference.',
  }));

  const list = el('div', { class: 'review-items' });
  for (const player of items) {
    list.append(el('span', { class: 'chip' },
      player.username,
      el('span', { class: 'meta', text: `${player.match_count} match${player.match_count === 1 ? '' : 'es'}` }),
      teamSelect(player),
    ));
  }
  strip.append(list);
}

function teamSelect(player) {
  const select = el('select', {
    class: 'team-select',
    onchange: (event) => setAssignment(player.username, event.target.value || null),
  });
  select.append(el('option', { value: 'A', text: state.series.team_a_name }));
  select.append(el('option', { value: 'B', text: state.series.team_b_name }));
  if (player.source !== 'inferred') {
    select.append(el('option', { value: '', text: '↺ auto' }));
  }
  select.value = player.team;
  return select;
}

function renderRoster(team, players) {
  const list = $(`roster-${team.toLowerCase()}`);
  list.replaceChildren();

  if (!players.length) {
    list.append(el('li', { class: 'note', text: 'No players assigned.' }));
    return;
  }

  for (const player of players) {
    const row = el('li', { class: player.needs_review ? 'review' : '' });
    row.append(el('span', {
      class: 'player-name',
      text: player.username,
      onclick: () => showPlayer(player.username),
    }));

    if (player.source === 'pinned' || player.source === 'override') {
      row.append(el('span', { class: 'badge pinned', text: 'pinned' }));
    }
    if (player.contested) {
      row.append(el('span', { class: 'badge contested', text: 'both sides' }));
    } else if (player.needs_review) {
      // Say *why* it needs review — "low confidence" next to "100%" reads as a bug.
      row.append(el('span', {
        class: 'badge low',
        text: player.match_count <= 1 ? 'one match only' : 'low confidence',
      }));
    }

    row.append(el('span', {
      class: 'player-meta',
      title: `Confidence ${Math.round(player.confidence * 100)}%`,
      text: `${player.match_count}m · ${Math.round(player.confidence * 100)}%`,
    }));
    row.append(teamSelect(player));
    list.append(row);
  }
}

async function setAssignment(username, team, matchId = null) {
  try {
    state.series = (await api(`/api/series/${state.seriesId}/assignments`, {
      method: 'PUT',
      body: JSON.stringify({ username, team, match_id: matchId }),
    })).series;
    renderSeries();
    await renderMetrics();
  } catch (error) {
    banner(error.message);
  }
}

async function saveTeamNames() {
  try {
    state.series = (await api(`/api/series/${state.seriesId}/teams`, {
      method: 'PUT',
      body: JSON.stringify({
        team_a_name: $('team-a-name').value,
        team_b_name: $('team-b-name').value,
      }),
    })).series;
    renderSeries();
    await renderMetrics();
  } catch (error) {
    banner(error.message);
  }
}

/* ------------------------------------------------------------------ render: tabs */

// A module's `tabs` array says which of these kinds it appears under. 'A'/'B' both
// map to the generic 'team' kind — which team is just a query param, not a
// different kind of page.
function currentTabKind() {
  return state.activeTab === 'A' || state.activeTab === 'B' ? 'team' : state.activeTab;
}

function availableTabs() {
  const kinds = new Set();
  for (const module of state.modules) {
    for (const tab of module.tabs || []) kinds.add(tab);
  }
  const tabs = [];
  if (kinds.has('summary')) tabs.push({ id: 'summary', label: 'Summary' });
  if (kinds.has('team') && state.series) {
    tabs.push({ id: 'A', label: state.series.team_a_name });
    tabs.push({ id: 'B', label: state.series.team_b_name });
  }
  if (kinds.has('matches')) tabs.push({ id: 'matches', label: 'Matches' });
  return tabs;
}

function renderTabBar() {
  const bar = $('tab-bar');
  const tabs = availableTabs();
  bar.hidden = !state.series || state.series.matches.length === 0 || tabs.length <= 1;

  // Team names can change (rename, auto-naming) without the active tab becoming
  // invalid — only reset it if the tab itself no longer exists.
  if (!tabs.some((tab) => tab.id === state.activeTab)) {
    state.activeTab = tabs[0] ? tabs[0].id : 'summary';
  }

  bar.replaceChildren(...tabs.map((tab) => el('button', {
    class: `tab-btn${tab.id === state.activeTab ? ' active' : ''}`,
    'data-tab': tab.id,
    onclick: () => {
      if (state.activeTab === tab.id) return;
      state.activeTab = tab.id;
      renderTabBar();
      renderMetrics();
    },
  }, tab.label)));
}

/* ------------------------------------------------------------------ render: metrics */

async function renderMetrics() {
  const container = $('metrics');
  container.replaceChildren();

  if (!state.series || !state.series.matches.length) {
    container.append(el('div', { class: 'panel' },
      el('div', { class: 'empty', text: 'Add one or more match IDs above to see metrics.' })));
    return;
  }

  const kind = currentTabKind();
  const teamQuery = kind === 'team' ? `?team=${state.activeTab}` : '';
  const visibleModules = state.modules.filter((module) => (module.tabs || []).includes(kind));

  // Lay out every card immediately with a placeholder, then fill them in as they land —
  // one slow module shouldn't hold up the rest of the dashboard.
  const bodies = new Map();
  for (const module of visibleModules) {
    const body = el('div', { class: 'module-body' }, el('div', { class: 'skeleton' }));
    bodies.set(module.id, body);
    container.append(el('section', { class: 'module-card' },
      el('div', { class: 'module-head' },
        el('h2', { text: module.name }),
        el('p', { text: module.description }),
      ),
      body,
    ));
  }

  await Promise.all(visibleModules.map(async (module) => {
    const body = bodies.get(module.id);
    try {
      const payload = await api(`/api/series/${state.seriesId}/metrics/${module.id}${teamQuery}`);
      body.replaceChildren();
      for (const section of payload.sections || []) {
        body.append(renderSection(section));
      }
    } catch (error) {
      body.replaceChildren(el('p', { class: 'note', text: `Failed to load: ${error.message}` }));
    }
  }));
}

/* ------------------------------------------------------------------ player modal */

async function showPlayer(username) {
  const modal = $('player-modal');
  const body = $('modal-body');
  body.replaceChildren(el('div', { class: 'skeleton' }));
  modal.hidden = false;

  try {
    const data = await api(`/api/series/${state.seriesId}/players/${encodeURIComponent(username)}`);
    body.replaceChildren(
      el('h2', { text: data.username }),
      el('p', {
        class: 'modal-sub',
        text: `${data.team_name || 'Unassigned'} · ${data.totals.matches} matches · `
            + `${Math.round(data.assignment.confidence * 100)}% confidence`
            + (data.assignment.contested ? ' · played for both teams' : ''),
      }),
      renderSection({
        type: 'stats', title: 'Totals',
        groups: [{
          label: data.team_name || '—', group: data.team,
          stats: [
            { label: 'Avg Damage', value: data.totals.avg_damage.toLocaleString() },
            { label: 'Total Damage', value: data.totals.total_damage.toLocaleString() },
            { label: 'Kills', value: data.totals.kills },
            { label: 'Assists', value: data.totals.assists },
            { label: 'Avg Score', value: data.totals.avg_match_score.toLocaleString() },
          ],
        }],
      }),
      renderSection({
        type: 'table', title: 'Match by match',
        columns: ['Match', 'Map', 'Side', 'Mech', 'Dmg', 'Kills', 'Assists', 'Score'],
        align: ['left', 'left', 'right', 'left', 'right', 'right', 'right', 'right'],
        rows: data.matches.map((m) => [
          m.match_id, m.map || '—', m.side, m.mech || '—',
          Math.round(m.damage).toLocaleString(), m.kills, m.assists, Math.round(m.match_score),
        ]),
      }),
    );
  } catch (error) {
    body.replaceChildren(el('p', { class: 'note', text: error.message }));
    return;
  }

  // Best-effort external enrichment — fetched after the main content is already on
  // screen, and never allowed to disturb it. Most casual/newer pilots simply aren't
  // tracked on Jarl's List, so silently showing nothing is the right failure mode,
  // not an error message every time that turns out to be true.
  try {
    const jarls = await api(`/api/players/${encodeURIComponent(username)}/jarls`);
    if (jarls.found) body.append(renderJarlsSection(jarls));
  } catch (error) {
    /* silently skip */
  }
}

function renderJarlsSection(jarls) {
  // This is the site's own "Overall" row (lifetime, not any single season) — verified
  // by hand against a real profile. A player without enough of a track record for a
  // lifetime rank (or a retired one) has has_rank=false; show their real numbers
  // without inventing a rank for them.
  const stats = [];
  if (jarls.has_rank) {
    stats.push({ label: 'Rank', value: `#${jarls.rank}` });
    stats.push({ label: 'Percentile', value: `${jarls.percentile}` });
  }
  if (jarls.wins != null && jarls.losses != null) {
    stats.push({ label: 'Record', value: `${jarls.wins}-${jarls.losses}` });
  }
  if (jarls.kd_ratio != null) {
    stats.push({ label: 'K/D', value: jarls.kd_ratio.toFixed(2) });
  }
  if (jarls.games_played != null) {
    stats.push({
      label: 'Games Played', value: `${jarls.games_played}`,
      hint: jarls.first_season != null ? `Season ${jarls.first_season}–${jarls.last_season}` : '',
    });
  }
  if (jarls.weight_class) {
    const label = ['light', 'medium', 'heavy', 'assault']
      .map((cls) => [cls, jarls.weight_class[cls]])
      .filter(([, pct]) => pct > 0)
      .map(([cls, pct]) => `${pct}% ${cls[0].toUpperCase()}${cls.slice(1)}`)
      .join(', ');
    if (label) stats.push({ label: 'Weight Class', value: label, wide: true });
  }

  let note = "Overall (lifetime) stats from leaderboard.isengrim.org — not affiliated with this app.";
  if (!jarls.has_rank) {
    note = `Not enough of a track record for an overall rank yet. ${note}`;
  }

  const section = renderSection({
    type: 'stats', title: "Jarl's List",
    groups: [{ label: jarls.unit_tag ? `Career — [${jarls.unit_tag}]` : 'Career', stats }],
    note,
  });
  section.append(el('a', {
    class: 'jarls-link', href: jarls.profile_url, target: '_blank', rel: 'noopener noreferrer',
  }, "View full profile on Jarl's List →"));
  return section;
}

/* ------------------------------------------------------------------ settings */

async function refreshTokenStatus() {
  const status = await api('/api/settings/token');
  const box = $('token-status');
  box.className = `token-status ${status.configured ? 'ok' : 'none'}`;

  let text;
  if (status.source === 'database') {
    text = ['Using a token saved in this app (ends in ', el('code', { text: status.masked }), ').'];
  } else if (status.source === 'env') {
    text = ['Using a token from your .env file (ends in ', el('code', { text: status.masked }), ').'];
  } else {
    text = ['No API token configured — matches can’t be fetched until you add one.'];
  }
  box.replaceChildren(el('span', { class: 'dot' }), el('span', {}, ...text));

  // Clearing only makes sense when there's a saved-in-app override to remove;
  // an .env token isn't something this UI manages.
  $('token-clear-btn').hidden = status.source !== 'database';
  return status;
}

function setTokenFormNote(message, kind) {
  const note = $('token-form-note');
  note.textContent = message || '';
  note.className = `section-note${kind ? ' ' + kind : ''}`;
}

async function openSettings() {
  $('token-input').value = '';
  setTokenFormNote('', null);
  $('settings-modal').hidden = false;
  try {
    await refreshTokenStatus();
  } catch (error) {
    setTokenFormNote(error.message, 'error');
  }
}

async function saveToken() {
  const input = $('token-input');
  const token = input.value.trim();
  if (!token) { setTokenFormNote('Paste a token first.', 'error'); return; }

  const button = $('token-save-btn');
  button.disabled = true;
  try {
    await api('/api/settings/token', { method: 'PUT', body: JSON.stringify({ token }) });
    input.value = '';
    setTokenFormNote('Saved.', 'success');
    await refreshTokenStatus();
  } catch (error) {
    setTokenFormNote(error.message, 'error');
  } finally {
    button.disabled = false;
  }
}

async function clearToken() {
  if (!confirm('Remove the token saved in this app? Matches will fall back to your .env token, if any.')) {
    return;
  }
  try {
    await api('/api/settings/token', { method: 'DELETE' });
    setTokenFormNote('Cleared.', 'success');
    await refreshTokenStatus();
  } catch (error) {
    setTokenFormNote(error.message, 'error');
  }
}

/* ------------------------------------------------------------------ boot */

async function newSeries() {
  const name = prompt('Name this series:', 'New Series');
  if (name === null) return;
  const created = await api('/api/series', {
    method: 'POST',
    body: JSON.stringify({ name: name || 'New Series', match_ids: '' }),
  });
  state.seriesId = created.series.id;
  state.activeTab = 'summary';
  await loadSeriesList(state.seriesId);
  $('ingest-log').replaceChildren();
  await refreshSeries();
}

async function deleteSeriesById(id, name, matchCount) {
  const label = `${name} (${matchCount} match${matchCount === 1 ? '' : 'es'})`;
  if (!confirm(`Delete "${label}"? This cannot be undone — the matches themselves stay cached, but this series' team names and any corrections you made are gone for good.`)) {
    return;
  }
  try {
    await api(`/api/series/${id}`, { method: 'DELETE' });
    if (id === state.seriesId) {
      // Deleted the one we were looking at — fall back to another series (or a
      // fresh one if that was the last), same as before.
      state.seriesId = null;
      state.series = null;
      state.activeTab = 'summary';
      $('ingest-log').replaceChildren();
      await ensureSeries();
      await refreshSeries();
    } else {
      // Deleted some other row in the menu — nothing else on screen changes.
      await loadSeriesList(state.seriesId);
    }
    banner(`Deleted "${label}".`, 'info');
  } catch (error) {
    banner(error.message);
  }
}

async function boot() {
  try {
    const health = await api('/api/health');
    if (!health.ok) {
      banner(health.detail);
    } else if (!health.token.configured) {
      banner('No MWO API token configured yet — add one via the ⚙ Settings button to fetch matches.', 'info');
    }

    state.modules = (await api('/api/metrics/modules')).modules;

    await ensureSeries();
    await refreshSeries();
  } catch (error) {
    banner(`Startup failed: ${error.message}`);
  }

  $('add-matches-btn').addEventListener('click', addMatches);
  $('new-series-btn').addEventListener('click', newSeries);

  $('series-trigger').addEventListener('click', () => {
    setSeriesMenuOpen($('series-menu').hidden);
  });
  document.addEventListener('click', (event) => {
    if (!$('series-switcher').contains(event.target)) setSeriesMenuOpen(false);
  });
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') setSeriesMenuOpen(false);
  });

  for (const id of ['team-a-name', 'team-b-name']) {
    $(id).addEventListener('change', saveTeamNames);
  }

  $('match-input').addEventListener('keydown', (event) => {
    if (event.key === 'Enter' && (event.ctrlKey || event.metaKey)) addMatches();
  });

  $('modal-close').addEventListener('click', () => { $('player-modal').hidden = true; });
  $('player-modal').addEventListener('click', (event) => {
    if (event.target.id === 'player-modal') $('player-modal').hidden = true;
  });

  $('settings-btn').addEventListener('click', openSettings);
  $('settings-close').addEventListener('click', () => { $('settings-modal').hidden = true; });
  $('settings-modal').addEventListener('click', (event) => {
    if (event.target.id === 'settings-modal') $('settings-modal').hidden = true;
  });
  $('token-save-btn').addEventListener('click', saveToken);
  $('token-clear-btn').addEventListener('click', clearToken);
  $('token-input').addEventListener('keydown', (event) => {
    if (event.key === 'Enter') saveToken();
  });

  document.addEventListener('keydown', (event) => {
    if (event.key !== 'Escape') return;
    $('player-modal').hidden = true;
    $('settings-modal').hidden = true;
  });
}

boot();

})();
