// Exercise the shipped game panels with one real practice bridge and synthetic server snapshots.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {pathToFileURL} = require('node:url');
const {webcrypto} = require('node:crypto');
const surveys = require('./fixtures/work_survey_definitions.json');

class Element {
  constructor(tagName) {
    this.tagName = tagName;
    this.children = [];
    this.events = new Map();
    this.style = {};
    this.dataset = {};
    this.value = '';
    this.text = '';
    const names = new Set();
    this.classList = {
      add: name => names.add(name), remove: name => names.delete(name),
      contains: name => names.has(name), toggle: (name, on) => on ? names.add(name) : names.delete(name),
    };
  }
  set textContent(value) { this.text = String(value); this.children = []; }
  get textContent() { return this.text + this.children.map(child => child.textContent).join(''); }
  append(...children) { this.children.push(...children); }
  replaceChildren(...children) { this.text = ''; this.children = children; }
  setAttribute(name, value) { this[name] = String(value); }
  addEventListener(type, callback) {
    if (!this.events.has(type)) this.events.set(type, []);
    this.events.get(type).push(callback);
  }
  find(id) {
    if (this.id === id) return this;
    for (const child of this.children) {
      const found = child.find(id);
      if (found) return found;
    }
  }
  async click() {
    assert.ok(!this.disabled && !this.hidden, 'control must be enabled and visible: ' + this.id);
    const handlers = this.events.get('click') || [];
    assert.ok(handlers.length, 'control must have a click handler: ' + this.id);
    for (const handler of handlers) await handler();
    await new Promise(resolve => setImmediate(resolve));
  }
}

const round = () => ({status:'completed', events:[], rule:{label:'저장됨'}, stimulus:{cards:[], selected_card_ids:[]}});
function newRun() {
  return {
    user_id:'synthetic-user', run_id:'synthetic-run', revision:10, status:'in_progress',
    flow_version:'five-game-v2', survey_set_version:'work-behavior-v2', survey_definition_snapshot:surveys,
    records:surveys.map(q => ({
      source_type:'survey', item_id:q.item_id, status:'submitted', data:{prompt_snapshot:q.prompt, selected_label_snapshot:'동의한다'},
      context:{response_type:'ordinal_6'},
    })),
    questions:[{question_id:'baseline-b01', question_mode:'baseline', conditioned_on_prior_evidence:false, question_text:'경험을 적어 주세요.'}],
    rule_games:{games:{rsp:{rounds:[round(), round(), round()]}, card:{rounds:[round(), round()]}}},
    appointment_games:{difficulty:null, games:['day', 'place', 'bus'].map(type => ({type, status:'pending', questions:[], score:0}))},
    aptitude_games:{attempts:[]},
  };
}

async function loadScreen(t, serverRun, {pendingStart, holdFirstAppointmentGet = false} = {}) {
  const directory = path.join(__dirname, '..', 'html');
  const html = fs.readFileSync(path.join(directory, 'index.html'), 'utf8');
  const roots = new Map();
  for (const [tag, name, id] of html.matchAll(/<(\w+)\b[^>]*?\bid="([^"]+)"[^>]*>/g)) {
    const node = new Element(name);
    node.id = id;
    node.hidden = /\shidden\b/.test(tag);
    roots.set(id, node);
  }
  const document = new Element('document');
  document.readyState = 'loading';
  document.createElement = tag => new Element(tag);
  document.getElementById = id => roots.get(id) || [...roots.values()].map(root => root.find(id)).find(Boolean);
  document.querySelectorAll = selector => selector === '.tab-view' ? [...roots.values()].filter(node => node.id.startsWith('view-')) : [];
  const storage = new Map([['astra.practice.v1:synthetic-user', JSON.stringify({selectedId:serverRun.run_id})]]);
  const aptitudeJournal = 'astra.aptitude.v1:' + serverRun.user_id + ':' + serverRun.run_id;
  if (pendingStart) storage.set(aptitudeJournal, JSON.stringify(pendingStart));
  let releaseAppointmentGet;
  const fetch = async (url, options) => {
    let result;
    if (options.method === 'POST') {
      const body = JSON.parse(options.body);
      if (pendingStart && url === '/api/runs/synthetic-run/aptitude-games' && body.action === 'start') {
        assert.deepEqual(body, pendingStart, 'replay must preserve the old uncertain request');
        return Response.json({error:'game_order_required'}, {status:409});
      }
      const attempt = serverRun.aptitude_games.attempts.find(item => item.id === body.attempt_id);
      if (url !== '/api/runs/synthetic-run/aptitude-games' || body.action !== 'stop' ||
          !attempt || attempt.status !== 'active' || body.expected_revision !== serverRun.revision) {
        throw Error('unexpected mutation ' + url);
      }
      attempt.status = 'interrupted';
      serverRun.revision++;
      return Response.json(serverRun);
    }
    switch (url) {
      case '/api/me': result = {user_id:serverRun.user_id, username:'synthetic'}; break;
      case '/api/interview-analysis-capabilities': result = {live_available:false}; break;
      case '/api/definitions': result = {surveys}; break;
      case '/api/runs': result = {runs:[serverRun]}; break;
      case '/api/rule-game-definitions': result = {duration_ms:20000, rounds_per_game:3}; break;
      case '/api/aptitude-games/definitions': result = {games:[]}; break;
      case '/api/runs/synthetic-run': result = serverRun; break;
      case '/api/runs/synthetic-run/appointment-games':
        if (holdFirstAppointmentGet && !releaseAppointmentGet) {
          const previous = Response.json({run:serverRun, server_time:new Date().toISOString()});
          return new Promise(resolve => { releaseAppointmentGet = () => resolve(previous); });
        }
      // All three game reads return the same owned run envelope.
      case '/api/runs/synthetic-run/rule-games':
      case '/api/runs/synthetic-run/aptitude-games':
        result = {run:serverRun, server_time:new Date().toISOString()}; break;
      default: throw Error('unexpected request ' + url);
    }
    return Response.json(result);
  };
  const testClock = {now:()=>0, timeOrigin:100000};
  const browser = {
    document, fetch, performance:testClock, crypto:webcrypto, structuredClone, setInterval:()=>0, clearInterval:()=>{},
    sessionStorage:{getItem:key=>storage.get(key) ?? null, setItem:(key,val)=>storage.set(key,val), removeItem:key=>storage.delete(key)},
    addEventListener:()=>{},
  };
  browser.window = browser;
  const context = vm.createContext(browser);
  // Native ESM imports its real relative dependencies. Supply the same browser globals used by the classic scripts.
  const globals = ['window', 'document', 'navigateTab', 'setInterval', 'performance'];
  const original = globals.map(key => Object.getOwnPropertyDescriptor(globalThis, key));
  t.after(() => globals.forEach((key, index) => {
    if (original[index]) Object.defineProperty(globalThis, key, original[index]);
    else delete globalThis[key];
  }));
  Object.assign(globalThis, {window:browser, document, navigateTab:(...args)=>browser.navigateTab(...args), setInterval:browser.setInterval, performance:testClock});
  const modules = [];
  for (const [tag, filename] of html.matchAll(/<script\b[^>]*?src="\/frontend\/([^"?]+)[^"]*"[^>]*>/g)) {
    const asset = path.join(directory, filename);
    if (/type="module"/.test(tag)) modules.push(asset);
    else vm.runInContext(fs.readFileSync(asset, 'utf8'), context, {filename});
  }
  document.readyState = 'interactive';
  for (const asset of modules) {
    const url = pathToFileURL(asset);
    url.searchParams.set('document', webcrypto.randomUUID());
    await import(url.href);
  }
  await Promise.all(document.events.get('DOMContentLoaded').map(handler => handler()));
  await new Promise(resolve => setImmediate(resolve));
  document.readyState = 'complete';
  return {
    get:document.getElementById,
    navigate:browser.navigateTab,
    context() {
      let value;
      const unsubscribe = browser.AstraPractice.subscribe(context => { value = context; });
      unsubscribe();
      return value;
    },
    async releaseAppointmentGet() {
      assert.ok(releaseAppointmentGet, 'the earlier appointment request was sent');
      releaseAppointmentGet();
      await new Promise(resolve => setImmediate(resolve));
    },
    pendingAptitude:() => storage.get(aptitudeJournal),
    publish() { serverRun.revision++; assert.equal(browser.AstraPractice.updateRun(structuredClone(serverRun)), true); },
  };
}

test('the final card leads through the three appointments and three more main games before the interview', async t => {
  const run = newRun();
  const ui = await loadScreen(t, run);
  await ui.get('practice-game').click();
  assert.equal(ui.get('view-game').classList.contains('active'), true);
  assert.equal(ui.get('appointment-games').hidden, true);
  assert.equal(ui.get('interview-answer-0').disabled, true);

  run.rule_games.games.card.rounds.push(round());
  ui.publish();
  assert.equal(ui.get('rule-game-panel').hidden, true);
  assert.equal(ui.get('appointment-games').hidden, false);
  assert.equal(ui.get('appointment-easy').disabled, false);
  await t.test('aptitude choices cannot displace the day game', () => {
    for (const name of ['rotation', 'path', 'potion']) {
      const choice = ui.get('aptitude-select-' + name);
      assert.ok(ui.get('aptitude-games').hidden || !choice || choice.disabled,
        name + ' must not be offered as the next game before the required day game');
    }
  });

  await t.test('an older out-of-order aptitude attempt can be stopped to resume appointments', async () => {
    run.aptitude_games.attempts.push({
      id:'in-flight-rotation', type:'rotation', mode:'practice', difficulty:'easy', status:'active', score:0,
      current_question:null, question_limit:1, questions:[{id:'q1', number:1, outcome:'wrong'}],
    });
    ui.publish();
    assert.ok(!ui.get('aptitude-games').hidden);
    await ui.get('aptitude-stop').click();
    assert.equal(run.aptitude_games.attempts[0].status, 'interrupted');
    assert.ok(!ui.get('view-game').classList.contains('aptitude-playing'));
    assert.equal(ui.get('appointment-easy').disabled, false);
    assert.equal(ui.get('interview-answer-0').disabled, true);
  });

  await t.test('practice history leaves all three aptitude main games due before interview', async () => {
    run.aptitude_games.attempts = ['rotation', 'path', 'potion'].map(type => ({
      type, mode:'practice', status:'complete', score:0, question_limit:1,
      questions:[{number:1, outcome:'correct'}],
    }));
    run.appointment_games.difficulty = 'easy';
    ui.publish();
    for (const [index, title] of ['요일', '장소', '버스'].entries()) {
      assert.match(ui.get('appointment-start').textContent, new RegExp(title));
      assert.equal(ui.get('interview-answer-0').disabled, true);
      const game = run.appointment_games.games[index];
      game.status = 'complete';
      game.questions = Array.from({length:10}, (_, i) => ({number:i+1, outcome:'correct'}));
      ui.publish();
    }
    ui.navigate('interview');
    assert.equal(ui.get('view-interview').classList.contains('active'), false, 'five core games do not grant interview entry');
    assert.ok(!ui.get('interview-answer-0') || ui.get('interview-answer-0').disabled);
    assert.ok(!ui.get('aptitude-games').hidden);
    if (ui.get('aptitude-menu')) await ui.get('aptitude-menu').click();
    for (const kind of ['rotation', 'path', 'potion']) {
      await ui.get('aptitude-select-' + kind).click();
      assert.equal(ui.get('aptitude-practice').disabled, false);
      await ui.get('aptitude-menu').click();
      ui.navigate('interview');
      assert.equal(ui.get('view-interview').classList.contains('active'), false);
      const questionCount = kind === 'potion' ? 48 : 10;
      run.aptitude_games.attempts.push({
        type:kind, mode:'main', status:'complete', score:0,
        question_limit:questionCount,
        questions:Array.from({length:questionCount}, (_, i)=>({number:i+1, outcome:'correct'})),
      });
      ui.publish();
    }
    ui.navigate('interview');
    assert.equal(ui.get('view-interview').classList.contains('active'), true);
    assert.equal(ui.get('interview-answer-0').disabled, false);
  });
});

test('a hidden appointment read does not prevent resuming the unfinished card round', async t => {
  const ui = await loadScreen(t, newRun(), {holdFirstAppointmentGet:true});
  assert.equal(ui.get('appointment-games').hidden, true);
  assert.equal(ui.context().appointmentGameLocked, false);
  assert.equal(ui.get('btnStartGame').disabled, false);
  await ui.releaseAppointmentGet();
});

test('a delayed card-two appointment GET cannot hide the day game after card three', async t => {
  const run = newRun();
  const ui = await loadScreen(t, run, {holdFirstAppointmentGet:true});
  await ui.get('practice-game').click();
  run.rule_games.games.card.rounds.push(round());
  ui.publish();
  await ui.releaseAppointmentGet();

  assert.equal(ui.context().run.revision, 11);
  assert.equal(ui.get('appointment-games').hidden, false);
  assert.equal(ui.get('appointment-easy').disabled, false);
  assert.equal(ui.context().appointmentGameLocked, false);
});

test('a delayed reveal response cannot replace the newer day question or its answer clock', async t => {
  const run = newRun();
  run.rule_games.games.card.rounds.push(round());
  run.appointment_games.difficulty = 'easy';
  const day = run.appointment_games.games[0];
  day.status = 'active';
  day.current_question = {id:'day-1', number:1, phase:'reveal', person_index:0, person:[0, 2], remaining_ms:1200};
  const ui = await loadScreen(t, run, {holdFirstAppointmentGet:true});
  day.questions = [{id:'day-1', number:1, outcome:'correct'}];
  day.current_question = {id:'day-2', number:2, phase:'answer', choices:[1, 3], remaining_ms:4800};
  ui.publish();
  await ui.releaseAppointmentGet();

  assert.equal(ui.context().run.appointment_games.games[0].current_question.id, 'day-2');
  assert.ok(!ui.get('appointment-day-0'), 'the old reveal should stay off screen');
  assert.equal(ui.get('appointment-choice-3').disabled, false);
  assert.match(ui.get('appointment-timer').textContent, /5초/);
});

test('a pre-existing uncertain optional start can reconcile and release the day game', async t => {
  const run = newRun();
  run.rule_games.games.card.rounds.push(round());
  const pendingStart = {
    action:'start', game_type:'rotation', mode:'practice', difficulty:'easy',
    expected_revision:run.revision, idempotency_key:'synthetic-uncertain-optional-start',
  };
  const ui = await loadScreen(t, run, {pendingStart});
  if (ui.pendingAptitude()) {
    assert.ok(!ui.get('aptitude-games').hidden, 'the saved uncertain request has a visible recovery control');
    await ui.get('aptitude-retry').click();
  }
  assert.equal(ui.pendingAptitude(), undefined);
  assert.equal(ui.get('appointment-easy').disabled, false);
  assert.equal(ui.get('interview-answer-0').disabled, true);
});

