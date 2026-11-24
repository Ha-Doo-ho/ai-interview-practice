// Offline DOM-boundary tests of the real preview script. Not browser/visual tests.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const C = require('../html/client.js');
const definitions = require('./fixtures/survey_definitions.json');

class Element {
  constructor(tag) { this.tagName = tag; this.children = []; this.events = {}; this.attrs = {}; this.value = ''; this.checked = false; this.disabled = false; this.hidden = false; this.dataset = {}; this.style = {}; this._text = ''; }
  set textContent(value) { this._text = String(value); this.children = []; }
  get textContent() { return this._text + this.children.map(child => child.textContent).join(''); }
  append(...nodes) { this.children.push(...nodes); }
  appendChild(node) { this.children.push(node); return node; }
  replaceChildren(...nodes) { this._text = ''; this.children = nodes; }
  setAttribute(key, value) { this.attrs[key] = String(value); }
  addEventListener(type, handler) { this.events[type] = handler; }
  focus() { this.focused = true; }
  querySelectorAll(selector) { return this.children.flatMap(child => [...(child.tagName === selector ? [child] : []), ...child.querySelectorAll(selector)]); }
  querySelector(selector) { return this.querySelectorAll(selector)[0] || null; }
}
const flush = () => new Promise(resolve => setImmediate(resolve));
async function setup({offline = false, icons = true, definitionPayload = definitions} = {}) {
  const roots = Object.fromEntries(['survey-title', 'survey-items', 'survey-progress', 'survey-error', 'survey-retry', 'survey-submit', 'cardTileGrid'].map(id => [id, new Element('div')]));
  const requests = [], navigation = [], alerts = [];
  let fail = offline;
  const find = (node, id) => node.id === id ? node : node.children.map(child => find(child, id)).find(Boolean);
  const document = {events: {}, createElement: tag => new Element(tag), getElementById: id => roots[id] || Object.values(roots).map(root => find(root, id)).find(Boolean), addEventListener(type, fn) { this.events[type] = fn; }};
  const transport = async (url, options) => {
    requests.push({url, options});
    assert.equal(url, '/api/definitions');
    assert.equal(options.method, 'GET');
    if (fail) throw Error('synthetic offline');
    return Response.json(definitionPayload);
  };
  const context = vm.createContext({document, window: {AstraClient: {...C, createApi: () => C.createApi(transport)}}, ...(icons ? {lucide: {createIcons() {}}} : {}), console, performance, structuredClone, setInterval, clearInterval, alert: text => alerts.push(text)});
  vm.runInContext(fs.readFileSync(require.resolve('../html/script.js'), 'utf8'), context);
  context.navigateTab = tab => navigation.push(tab);
  await document.events.DOMContentLoaded();
  await flush();
  return {roots, context, document, requests, navigation, alerts, reconnect() { fail = false; }};
}
function choose(env, id, value, type = 'change') {
  const input = env.document.getElementById(id);
  assert.ok(input, 'Missing survey control: ' + id);
  if (input.type === 'checkbox' || input.type === 'radio') input.checked = Boolean(value);
  else input.value = String(value);
  input.events[type]({target: input});
  return input;
}
function fill(env) {
  choose(env, 'O-B01-selected_position-5', true);
  choose(env, 'O-B02-selected_position-2', true);
  choose(env, 'O-B03-selected_position-6', true);
  choose(env, 'P-B01-self-4', true);
  choose(env, 'P-B01-imagined_others-5', true);
  choose(env, 'S-B02-confirm', true);
  choose(env, 'R-UNMAPPED-rank-1', 'helping');
  choose(env, 'R-UNMAPPED-rank-2', 'growth');
  choose(env, 'R-UNMAPPED-rank-3', 'autonomy');
}

test('five-item preview preserves no-experience and uncertainty separately from agreement',async()=>{
  const items=structuredClone(require('./fixtures/work_survey_definitions.json'));
  const env=await setup({definitionPayload:{...definitions,current_survey_set_version:'work-behavior-v2',current_surveys:items}});
  choose(env,'O-B01-selected_position-6',true);
  const absent=env.document.getElementById('O-B01-nonresponse-no_experience');assert.ok(absent);absent.events.click();
  const unsure=env.document.getElementById('O-B02-nonresponse-unsure');assert.ok(unsure);unsure.events.click();
  for(const item of items.slice(2))choose(env,item.item_id+'-selected_position-4',true);
  env.context.submitSurveys();
  let preview=vm.runInContext('currentRun.surveyPreview',env.context);
  assert.equal(preview.server_saved,false);assert.equal(preview.responses.length,5);
  assert.equal(preview.responses[0].status,'skipped');assert.equal(preview.responses[0].nonresponse_reason,'no_experience');
  assert.deepEqual(Object.keys(preview.responses[0].response),[]);
  assert.equal(preview.responses[1].nonresponse_reason,'unsure');
  assert.equal(env.document.getElementById('O-B01-selected_position-6').checked,false);
  choose(env,'O-B01-selected_position-3',true);env.context.submitSurveys();
  preview=vm.runInContext('currentRun.surveyPreview',env.context);
  assert.equal(preview.responses[0].status,'submitted');assert.equal(preview.responses[0].nonresponse_reason,undefined);
  assert.equal(preview.responses[0].response.selected_position,3);
});

test('six canonical questions render with four input formats and no assumed answers [SCN-001,004,006,009]', async () => {
  const env = await setup();
  const cards = env.roots['survey-items'].children;
  assert.equal(cards.length, 6, 'The restored survey must show all six questions');
  for (const [index, item] of definitions.surveys.entries()) assert.ok(cards[index].textContent.includes(item.prompt));
  assert.deepEqual(cards.slice(0, 3).map(card => card.querySelectorAll('input').length), [6, 6, 6]);
  assert.deepEqual(cards[0].querySelectorAll('label').map(label => label.textContent), ['전혀 그렇지 않다', '그렇지 않다', '그렇지 않은 편이다', '그런 편이다', '그렇다', '매우 그렇다']);
  assert.equal(cards[3].querySelectorAll('input').length, 12);
  assert.match(cards[3].textContent, /실제.*평가.*아닙니다/);
  assert.equal(cards[4].querySelectorAll('input').length, 2);
  assert.equal(cards[5].querySelectorAll('select').length, 3);
  assert.ok(cards.flatMap(card => card.querySelectorAll('input')).every(input => !input.checked));
  assert.match(env.roots['survey-progress'].textContent, /0\s*\/\s*6/);
});

test('unanswered questions prevent continuation instead of reporting a saved survey', async () => {
  const env = await setup();
  env.context.submitSurveys();
  assert.equal(env.navigation.length, 0);
  assert.match(env.roots['survey-error'].textContent, /1번/);
  assert.equal(env.alerts.length, 0);
});

test('ordinal labels, separate perspectives, explicit center and ranked order survive confirmation [SCN-001,004,007,009]', async () => {
  const env = await setup();
  fill(env);
  assert.match(env.roots['survey-progress'].textContent, /6\s*\/\s*6/);
  env.context.submitSurveys();
  const preview = JSON.parse(vm.runInContext('JSON.stringify(currentRun.surveyPreview)', env.context));
  assert.equal(preview.server_saved, false);
  assert.equal(preview.responses.length, 6);
  assert.deepEqual(preview.responses[0].response, {selected_position: 5});
  assert.equal(preview.responses[0].definition.ordered_options[4].label, '그렇다');
  assert.equal(preview.responses[3].response.self.selected_position, 4);
  assert.equal(preview.responses[3].response.imagined_others.selected_position, 5);
  assert.deepEqual(preview.responses[4].response, {final_value: 0, interaction_occurred: false, explicit_confirmation: true, change_count: 0});
  assert.deepEqual(preview.responses[5].response.selected_ids, ['helping', 'growth', 'autonomy']);
  assert.equal(preview.responses[5].definition.candidates.length, 5);
  assert.deepEqual(env.navigation, ['game']);
  assert.ok(env.requests.every(request => request.options.method === 'GET'));
});

test('slider direction changes require a fresh explicit confirmation [SCN-006,007]', async () => {
  const env = await setup();
  fill(env);
  choose(env, 'S-B02-value', -3, 'input');
  assert.equal(env.document.getElementById('S-B02-confirm').checked, false);
  assert.match(env.roots['survey-progress'].textContent, /5\s*\/\s*6/);
  env.context.submitSurveys();
  assert.equal(env.navigation.length, 0);
  choose(env, 'S-B02-confirm', true);
  env.context.submitSurveys();
  const response = JSON.parse(vm.runInContext('JSON.stringify(currentRun.surveyPreview.responses[4].response)', env.context));
  assert.deepEqual(response, {final_value: -3, interaction_occurred: true, explicit_confirmation: true, change_count: 1});
});

test('rank slots reject duplicates and preserve an explicit reordered result [SCN-009]', async () => {
  const env = await setup();
  fill(env);
  choose(env, 'R-UNMAPPED-rank-2', 'helping');
  env.context.submitSurveys();
  assert.equal(env.navigation.length, 0);
  assert.match(env.roots['survey-error'].textContent, /6번/);
  choose(env, 'R-UNMAPPED-rank-1', 'growth');
  env.context.submitSurveys();
  const response = JSON.parse(vm.runInContext('JSON.stringify(currentRun.surveyPreview.responses[5].response)', env.context));
  assert.deepEqual(response.selected_ids, ['growth', 'helping', 'autonomy']);
  assert.equal(response.selection_events.length, 5);
});

test('definitions failure blocks progression and supports retry without invented questions', async () => {
  const env = await setup({offline: true});
  assert.equal(env.roots['survey-items'].children.length, 0);
  assert.equal(env.roots['survey-submit'].disabled, true);
  assert.equal(env.roots['survey-retry'].hidden, false);
  assert.match(env.roots['survey-error'].textContent, /불러오지 못/);
  env.reconnect();
  await env.context.loadSurveys();
  assert.equal(env.roots['survey-items'].children.length, 6);
  assert.equal(env.roots['survey-submit'].disabled, false);
});

test('unavailable icon CDN does not prevent survey input', async () => {
  const env = await setup({icons: false});
  assert.equal(env.roots['survey-items'].children.length, 6);
});
