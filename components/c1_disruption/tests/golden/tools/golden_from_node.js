// Spec freeze for the Node → Python port (Phase 1).
//
// Reads the OLD Node project (read-only; nothing is written there) and either
//   --write  exports every golden scenario S1–S16 to ../scenarios/Sxx.json, or
//   --check  proves the frozen JSON still matches the old project:
//              1. approved fields == backend/tests/golden/scenarios.js (hand-worked, owner-approved)
//              2. every field   == the old engine's output (generateMvd)
//              3. every scenario replayed through the old Express API gives the same plan
//              4. every case in ../api_cases.json passes against the old Express API
//
// Usage (Node 18+):
//   node golden_from_node.js --write "D:\RESEARCH PROJECT\anchor-ai-component1"
//   node golden_from_node.js --check "D:\RESEARCH PROJECT\anchor-ai-component1"
//
// The JSON is the spec from now on; this script only exists to show where it
// came from and that it matches the Node implementation it replaces.

const fs = require('fs');
const path = require('path');

const [mode, oldRoot] = process.argv.slice(2);
if (!['--write', '--check'].includes(mode) || !oldRoot) {
  console.error('usage: node golden_from_node.js --write|--check <old repo root>');
  process.exit(2);
}
const backend = path.join(oldRoot, 'backend');
const need = (rel) => require(path.join(backend, rel));

const scenariosPath = path.join(backend, 'tests/golden/scenarios.js');
const scenarios = need('tests/golden/scenarios.js');
const { generateMvd } = need('src/engine/mvd.js');
const { toMinutes } = need('src/engine/time.js');
const { createApp } = need('src/app.js');
const { createMemoryStore } = need('src/data/memoryStore.js');
const { fixedClock } = need('src/services/clock.js');
const request = need('node_modules/supertest');

const GOLDEN_DIR = path.resolve(__dirname, '..');
const SCENARIO_DIR = path.join(GOLDEN_DIR, 'scenarios');
const API_CASES = path.join(GOLDEN_DIR, 'api_cases.json');

// Fields the owner approved by hand in scenarios.js. Never edited here.
const APPROVED_TASK_FIELDS = ['fi', 'efUsed', 'tag', 'start', 'end', 'compressionPct', 'reason', 'deadlineRisk'];

const fileName = (id) => `S${id.slice(1).padStart(2, '0')}.json`;
const isEqual = (a, b) => JSON.stringify(a) === JSON.stringify(b);
const failures = [];
const fail = (where, msg) => failures.push(`${where}: ${msg}`);

// ---------------------------------------------------------------------------
// Hand-written Fi workings: the `//` comments in scenarios.js above each task
// line, and the scenario-level comments between `expected: {` and `tasks: {`.
function readWorkings() {
  const lines = fs.readFileSync(scenariosPath, 'utf8').split(/\r?\n/);
  const out = {};
  let id = null;
  let state = 'outside'; // outside → expected → tasks
  let buffer = [];
  for (const line of lines) {
    const idMatch = line.match(/^\s*id: '(S\d+)',/);
    if (idMatch) {
      id = idMatch[1];
      out[id] = { scenario: [], tasks: {} };
      state = 'outside';
      buffer = [];
      continue;
    }
    if (!id) continue;
    if (/^\s*expected: \{/.test(line)) { state = 'expected'; buffer = []; continue; }
    const comment = line.match(/^\s*\/\/ ?(.*)$/);
    if (state === 'expected') {
      // A scenario ends with `  },` (2-space indent); S11 has no `tasks:` block.
      if (/^ {2}\},\s*$/.test(line)) { state = 'outside'; continue; }
      if (comment) out[id].scenario.push(comment[1]);
      if (/^\s*tasks: \{/.test(line)) { state = 'tasks'; buffer = []; }
      continue;
    }
    if (state === 'tasks') {
      if (comment) { buffer.push(comment[1]); continue; }
      const task = line.match(/^\s*(\w+): \{ fi:/);
      if (task) { out[id].tasks[task[1]] = buffer; buffer = []; continue; }
      if (/^\s*\},\s*$/.test(line)) state = 'outside';
    }
  }
  return out;
}

const pick = (obj, keys) => Object.fromEntries(keys.map((k) => [k, obj[k]]));

// Expected outputs for one scenario: approved fields + fields captured from the
// approved engine (explanation text etc., not part of the hand-worked file).
function buildScenario(s, workings) {
  const base = {
    id: s.id,
    name: s.name,
    source: 'anchor-ai-component1 backend/tests/golden/scenarios.js (owner-approved, test-first)',
    input: s.input,
  };
  if (s.expected.throws) {
    let message = null;
    try { generateMvd(s.input); } catch (err) { message = err.message; }
    return {
      ...base,
      workings: workings.scenario,
      expected: {
        error: {
          // Approved check: the message names the disruption type, then the task type.
          messageRegex: s.expected.throws.source,
          message, // captured from the engine
          httpStatus: 422,
        },
      },
    };
  }
  const mvd = generateMvd(s.input);
  const tasks = {};
  for (const [taskId, exp] of Object.entries(s.expected.tasks)) {
    const got = mvd.tasks.find((t) => t.id === taskId);
    tasks[taskId] = {
      ...pick(exp, APPROVED_TASK_FIELDS),
      group: got.group,
      explanation: got.explanation,
      workings: workings.tasks[taskId] || [],
    };
  }
  const protect = {};
  for (const [blockId, exp] of Object.entries(s.expected.protect)) {
    const got = mvd.protect.find((p) => p.id === blockId);
    protect[blockId] = { ...exp, explanation: got.explanation };
  }
  return {
    ...base,
    workings: workings.scenario,
    expected: {
      approvedFields: APPROVED_TASK_FIELDS.map((f) => `tasks.*.${f}`).concat('protect.*.tag/start/end/reason'),
      engineCapturedFields: [
        'tasks.*.group', 'tasks.*.explanation', 'protect.*.explanation',
        'order', 'horizon', 'disruptionKind', 'freeMinutesLeft', 'warnings',
      ],
      comparison: { fi: 'equal after rounding to 3 decimal places (R12)', everythingElse: 'exactly equal' },
      disruptionKind: mvd.disruption.kind,
      horizon: mvd.horizon,
      order: mvd.tasks.map((t) => t.id),
      freeMinutesLeft: mvd.freeMinutesLeft,
      tasks,
      protect,
      warnings: mvd.warnings,
    },
  };
}

// ---------------------------------------------------------------------------
// Check 1 + 2: frozen JSON vs scenarios.js and vs the engine.
function checkScenario(json, s) {
  const where = json.id;
  if (!isEqual(json.input, s.input)) fail(where, 'input differs from scenarios.js');
  if (s.expected.throws) {
    if (!json.expected.error) return fail(where, 'expected an error case');
    if (json.expected.error.messageRegex !== s.expected.throws.source) fail(where, 'error regex differs');
    let message = null;
    try { generateMvd(s.input); } catch (err) { message = err.message; }
    if (message !== json.expected.error.message) fail(where, `engine message differs: ${message}`);
    if (!new RegExp(json.expected.error.messageRegex).test(message)) fail(where, 'message does not match regex');
    return;
  }
  const exp = json.expected;
  if (!isEqual(Object.keys(exp.tasks).sort(), Object.keys(s.expected.tasks).sort())) fail(where, 'task ids differ');
  for (const [taskId, approved] of Object.entries(s.expected.tasks)) {
    if (!isEqual(pick(exp.tasks[taskId], APPROVED_TASK_FIELDS), pick(approved, APPROVED_TASK_FIELDS))) {
      fail(`${where}.${taskId}`, 'approved fields differ from scenarios.js');
    }
    if (exp.tasks[taskId].workings.length === 0) fail(`${where}.${taskId}`, 'no Fi workings found');
  }
  const protectApproved = Object.fromEntries(
    Object.entries(exp.protect).map(([k, v]) => [k, pick(v, ['tag', 'start', 'end', 'reason'])])
  );
  if (!isEqual(protectApproved, s.expected.protect)) fail(where, 'protect differs from scenarios.js');

  const mvd = generateMvd(s.input);
  if (mvd.tasks.length !== Object.keys(exp.tasks).length) fail(where, 'engine returns a different number of tasks');
  for (const got of mvd.tasks) {
    const e = exp.tasks[got.id];
    if (!e) { fail(where, `engine task ${got.id} missing from JSON`); continue; }
    if (Number(got.fi.toFixed(3)) !== e.fi) fail(`${where}.${got.id}`, `fi ${got.fi} vs ${e.fi}`);
    for (const f of APPROVED_TASK_FIELDS.filter((x) => x !== 'fi').concat('group', 'explanation')) {
      if (!isEqual(got[f], e[f])) fail(`${where}.${got.id}`, `${f}: engine ${JSON.stringify(got[f])} vs JSON ${JSON.stringify(e[f])}`);
    }
  }
  for (const p of mvd.protect) {
    const e = exp.protect[p.id];
    if (!e || !isEqual(pick(p, ['tag', 'start', 'end', 'reason', 'explanation']), e)) fail(`${where}.${p.id}`, 'protect block differs');
  }
  const scalars = {
    disruptionKind: mvd.disruption.kind,
    horizon: mvd.horizon,
    order: mvd.tasks.map((t) => t.id),
    freeMinutesLeft: mvd.freeMinutesLeft,
    warnings: mvd.warnings,
  };
  for (const [k, v] of Object.entries(scalars)) if (!isEqual(v, exp[k])) fail(where, `${k} differs`);
}

// Check 3: replay through the old HTTP API (same flow as goldenFlow.test.js).
const MINUTES_PER_DAY = 24 * 60;
const timeLost = ({ start, end }) => (toMinutes(end) - toMinutes(start) + MINUTES_PER_DAY) % MINUTES_PER_DAY;

async function checkScenarioHttp(json) {
  const where = `${json.id} (HTTP)`;
  const { input } = json;
  const app = createApp({ store: createMemoryStore(), clock: fixedClock(`${input.date}T${input.planFrom}`) });
  const call = (method, url, body) => request(app)[method](url).set('X-User-Id', 'u1').send(body);
  await call('put', '/api/me/settings', { workStart: input.workHours.start, workEnd: input.workHours.end });
  for (const b of input.protectedBlocks) await call('post', '/api/protected-blocks', { label: b.label, start: b.start, end: b.end });
  const idMap = {};
  for (const t of input.tasks) {
    const res = await call('post', '/api/tasks', {
      title: t.title, type: t.type, priority: t.priority, estimatedHours: t.estimatedHours,
      deadline: t.deadline, delegable: t.delegable, plannedDate: input.date,
    });
    idMap[res.body.id] = t.id;
  }
  const report = await call('post', '/api/disruptions', {
    date: input.date, type: input.disruption.type, start: input.disruption.start,
    timeLostMinutes: timeLost(input.disruption), severity: 2, confirmed: true,
  });
  const res = await call('post', `/api/disruptions/${report.body.id}/mvd`, { planFrom: input.planFrom });
  if (json.expected.error) {
    if (res.status !== json.expected.error.httpStatus) fail(where, `status ${res.status}`);
    if (res.body.error.message !== json.expected.error.message) fail(where, 'error message differs');
    return;
  }
  if (res.status !== 201) return fail(where, `status ${res.status}`);
  const exp = json.expected;
  const order = res.body.plan.tasks.map((t) => idMap[t.id]);
  if (!isEqual(order, exp.order)) fail(where, `order ${order}`);
  for (const t of res.body.plan.tasks) {
    const e = exp.tasks[idMap[t.id]];
    if (Number(t.fi.toFixed(3)) !== e.fi) fail(`${where}.${idMap[t.id]}`, 'fi differs');
    for (const f of APPROVED_TASK_FIELDS.filter((x) => x !== 'fi').concat('group', 'explanation')) {
      if (!isEqual(t[f], e[f])) fail(`${where}.${idMap[t.id]}`, `${f} differs`);
    }
  }
  if (res.body.plan.freeMinutesLeft !== exp.freeMinutesLeft) fail(where, 'freeMinutesLeft differs');
  const protect = res.body.plan.protect.map((p) => pick(p, ['tag', 'start', 'end', 'reason', 'explanation']));
  if (!isEqual(protect, Object.values(exp.protect))) fail(where, 'protect differs');
}

// ---------------------------------------------------------------------------
// Check 4: run api_cases.json against the old app. The case format is described
// in ../README.md; the Python runner (Phase 4) reads the same file.
const ANY_STRING = '<any-string>';

function substitute(value, vars) {
  if (typeof value === 'string') {
    const whole = value.match(/^\$\{([\w.]+)\}$/);
    if (whole) return getPath(vars, whole[1]);
    return value.replace(/\$\{([\w.]+)\}/g, (_, p) => String(getPath(vars, p)));
  }
  if (Array.isArray(value)) return value.map((v) => substitute(v, vars));
  if (value && typeof value === 'object') {
    return Object.fromEntries(Object.entries(value).map(([k, v]) => [k, substitute(v, vars)]));
  }
  return value;
}

function getPath(obj, p) {
  if (p === '' || p === undefined) return obj;
  return p.split('.').reduce((o, k) => (o === undefined || o === null ? undefined : o[k]), obj);
}

// Partial match: objects need only the listed keys, arrays must have the same
// length and match element by element, "<any-string>" matches any string.
function matches(got, want) {
  if (want === ANY_STRING) return typeof got === 'string';
  if (Array.isArray(want)) return Array.isArray(got) && got.length === want.length && want.every((w, i) => matches(got[i], w));
  if (want && typeof want === 'object') {
    return got !== null && typeof got === 'object' && Object.entries(want).every(([k, w]) => matches(got[k], w));
  }
  return got === want;
}

function equalsExact(got, want) {
  if (want === ANY_STRING) return typeof got === 'string';
  if (Array.isArray(want)) return Array.isArray(got) && got.length === want.length && want.every((w, i) => equalsExact(got[i], w));
  if (want && typeof want === 'object') {
    if (got === null || typeof got !== 'object' || Array.isArray(got)) return false;
    const keys = Object.keys(want);
    return keys.length === Object.keys(got).length && keys.every((k) => equalsExact(got[k], want[k]));
  }
  return got === want;
}

function checkExpect(where, body, status, expect) {
  if (expect.status !== undefined && status !== expect.status) fail(where, `status ${status}, want ${expect.status} (${JSON.stringify(body)})`);
  if ('equals' in expect && !equalsExact(body, expect.equals)) fail(where, `body ${JSON.stringify(body)} != ${JSON.stringify(expect.equals)}`);
  if ('match' in expect && !matches(body, expect.match)) fail(where, `body ${JSON.stringify(body)} does not match ${JSON.stringify(expect.match)}`);
  if (expect.length !== undefined && (!Array.isArray(body) || body.length !== expect.length)) fail(where, `length ${body && body.length}, want ${expect.length}`);
  if (expect.errorCode && !(body && body.error && body.error.code === expect.errorCode)) fail(where, `error code ${JSON.stringify(body)}, want ${expect.errorCode}`);
  if (expect.messageRegex && !(body && body.error && new RegExp(expect.messageRegex).test(body.error.message))) {
    fail(where, `message ${JSON.stringify(body && body.error)} does not match /${expect.messageRegex}/`);
  }
  for (const at of expect.at || []) {
    let value = getPath(body, at.path);
    if (at.find) value = Array.isArray(value) ? value.find((v) => matches(v, at.find)) : undefined;
    if (at.pluck) value = Array.isArray(value) ? value.map((v) => v[at.pluck]) : undefined;
    if ('equals' in at && !equalsExact(value, at.equals)) fail(where, `${at.path}: ${JSON.stringify(value)} != ${JSON.stringify(at.equals)}`);
    if ('match' in at && !matches(value, at.match)) fail(where, `${at.path}: ${JSON.stringify(value)} does not match ${JSON.stringify(at.match)}`);
  }
}

function expandBody(body, templates) {
  if (!body || typeof body !== 'object' || Array.isArray(body)) return body;
  const name = Object.keys(templates).find((t) => `$${t}` in body);
  if (!name) return body;
  const merged = { ...templates[name], ...body[`$${name}`] };
  for (const k of body.$omit || []) delete merged[k];
  return merged;
}

async function runApiCases() {
  const spec = JSON.parse(fs.readFileSync(API_CASES, 'utf8'));
  let count = 0;
  for (const c of spec.cases) {
    count += 1;
    const store = createMemoryStore();
    let clock = fixedClock(c.now || spec.defaultNow);
    const app = createApp({ store, clock: { now: () => clock.now() } });
    const vars = {};
    const steps = [...(c.fixture ? spec.fixtures[c.fixture] : []), ...c.steps];
    for (const [i, raw] of steps.entries()) {
      const where = `api ${c.id} step ${i + 1}`;
      const step = substitute(raw, vars);
      if (step.setNow) { clock = fixedClock(step.setNow); continue; }
      if (step.store) {
        const rows = await store.list(step.store.collection, step.store.where || {});
        checkExpect(where, rows, undefined, step.expect || {});
        continue;
      }
      let req = request(app)[step.method.toLowerCase()](step.path);
      if (step.as !== null && step.as !== undefined) req = req.set('X-User-Id', step.as);
      for (const [h, v] of Object.entries(step.headers || {})) req = req.set(h, v);
      if (step.rawBody !== undefined) req = req.send(step.rawBody);
      else if (step.body !== undefined) req = req.send(expandBody(step.body, spec.templates));
      const res = await req;
      checkExpect(where, res.body, res.status, step.expect || {});
      if (step.save) vars[step.save] = res.body;
    }
  }
  return count;
}

// ---------------------------------------------------------------------------
async function main() {
  const workings = readWorkings();
  if (mode === '--write') {
    fs.mkdirSync(SCENARIO_DIR, { recursive: true });
    for (const s of scenarios) {
      const json = buildScenario(s, workings[s.id]);
      fs.writeFileSync(path.join(SCENARIO_DIR, fileName(s.id)), `${JSON.stringify(json, null, 2)}\n`);
    }
    console.log(`wrote ${scenarios.length} scenarios to ${SCENARIO_DIR}`);
  }

  const files = fs.readdirSync(SCENARIO_DIR).filter((f) => /^S\d+\.json$/.test(f)).sort();
  if (files.length !== scenarios.length) fail('scenarios', `${files.length} JSON files for ${scenarios.length} scenarios`);
  let taskChecks = 0;
  for (const s of scenarios) {
    const json = JSON.parse(fs.readFileSync(path.join(SCENARIO_DIR, fileName(s.id)), 'utf8'));
    checkScenario(json, s);
    await checkScenarioHttp(json);
    taskChecks += json.expected.tasks ? Object.keys(json.expected.tasks).length : 1;
  }
  const apiCount = fs.existsSync(API_CASES) ? await runApiCases() : 0;

  if (failures.length) {
    console.error(`FAILED (${failures.length}):\n  ${failures.join('\n  ')}`);
    process.exit(1);
  }
  console.log(`OK: ${scenarios.length} scenarios (${taskChecks} task expectations) match scenarios.js, the engine and the HTTP API; ${apiCount} API cases pass against the old Express app`);
}

main().catch((err) => { console.error(err); process.exit(1); });
