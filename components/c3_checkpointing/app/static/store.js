/* Two interchangeable data stores for the prototype.
 *   LocalStore  - everything stays in this browser (works when index.html is opened as a file)
 *   ApiStore    - everything goes through the C3 backend (FastAPI + database)
 * Both expose the same async methods, so the interface code does not care which one it uses.
 */
(function () {
  'use strict';

  const C = window.C3Core;
  const MAX_FILE_BYTES = 1024 * 1024;
  const STORE_KEY = 'c3_prototype_v1';

  // ------------------------------------------------------------------ shared helpers
  function toCsv(events) {
    const q = (v) => '"' + String(v).replace(/"/g, '""') + '"';
    const lines = ['time,event,task,details'].concat(events.map((r) =>
      [q(new Date(r.ts).toISOString()), q(r.event), q(r.task), q(JSON.stringify(r.details))].join(',')));
    return lines.join('\n');
  }

  function download(text, filename) {
    const blob = new Blob([text], { type: 'text/csv' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  }

  function predictionShape(p) {
    return { score: p.score, max: p.max, level: p.level, depth: p.depth.name, suggested: p.depth.suggested, reasons: p.reasons };
  }

  // ------------------------------------------------------------------ LocalStore
  function seedTasks() {
    return [
      { id: 't1', title: 'Hotel booking website', kind: 'code', complexity: 'moderate', column: 'doing' },
      { id: 't2', title: 'Database assignment report', kind: 'document', complexity: 'moderate', column: 'doing' },
      { id: 't3', title: 'Python data-cleaning script', kind: 'code', complexity: 'simple', column: 'todo' },
      { id: 't4', title: 'Software architecture quiz notes', kind: 'document', complexity: 'simple', column: 'done' },
    ];
  }

  function freshState() { return { tasks: seedTasks(), log: [], interruptions: 0 }; }

  function createLocalStore() {
    function read() {
      try {
        const raw = localStorage.getItem(STORE_KEY);
        if (raw) {
          const s = JSON.parse(raw);
          if (s && Array.isArray(s.tasks) && Array.isArray(s.log)) return s;
        }
      } catch (e) { /* storage unavailable: start fresh */ }
      return freshState();
    }
    let state = read();
    const persist = () => { try { localStorage.setItem(STORE_KEY, JSON.stringify(state)); } catch (e) { /* ignore */ } };
    const find = (id) => {
      const t = state.tasks.find((x) => x.id === id);
      if (!t) throw new Error('Task not found.');
      return t;
    };
    const log = (event, task, details, ts) => {
      state.log.push({ ts: ts || Date.now(), event, taskId: task ? task.id : '', task: task ? task.title : '', details: details || {} });
    };
    const copy = (x) => JSON.parse(JSON.stringify(x));

    function demoState() {
      const now = Date.now();
      const s = freshState();
      const make = (task, cp, minutes, type, agoMin) => {
        const p = C.predictDifficulty({ minutes, complexity: task.complexity, openItems: cp.openItems.length, type });
        task.column = 'interrupted';
        task.checkpoint = Object.assign({}, cp, { type, minutes, complexity: task.complexity, level: p.level, score: p.score,
          depth: p.depth.name, files: [], savedAt: now - agoMin * 60000 });
        s.log.push({ ts: now - agoMin * 60000, event: 'checkpoint_saved', taskId: task.id, task: task.title,
          details: { level: p.level, depth: p.depth.name, minutes, demo: true } });
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
        goal: 'Complete the database assignment report', completed: 'ER diagram and normalisation to 3NF',
        workingPoint: 'Writing the SQL queries section', problem: '',
        nextStep: 'Write the report queries and add references', resources: 'report_notes.md',
        openItems: ['SQL queries for the reports section'],
      }, 20, 'quick_message', 20);
      s.interruptions = 2;
      return s;
    }

    return {
      mode: 'local',
      label: 'Browser only',
      loraAvailable: false,
      async load() { return { tasks: copy(state.tasks), events: state.log.length, interruptions: state.interruptions }; },
      async predict(input) { return predictionShape(C.predictDifficulty(input)); },
      async analyzeFiles(files) {
        const out = [];
        for (const file of files) {
          let info;
          const lower = file.name.toLowerCase();
          if (file.size > MAX_FILE_BYTES) info = { supported: false, name: file.name, reason: 'file is larger than 1 MB' };
          else if (lower.endsWith('.docx')) info = { supported: false, name: file.name, reason: '.docx needs the backend server' };
          else info = C.analyzeFile(file.name, await file.text());
          info.suggest = C.suggestFromFile(info);
          out.push(info);
        }
        return out;
      },
      async move(id, column) {
        const t = find(id);
        if (t.column === column) return copy(t);
        if (column === 'interrupted') throw new Error('Use the checkpoint form to interrupt a task.');
        if (t.column === 'interrupted' && column === 'doing') throw new Error('Resume the task to continue it; it cannot be moved back.');
        if (t.column === 'interrupted' && column === 'todo') throw new Error('Resume or complete the task instead of moving it back.');
        const from = t.column;
        t.column = column;
        log('task_moved', t, { from, to: column });
        persist();
        return copy(t);
      },
      async saveCheckpoint(id, p) {
        const t = find(id);
        if (t.column !== 'doing') throw new Error('Only a task that is in progress can be interrupted.');
        const fields = ['goal', 'completed', 'workingPoint', 'problem', 'nextStep', 'resources'];
        if (!fields.some((k) => (p[k] || '').trim())) throw new Error('Write at least one line in the checkpoint.');
        const count = p.openItemsCount != null ? p.openItemsCount : (p.openItems || []).length;
        const pred = C.predictDifficulty({ minutes: p.minutes, complexity: p.complexity, openItems: count, type: p.type });
        t.checkpoint = Object.assign({}, p, { level: pred.level, score: pred.score, depth: pred.depth.name, savedAt: Date.now() });
        t.complexity = p.complexity;
        t.column = 'interrupted';
        state.interruptions += 1;
        log('checkpoint_saved', t, { level: pred.level, depth: pred.depth.name, minutes: p.minutes, type: p.type,
          fields_filled: fields.filter((k) => (p[k] || '').trim()).length, files: (p.files || []).length, trigger: p.trigger || 'user' });
        persist();
        return copy(t);
      },
      async summary(id, opts) {
        const t = find(id);
        if (!t.checkpoint) throw new Error('This task has no open checkpoint.');
        const away = opts.awayMinutes != null ? opts.awayMinutes : Math.max(0, (Date.now() - t.checkpoint.savedAt) / 60000);
        const s = C.buildSummary(t, t.checkpoint, t.checkpoint.level, away);
        return { intro: s.intro, lines: s.lines, text: C.summaryToText(s), level: t.checkpoint.level, depth: s.depth.name,
          mode: 'template', requestedMode: opts.mode || 'template',
          fallbackReason: opts.mode === 'lora' ? 'The AI model needs the backend server.' : null };
      },
      async resume(id, p) {
        const t = find(id);
        if (!t.checkpoint) throw new Error('This task has no open checkpoint.');
        if (p.action === 'edited' && !(p.finalText || '').trim()) throw new Error('The edited summary is empty.');
        const away = p.awayMinutes != null ? p.awayMinutes : Math.max(0, (Date.now() - t.checkpoint.savedAt) / 60000);
        const d = { level: t.checkpoint.level, away_min: Math.round(away), viewed_s: Math.round(p.viewedSeconds || 0), mode: p.mode || 'template' };
        if (p.action === 'edited') Object.assign(d, { chars_before: (p.shownText || '').length, chars_after: (p.finalText || '').length });
        log('summary_' + p.action, t, d);
        t.lastCheckpoint = t.checkpoint;
        delete t.checkpoint;
        t.column = 'doing';
        persist();
        return copy(t);
      },
      async event(event, id, details) { log(event, id ? find(id) : null, details); persist(); },
      async events() { return copy(state.log); },
      async exportCsv() { download(toCsv(state.log), 'c3_study_log.csv'); },
      async demo() { state = demoState(); persist(); },
      async reset() { state = freshState(); persist(); },
    };
  }

  // ------------------------------------------------------------------ ApiStore
  function createApiStore(health) {
    const params = new URLSearchParams(location.search);
    let user = params.get('user');
    let key = params.get('key');
    try {
      if (user) localStorage.setItem('c3_user_id', user); else user = localStorage.getItem('c3_user_id');
      if (key) localStorage.setItem('c3_api_key', key); else key = localStorage.getItem('c3_api_key');
    } catch (e) { /* storage unavailable */ }
    user = user || 'demo-user';
    key = key || 'change-me';

    async function request(method, path, body, raw) {
      const headers = { 'X-API-Key': key, 'X-User-Id': user };
      let payload;
      if (body instanceof FormData) payload = body;
      else if (body !== undefined) { headers['Content-Type'] = 'application/json'; payload = JSON.stringify(body); }
      const res = await fetch('/api' + path, { method, headers, body: payload });
      if (!res.ok) {
        let msg = 'Request failed (' + res.status + ').';
        try {
          const j = await res.json();
          if (typeof j.detail === 'string') msg = j.detail;
          else if (Array.isArray(j.detail) && j.detail.length) msg = j.detail[0].msg || msg;
        } catch (e) { /* keep default message */ }
        if (res.status === 401) msg = 'The server refused the API key. Open the page with ?key=YOUR_KEY once.';
        throw new Error(msg);
      }
      if (raw) return res;
      return res.status === 204 ? null : res.json();
    }

    return {
      mode: 'server',
      label: 'Connected to server',
      user,
      loraAvailable: (health.modes || []).includes('lora'),
      async load() {
        const [tasks, state] = await Promise.all([request('GET', '/tasks'), request('GET', '/state')]);
        return { tasks, events: state.events, interruptions: state.interruptions };
      },
      predict(input) { return request('POST', '/predict', { minutes: input.minutes, complexity: input.complexity, openItems: input.openItems, type: input.type }); },
      async analyzeFiles(files) {
        const form = new FormData();
        for (const f of files) form.append('files', f, f.name);
        return (await request('POST', '/files/analyze', form)).files;
      },
      move(id, column) { return request('PATCH', '/tasks/' + id, { column }); },
      saveCheckpoint(id, p) { return request('POST', '/tasks/' + id + '/checkpoint', p); },
      summary(id, opts) {
        const q = new URLSearchParams({ mode: opts.mode || 'template' });
        if (opts.awayMinutes != null) q.set('awayMinutes', opts.awayMinutes);
        return request('GET', '/tasks/' + id + '/summary?' + q.toString());
      },
      resume(id, p) { return request('POST', '/tasks/' + id + '/resume', p); },
      async event(event, id, details) { await request('POST', '/events', { event, taskId: id || null, details: details || {} }); },
      events() { return request('GET', '/events'); },
      async exportCsv() {
        const res = await request('GET', '/export.csv', undefined, true);
        download(await res.text(), 'c3_study_log.csv');
      },
      async demo() { await request('POST', '/demo'); },
      async reset() { await request('POST', '/reset'); },
    };
  }

  async function detect() {
    try {
      const res = await fetch('/api/health', { cache: 'no-store' });
      if (res.ok) {
        const health = await res.json();
        if (health && health.component === 'c3_checkpointing') return createApiStore(health);
      }
    } catch (e) { /* no server: stay local */ }
    return createLocalStore();
  }

  window.C3Store = { detect, createLocalStore, createApiStore };
})();
