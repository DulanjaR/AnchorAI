(function () {
  'use strict';

  const C = window.C3Core;
  const STORE_KEY = 'c3_prototype_v1';
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
  const MAX_FILE_BYTES = 1024 * 1024;

  const $ = (sel, root) => (root || document).querySelector(sel);
  const $$ = (sel, root) => Array.from((root || document).querySelectorAll(sel));
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (ch) => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]));

  // ---------------------------------------------------------------- state
  function seedTasks() {
    return [
      { id: 't1', title: 'Hotel booking website', kind: 'code', complexity: 'moderate', column: 'doing' },
      { id: 't2', title: 'Database assignment report', kind: 'document', complexity: 'moderate', column: 'doing' },
      { id: 't3', title: 'Python data-cleaning script', kind: 'code', complexity: 'simple', column: 'todo' },
      { id: 't4', title: 'Software architecture quiz notes', kind: 'document', complexity: 'simple', column: 'done' },
    ];
  }

  function freshState() {
    return { tasks: seedTasks(), log: [], interruptions: 0 };
  }

  function loadState() {
    try {
      const raw = localStorage.getItem(STORE_KEY);
      if (raw) {
        const s = JSON.parse(raw);
        if (s && Array.isArray(s.tasks) && Array.isArray(s.log)) return s;
      }
    } catch (e) { /* storage unavailable: start fresh */ }
    return freshState();
  }

  let state = loadState();
  let awayOverride = null;

  function persist() {
    try { localStorage.setItem(STORE_KEY, JSON.stringify(state)); } catch (e) { /* ignore */ }
  }

  function taskById(id) { return state.tasks.find((t) => t.id === id); }

  function logEvent(event, task, details) {
    state.log.push({ ts: Date.now(), event, taskId: task ? task.id : '', task: task ? task.title : '', details: details || {} });
    persist();
  }

  function demoState() {
    const now = Date.now();
    const s = freshState();
    const make = (task, cp, minutes, type, agoMin) => {
      const prediction = C.predictDifficulty({ minutes, complexity: task.complexity, openItems: cp.openItems.length, type });
      task.column = 'interrupted';
      task.checkpoint = Object.assign({}, cp, {
        type, minutes, level: prediction.level, depth: prediction.depth.name, savedAt: now - agoMin * 60000,
      });
    };
    make(s.tasks[0], {
      goal: 'Finish the hotel booking website for the web-technologies assignment',
      completed: 'login.html, register.html and home.html are finished',
      workingPoint: 'contact.html: the form has name and email fields but no submit handler',
      problem: 'Should the email be validated in JavaScript or on the server?',
      nextStep: 'Add the submit button and connect the form to the backend',
      resources: 'Figma UI link, contact.html',
      openItems: ['validate email format', 'add submit button and connect to backend', 'show error message under the field'],
    }, 300, 'other_task', 300);
    make(s.tasks[1], {
      goal: 'Complete the database assignment report',
      completed: 'ER diagram and normalisation to 3NF',
      workingPoint: 'Writing the SQL queries section',
      problem: '',
      nextStep: 'Write the report queries and add references',
      resources: 'report_notes.md',
      openItems: ['SQL queries for the reports section'],
    }, 20, 'quick_message', 20);
    s.interruptions = 2;
    s.log.push({ ts: now - 300 * 60000, event: 'checkpoint_saved', taskId: 't1', task: s.tasks[0].title, details: { level: 'High', depth: 'Full', minutes: 300, demo: true } });
    s.log.push({ ts: now - 20 * 60000, event: 'checkpoint_saved', taskId: 't2', task: s.tasks[1].title, details: { level: 'Low', depth: 'Short', minutes: 20, demo: true } });
    return s;
  }

  // ---------------------------------------------------------------- helpers
  function fmtTime(ts) {
    const d = new Date(ts);
    return d.toLocaleDateString([], { month: 'short', day: 'numeric' }) + ' ' +
      d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  }

  function awayMinutesFor(task) {
    if (awayOverride != null) return awayOverride;
    const savedAt = task.checkpoint ? task.checkpoint.savedAt : Date.now();
    return Math.max(0, (Date.now() - savedAt) / 60000);
  }

  function toast(message) {
    const el = document.createElement('div');
    el.className = 'toast';
    el.textContent = message;
    $('#toasts').appendChild(el);
    setTimeout(() => el.remove(), 4200);
  }

  function badge(level) { return '<span class="badge ' + level + '">' + level + ' difficulty</span>'; }

  // ---------------------------------------------------------------- board
  function renderBoard() {
    const board = $('#board');
    board.innerHTML = COLUMNS.map((col) => {
      const tasks = state.tasks.filter((t) => t.column === col.id);
      const cards = tasks.length ? tasks.map(cardHtml).join('') : '<div class="empty-col">Drop a task here</div>';
      return '<section class="col col-' + col.id + '" data-col="' + col.id + '">' +
        '<h2><span>' + esc(col.title) + '</span><span>' + tasks.length + '</span></h2>' +
        '<div class="cards" data-drop="' + col.id + '">' + cards + '</div></section>';
    }).join('');
    $('#logCount').textContent = String(state.log.length);
  }

  function cardHtml(t) {
    const cp = t.checkpoint;
    const moveOptions = COLUMNS.map((c) => '<option value="' + c.id + '"' + (c.id === t.column ? ' selected' : '') + '>' + esc(c.title) + '</option>').join('');
    let extra = '';
    if (t.column === 'interrupted' && cp) {
      extra = '<p class="snippet"><strong>Stopped at:</strong> ' + esc(cp.workingPoint || 'not written') + '</p>';
    }
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

  function moveTask(id, target) {
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
    const from = t.column;
    t.column = target;
    logEvent('task_moved', t, { from, to: target });
    renderBoard();
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
      const id = btn.dataset.id;
      if (btn.dataset.action === 'interrupt') openCheckpoint(id, {});
      if (btn.dataset.action === 'resume') openSummary(id);
    });
    board.addEventListener('change', (e) => {
      const sel = e.target.closest('select[data-action="move"]');
      if (sel) moveTask(sel.dataset.id, sel.value);
    });
  }

  // ---------------------------------------------------------------- checkpoint dialog
  function openCheckpoint(taskId, preset) {
    const task = taskById(taskId);
    if (!task) return;
    const dlg = $('#cpDialog');
    const insights = [];
    const form = { manualOpen: null };

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
      '<div class="predict" aria-live="polite"><div><div class="note">Predicted resumption difficulty</div><div class="big" id="cpLevel"></div></div>' +
      '<div><div class="depth" id="cpDepth"></div><ul id="cpReasons"></ul></div></div>' +
      '<div class="section-title">2. Your checkpoint <span class="note" style="text-transform:none;letter-spacing:0">(you can skip any question)</span></div>' +
      '<div class="grid2">' +
      C.FIELDS.map((f) =>
        '<div class="field"><label for="cp-' + f.key + '">' + f.label + '<span class="sug off" id="sug-' + f.key + '">suggested</span></label>' +
        '<textarea id="cp-' + f.key + '" rows="2"></textarea></div>').join('') +
      '</div>' +
      '<div class="section-title">3. Add your files (optional, read-only)</div>' +
      '<input type="file" id="cpFiles" multiple accept=".txt,.md,.py,.js,.html,.css,.java,.php,.docx">' +
      '<div class="note">Text and code files are read in your browser to suggest what you were doing. Their text is not saved. Word (.docx) files will be read by the backend later.</div>' +
      '<div class="insights" id="cpInsights"></div>' +
      '</div>' +
      '<div class="dlg-foot"><button type="button" class="btn ghost" data-close>Cancel</button><button type="submit" class="btn primary" id="cpSave">Save checkpoint</button></div>' +
      '</form>';

    $('#cpType', dlg).value = preset.type || 'meeting';
    $('#cpComplexity', dlg).value = task.complexity;

    function openItemsAuto() { return insights.reduce((n, i) => n + (i.supported ? i.openCount : 0), 0); }

    function currentInput() {
      const open = form.manualOpen != null ? form.manualOpen : openItemsAuto();
      return {
        minutes: Number($('#cpMinutes', dlg).value),
        complexity: $('#cpComplexity', dlg).value,
        openItems: open,
        type: $('#cpType', dlg).value,
      };
    }

    function refresh() {
      const input = currentInput();
      $('#cpOpen', dlg).value = input.openItems;
      $('#cpOpenNote', dlg).textContent = form.manualOpen != null ? 'Set by you.' : 'Counted from your files when you add them.';
      const p = C.predictDifficulty(input);
      $('#cpLevel', dlg).innerHTML = badge(p.level).replace('badge ', 'badge big-badge ') + ' <span class="note">score ' + p.score + ' of ' + p.max + '</span>';
      $('#cpDepth', dlg).innerHTML = '<strong>Checkpoint depth: ' + p.depth.name + '</strong> &middot; ' + p.depth.suggested.length + ' fields suggested';
      $('#cpReasons', dlg).innerHTML = p.reasons.map((r) => '<li>' + esc(r.text) + ' (+' + r.points + ')</li>').join('');
      C.FIELDS.forEach((f) => $('#sug-' + f.key, dlg).classList.toggle('off', !p.depth.suggested.includes(f.key)));
    }

    function setField(key, text, append) {
      const el = $('#cp-' + key, dlg);
      if (!text) return;
      el.value = append && el.value.trim() ? el.value.trim() + '; ' + text : text;
    }

    function renderInsights() {
      $('#cpInsights', dlg).innerHTML = insights.map((i, idx) => {
        if (!i.supported) {
          return '<div class="insight"><strong>' + esc(i.name) + '</strong><div class="note">Not read here (' + esc(i.reason || 'type not supported') + '). It can still be added to resources.</div>' +
            '<div class="row"><button type="button" class="btn" data-use="resources" data-idx="' + idx + '">Add to resources</button></div></div>';
        }
        const bits = [i.lineCount + ' lines', i.openCount + ' open item' + (i.openCount === 1 ? '' : 's')];
        if (i.symbols.length) bits.push('functions: ' + i.symbols.slice(0, 4).join(', '));
        const sug = C.suggestFromFile(i);
        return '<div class="insight"><strong>' + esc(i.name) + '</strong><div class="note">' + esc(bits.join(' · ')) + '</div><div class="row">' +
          (sug.workingPoint ? '<button type="button" class="btn" data-use="workingPoint" data-idx="' + idx + '">Use as working point</button>' : '') +
          (sug.completed ? '<button type="button" class="btn" data-use="completed" data-idx="' + idx + '">Use as completed work</button>' : '') +
          '<button type="button" class="btn" data-use="resources" data-idx="' + idx + '">Add to resources</button></div></div>';
      }).join('');
    }

    dlg.oninput = (e) => {
      if (e.target.id === 'cpOpen') form.manualOpen = Math.max(0, Math.floor(Number(e.target.value) || 0));
      if (['cpMinutes', 'cpOpen', 'cpType', 'cpComplexity'].includes(e.target.id)) refresh();
    };
    dlg.onchange = async (e) => {
      if (e.target.id === 'cpType' || e.target.id === 'cpComplexity') refresh();
      if (e.target.id !== 'cpFiles') return;
      for (const file of Array.from(e.target.files)) {
        let info;
        const lower = file.name.toLowerCase();
        if (file.size > MAX_FILE_BYTES) info = { supported: false, name: file.name, reason: 'file is larger than 1 MB' };
        else if (lower.endsWith('.docx')) info = { supported: false, name: file.name, reason: '.docx is read by the backend later' };
        else info = C.analyzeFile(file.name, await file.text());
        const at = insights.findIndex((x) => x.name === info.name);
        if (at >= 0) insights[at] = info; else insights.push(info);
      }
      e.target.value = '';
      renderInsights();
      refresh();
    };
    dlg.onclick = (e) => {
      const quick = e.target.closest('[data-min]');
      if (quick) { $('#cpMinutes', dlg).value = quick.dataset.min; refresh(); return; }
      const use = e.target.closest('[data-use]');
      if (use) {
        const info = insights[Number(use.dataset.idx)];
        const sug = info.supported ? C.suggestFromFile(info) : { resources: info.name };
        setField(use.dataset.use, sug[use.dataset.use], use.dataset.use === 'resources');
        return;
      }
      if (e.target.closest('[data-close]')) dlg.close();
    };
    $('#cpForm', dlg).addEventListener('submit', (e) => {
      e.preventDefault();
      const values = {};
      C.FIELDS.forEach((f) => { values[f.key] = $('#cp-' + f.key, dlg).value.trim(); });
      if (!Object.values(values).some(Boolean)) { toast('Write at least one line, or press Cancel.'); return; }
      const input = currentInput();
      const p = C.predictDifficulty(input);
      const openList = [];
      insights.forEach((i) => {
        if (!i.supported) return;
        i.todos.forEach((t) => openList.push(t.text));
        i.openItems.forEach((t) => openList.push(t));
      });
      task.checkpoint = Object.assign({}, values, {
        type: input.type, minutes: input.minutes, complexity: input.complexity,
        level: p.level, depth: p.depth.name, openItems: openList, savedAt: Date.now(),
        files: insights.map((i) => i.name),
      });
      task.complexity = input.complexity;
      task.column = 'interrupted';
      state.interruptions += 1;
      logEvent('checkpoint_saved', task, {
        level: p.level, depth: p.depth.name, minutes: input.minutes, type: input.type,
        fields_filled: Object.values(values).filter(Boolean).length, files: insights.length,
      });
      dlg.close();
      renderBoard();
      toast('Checkpoint saved. Predicted difficulty: ' + p.level + '.');
    });

    refresh();
    renderInsights();
    dlg.showModal();
  }

  // ---------------------------------------------------------------- resume popup and summary
  function openResumeList() {
    const dlg = $('#resumeDialog');
    const waiting = state.tasks.filter((t) => t.column === 'interrupted' && t.checkpoint);
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
        waiting.forEach((t) => logEvent('resume_prompt_dismissed', t, { level: t.checkpoint.level }));
        dlg.close();
        renderBoard();
        return;
      }
      if (e.target.closest('[data-close]')) dlg.close();
    };
    logEvent('resume_prompt_shown', null, { waiting: waiting.length });
    dlg.showModal();
  }

  function openSummary(taskId) {
    const task = taskById(taskId);
    if (!task || !task.checkpoint) return;
    const cp = task.checkpoint;
    const level = cp.level;
    const away = awayMinutesFor(task);
    const summary = C.buildSummary(task, cp, level, away);
    const opened = Date.now();
    const dlg = $('#summaryDialog');

    dlg.innerHTML =
      '<div class="dlg-head"><h2>Restart summary</h2><button class="x" data-close aria-label="Close">&times;</button></div>' +
      '<div class="dlg-body"><div class="tags">' + badge(level) + '<span class="tag">' + esc(summary.depth.name) + ' summary</span></div>' +
      '<div id="sumView"><p class="summary-intro">' + esc(summary.intro) + '</p><div class="summary-lines">' +
      (summary.lines.length ? summary.lines.map((l) => '<div class="summary-line"><b>' + esc(l.label) + '</b>' + esc(l.text) + '</div>').join('')
        : '<div class="note">No checkpoint text was written.</div>') + '</div></div>' +
      '<div id="sumEdit" hidden><label class="lbl" for="sumText">Edit the summary</label><textarea id="sumText" rows="10"></textarea></div>' +
      '<p class="note" style="margin-top:12px">This only restates what you wrote. It never adds code or answers.</p></div>' +
      '<div class="dlg-foot"><button class="btn ghost" id="sumIgnore">Ignore</button><button class="btn" id="sumEditBtn">Edit</button>' +
      '<button class="btn primary" id="sumAccept">Accept and resume</button></div>';

    const text = C.summaryToText(summary);
    $('#sumText', dlg).value = text;
    let editing = false;

    function finish(action, extra) {
      const seconds = Math.round((Date.now() - opened) / 1000);
      logEvent('summary_' + action, task, Object.assign({ level, away_min: Math.round(away), viewed_s: seconds }, extra));
      task.lastCheckpoint = task.checkpoint;
      delete task.checkpoint;
      task.column = 'doing';
      dlg.close();
      renderBoard();
      toast(action === 'ignored' ? 'Summary ignored. Task is back in progress.' : 'Summary ' + action + '. Task is back in progress.');
    }

    dlg.onclick = (e) => {
      if (e.target.closest('[data-close]')) { dlg.close(); return; }
      if (e.target.id === 'sumAccept') {
        if (editing) {
          const edited = $('#sumText', dlg).value;
          finish(edited.trim() === text.trim() ? 'accepted' : 'edited', { chars_before: text.length, chars_after: edited.length });
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
    dlg.showModal();
  }

  // ---------------------------------------------------------------- incoming interruption
  function openIncoming() {
    const doing = state.tasks.filter((t) => t.column === 'doing');
    if (!doing.length) { toast('No task is in progress. Start a task first.'); return; }
    const dlg = $('#incomingDialog');
    dlg.innerHTML =
      '<div class="dlg-head"><h2>Incoming interruption</h2><button class="x" data-close aria-label="Close">&times;</button></div>' +
      '<div class="dlg-body"><p><strong>A meeting starts in 5 minutes.</strong> Save a checkpoint so you can pick up where you stopped?</p>' +
      '<label class="lbl" for="incTask">Task you are working on</label><select class="full" id="incTask">' +
      doing.map((t) => '<option value="' + t.id + '">' + esc(t.title) + '</option>').join('') + '</select></div>' +
      '<div class="dlg-foot"><button class="btn ghost" data-close>Skip</button><button class="btn primary" id="incSave">Save checkpoint</button></div>';
    dlg.onclick = (e) => {
      if (e.target.id === 'incSave') {
        const id = $('#incTask', dlg).value;
        dlg.close();
        logEvent('interruption_notified', taskById(id), { type: 'meeting' });
        openCheckpoint(id, { type: 'meeting' });
        return;
      }
      if (e.target.closest('[data-close]')) {
        if (e.target.textContent === 'Skip') logEvent('interruption_notified_skipped', null, {});
        dlg.close();
      }
    };
    dlg.showModal();
  }

  // ---------------------------------------------------------------- study log
  function renderLog() {
    const body = $('#logBody');
    const rows = state.log.slice().reverse();
    body.innerHTML = rows.map((r) =>
      '<tr><td>' + esc(fmtTime(r.ts)) + '</td><td>' + esc(r.event) + '</td><td>' + esc(r.task) + '</td>' +
      '<td class="details">' + esc(JSON.stringify(r.details)) + '</td></tr>').join('');
    $('#logEmpty').hidden = rows.length > 0;
    const count = (ev) => state.log.filter((r) => r.event === ev).length;
    const stats = [
      ['Checkpoints saved', count('checkpoint_saved')],
      ['Summaries accepted', count('summary_accepted')],
      ['Summaries edited', count('summary_edited')],
      ['Summaries ignored', count('summary_ignored')],
    ];
    $('#logStats').innerHTML = stats.map((s) => '<div class="stat"><b>' + s[1] + '</b><span>' + s[0] + '</span></div>').join('');
  }

  function exportCsv() {
    const q = (v) => '"' + String(v).replace(/"/g, '""') + '"';
    const lines = ['time,event,task,details'].concat(state.log.map((r) =>
      [q(new Date(r.ts).toISOString()), q(r.event), q(r.task), q(JSON.stringify(r.details))].join(',')));
    const blob = new Blob([lines.join('\n')], { type: 'text/csv' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'c3_study_log.csv';
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  }

  // ---------------------------------------------------------------- wiring
  function showTab(name) {
    $$('.tab').forEach((b) => b.classList.toggle('active', b.dataset.tab === name));
    $('#tab-board').hidden = name !== 'board';
    $('#tab-log').hidden = name !== 'log';
    if (name === 'log') renderLog();
  }

  function init() {
    bindBoard();
    renderBoard();
    $$('.tab').forEach((b) => b.addEventListener('click', () => showTab(b.dataset.tab)));
    $('#btnIncoming').addEventListener('click', openIncoming);
    $('#btnBack').addEventListener('click', openResumeList);
    $('#btnRule').addEventListener('click', () => $('#ruleDialog').showModal());
    $('#btnDemo').addEventListener('click', () => { state = demoState(); awayOverride = null; persist(); renderBoard(); toast('Demo data loaded: two interrupted tasks.'); });
    $('#btnReset').addEventListener('click', () => { if (confirm('Reset the board and the study log?')) { state = freshState(); awayOverride = null; persist(); renderBoard(); renderLog(); } });
    $('#btnExport').addEventListener('click', exportCsv);
    $('#btnClearLog').addEventListener('click', () => { if (confirm('Clear the study log?')) { state.log = []; persist(); renderLog(); renderBoard(); } });
    $$('dialog').forEach((d) => {
      d.addEventListener('click', (e) => { if (e.target === d) d.close(); });
      d.addEventListener('click', (e) => { if (e.target.closest('[data-close]') && d.id === 'ruleDialog') d.close(); });
    });
    if (state.tasks.some((t) => t.column === 'interrupted' && t.checkpoint)) setTimeout(openResumeList, 500);
  }

  init();
  window.C3App = { get state() { return state; } };
})();
