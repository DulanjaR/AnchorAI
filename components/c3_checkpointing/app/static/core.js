(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.C3Core = factory();
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  const LEVELS = ['Low', 'Medium', 'High'];
  const COMPLEXITY = { simple: 0, moderate: 1, complex: 2 };
  const MAX_SCORE = 8;

  const FIELDS = [
    { key: 'goal', label: 'Goal' },
    { key: 'completed', label: 'Completed work' },
    { key: 'workingPoint', label: 'Current working point' },
    { key: 'problem', label: 'Current problem or decision' },
    { key: 'nextStep', label: 'Next step' },
    { key: 'resources', label: 'Files / resources' },
  ];

  const DEPTH = {
    Low: { name: 'Short', suggested: ['workingPoint', 'nextStep'] },
    Medium: { name: 'Standard', suggested: ['goal', 'workingPoint', 'problem', 'nextStep'] },
    High: { name: 'Full', suggested: ['goal', 'completed', 'workingPoint', 'problem', 'nextStep', 'resources'] },
  };

  const SOURCE_EXT = ['py', 'js', 'html', 'css', 'java', 'php'];
  const TEXT_EXT = ['md', 'txt'];

  function validMinutes(m) {
    if (m === null || m === undefined || m === '') return null;
    const n = Number(m);
    return n >= 0 ? n : null;
  }

  function formatMinutes(value) {
    const m = validMinutes(value);
    if (m === null) return 'an unknown time';
    if (m < 1) return 'less than a minute';
    if (m < 60) return Math.round(m) + ' min';
    if (m < 1440) {
      const h = m / 60;
      return (Number.isInteger(h) ? h : h.toFixed(1)) + ' h';
    }
    const d = m / 1440;
    if (d === 1) return '1 day';
    return (Number.isInteger(d) ? d : d.toFixed(1)) + ' days';
  }

  function durationPoints(value) {
    const minutes = validMinutes(value);
    if (minutes === null) return 0;
    if (minutes < 15) return 0;
    if (minutes < 60) return 1;
    if (minutes < 240) return 2;
    return 3;
  }

  function openItemPoints(n) {
    if (n >= 5) return 2;
    if (n >= 2) return 1;
    return 0;
  }

  // Transparent, hand-set rule. Direction (longer interruption and more complex task -> harder)
  // follows the Model 1b weights; thresholds are placeholders until pilot data recalibrates them.
  function predictDifficulty(input) {
    const minutes = validMinutes(input.minutes);
    const complexity = Object.prototype.hasOwnProperty.call(COMPLEXITY, input.complexity) ? input.complexity : 'moderate';
    const openItems = Math.max(0, Math.floor(Number(input.openItems) || 0));
    const switches = input.type === 'other_task';

    const d = durationPoints(minutes);
    const c = COMPLEXITY[complexity];
    const o = openItemPoints(openItems);
    const s = switches ? 1 : 0;
    const score = d + c + o + s;
    const level = score >= 5 ? 'High' : score >= 3 ? 'Medium' : 'Low';

    const reasons = [
      { text: minutes !== null ? 'Away about ' + formatMinutes(minutes) : 'Time away not given', points: d },
      { text: 'Task complexity: ' + complexity, points: c },
      { text: openItems + ' unfinished item' + (openItems === 1 ? '' : 's'), points: o },
      { text: switches ? 'Interrupted by another work task' : 'Interruption does not need another work task', points: s },
    ];
    return { score, max: MAX_SCORE, level, depth: DEPTH[level], reasons };
  }

  function clean(text) {
    return String(text || '').trim();
  }

  // Restates only what the student wrote. It never adds content of its own (that is C4's role).
  function buildSummary(task, checkpoint, level, awayMinutes) {
    const cp = checkpoint || {};
    const lines = [];
    const add = (label, text) => {
      const t = clean(text);
      if (t) lines.push({ label, text: t });
    };

    add('You stopped at', cp.workingPoint);
    add('Next step', cp.nextStep);
    if (level === 'Medium' || level === 'High') {
      add('Goal', cp.goal);
      add('Open problem or decision', cp.problem);
    }
    if (level === 'High') {
      add('Already done', cp.completed);
      add('Files / resources', cp.resources);
      const items = (cp.openItems || []).slice(0, 5);
      if (items.length) add('Open items found in your own files', items.join('; '));
    }

    const intro = 'Welcome back to "' + (task && task.title ? task.title : 'your task') + '". You were away about ' +
      formatMinutes(awayMinutes) + '.';
    return { intro, lines, level, depth: DEPTH[level] };
  }

  function summaryToText(summary) {
    const body = summary.lines.map((l) => l.label + ': ' + l.text).join('\n');
    return summary.intro + (body ? '\n\n' + body : '\n\n(No checkpoint text was written.)');
  }

  function stripTags(s) {
    return String(s).replace(/<[^>]*>/g, '').trim();
  }

  // Read-only analysis of a text file. Only small facts are extracted; the file text is not kept.
  function analyzeFile(name, text) {
    const ext = (String(name).split('.').pop() || '').toLowerCase();
    const isSource = SOURCE_EXT.includes(ext);
    const isText = TEXT_EXT.includes(ext);
    if (!isSource && !isText) return { supported: false, name, ext };

    const lines = String(text || '').split(/\r?\n/);
    const todos = [];
    const openItems = [];
    const doneItems = [];
    const headings = [];
    const symbols = [];

    lines.forEach((raw, i) => {
      const t = raw.trim();
      const m = t.match(/\b(TODO|FIXME)\b[:\s-]*(.*)$/i);
      if (m) {
        const body = m[2].replace(/(-->|\*\/)\s*$/, '').trim();
        todos.push({ line: i + 1, text: body || t });
      }
      if (isText) {
        let h = t.match(/^#{1,3}\s+(.*)$/);
        if (h) headings.push(h[1].trim());
        h = t.match(/^[-*]\s+\[ \]\s+(.*)$/);
        if (h) openItems.push(h[1].trim());
        h = t.match(/^[-*]\s+\[[xX]\]\s+(.*)$/);
        if (h) doneItems.push(h[1].trim());
      }
      if (ext === 'html') {
        const title = t.match(/<title[^>]*>(.*?)<\/title>/i);
        if (title) headings.push(stripTags(title[1]));
        const h1 = t.match(/<h1[^>]*>(.*?)<\/h1>/i);
        if (h1) headings.push(stripTags(h1[1]));
      }
      let s;
      if (ext === 'js' || ext === 'html') {
        if ((s = t.match(/\bfunction\s+([A-Za-z_$][\w$]*)/))) symbols.push(s[1]);
        else if ((s = t.match(/\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?(?:\([^)]*\)|[A-Za-z_$][\w$]*)\s*=>/))) symbols.push(s[1]);
      } else if (ext === 'py') {
        if ((s = t.match(/^(?:def|class)\s+(\w+)/))) symbols.push(s[1]);
      } else if (ext === 'java' || ext === 'php') {
        if ((s = t.match(/\bclass\s+(\w+)/))) symbols.push(s[1]);
        else if (ext === 'php' && (s = t.match(/\bfunction\s+(\w+)/))) symbols.push(s[1]);
      }
    });

    const unique = (arr) => Array.from(new Set(arr));
    return {
      supported: true,
      name,
      ext,
      lineCount: lines.length,
      todos,
      openItems,
      doneItems,
      headings: unique(headings).slice(0, 12),
      symbols: unique(symbols).slice(0, 30),
      openCount: todos.length + openItems.length,
    };
  }

  // Suggestions are facts taken from the file; the student decides whether to use them.
  function suggestFromFile(insight) {
    if (!insight || !insight.supported) return {};
    const out = { resources: insight.name };
    if (insight.doneItems.length) out.completed = 'Done in ' + insight.name + ': ' + insight.doneItems.slice(0, 5).join('; ');
    else if (insight.symbols.length) out.completed = insight.name + ' contains: ' + insight.symbols.join(', ');
    if (insight.todos.length) out.workingPoint = insight.name + ', line ' + insight.todos[0].line + ': ' + insight.todos[0].text;
    else if (insight.openItems.length) out.workingPoint = insight.name + ': ' + insight.openItems[0];
    return out;
  }

  // ---- auto-log: what changed in the student's own files since the checkpoint ----------------
  // Only names, headings, open-item texts and line counts are compared; the file text is never kept.
  function snapshotOf(insight) {
    return {
      name: insight.name,
      lineCount: insight.lineCount,
      symbols: insight.symbols.slice(),
      headings: insight.headings.slice(),
      open: insight.todos.map((t) => t.text).concat(insight.openItems),
      done: insight.doneItems.slice(),
    };
  }

  const added = (before, now) => now.filter((x) => !before.includes(x));

  function compareSnapshots(saved, insights) {
    const snaps = (saved || []);
    const nowList = insights.filter((i) => i && i.supported).map(snapshotOf);
    const files = nowList.map((now) => {
      const old = snaps.find((s) => s.name === now.name);
      if (!old) {
        return { name: now.name, status: 'new', lineDelta: 0, newSymbols: now.symbols, removedSymbols: [],
          newHeadings: now.headings, resolved: [], newOpen: now.open, newlyDone: now.done };
      }
      const lineDelta = now.lineCount - old.lineCount;
      const f = {
        name: now.name, status: 'unchanged', lineDelta,
        newSymbols: added(old.symbols || [], now.symbols), removedSymbols: added(now.symbols, old.symbols || []),
        newHeadings: added(old.headings || [], now.headings),
        resolved: added(now.open, old.open || []), newOpen: added(old.open || [], now.open),
        newlyDone: added(old.done || [], now.done),
      };
      const changed = lineDelta !== 0 || f.newSymbols.length || f.removedSymbols.length || f.newHeadings.length ||
        f.resolved.length || f.newOpen.length || f.newlyDone.length;
      f.status = changed ? 'changed' : 'unchanged';
      return f;
    });
    const notChecked = snaps.filter((s) => !nowList.some((n) => n.name === s.name)).map((s) => s.name);
    const sum = (key) => files.reduce((n, f) => n + f[key].length, 0);
    return {
      files,
      notChecked,
      totals: {
        filesChecked: files.length,
        filesChanged: files.filter((f) => f.status === 'changed').length,
        linesDelta: files.reduce((n, f) => n + (f.status === 'new' ? 0 : f.lineDelta), 0),
        newSymbols: sum('newSymbols'),
        resolved: sum('resolved'),
        newOpen: sum('newOpen'),
      },
    };
  }

  function describeFileChange(f) {
    if (f.status === 'unchanged') return ['No change found.'];
    const out = [];
    if (f.status === 'new') out.push('New file since the checkpoint.');
    else if (f.lineDelta) out.push((f.lineDelta > 0 ? '+' : '') + f.lineDelta + ' lines');
    if (f.newSymbols.length) out.push('new: ' + f.newSymbols.join(', '));
    if (f.removedSymbols.length) out.push('no longer found: ' + f.removedSymbols.join(', '));
    if (f.newHeadings.length) out.push('new heading: ' + f.newHeadings.join(', '));
    if (f.newlyDone.length) out.push('ticked off: ' + f.newlyDone.join('; '));
    if (f.resolved.length) out.push('open item no longer found (done or removed): ' + f.resolved.join('; '));
    if (f.newOpen.length) out.push('new open item: ' + f.newOpen.join('; '));
    return out;
  }

  return {
    LEVELS, FIELDS, DEPTH, COMPLEXITY, MAX_SCORE,
    formatMinutes, durationPoints, openItemPoints,
    predictDifficulty, buildSummary, summaryToText, analyzeFile, suggestFromFile,
    snapshotOf, compareSnapshots, describeFileChange,
  };
});
