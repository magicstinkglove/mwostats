/* Generic renderers for metric-module sections.
 *
 * A backend module returns {sections: [...]}, each with a `type`. This file knows how to
 * draw each type — so adding a new Python metric module requires no changes here, as long
 * as it uses the existing section helpers in app/metrics/base.py.
 */

/* Wrapped in an IIFE: classic <script> tags share one global scope, so anything declared
 * at top level here would collide with app.js. Only window.MWOModules is exported. */
(function () {
'use strict';

// Validated categorical palette (dark-mode steps), fixed order — never cycled or
// reassigned by value. Checked against this app's chart surface (#161b22): worst
// adjacent CVD deltaE 8.4 (target >=8), worst adjacent normal-vision deltaE 19.3
// (floor >=15), all >=3:1 contrast. A line_section caps at 8 lines for exactly
// this reason — a 9th color would just repeat one of these.
const LINE_PALETTE = [
  '#3987e5', // blue
  '#d95926', // orange
  '#199e70', // aqua
  '#c98500', // yellow
  '#d55181', // magenta
  '#008300', // green
  '#9085e9', // violet
  '#e66767', // red
];
const CHART_SURFACE = '#161b22'; // must match .module-card's --panel background

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (value === null || value === undefined || value === false) continue;
    if (key === 'class') node.className = value;
    else if (key === 'text') node.textContent = value;
    else if (key.startsWith('on')) node.addEventListener(key.slice(2).toLowerCase(), value);
    else node.setAttribute(key, value);
  }
  for (const child of children.flat()) {
    if (child === null || child === undefined) continue;
    node.append(child.nodeType ? child : document.createTextNode(String(child)));
  }
  return node;
}

function sectionShell(section, ...body) {
  const wrap = el('div', { class: 'section' });
  if (section.title) wrap.append(el('h3', { text: section.title }));
  wrap.append(...body);
  if (section.note) wrap.append(el('p', { class: 'section-note', text: section.note }));
  return wrap;
}

/* ------------------------------------------------------------------ stats */

const TEAM_DOT = { A: 'var(--team-a)', B: 'var(--team-b)' };

function renderStats(section) {
  const groups = el('div', { class: 'stat-groups' });
  for (const group of section.groups || []) {
    const box = el('div', { class: 'stat-group', 'data-group': group.group || '' });
    box.append(el('h4', { text: group.label }));
    const grid = el('div', { class: 'stat-grid' });
    for (const stat of group.stats || []) {
      // `name` is who achieved the stat — the headline for a leaderboard entry, so it
      // renders first and prominent, on its own line (with a team dot, not spelled-out
      // "Team B" text) so a long username never runs on into the number or gets clipped
      // mid-word. The number becomes the supporting line underneath it. A stat with no
      // `name` (plain numeric tiles elsewhere) is unaffected — value stays the headline.
      grid.append(el('div', { class: `stat${stat.name ? ' has-name' : ''}` },
        el('div', { class: 'stat-label', text: stat.label }),
        stat.name ? el('div', { class: 'stat-name' },
          stat.team ? el('span', { class: 'stat-name-dot', style: `background:${TEAM_DOT[stat.team] || 'var(--muted)'}` }) : null,
          el('span', { class: 'stat-name-text', title: stat.name, text: stat.name }),
        ) : null,
        el('div', { class: 'stat-value', text: stat.value }),
        stat.hint ? el('div', { class: 'stat-hint', text: stat.hint }) : null,
      ));
    }
    box.append(grid);
    groups.append(box);
  }
  return sectionShell(section, groups);
}

/* ------------------------------------------------------------------ table */

// Sort numerically when the column looks numeric, alphabetically otherwise.
function compareCells(a, b) {
  const na = parseFloat(String(a).replace(/[,+]/g, ''));
  const nb = parseFloat(String(b).replace(/[,+]/g, ''));
  const bothNumeric = !Number.isNaN(na) && !Number.isNaN(nb);
  if (bothNumeric) return na - nb;
  return String(a).localeCompare(String(b), undefined, { numeric: true });
}

function renderTable(section) {
  const wrap = el('div', { class: 'table-wrap' });
  const table = el('table');
  const thead = el('thead');
  const headRow = el('tr');
  const align = section.align || [];
  let sortState = { index: null, asc: true };

  const tbody = el('tbody');

  const paint = (rows) => {
    tbody.replaceChildren();
    for (const row of rows) {
      const tr = el('tr');
      row.forEach((cell, index) => {
        const isReview = String(cell).toLowerCase() === 'review';
        // An explicit empty string means "intentionally blank" (e.g. a flag column);
        // only genuinely missing values get a dash.
        tr.append(el('td', {
          class: [align[index] === 'right' ? 'right' : '', isReview ? 'tag-review' : ''].filter(Boolean).join(' '),
          text: cell === null || cell === undefined ? '—' : cell,
        }));
      });
      tbody.append(tr);
    }
  };

  (section.columns || []).forEach((column, index) => {
    const th = el('th', {
      class: align[index] === 'right' ? 'right' : '',
      onclick: () => {
        sortState = {
          index,
          asc: sortState.index === index ? !sortState.asc : true,
        };
        const sorted = [...(section.rows || [])].sort((x, y) => {
          const result = compareCells(x[index], y[index]);
          return sortState.asc ? result : -result;
        });
        paint(sorted);
        thead.querySelectorAll('.sort-arrow').forEach((n) => n.remove());
        th.append(el('span', { class: 'sort-arrow', text: sortState.asc ? '▲' : '▼' }));
      },
    }, column);
    headRow.append(th);
  });

  thead.append(headRow);
  paint(section.rows || []);
  table.append(thead, tbody);
  wrap.append(table);
  return sectionShell(section, wrap);
}

/* ------------------------------------------------------------------ bar */

function renderBar(section) {
  const items = section.items || [];
  const max = Math.max(...items.map((i) => Math.abs(i.value)), 1);
  const bars = el('div', { class: 'bars' });
  for (const item of items) {
    bars.append(el('div', { class: 'bar-row' },
      el('div', { class: 'bar-label', title: item.label, text: item.label }),
      el('div', { class: 'bar-track' },
        el('div', {
          class: 'bar-fill',
          'data-group': item.group || '',
          style: `width:${(Math.abs(item.value) / max) * 100}%`,
        })),
      el('div', {
        class: 'bar-value',
        text: `${item.value.toLocaleString()}${section.unit ? ' ' + section.unit : ''}`,
      }),
    ));
  }
  return sectionShell(section, bars);
}

/* ------------------------------------------------------------------ line */

const MAX_DIRECT_LABELS = 4; // past this, converging lines make direct labels noise
const END_LABEL_MIN_GAP = 14; // px; closer than this and labels overlap, so skip them all

function renderLine(section) {
  const lines = section.lines || [];
  const xLabels = section.x || [];
  const width = Math.max(560, xLabels.length * 90);
  const height = 280;
  const pad = { top: 16, right: 16, bottom: 34, left: 52 };
  const plotW = width - pad.left - pad.right;
  const plotH = height - pad.top - pad.bottom;
  const xCount = Math.max(xLabels.length - 1, 1);
  const xAt = (index) => pad.left + (plotW / xCount) * index;

  const allValues = lines.flatMap((l) => l.points.filter((p) => p !== null && p !== undefined));
  const max = Math.max(...allValues, 1);
  const yAt = (value) => pad.top + plotH - (value / max) * plotH;

  // Color is assigned by each line's position, not its value — stable across
  // re-renders as long as the backend orders `lines` by something fixed (username).
  const colored = lines.map((line, index) => ({ ...line, color: LINE_PALETTE[index % LINE_PALETTE.length] }));

  const svgNS = 'http://www.w3.org/2000/svg';
  const svg = document.createElementNS(svgNS, 'svg');
  svg.setAttribute('viewBox', `0 0 ${width} ${height}`);
  svg.setAttribute('width', width);
  svg.setAttribute('height', height);

  const add = (tag, attrs, parent = svg) => {
    const node = document.createElementNS(svgNS, tag);
    for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, value);
    parent.append(node);
    return node;
  };

  // gridlines + y-axis labels
  for (let i = 0; i <= 4; i++) {
    const y = pad.top + (plotH / 4) * i;
    add('line', { x1: pad.left, y1: y, x2: width - pad.right, y2: y, stroke: '#2a323d', 'stroke-width': 1 });
    const label = add('text', {
      x: pad.left - 8, y: y + 4, 'text-anchor': 'end',
      fill: '#8b949e', 'font-size': 10, 'font-family': 'monospace',
    });
    label.textContent = Math.round(max - (max / 4) * i).toLocaleString();
  }

  // x-axis labels
  xLabels.forEach((label, index) => {
    const node = add('text', {
      x: xAt(index), y: height - 12, 'text-anchor': 'middle',
      fill: '#8b949e', 'font-size': 10, 'font-family': 'monospace',
    });
    node.textContent = label;
  });

  // One <g> per line (polyline + markers together) so hover/hide can target a
  // whole series at once, and so the hovered line can be raised to the front.
  const lineGroups = new Map(); // label -> {g, lastPoint}
  for (const line of colored) {
    const g = add('g', { 'data-label': line.label });
    let run = [];
    let lastPoint = null;
    const flush = () => {
      if (run.length > 1) {
        add('polyline', {
          points: run.map((p) => `${p[0]},${p[1]}`).join(' '),
          fill: 'none', stroke: line.color, 'stroke-width': 2,
          'stroke-linecap': 'round', 'stroke-linejoin': 'round',
        }, g);
      }
      run = [];
    };
    line.points.forEach((value, index) => {
      if (value === null || value === undefined) { flush(); return; }
      const point = [xAt(index), yAt(value)];
      run.push(point);
      lastPoint = point;
      // r=4 (8px) marker with a surface-color ring so it stays legible where
      // lines cross; the ring is drawn first so the fill sits on top of it.
      add('circle', { cx: point[0], cy: point[1], r: 6, fill: CHART_SURFACE }, g);
      add('circle', { cx: point[0], cy: point[1], r: 4, fill: line.color }, g);
    });
    flush();
    lineGroups.set(line.label, { g, lastPoint });
  }

  // Direct end-labels: only worthwhile with few, non-converging lines (see
  // marks-and-anatomy — past ~4 series, or when labels would collide, the
  // legend + tooltip carry identity instead).
  const endpoints = colored
    .map((line) => ({ line, point: lineGroups.get(line.label).lastPoint }))
    .filter((e) => e.point);
  let showEndLabels = colored.length <= MAX_DIRECT_LABELS && endpoints.length > 0;
  if (showEndLabels) {
    const ys = endpoints.map((e) => e.point[1]).sort((a, b) => a - b);
    for (let i = 1; i < ys.length; i++) {
      if (ys[i] - ys[i - 1] < END_LABEL_MIN_GAP) { showEndLabels = false; break; }
    }
  }
  if (showEndLabels) {
    for (const { line, point } of endpoints) {
      add('circle', { cx: point[0] + 9, cy: point[1], r: 3, fill: line.color });
      // Text carries a text token, never the series color — the dot beside it
      // is the identity cue (marks-and-anatomy: "text never wears the data color").
      add('text', {
        x: point[0] + 15, y: point[1] + 4, fill: '#c3c2b7', 'font-size': 11,
      }).textContent = line.label;
    }
  }

  // Crosshair + one shared tooltip, so a value is reachable without landing a
  // pointer exactly on a 2px line — the whole plot width is the hit target.
  const crosshair = add('line', {
    x1: 0, y1: pad.top, x2: 0, y2: height - pad.bottom,
    stroke: '#8b949e', 'stroke-width': 1, opacity: 0,
  });
  const hitArea = add('rect', {
    x: pad.left, y: pad.top, width: plotW, height: plotH,
    fill: 'transparent',
  });

  const container = el('div', { class: 'chart-container' });
  const tooltip = el('div', { class: 'chart-tooltip' });
  container.append(el('div', { class: 'chart-wrap' }, svg), tooltip);

  const hidden = new Set();
  let hovered = null;

  function applyState() {
    for (const line of colored) {
      const { g } = lineGroups.get(line.label);
      if (hidden.has(line.label)) {
        g.setAttribute('opacity', '0.15');
      } else if (hovered && hovered !== line.label) {
        g.setAttribute('opacity', '0.2');
      } else {
        g.setAttribute('opacity', '1');
        if (hovered === line.label) svg.append(g); // raise to front
      }
    }
    for (const row of legendRows.values()) {
      row.el.classList.toggle('is-hidden', hidden.has(row.label));
    }
  }

  hitArea.addEventListener('pointermove', (event) => {
    const rect = svg.getBoundingClientRect();
    const scale = rect.width / width; // svg may be laid out at a different CSS size than its viewBox
    const localX = (event.clientX - rect.left) / scale;
    const index = Math.max(0, Math.min(xCount, Math.round((localX - pad.left) / (plotW / xCount))));
    const x = xAt(index);

    crosshair.setAttribute('x1', x);
    crosshair.setAttribute('x2', x);
    crosshair.setAttribute('opacity', '1');

    const rows = colored
      .filter((line) => !hidden.has(line.label))
      .map((line) => ({ line, value: line.points[index] }))
      .filter((r) => r.value !== null && r.value !== undefined)
      .sort((a, b) => b.value - a.value);

    if (!rows.length) { tooltip.classList.remove('is-visible'); return; }

    tooltip.replaceChildren(
      el('div', { class: 'tt-x', text: xLabels[index] }),
      ...rows.map((r) => el('div', { class: 'tt-row' },
        el('span', { class: 'tt-key', style: `background:${r.line.color}` }),
        el('span', { class: 'tt-name', text: r.line.label }),
        el('span', { class: 'tt-value', text: Math.round(r.value).toLocaleString() }),
      )),
    );
    tooltip.classList.add('is-visible');
    // Keep the tooltip beside the crosshair without running off either edge.
    const tipWidth = 160;
    const rawLeft = x * scale + 14;
    tooltip.style.left = `${Math.min(rawLeft, rect.width - tipWidth)}px`;
    tooltip.style.top = `${pad.top}px`;
  });
  hitArea.addEventListener('pointerleave', () => {
    crosshair.setAttribute('opacity', '0');
    tooltip.classList.remove('is-visible');
  });

  // Legend: hover highlights a line, click toggles it — the interactivity the
  // per-team split alone doesn't provide.
  const legendRows = new Map(); // label -> {el, label}
  const legend = el('div', { class: 'chart-legend' });
  for (const line of colored) {
    const row = el('div', {
      class: 'legend-row',
      onmouseenter: () => { hovered = line.label; applyState(); },
      onmouseleave: () => { hovered = null; applyState(); },
      onclick: () => {
        if (hidden.has(line.label)) hidden.delete(line.label); else hidden.add(line.label);
        applyState();
      },
    },
      el('span', { class: 'legend-key', style: `background:${line.color}` }),
      el('span', { text: line.label }),
    );
    legendRows.set(line.label, { el: row, label: line.label });
    legend.append(row);
  }

  return sectionShell(section, container, legend);
}

/* ------------------------------------------------------------------ dispatch */

const RENDERERS = {
  stats: renderStats,
  table: renderTable,
  bar: renderBar,
  line: renderLine,
  note: (section) => el('p', { class: 'note', text: section.text }),
};

function renderSection(section) {
  const renderer = RENDERERS[section.type];
  if (!renderer) {
    return el('p', { class: 'note', text: `(No renderer for section type "${section.type}")` });
  }
  try {
    return renderer(section);
  } catch (error) {
    return el('p', { class: 'note', text: `Failed to render "${section.title || section.type}": ${error.message}` });
  }
}

window.MWOModules = { el, renderSection };

})();
