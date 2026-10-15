const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const html = fs.readFileSync(path.join(__dirname, '../web/mobile.html'), 'utf8');
const pollingCode = html.slice(html.indexOf('    function statusText('), html.indexOf('    function buildGeneratePayload('));
const displayCode = html.slice(html.indexOf('    function currentStepText('), html.indexOf('    function imageRecords('));

function harness() {
  const state = {
    jobs: new Map(), nextBatchId: 1, maxActiveJobs: 100, serialBatches: [],
    polling: false, timer: null, tab: 'generate',
  };
  const calls = {lists: 0, details: 0, submissions: 0, timers: 0};
  const server = {jobs: [], details: new Map(), fail: false};
  const context = vm.createContext({
    state, jobsEl: {innerHTML: ''}, generateBtn: {textContent: ''},
    compactRemoteError: String, updateGenerateButton() {}, ensureProgressSocket() {},
    async loadGallery() {},
    async submitNextSerialJobIfReady() { calls.submissions++; },
    setInterval(fn) { calls.timers++; return fn; },
    async requestJson(url) {
      if (url.endsWith('/jobs')) {
        calls.lists++;
        if (server.fail) throw new Error('offline');
        return {jobs: server.jobs.map(job => ({...job}))};
      }
      calls.details++;
      const id = url.split('/').pop();
      return server.details.get(id) || server.jobs.find(job => job.prompt_id === id);
    },
  });
  vm.runInContext(displayCode + pollingCode, context);
  return {state, calls, server, context, poll: () => context.pollJobs()};
}

function running(id, value = 2) {
  return {
    prompt_id: id, status: 'running', width: 864, height: 1536,
    batch_index: 1, batch_total: 1, progress: {value, max: 10},
  };
}

test('an idle page discovers other devices, follows progress and discovers the next task after completion', async () => {
  const h = harness();
  await h.poll();
  assert.equal(h.state.jobs.size, 0);
  h.server.jobs = [running('remote')];
  await h.poll();
  assert.match(h.context.generateBtn.textContent, /生成中.*步骤：2\/10/);
  assert.equal(h.state.jobs.get('remote').restored, true);
  h.server.jobs = [running('remote', 7)];
  await h.poll();
  assert.match(h.context.generateBtn.textContent, /步骤：7\/10/);
  h.server.jobs = [];
  h.server.details.set('remote', {status: 'completed', images: [{filename: 'result.png'}]});
  await h.poll();
  assert.match(h.context.generateBtn.textContent, /已完成/);
  h.server.jobs = [running('next')];
  await h.poll();
  assert.match(h.context.generateBtn.textContent, /生成中/);
  assert.equal(h.state.jobs.get('next').status, 'running');
});

test('merging snapshots preserves local serial-batch and gallery ownership', async () => {
  const h = harness();
  h.state.jobs.set('local', {...running('local'), batchId: 9, batchIndex: 2, batchTotal: 8});
  h.server.jobs = [{...running('local', 6), batch_index: 2, batch_total: 8}];
  await h.poll();
  const job = h.state.jobs.get('local');
  assert.equal(job.batchId, 9);
  assert.equal(job.batchIndex, 2);
  assert.equal(job.batchTotal, 8);
  assert.equal(job.restored, false);
  assert.equal(job.progress.value, 6);
});

test('temporary list failure keeps existing tasks and does not submit the next batch blindly', async () => {
  const h = harness();
  h.server.fail = true;
  await h.poll();
  assert.equal(h.calls.submissions, 0);
  assert.equal(h.state.polling, false);
  h.server.fail = false;
  h.server.jobs = [running('recovered')];
  await h.poll();
  assert.equal(h.state.jobs.get('recovered').status, 'running');
});

test('timer remains active while idle and overlapping polls are suppressed', async () => {
  const h = harness();
  let release;
  h.context.requestJson = () => new Promise(resolve => { release = resolve; });
  h.context.startPolling();
  const timer = h.state.timer;
  await h.poll();
  assert.equal(h.state.polling, true);
  release({jobs: []});
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(h.state.polling, false);
  assert.equal(h.state.timer, timer);
  h.context.startPolling();
  assert.equal(h.calls.timers, 1);
});
