(function () {
  'use strict';

  const C = window.C3Core;
  const COLUMNS = [
    { id: 'todo', title: 'To do' },
    { id: 'doing', title: 'In progress' },
    { id: 'interrupted', title: 'Interrupted - not completed' },
    { id: 'done', title: 'Done' },
  ];
  const TYPES = {
    quick_message: 'Quick message',
    meeting: 'Meeting or call',
    other_task: 'Switching to another work task',
    break: 'Break',
  };
  const COMPLEXITY_LABEL = { simple: 'Simple', moderate: 'Moderate', complex: 'Complex' };

  const $ = (sel, root) => (root || document).querySelector(sel);

  // A file dropped outside a drop zone must not make the browser open it and leave the app.
  window.addEventListener('dragover', (e) => { if (e.dataTransfer && Array.from(e.dataTransfer.types || []).includes('Files')) e.preventDefault(); });
  window.addEventListener('drop', (e) => { if (e.dataTransfer && Array.from(e.dataTransfer.types || []).includes('Files')) e.preventDefault(); });

  function wireDrop(zone, onFiles) {
    if (!zone) return;
    ['dragenter', 'dragover'].forEach((ev) => zone.addEventListener(ev, (e) => { e.preventDefault(); zone.classList.add('over'); }));
    zone.addEventListener('dragleave', () => zone.classList.remove('over'));
    zone.addEventListener('drop', (e) => {
      e.preventDefault();
      zone.classList.remove('over');
      const files = Array.from((e.dataTransfer && e.dataTransfer.files) || []);
      if (files.length) onFiles(files);
    });
  }
  const $$ = (sel, root) => Array.from((root || document).querySelectorAll(sel));
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (ch) => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]));

  let store = null;
  let cache = { tasks: [], events: 0 };
  let awayOverride = null;

  const taskById = (id) => cache.tasks.find((t) => t.id === id);

  // ---------------------------------------------------------------- helpers
  function toast(message) {
    const el = document.createElement('div');
    el.className = 'toast';
    el.textContent = message;
    $('#toasts').appendChild(el);
    setTimeout(() => el.remove(), 4800);
  }

  async function attempt(fn) {
    try {
      return await fn();
    } catch (e) {
      toast(e && e.message ? e.message : 'Something went wrong.');
      return null;
    }
  }

  function note(event, taskId, details) {
    store.event(event, taskId, details).catch(() => { /* a lost note must never block the screen */ });
  }

  async function refresh() {
    cache = await store.load();
    renderBoard();
  }

  function awayMinutesFor(task) {
    if (awayOverride != null) return awayOverride;
    const savedAt = task.checkpoint ? task.checkpoint.savedAt : Date.now();
    return Math.max(0, (Date.now() - savedAt) / 60000);
  }

  function badge(level) { return '<span class="badge ' + level + '">' + level + ' difficulty</span>'; }

  // ---------------------------------------------------------------- board
  function renderBoard() {
    $('#board').innerHTML = COLUMNS.map((col) => {
      const tasks = cache.tasks.filter((t) => t.column === col.id);
      const cards = tasks.length ? tasks.map(cardHtml).join('') : '<div class="empty-col">Drop a task here</div>';
      return '<section class="col col-' + col.id + '" data-col="' + col.id + '">' +
        '<h2><span>' + esc(col.title) + '</span><span>' + tasks.length + '</span></h2>' +
        '<div class="cards">' + cards + '</div></section>';
    }).join('');
    $('#logCount').textContent = String(cache.events);
  }

  function cardHtml(t) {
    const cp = t.checkpoint;
    const moveOptions = COLUMNS.map((c) => '<option value="' + c.id + '"' + (c.id === t.column ? ' selected' : '') + '>' + esc(c.title) + '</option>').join('');
    const extra = t.column === 'interrupted' && cp
      ? '<p class="snippet"><strong>Stopped at:</strong> ' + esc(cp.workingPoint || 'not written') + '</p>' : '';
    const actions = [];
    if (t.column === 'doing') actions.push('<button class="btn" data-action="interrupt" data-id="' + t.id + '">Interrupt</button>');
    if (t.column === 'interrupted') actions.push('<button class="btn primary" data-action="resume" data-id="' + t.id + '">Resume</button>');
    actions.push('<select data-action="move" data-id="' + t.id + '" aria-label="Move task">' + moveOptions + '</select>');
    return '<article class="card" draggable="true" tabindex="0" data-id="' + t.id + '">' +
      '<h3>' + esc(t.title) + '</h3>' +
      '<div class="tags"><span class="tag">' + (t.kind === 'code' ? 'Code' : 'Document') + '</span>' +
      '<span class="tag">' + COMPLEXITY_LABEL[t.complexity] + '</span>' +
      (t.column === 'interrupted' && cp ? badge(cp.level) : '') + '</div>' + extra +
      '<div class="card-actions">' + actions.join('') + '</div></article>';
  }

  async function moveTask(id, target) {
    const t = taskById(id);
    if (!t || t.column === target) return;
    if (target === 'interrupted') {
      if (t.column !== 'doing') { toast('Only a task that is in progress can be interrupted.'); renderBoard(); return; }
      openCheckpoint(t.id, {});
      renderBoard();
      return;
    }
    if (t.column === 'interrupted') {
      if (target === 'doing') { openSummary(t.id); renderBoard(); return; }
      if (target === 'todo') { toast('Resume or complete the task instead of moving it back.'); renderBoard(); return; }
    }
    await attempt(() => store.move(id, target));
    await refresh();
  }

  function bindBoard() {
    const board = $('#board');
    let dragId = null;

    board.addEventListener('dragstart', (e) => {
      const card = e.target.closest('.card');
      if (!card) return;
      dragId = card.dataset.id;
      e.dataTransfer.effectAllowed = 'move';
      e.dataTransfer.setData('text/plain', dragId);
      card.classList.add('dragging');
    });
    board.addEventListener('dragend', (e) => {
      const card = e.target.closest('.card');
      if (card) card.classList.remove('dragging');
      $$('.col.over').forEach((c) => c.classList.remove('over'));
    });
    board.addEventListener('dragover', (e) => {
      const col = e.target.closest('.col');
      if (!col) return;
      e.preventDefault();
      e.dataTransfer.dropEffect = 'move';
      $$('.col.over').forEach((c) => { if (c !== col) c.classList.remove('over'); });
      col.classList.add('over');
    });
    board.addEventListener('dragleave', (e) => {
      const col = e.target.closest('.col');
      if (col && !col.contains(e.relatedTarget)) col.classList.remove('over');
    });
    board.addEventListener('drop', (e) => {
      const col = e.target.closest('.col');
      if (!col) return;
      e.preventDefault();
      col.classList.remove('over');
      const id = dragId || e.dataTransfer.getData('text/plain');
      dragId = null;
      moveTask(id, col.dataset.col);
    });
    board.addEventListener('click', (e) => {
      const btn = e.target.closest('button[data-action]');
      if (!btn) return;
      if (btn.dataset.action === 'interrupt') openCheckpoint(btn.dataset.id, {});
      if (btn.dataset.action === 'resume') openSummary(btn.dataset.id);
    });
    board.addEventListener('change', (e) => {
      const sel = e.target.closest('select[data-action="move"]');
      if (sel) moveTask(sel.dataset.id, sel.value);
    });
  }

  // ---------------------------------------------------------------- checkpoint dialog
  async function openCheckpoint(taskId, preset) {
    const task = taskById(taskId);
    if (!task) return;
    const dlg = $('#cpDialog');
    const insights = [];
    const form = { manualOpen: null };
    let seq = 0;

    dlg.innerHTML =
      '<form method="dialog" id="cpForm">' +
      '<div class="dlg-head"><h2>Save a checkpoint &middot; ' + esc(task.title) + '</h2><button type="button" class="x" data-close aria-label="Close">&times;</button></div>' +
      '<div class="dlg-body">' +
      '<div class="section-title" style="margin-top:0">1. The interruption</div>' +
      '<div class="grid2">' +
      '<div class="field"><label for="cpType">What is interrupting you?</label><select class="full" id="cpType">' +
      Object.keys(TYPES).map((k) => '<option value="' + k + '">' + TYPES[k] + '</option>').join('') + '</select></div>' +
      '<div class="field"><label for="cpComplexity">Task complexity</label><select class="full" id="cpComplexity">' +
      Object.keys(COMPLEXITY_LABEL).map((k) => '<option value="' + k + '">' + COMPLEXITY_LABEL[k] + '</option>').join('') + '</select></div>' +
      '<div class="field"><label for="cpMinutes">Expected time away (minutes)</label><input type="number" id="cpMinutes" min="0" step="1" value="30">' +
      '<div class="quick"><button type="button" class="btn" data-min="10">10 min</button><button type="button" class="btn" data-min="60">1 hour</button>' +
      '<button type="button" class="btn" data-min="300">5 hours</button><button type="button" class="btn" data-min="1440">1 day</button></div></div>' +
      '<div class="field"><label for="cpOpen">Unfinished items</label><input type="number" id="cpOpen" min="0" step="1" value="0">' +
      '<div class="note" id="cpOpenNote">Counted from your files when you add them.</div></div>' +
      '</div>' +
      '<div class="predict" aria-live="polite"><div><div class="note">Predicted resumption difficulty</div><div class="big" id="cpLevel">...</div></div>' +
      '<div><div class="depth" id="cpDepth"></div><ul id="cpReasons"></ul></div></div>' +
      '<div class="charts" id="cpCharts"><div class="chart-card"><div class="chart-title">What adds to the score</div><div id="cpFactors"></div></div>' +
      '<div class="chart-card"><div class="chart-title">Score vs time away <span class="note">(moves as you type)</span></div><div id="cpCurve"></div></div></div>' +
      '<div class="section-title">2. Your checkpoint <span class="note" style="text-transform:none;letter-spacing:0">(you can skip any question; greyed boxes are optional at this depth)</span></div>' +
      '<div class="grid2">' +
      C.FIELDS.map((f) =>
        '<div class="field"><label for="cp-' + f.key + '">' + f.label + '<span class="sug off" id="sug-' + f.key + '">suggested</span></label>' +
        '<textarea id="cp-' + f.key + '" rows="2"></textarea></div>').join('') +
      '</div>' +
      '<div class="section-title">3. Add your files (optional, read-only)</div>' +
      '<div class="dropzone" id="cpDrop"><div class="drop-title">Drop your unfinished files here from File Explorer</div>' +
      '<div class="note">or choose them:</div><input type="file" id="cpFiles" multiple accept=".txt,.md,.py,.js,.html,.css,.java,.php,.docx"></div>' +
      '<div class="note" id="cpFilesNote"></div>' +
      '<div class="insights" id="cpInsights"></div>' +
      '</div>' +
      '<div class="dlg-foot"><button type="button" class="btn ghost" data-close>Cancel</button><button type="submit" class="btn primary" id="cpSave">Save checkpoint</button></div>' +
      '</form>';

    $('#cpType', dlg).value = preset.type || 'meeting';
    $('#cpComplexity', dlg).value = task.complexity;
    $('#cpFilesNote', dlg).textContent = store.mode === 'server'
      ? 'Text, code and Word (.docx) files are analysed on the server. Only headings, open items and function names are kept; the file text is not stored.'
      : 'Text and code files are read in your browser. Their text is not saved. Word (.docx) files need the backend server.';

    const openItemsAuto = () => insights.reduce((n, i) => n + (i.supported ? i.openCount : 0), 0);

    function currentInput() {
      return {
        minutes: Number($('#cpMinutes', dlg).value),
        complexity: $('#cpComplexity', dlg).value,
        openItems: form.manualOpen != null ? form.manualOpen : openItemsAuto(),
        type: $('#cpType', dlg).value,
      };
    }

    const FACTOR_MAX = [3, 2, 2, 1];
    const FACTOR_COLOR = ['#2f6fed', '#7a5af8', '#f79009', '#12b76a'];
    const LEVEL_COLOR = { Low: '#12b76a', Medium: '#f79009', High: '#d92d20' };

    function renderFactors(p) {
      const bars = p.reasons.map((r, i) => {
        const max = FACTOR_MAX[i] || 3;
        return '<div class="fbar"><div class="fbar-label"><span>' + esc(r.text) + '</span><b>+' + r.points + ' of ' + max + '</b></div>' +
          '<div class="fbar-track"><div class="fbar-fill" style="width:' + Math.round((r.points / max) * 100) + '%;background:' + FACTOR_COLOR[i % 4] + '"></div></div></div>';
      }).join('');
      let cells = '';
      for (let i = 0; i <= p.max; i++) {
        const zone = i >= 5 ? 'high' : i >= 3 ? 'med' : 'low'; // same cut points as the rule: Medium from 3, High from 5
        cells += '<div class="cell ' + zone + (i <= p.score ? ' on' : '') + '">' + i + '</div>';
      }
      $('#cpFactors', dlg).innerHTML = bars + '<div class="meter-title">Total score ' + p.score + ' of ' + p.max + ' &rarr; ' + esc(p.level) + '</div>' +
        '<div class="meter">' + cells + '</div><div class="meter-legend"><span>Low 0-2</span><span>Medium 3-4</span><span>High 5-8</span></div>';
    }

    function renderCurve(input) {
      const W = 360, H = 170, L = 28, R = 12, T = 14, B = 30;
      const minX = 1, maxX = 1440, lg = Math.log(maxX / minX);
      const clamp = (m) => Math.max(minX, Math.min(maxX, Number(m) || minX));
      const px = (m) => L + (Math.log(clamp(m) / minX) / lg) * (W - L - R);
      const py = (sc) => T + (1 - sc / C.MAX_SCORE) * (H - T - B);
      const scoreAt = (m) => C.predictDifficulty({ minutes: m, complexity: input.complexity, openItems: input.openItems, type: input.type });
      const band = (from, to, color) => '<rect x="' + L + '" y="' + py(to) + '" width="' + (W - L - R) + '" height="' + (py(from) - py(to)) + '" fill="' + color + '" opacity="0.14"/>';
      const pts = [];
      for (let i = 0; i <= 140; i++) {
        const m = minX * Math.exp((lg * i) / 140);
        pts.push(px(m).toFixed(1) + ',' + py(scoreAt(m).score).toFixed(1));
      }
      const cur = scoreAt(clamp(input.minutes));
      const cx = px(input.minutes), cy = py(cur.score);
      const ticks = [[5, '5 min'], [15, '15 min'], [60, '1 h'], [240, '4 h'], [1440, '1 day']];
      const label = C.formatMinutes(input.minutes) + ' \u2192 score ' + cur.score;
      let svg = '<svg viewBox="0 0 ' + W + ' ' + H + '" width="100%" role="img" aria-label="Difficulty score against time away">' +
        band(0, 2.5, LEVEL_COLOR.Low) + band(2.5, 4.5, LEVEL_COLOR.Medium) + band(4.5, C.MAX_SCORE, LEVEL_COLOR.High);
      [0, 2, 4, 6, 8].forEach((v) => { svg += '<text x="' + (L - 6) + '" y="' + (py(v) + 3) + '" text-anchor="end" font-size="9" fill="#667085">' + v + '</text>'; });
      ticks.forEach(([m, t]) => {
        svg += '<line x1="' + px(m) + '" y1="' + T + '" x2="' + px(m) + '" y2="' + (H - B) + '" stroke="#d0d5dd" stroke-dasharray="2 3"/>' +
          '<text x="' + px(m) + '" y="' + (H - B + 13) + '" text-anchor="middle" font-size="9" fill="#667085">' + t + '</text>';
      });
      svg += '<polyline points="' + pts.join(' ') + '" fill="none" stroke="#1d2939" stroke-width="1.8"/>' +
        '<line x1="' + cx + '" y1="' + cy + '" x2="' + cx + '" y2="' + (H - B) + '" stroke="' + LEVEL_COLOR[cur.level] + '" stroke-width="1.5"/>' +
        '<circle cx="' + cx + '" cy="' + cy + '" r="5.5" fill="' + LEVEL_COLOR[cur.level] + '" stroke="#fff" stroke-width="2"/>' +
        '<text x="' + (L + 4) + '" y="' + (py(7) + 3) + '" font-size="9" fill="' + LEVEL_COLOR.High + '">High</text>' +
        '<text x="' + (L + 4) + '" y="' + (py(3.5) + 3) + '" font-size="9" fill="' + LEVEL_COLOR.Medium + '">Medium</text>' +
        '<text x="' + (L + 4) + '" y="' + (py(1) + 3) + '" font-size="9" fill="' + LEVEL_COLOR.Low + '">Low</text></svg>';
      $('#cpCurve', dlg).innerHTML = svg + '<div class="curve-now"><span class="dot" style="background:' + LEVEL_COLOR[cur.level] + '"></span><b>' + esc(label) + '</b> &middot; ' + cur.level + ' difficulty</div>';
    }

    async function refreshPrediction() {
      const input = currentInput();
      renderCurve(input);
      $('#cpOpen', dlg).value = input.openItems;
      $('#cpOpenNote', dlg).textContent = form.manualOpen != null ? 'Set by you.' : 'Counted from your files when you add them.';
      const mine = ++seq;
      let p;
      try { p = await store.predict(input); } catch (e) { return; }
      if (mine !== seq) return;
      $('#cpLevel', dlg).innerHTML = badge(p.level).replace('badge ', 'badge big-badge ') + ' <span class="note">score ' + p.score + ' of ' + p.max + '</span>';
      $('#cpDepth', dlg).innerHTML = '<strong>Checkpoint depth: ' + esc(p.depth) + '</strong> &middot; ' + p.suggested.length + ' fields suggested';
      $('#cpReasons', dlg).innerHTML = p.reasons.map((r) => '<li>' + esc(r.text) + ' (+' + r.points + ')</li>').join('');
      C.FIELDS.forEach((f) => {
        $('#sug-' + f.key, dlg).classList.toggle('off', !p.suggested.includes(f.key));
        $('#cp-' + f.key, dlg).closest('.field').classList.toggle('dim', !p.suggested.includes(f.key));
      });
      renderFactors(p);
    }

    function setField(key, text, append) {
      const el = $('#cp-' + key, dlg);
      if (!text) return;
      el.value = append && el.value.trim() ? el.value.trim() + '; ' + text : text;
    }

    function renderInsights() {
      $('#cpInsights', dlg).innerHTML = insights.map((i, idx) => {
        if (!i.supported) {
          return '<div class="insight"><strong>' + esc(i.name) + '</strong><div class="note">Not read (' + esc(i.reason || 'type not supported') + '). It can still be added to resources.</div>' +
            '<div class="row"><button type="button" class="btn" data-use="resources" data-idx="' + idx + '">Add to resources</button></div></div>';
        }
        const bits = [i.lineCount + ' lines', i.openCount + ' open item' + (i.openCount === 1 ? '' : 's')];
        if (i.symbols && i.symbols.length) bits.push('functions: ' + i.symbols.slice(0, 4).join(', '));
        const sug = i.suggest || {};
        return '<div class="insight"><strong>' + esc(i.name) + '</strong><div class="note">' + esc(bits.join(' · ')) + '</div><div class="row">' +
          (sug.workingPoint ? '<button type="button" class="btn" data-use="workingPoint" data-idx="' + idx + '">Use as working point</button>' : '') +
          (sug.completed ? '<button type="button" class="btn" data-use="completed" data-idx="' + idx + '">Use as completed work</button>' : '') +
          '<button type="button" class="btn" data-use="resources" data-idx="' + idx + '">Add to resources</button></div></div>';
      }).join('');
    }

    dlg.oninput = (e) => {
      if (e.target.id === 'cpOpen') form.manualOpen = Math.max(0, Math.floor(Number(e.target.value) || 0));
      if (['cpMinutes', 'cpOpen', 'cpType', 'cpComplexity'].includes(e.target.id)) refreshPrediction();
    };
    async function addFiles(files) {
      const result = await attempt(() => store.analyzeFiles(files));
      if (!result) return;
      result.forEach((info) => {
        const at = insights.findIndex((x) => x.name === info.name);
        if (at >= 0) insights[at] = info; else insights.push(info);
      });
      renderInsights();
      refreshPrediction();
    }
    wireDrop($('#cpDrop', dlg), addFiles);
    dlg.onchange = async (e) => {
      if (e.target.id === 'cpType' || e.target.id === 'cpComplexity') refreshPrediction();
      if (e.target.id !== 'cpFiles') return;
      const files = Array.from(e.target.files);
      e.target.value = '';
      await addFiles(files);
    };
    dlg.onclick = (e) => {
      const quick = e.target.closest('[data-min]');
      if (quick) { $('#cpMinutes', dlg).value = quick.dataset.min; refreshPrediction(); return; }
      const use = e.target.closest('[data-use]');
      if (use) {
        const info = insights[Number(use.dataset.idx)];
        const sug = info.supported ? (info.suggest || {}) : { resources: info.name };
        setField(use.dataset.use, sug[use.dataset.use], use.dataset.use === 'resources');
        return;
      }
      if (e.target.closest('[data-close]')) dlg.close();
    };
    $('#cpForm', dlg).addEventListener('submit', async (e) => {
      e.preventDefault();
      const values = {};
      C.FIELDS.forEach((f) => { values[f.key] = $('#cp-' + f.key, dlg).value.trim(); });
      if (!Object.values(values).some(Boolean)) { toast('Write at least one line, or press Cancel.'); return; }
      const input = currentInput();
      const openList = [];
      insights.forEach((i) => {
        if (!i.supported) return;
        i.todos.forEach((t) => openList.push(t.text));
        i.openItems.forEach((t) => openList.push(t));
      });
      const payload = Object.assign({}, values, {
        openItems: openList, files: insights.map((i) => i.name), fileSnapshots: insights.filter((i) => i.supported).map(C.snapshotOf), type: input.type, minutes: input.minutes,
        complexity: input.complexity, openItemsCount: input.openItems, trigger: preset.trigger || 'user',
      });
      const saved = await attempt(() => store.saveCheckpoint(taskId, payload));
      if (!saved) return;
      dlg.close();
      await refresh();
      toast('Checkpoint saved. Predicted difficulty: ' + saved.checkpoint.level + '.');
    });

    await refreshPrediction();
    dlg.showModal();
  }

  // ---------------------------------------------------------------- resume popup and summary
  function openResumeList() {
    const dlg = $('#resumeDialog');
    const waiting = cache.tasks.filter((t) => t.column === 'interrupted' && t.checkpoint);
    if (!waiting.length) { toast('No interrupted tasks. Nothing to resume.'); return; }
    dlg.innerHTML =
      '<div class="dlg-head"><h2>Welcome back</h2><button class="x" data-close aria-label="Close">&times;</button></div>' +
      '<div class="dlg-body"><p>You have <strong>' + waiting.length + ' interrupted task' + (waiting.length === 1 ? '' : 's') + '</strong> that ' +
      (waiting.length === 1 ? 'is' : 'are') + ' still not completed.</p>' +
      '<div class="away-row"><label for="awaySel">Demo: pretend I was away for</label><select id="awaySel">' +
      '<option value="">the real time</option><option value="5">5 minutes</option><option value="60">1 hour</option><option value="300">5 hours</option><option value="1440">1 day</option></select></div>' +
      '<div id="resumeItems"></div></div>' +
      '<div class="dlg-foot"><button class="btn ghost" id="ignoreAll">Not now</button></div>';

    function renderItems() {
      $('#resumeItems', dlg).innerHTML = waiting.map((t) =>
        '<div class="resume-item"><div><h3>' + esc(t.title) + '</h3><div class="tags">' + badge(t.checkpoint.level) +
        '<span class="tag">away ' + C.formatMinutes(awayMinutesFor(t)) + '</span></div>' +
        '<div class="note">Stopped at: ' + esc(t.checkpoint.workingPoint || 'not written') + '</div></div>' +
        '<button class="btn primary" data-resume="' + t.id + '">Resume</button></div>').join('');
    }
    renderItems();
    $('#awaySel', dlg).addEventListener('change', (e) => {
      awayOverride = e.target.value === '' ? null : Number(e.target.value);
      renderItems();
    });
    dlg.onclick = (e) => {
      const r = e.target.closest('[data-resume]');
      if (r) { dlg.close(); openSummary(r.dataset.resume); return; }
      if (e.target.id === 'ignoreAll') {
        waiting.forEach((t) => note('resume_prompt_dismissed', t.id, { level: t.checkpoint.level }));
        dlg.close();
        return;
      }
      if (e.target.closest('[data-close]')) dlg.close();
    };
    note('resume_prompt_shown', null, { waiting: waiting.length });
    dlg.showModal();
  }

  async function openSummary(taskId) {
    const task = taskById(taskId);
    if (!task || !task.checkpoint) return;
    const away = awayMinutesFor(task);
    const opened = Date.now();
    const dlg = $('#summaryDialog');
    let data = null;
    let editing = false;
    let wanted = 'template';
    const snaps = (task.checkpoint.fileSnapshots || []);

    const writer = store.mode === 'server'
      ? '<div class="away-row"><label for="sumMode">Summary writer</label><select id="sumMode">' +
        '<option value="template">Rule-based template</option>' +
        '<option value="lora"' + (store.loraAvailable ? '' : ' disabled') + '>AI model (fine-tuned Qwen)' + (store.loraAvailable ? '' : ' - not installed on this server') + '</option></select></div>'
      : '<p class="note">Summary writer: rule-based template. The fine-tuned AI model runs on the backend server.</p>';

    dlg.innerHTML =
      '<div class="dlg-head"><h2>Restart summary</h2><button class="x" data-close aria-label="Close">&times;</button></div>' +
      '<div class="dlg-body">' + writer + '<div class="tags" id="sumTags"></div>' +
      '<div id="sumWarn" class="note warn" hidden></div>' +
      '<div id="sumView"><p class="note">Writing your summary...</p></div>' +
      '<div id="sumEdit" hidden><label class="lbl" for="sumText">Edit the summary</label><textarea id="sumText" rows="10"></textarea></div>' +
      '<div class="autolog"><div class="section-title" style="margin-top:14px">Auto-log: what changed in your files</div>' +
      (snaps.length
        ? '<p class="note">At your checkpoint the app noticed: ' + esc(snaps.map((x) => x.name).join(', ')) + '. Add the same files again to see what changed since then.</p>' +
          '<div class="dropzone" id="sumDrop"><div class="drop-title">Drop the same files here again</div>' +
          '<div class="note">or choose them:</div><input type="file" id="sumFiles" multiple accept=".txt,.md,.py,.js,.html,.css,.java,.php,.docx"></div>'
        : '<p class="note">No readable files were added at the checkpoint, so there is nothing to compare. Add files next time to get an automatic change list.</p>') +
      '<div id="autoLogOut"></div></div>' +
      '<p class="note" style="margin-top:12px">This only restates what you wrote. It never adds code or answers.</p></div>' +
      '<div class="dlg-foot"><button class="btn ghost" id="sumIgnore" disabled>Ignore</button><button class="btn" id="sumEditBtn" disabled>Edit</button>' +
      '<button class="btn primary" id="sumAccept" disabled>Accept and resume</button></div>';

    function paint() {
      $('#sumTags', dlg).innerHTML = badge(data.level) + '<span class="tag">' + esc(data.depth) + ' summary</span>' +
        '<span class="tag">' + (data.mode === 'lora' ? 'AI model' : 'Template') + '</span>';
      const warn = $('#sumWarn', dlg);
      warn.hidden = !data.fallbackReason;
      warn.textContent = data.fallbackReason ? 'Showing the template summary. ' + data.fallbackReason : '';
      if (data.mode === 'lora') {
        $('#sumView', dlg).innerHTML = '<div class="summary-text">' + esc(data.text) + '</div>';
      } else {
        $('#sumView', dlg).innerHTML = '<p class="summary-intro">' + esc(data.intro) + '</p><div class="summary-lines">' +
          (data.lines.length ? data.lines.map((l) => '<div class="summary-line"><b>' + esc(l.label) + '</b>' + esc(l.text) + '</div>').join('')
            : '<div class="note">No checkpoint text was written.</div>') + '</div>';
      }
      $('#sumText', dlg).value = data.text;
      $$('.dlg-foot button', dlg).forEach((b) => { b.disabled = false; });
    }

    async function load(mode) {
      $$('.dlg-foot button', dlg).forEach((b) => { b.disabled = true; });
      $('#sumView', dlg).innerHTML = '<p class="note">Writing your summary...</p>';
      const result = await attempt(() => store.summary(taskId, { awayMinutes: away, mode }));
      if (!result) { dlg.close(); return false; }
      data = result;
      paint();
      return true;
    }

    async function finish(action, extra) {
      const payload = Object.assign({
        action, shownText: data.text, viewedSeconds: Math.round((Date.now() - opened) / 1000), awayMinutes: away, mode: data.mode,
      }, extra);
      const done = await attempt(() => store.resume(taskId, payload));
      if (!done) return;
      dlg.close();
      await refresh();
      toast(action === 'ignored' ? 'Summary ignored. Task is back in progress.' : 'Summary ' + action + '. Task is back in progress.');
    }

    dlg.onclick = (e) => {
      if (e.target.closest('[data-close]')) { dlg.close(); return; }
      if (e.target.id === 'sumAccept') {
        if (editing) {
          const edited = $('#sumText', dlg).value;
          if (edited.trim() === data.text.trim()) finish('accepted', {});
          else finish('edited', { finalText: edited });
        } else finish('accepted', {});
      }
      if (e.target.id === 'sumIgnore') finish('ignored', {});
      if (e.target.id === 'sumEditBtn') {
        editing = !editing;
        $('#sumView', dlg).hidden = editing;
        $('#sumEdit', dlg).hidden = !editing;
        e.target.textContent = editing ? 'Back to view' : 'Edit';
        $('#sumAccept', dlg).textContent = editing ? 'Save edit and resume' : 'Accept and resume';
      }
    };
    async function recheckFiles(files) {
      if (!files.length) return;
      const result = await attempt(() => store.analyzeFiles(files));
      if (!result) return;
      const cmp = C.compareSnapshots(snaps, result);
      const t = cmp.totals;
      const out = $('#autoLogOut', dlg);
      if (!t.filesChecked) { out.innerHTML = '<p class="note">None of those files could be read (use text, code or .docx files).</p>'; return; }
      note('files_rechecked', task.id, t);
      const sign = (n) => (n > 0 ? '+' : '') + n;
      const chips = [[t.filesChecked, 'files checked'], [t.filesChanged, 'changed'], [sign(t.linesDelta), 'lines'],
        [t.newSymbols, 'new functions'], [t.resolved, 'open items gone'], [t.newOpen, 'new open items']];
      out.innerHTML = '<div class="stats mini">' + chips.map((c) => '<div class="stat"><b>' + esc(String(c[0])) + '</b><span>' + c[1] + '</span></div>').join('') + '</div>' +
        cmp.files.map((f) => '<div class="insight"><strong>' + esc(f.name) + '</strong> <span class="tag">' + f.status + '</span><ul class="changes">' +
          C.describeFileChange(f).map((x) => '<li>' + esc(x) + '</li>').join('') + '</ul></div>').join('') +
        (cmp.notChecked.length ? '<div class="note">Not added again: ' + esc(cmp.notChecked.join(', ')) + '</div>' : '');
    }
    wireDrop($('#sumDrop', dlg), recheckFiles);
    dlg.onchange = async (e) => {
      if (e.target.id === 'sumFiles') { const files = Array.from(e.target.files); e.target.value = ''; await recheckFiles(files); return; }
      if (e.target.id !== 'sumMode') return;
      wanted = e.target.value;
      editing = false;
      $('#sumView', dlg).hidden = false;
      $('#sumEdit', dlg).hidden = true;
      $('#sumEditBtn', dlg).textContent = 'Edit';
      $('#sumAccept', dlg).textContent = 'Accept and resume';
      await load(wanted);
    };
    dlg.showModal();
    await load(wanted);
  }

  // ---------------------------------------------------------------- new task
  function openNewTask() {
    const dlg = $('#newDialog');
    dlg.innerHTML =
      '<form method="dialog" id="newForm"><div class="dlg-head"><h2>New task</h2><button type="button" class="x" data-close aria-label="Close">&times;</button></div>' +
      '<div class="dlg-body"><div class="field"><label for="ntTitle">What are you working on?</label>' +
      '<input id="ntTitle" class="full" maxlength="120" placeholder="e.g. Inventory app (Java)" autocomplete="off"></div>' +
      '<div class="grid2"><div class="field"><label for="ntKind">Type</label><select class="full" id="ntKind">' +
      '<option value="code">Code project</option><option value="document">Document or report</option></select></div>' +
      '<div class="field"><label for="ntCx">Complexity</label><select class="full" id="ntCx">' +
      Object.keys(COMPLEXITY_LABEL).map((k) => '<option value="' + k + '"' + (k === 'moderate' ? ' selected' : '') + '>' + COMPLEXITY_LABEL[k] + '</option>').join('') +
      '</select></div></div>' +
      '<label class="check"><input type="checkbox" id="ntDoing" checked> I am working on it now (put it in In progress)</label></div>' +
      '<div class="dlg-foot"><button type="button" class="btn ghost" data-close>Cancel</button><button type="submit" class="btn primary" id="ntAdd">Add task</button></div></form>';
    dlg.onclick = (e) => { if (e.target.closest('[data-close]')) dlg.close(); };
    $('#newForm', dlg).addEventListener('submit', async (e) => {
      e.preventDefault();
      const title = $('#ntTitle', dlg).value.trim();
      if (!title) { toast('Give the task a name.'); return; }
      const created = await attempt(() => store.createTask({ title, kind: $('#ntKind', dlg).value, complexity: $('#ntCx', dlg).value }));
      if (!created) return;
      if ($('#ntDoing', dlg).checked) await attempt(() => store.move(created.id, 'doing'));
      dlg.close();
      await refresh();
      toast('Task added. Press Interrupt on its card when something interrupts you.');
    });
    dlg.showModal();
    $('#ntTitle', dlg).focus();
  }

  // ---------------------------------------------------------------- incoming interruption
  function openIncoming() {
    const doing = cache.tasks.filter((t) => t.column === 'doing');
    if (!doing.length) { toast('No task is in progress. Start a task first.'); return; }
    const dlg = $('#incomingDialog');
    dlg.innerHTML =
      '<div class="dlg-head"><h2>Incoming interruption</h2><button class="x" data-close aria-label="Close">&times;</button></div>' +
      '<div class="dlg-body"><p><strong>A meeting starts in 5 minutes.</strong> Save a checkpoint so you can pick up where you stopped?</p>' +
      '<label class="lbl" for="incTask">Task you are working on</label><select class="full" id="incTask">' +
      doing.map((t) => '<option value="' + t.id + '">' + esc(t.title) + '</option>').join('') + '</select></div>' +
      '<div class="dlg-foot"><button class="btn ghost" data-skip>Skip</button><button class="btn primary" id="incSave">Save checkpoint</button></div>';
    dlg.onclick = (e) => {
      if (e.target.id === 'incSave') {
        const id = $('#incTask', dlg).value;
        dlg.close();
        note('interruption_notified', id, { type: 'meeting' });
        openCheckpoint(id, { type: 'meeting', trigger: 'notification' });
        return;
      }
      if (e.target.closest('[data-skip]')) { note('interruption_notified_skipped', null, {}); dlg.close(); return; }
      if (e.target.closest('[data-close]')) dlg.close();
    };
    dlg.showModal();
  }

  // ---------------------------------------------------------------- study log
  async function renderLog() {
    const events = await attempt(() => store.events());
    if (!events) return;
    const rows = events.slice().reverse();
    const fmt = (ts) => {
      const d = new Date(ts);
      return d.toLocaleDateString([], { month: 'short', day: 'numeric' }) + ' ' + d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    };
    $('#logBody').innerHTML = rows.map((r) =>
      '<tr><td>' + esc(fmt(r.ts)) + '</td><td>' + esc(r.event) + '</td><td>' + esc(r.task) + '</td>' +
      '<td class="details">' + esc(JSON.stringify(r.details)) + '</td></tr>').join('');
    $('#logEmpty').hidden = rows.length > 0;
    const count = (ev) => events.filter((r) => r.event === ev).length;
    const stats = [['Checkpoints saved', count('checkpoint_saved')], ['Summaries accepted', count('summary_accepted')],
      ['Summaries edited', count('summary_edited')], ['Summaries ignored', count('summary_ignored')]];
    $('#logStats').innerHTML = stats.map((s) => '<div class="stat"><b>' + s[1] + '</b><span>' + s[0] + '</span></div>').join('');
    const bars = (rowsData) => {
      const max = Math.max(1, ...rowsData.map((r) => r[1]));
      return rowsData.map((r) => '<div class="fbar"><div class="fbar-label"><span>' + esc(r[0]) + '</span><b>' + r[1] + '</b></div>' +
        '<div class="fbar-track"><div class="fbar-fill" style="width:' + Math.round((r[1] / max) * 100) + '%;background:' + r[2] + '"></div></div></div>').join('');
    };
    const levelCount = (lvl) => events.filter((r) => r.event === 'checkpoint_saved' && r.details && r.details.level === lvl).length;
    $('#logCharts').innerHTML =
      '<div class="chart-card"><div class="chart-title">What students did with the summary</div>' +
        bars([['Accepted', count('summary_accepted'), '#12b76a'], ['Edited', count('summary_edited'), '#f79009'], ['Ignored', count('summary_ignored'), '#98a2b3']]) + '</div>' +
      '<div class="chart-card"><div class="chart-title">Checkpoints by predicted difficulty</div>' +
        bars([['Low', levelCount('Low'), '#12b76a'], ['Medium', levelCount('Medium'), '#f79009'], ['High', levelCount('High'), '#d92d20']]) + '</div>';
  }

  // ---------------------------------------------------------------- wiring
  function showTab(name) {
    $$('.tab').forEach((b) => b.classList.toggle('active', b.dataset.tab === name));
    $('#tab-board').hidden = name !== 'board';
    $('#tab-log').hidden = name !== 'log';
    if (name === 'log') renderLog();
  }

  async function init() {
    store = await window.C3Store.detect();
    const badgeEl = $('#modeBadge');
    badgeEl.textContent = store.mode === 'server' ? 'Server · ' + store.user : 'Browser only';
    badgeEl.title = store.mode === 'server'
      ? 'Data is stored by the C3 backend (database). Participant code: ' + store.user
      : 'Data stays in this browser. Run the backend to store it in the database.';
    badgeEl.classList.add(store.mode);

    bindBoard();
    $$('.tab').forEach((b) => b.addEventListener('click', () => showTab(b.dataset.tab)));
    $('#btnIncoming').addEventListener('click', openIncoming);
    $('#btnBack').addEventListener('click', openResumeList);
    $('#btnNewTask').addEventListener('click', openNewTask);
    $('#btnRule').addEventListener('click', () => $('#ruleDialog').showModal());
    $('#btnDemo').addEventListener('click', async () => {
      await attempt(() => store.demo());
      awayOverride = null;
      await refresh();
      toast('Demo data loaded: two interrupted tasks.');
    });
    $('#btnReset').addEventListener('click', async () => {
      if (!confirm('Reset the board and the study log?')) return;
      await attempt(() => store.reset());
      awayOverride = null;
      await refresh();
      renderLog();
    });
    $('#btnExport').addEventListener('click', () => attempt(() => store.exportCsv()));
    $$('dialog').forEach((d) => {
      d.addEventListener('click', (e) => { if (e.target === d) d.close(); });
      d.addEventListener('click', (e) => { if (e.target.closest('[data-close]') && d.id === 'ruleDialog') d.close(); });
    });

    const ok = await attempt(() => refresh());
    if (ok === null && !cache.tasks.length) { toast('Could not load the tasks.'); return; }
    if (cache.tasks.some((t) => t.column === 'interrupted' && t.checkpoint)) setTimeout(openResumeList, 500);
  }

  init();
  window.C3App = { get tasks() { return cache.tasks; }, get store() { return store; }, refresh };
})();
