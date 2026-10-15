const test = require('node:test');
const assert = require('node:assert');
const C = require('../app/static/core.js');

test('duration points change at 15, 60 and 240 minutes', () => {
  assert.strictEqual(C.durationPoints(14), 0);
  assert.strictEqual(C.durationPoints(15), 1);
  assert.strictEqual(C.durationPoints(59), 1);
  assert.strictEqual(C.durationPoints(60), 2);
  assert.strictEqual(C.durationPoints(239), 2);
  assert.strictEqual(C.durationPoints(240), 3);
});

test('missing or invalid duration counts as zero points', () => {
  assert.strictEqual(C.durationPoints(NaN), 0);
  assert.strictEqual(C.durationPoints(undefined), 0);
  assert.strictEqual(C.durationPoints(-5), 0);
});

test('quick message on a simple task is Low', () => {
  const r = C.predictDifficulty({ minutes: 5, complexity: 'simple', openItems: 0, type: 'quick_message' });
  assert.strictEqual(r.score, 0);
  assert.strictEqual(r.level, 'Low');
  assert.strictEqual(r.depth.name, 'Short');
});

test('meeting on a moderate task with some open items is Medium', () => {
  const r = C.predictDifficulty({ minutes: 30, complexity: 'moderate', openItems: 3, type: 'meeting' });
  assert.strictEqual(r.score, 3);
  assert.strictEqual(r.level, 'Medium');
});

test('long interruption by another work task on a complex task is High', () => {
  const r = C.predictDifficulty({ minutes: 300, complexity: 'complex', openItems: 6, type: 'other_task' });
  assert.strictEqual(r.score, 8);
  assert.strictEqual(r.level, 'High');
  assert.strictEqual(r.depth.name, 'Full');
});

test('longer interruption never lowers difficulty', () => {
  const base = { complexity: 'moderate', openItems: 2, type: 'meeting' };
  let last = -1;
  for (const minutes of [1, 10, 30, 90, 300, 2000]) {
    const r = C.predictDifficulty({ ...base, minutes });
    assert.ok(r.score >= last);
    last = r.score;
  }
});

test('more complex task never lowers difficulty', () => {
  const base = { minutes: 60, openItems: 2, type: 'meeting' };
  const scores = ['simple', 'moderate', 'complex'].map((complexity) => C.predictDifficulty({ ...base, complexity }).score);
  assert.deepStrictEqual(scores, [...scores].sort((a, b) => a - b));
});

test('unknown complexity falls back to moderate', () => {
  const r = C.predictDifficulty({ minutes: 20, complexity: 'weird', openItems: 0, type: 'meeting' });
  assert.strictEqual(r.reasons[1].points, 1);
});

test('score explanation points add up to the score', () => {
  const r = C.predictDifficulty({ minutes: 120, complexity: 'complex', openItems: 4, type: 'other_task' });
  assert.strictEqual(r.reasons.reduce((a, b) => a + b.points, 0), r.score);
});

test('suggested fields grow with difficulty', () => {
  assert.strictEqual(C.DEPTH.Low.suggested.length, 2);
  assert.strictEqual(C.DEPTH.Medium.suggested.length, 4);
  assert.strictEqual(C.DEPTH.High.suggested.length, 6);
});

const cp = {
  goal: 'Finish the booking site',
  completed: 'login.html, register.html',
  workingPoint: 'contact.html form has no submit handler',
  problem: 'How to validate the email?',
  nextStep: 'Add submit button',
  resources: 'Figma link',
  openItems: ['validate email', 'add submit'],
};

test('summary length depends on level', () => {
  const task = { title: 'Hotel site' };
  assert.strictEqual(C.buildSummary(task, cp, 'Low', 30).lines.length, 2);
  assert.strictEqual(C.buildSummary(task, cp, 'Medium', 30).lines.length, 4);
  assert.strictEqual(C.buildSummary(task, cp, 'High', 30).lines.length, 7);
});

test('summary only restates the student text (no new content)', () => {
  const s = C.buildSummary({ title: 'Hotel site' }, cp, 'High', 300);
  const allowed = Object.values(cp).flat().concat(['validate email; add submit']);
  s.lines.forEach((l) => assert.ok(allowed.includes(l.text), 'unexpected text: ' + l.text));
});

test('empty fields are left out of the summary', () => {
  const s = C.buildSummary({ title: 'T' }, { workingPoint: 'here', nextStep: '  ' }, 'Medium', 10);
  assert.deepStrictEqual(s.lines.map((l) => l.label), ['You stopped at']);
});

test('summary text names the task and the time away', () => {
  const t = C.summaryToText(C.buildSummary({ title: 'Hotel site' }, cp, 'Low', 300));
  assert.ok(t.includes('Hotel site'));
  assert.ok(t.includes('5 h'));
});

test('time formatting', () => {
  assert.strictEqual(C.formatMinutes(0.4), 'less than a minute');
  assert.strictEqual(C.formatMinutes(45), '45 min');
  assert.strictEqual(C.formatMinutes(90), '1.5 h');
  assert.strictEqual(C.formatMinutes(1440), '1 day');
  assert.strictEqual(C.formatMinutes(2880), '2 days');
  assert.strictEqual(C.formatMinutes(NaN), 'an unknown time');
});

const html = [
  '<html><head><title>Contact Us</title></head><body>',
  '<h1>Contact <b>Us</b></h1>',
  '<!-- TODO: validate email -->',
  '<script>function validateName(v){return v.length>1}',
  '// FIXME: show error',
  'const send = (a) => a;</script></body></html>',
].join('\n');

test('html file: headings, todos and functions are found', () => {
  const r = C.analyzeFile('contact.html', html);
  assert.ok(r.supported);
  assert.deepStrictEqual(r.headings, ['Contact Us']);
  assert.strictEqual(r.todos.length, 2);
  assert.strictEqual(r.todos[0].text, 'validate email');
  assert.deepStrictEqual(r.symbols, ['validateName', 'send']);
  assert.strictEqual(r.openCount, 2);
});

test('markdown file: checklist items are counted', () => {
  const md = '# Report\n- [x] ER diagram\n- [ ] SQL queries\n- [ ] Conclusion\nTODO: references';
  const r = C.analyzeFile('notes.md', md);
  assert.strictEqual(r.doneItems.length, 1);
  assert.strictEqual(r.openItems.length, 2);
  assert.strictEqual(r.openCount, 3);
  assert.deepStrictEqual(r.headings, ['Report']);
});

test('python file: functions and classes', () => {
  const r = C.analyzeFile('clean.py', 'def load(path):\n    pass\nclass Cleaner:\n    # TODO handle nulls\n    pass\n');
  assert.deepStrictEqual(r.symbols, ['load', 'Cleaner']);
  assert.strictEqual(r.todos.length, 1);
});

test('unsupported file types are not analysed', () => {
  assert.strictEqual(C.analyzeFile('photo.png', 'x').supported, false);
  assert.strictEqual(C.analyzeFile('slides.pptx', 'x').supported, false);
});

test('analysis does not keep the file text', () => {
  const secret = 'SECRET_PASSWORD_123';
  const r = C.analyzeFile('a.txt', 'line one\n' + secret + '\n');
  assert.ok(!JSON.stringify(r).includes(secret));
});

test('file suggestions are copied from the file, not invented', () => {
  const r = C.analyzeFile('contact.html', html);
  const s = C.suggestFromFile(r);
  assert.strictEqual(s.resources, 'contact.html');
  assert.ok(s.workingPoint.includes('validate email'));
  assert.ok(s.completed.includes('validateName'));
});

const vectors = require('./vectors.json');

test('difficulty matches the shared vectors (same as the Python tests)', () => {
  for (const v of vectors.predict) {
    const r = C.predictDifficulty(v.in);
    assert.strictEqual(r.score, v.score, JSON.stringify(v.in));
    assert.strictEqual(r.level, v.level, JSON.stringify(v.in));
  }
});

test('minute formatting matches the shared vectors', () => {
  for (const [minutes, expected] of vectors.format_minutes) assert.strictEqual(C.formatMinutes(minutes), expected);
});

test('summary labels match the shared vectors', () => {
  const v = vectors.summary;
  for (const level of ['Low', 'Medium', 'High']) {
    const s = C.buildSummary({ title: v.task }, v.checkpoint, level, 300);
    assert.deepStrictEqual(s.lines.map((l) => l.label), v.labels[level]);
    assert.strictEqual(s.intro, v.intro_300);
  }
});
