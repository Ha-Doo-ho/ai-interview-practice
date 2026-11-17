// Execute the actual authentication UI handlers with a synthetic DOM and transport.
// These are offline boundary tests, not browser or visual tests.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const C = require('../html/client.js');
const path = require('node:path');
const sourcePath = path.join(__dirname, '../html/auth.js');
const user = {user_id: 'synthetic-user', username: 'tester-auth'};
const rejected = (code, status) => Response.json({error: code}, {status});

class Element {
  constructor() { this.value = ''; this.textContent = ''; this.hidden = false; this.disabled = false; this.events = {}; this.attrs = {}; }
  addEventListener(name, handler) { this.events[name] = handler; }
  setAttribute(name, value) { this.attrs[name] = String(value); }
  focus() { this.focused = true; }
}
async function setup(handler = () => rejected('unauthorized', 401)) {
  const html = fs.readFileSync(path.join(__dirname, '../html/index.html'), 'utf8');
  const elements = Object.fromEntries([...html.matchAll(/id="([^"]+)"/g)].map(match => [match[1], new Element()]));
  const requests = [], events = {}, windowEvents = {};
  let reloads = 0;
  const document = {
    getElementById: id => elements[id],
    addEventListener: (name, handler) => { events[name] = handler; },
    querySelectorAll: () => [],
  };
  const transport = async (url, options) => {
    assert.equal(options.credentials, 'same-origin');
    if (options.method !== 'GET') assert.equal(options.headers['X-Requested-With'], 'interview-app');
    requests.push({path: url.slice(4), method: options.method, body: options.body ? JSON.parse(options.body) : undefined});
    return handler(requests.at(-1));
  };
  const forbiddenStorage = new Proxy({}, {get() { throw Error('Authentication must not use browser storage'); }});
  const window = {AstraClient: {...C, createApi: () => C.createApi(transport)},
    addEventListener: (name, handler) => { windowEvents[name] = handler; },
    location: {reload() { reloads++; }}, localStorage: forbiddenStorage, sessionStorage: forbiddenStorage};
  const context = vm.createContext({document, window, localStorage: forbiddenStorage, sessionStorage: forbiddenStorage,
    console: {log() { throw Error('Unexpected authentication log'); }, error() { throw Error('Unexpected authentication log'); }}});
  if (fs.existsSync(sourcePath)) vm.runInContext(fs.readFileSync(sourcePath, 'utf8'), context);
  if (events.DOMContentLoaded) await events.DOMContentLoaded();
  const click = async id => {
    assert.ok(elements[id]?.events.click, 'Missing working control: ' + id);
    return elements[id].events.click({preventDefault() {}});
  };
  const submit = async () => {
    assert.ok(elements['auth-form']?.events.submit, 'Authentication form is not connected');
    return elements['auth-form'].events.submit({preventDefault() {}});
  };
  const fill = (password = 'synthetic-password') => {
    elements['auth-username'].value = user.username;
    elements['auth-password'].value = password;
    elements['auth-confirm'].value = password;
  };
  return {elements, requests, click, submit, fill, events, windowEvents, reloads: () => reloads};
}

test('startup restores the real server session instead of assuming a guest', async () => {
  const env = await setup(() => Response.json(user));
  assert.ok(env.elements['auth-status'], 'The page must expose authentication state');
  assert.match(env.elements['auth-status'].textContent, /tester-auth/);
  assert.equal(env.elements['auth-logout'].hidden, false);
  assert.equal(env.elements['auth-open-login'].hidden, true);
  assert.deepEqual(env.requests.map(request => request.path), ['/me']);
});

test('registration submits matching credentials once and shows automatic login without storage', async () => {
  const env = await setup(request => request.path === '/me' ? rejected('unauthorized', 401) : Response.json(user, {status: 201}));
  await env.click('auth-open-register');
  env.fill('  synthetic-password  ');
  await env.submit();
  assert.deepEqual(env.requests.at(-1), {path: '/register', method: 'POST', body: {username: user.username, password: '  synthetic-password  '}});
  assert.match(env.elements['auth-status'].textContent, /tester-auth/);
  assert.equal(env.elements['auth-panel'].hidden, true);
  assert.equal(env.elements['auth-password'].value, '');
  assert.equal(env.elements['auth-confirm'].value, '');
});

test('mismatched confirmation is rejected before sending credentials', async () => {
  const env = await setup();
  await env.click('auth-open-register'); env.fill(); env.elements['auth-confirm'].value = 'different';
  await env.submit();
  assert.equal(env.requests.length, 1);
  assert.match(env.elements['auth-form-error'].textContent, /일치/);
});

test('duplicate username and invalid credentials produce safe actionable messages', async () => {
  for (const [mode, code, status, message] of [['register', 'username_taken', 409, /이미 사용/], ['login', 'invalid_credentials', 401, /아이디.*비밀번호/]]) {
    const env = await setup(request => request.path === '/me' ? rejected('unauthorized', 401) : rejected(code, status));
    await env.click('auth-open-' + mode); env.fill(); await env.submit();
    assert.match(env.elements['auth-form-error'].textContent, message);
    assert.equal(env.elements['auth-logout'].hidden, true);
    assert.equal(env.elements['auth-submit'].disabled, false);
    assert.equal(env.elements['auth-password'].value, '');
  }
});

test('login bypasses registration confirmation and does not create another account', async () => {
  const env = await setup(request => request.path === '/me' ? rejected('unauthorized', 401) : Response.json(user));
  await env.click('auth-open-login'); env.fill(); env.elements['auth-confirm'].value = '';
  await env.submit();
  assert.equal(env.requests.at(-1).path, '/login');
  assert.match(env.elements['auth-status'].textContent, /tester-auth/);
});

test('pending authentication prevents a duplicate submit and mode switching', async () => {
  let resolve;
  const env = await setup(request => request.path === '/me' ? rejected('unauthorized', 401) : new Promise(done => { resolve = done; }));
  await env.click('auth-open-register'); env.fill();
  const pending = env.submit();
  await env.submit(); await env.click('auth-mode-login');
  assert.equal(env.requests.filter(request => request.method === 'POST').length, 1);
  assert.equal(env.elements['auth-submit'].disabled, true);
  resolve(Response.json(user)); await pending;
  assert.equal(env.elements['auth-panel'].hidden, true);
});

test('lost registration response checks the server session without registering twice', async () => {
  let registered = false;
  const env = await setup(request => {
    if (request.path === '/me') return registered ? Response.json(user) : rejected('unauthorized', 401);
    registered = true; throw Error('synthetic lost response');
  });
  await env.click('auth-open-register'); env.fill(); await env.submit();
  assert.equal(env.requests.filter(request => request.path === '/register').length, 1);
  assert.match(env.elements['auth-status'].textContent, /tester-auth/);
});

test('unknown session is distinct from logged out and can be checked again', async () => {
  let offline = true;
  const env = await setup(() => { if (offline) throw Error('synthetic offline'); return Response.json(user); });
  assert.ok(env.elements['auth-retry'], 'Missing session retry');
  assert.equal(env.elements['auth-retry'].hidden, false);
  assert.match(env.elements['auth-status'].textContent, /확인.*못/);
  offline = false; await env.click('auth-retry');
  assert.match(env.elements['auth-status'].textContent, /tester-auth/);
});

test('logout refreshes the preview only after the server confirms logout', async () => {
  const env = await setup(request => request.path === '/me' ? Response.json(user) : new Response(null, {status: 204}));
  await env.click('auth-logout');
  assert.equal(env.requests.at(-1).path, '/logout');
  assert.equal(env.reloads(), 1);
  assert.equal(env.elements['auth-logout'].hidden, true);
});

test('failed logout preserves the confirmed session and supports retry', async () => {
  const env = await setup(request => request.path === '/me' ? Response.json(user) : rejected('request_failed', 500));
  await env.click('auth-logout');
  assert.equal(env.reloads(), 0);
  assert.equal(env.elements['auth-logout'].hidden, false);
  assert.match(env.elements['auth-session-error'].textContent, /로그아웃.*다시/);
});

test('lost registration without a confirmed session offers login rather than claiming success', async () => {
  const env = await setup(request => {
    if (request.path === '/me') return rejected('unauthorized', 401);
    throw Error('synthetic lost response');
  });
  await env.click('auth-open-register'); env.fill(); await env.submit();
  assert.equal(env.requests.filter(request => request.path === '/register').length, 1);
  assert.equal(env.elements['auth-logout'].hidden, true);
  assert.match(env.elements['auth-form-error'].textContent, /이미 계정.*로그인/);
});

test('lost logout response is reconciled against a revoked server session', async () => {
  let loggedIn = true;
  const env = await setup(request => {
    if (request.path === '/me') return loggedIn ? Response.json(user) : rejected('unauthorized', 401);
    loggedIn = false; throw Error('synthetic lost response');
  });
  await env.click('auth-logout');
  assert.equal(env.reloads(), 1);
  assert.equal(env.elements['auth-logout'].hidden, true);
});

test('username markup is shown as literal text', async () => {
  const env = await setup(() => Response.json({...user, username: '<img src=x onerror=alert(1)>'}));
  assert.equal(env.elements['auth-status'].textContent, '<img src=x onerror=alert(1)>님 · 로그인됨');
  assert.equal(env.elements['auth-status'].innerHTML, undefined);
});
