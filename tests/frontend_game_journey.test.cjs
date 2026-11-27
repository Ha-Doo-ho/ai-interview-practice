const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const client = require('../html/client.js');

const tabs = ['survey', 'game', 'interview', 'report', 'records', 'guide'];
function runAt(count) {
  const rounds = total => Array.from({length:total}, () => ({status:'completed'}));
  return {
    flow_version:'five-game-v2', status:'in_progress', user_id:'owner', run_id:'demo', revision:count,
    rule_games:{games:{rsp:{rounds:rounds(count >= 1 ? 3 : 0)}, card:{rounds:rounds(count >= 2 ? 3 : 0)}}},
    appointment_games:{games:['day','place','bus'].map((type,i) => ({
      type, status:count >= 3+i ? 'complete':'pending', questions:count >= 3+i ? Array(10).fill({}) : []
    }))},
    aptitude_games:{attempts:['rotation','path','potion'].slice(0, Math.max(0,count-5)).map(type => ({type,mode:'main',status:'complete'}))}
  };
}

function page(hash = '#/survey') {
  const elements = new Map(), handlers = {}, subscribers = [], calls = [];
  const html = fs.readFileSync('html/index.html','utf8');
  function element(id) {
    const classes = new Set();
    return {id, hidden:false, disabled:false, children:[], textContent:'', events:{},
      classList:{add:c=>classes.add(c),remove:c=>classes.delete(c),contains:c=>classes.has(c)},
      addEventListener(k,f){this.events[k]=f;}, click(){return this.events.click?.();},
      scrollIntoView(){this.scrolled=true;}, focus(){this.focused=true;}
    };
  }
  for (const [,id] of html.matchAll(/id="([^"]+)"/g)) elements.set(id,element(id));
  const nav = tabs.map(element);
  const document = {
    getElementById:id=>elements.get(id),
    querySelectorAll:s=>s==='.tab-view'?tabs.map(t=>elements.get('view-'+t)):nav,
    addEventListener:(k,f)=>(handlers[k]??=[]).push(f)
  };
  const location = {hash}, history = {};
  for(const method of ['pushState','replaceState'])history[method]=(_,__,h)=>{location.hash=h;};
  const context = {run:null,user:null};
  let get = async () => context.run;
  function publish(run) {
    context.run=run;context.user=run?{user_id:run.user_id}:null;
    for (const f of subscribers) f(context);
  }
  const window = {location,history, addEventListener:(k,f)=>(handlers[k]??=[]).push(f),
    AstraClient:{...client,createApi:()=>async(path,options)=>{calls.push({path,options});return get();}},
    AstraPractice:{subscribe:f=>{subscribers.push(f);f(context);}, updateRun:run=>{
      if(run.run_id!==context.run?.run_id||run.user_id!==context.user?.user_id||run.revision<context.run.revision)return false;
      publish(run);return true;
    }}
  };
  const sandbox = vm.createContext({document,window,console});
  vm.runInContext(fs.readFileSync('html/script.js','utf8'),sandbox);
  vm.runInContext('initializeTabNavigation()',sandbox);
  const panelPath='html/game-journey.js';
  if(fs.existsSync(panelPath)) {
    const oldCount=handlers.DOMContentLoaded.length;
    vm.runInContext(fs.readFileSync(panelPath,'utf8'),sandbox);
    for(const f of handlers.DOMContentLoaded.slice(oldCount))f();
  }
  return {publish,window,context,elements,calls,handlers,
    pointGet:f=>{get=f;},nav:t=>sandbox.navigateTab(t),
    active:()=>tabs.find(t=>elements.get('view-'+t).classList.contains('active'))};
}

test('menu, direct link after session restoration and browser history enforce all eight games',()=>{
  const p=page('#/interview');
  p.publish(runAt(5));
  assert.equal(p.active(),'game');
  assert.equal(p.window.location.hash,'#/game');
  p.nav('survey');p.nav('interview');
  assert.equal(p.active(),'game');
  p.publish(runAt(7));p.nav('guide');
  p.window.location.hash='#/interview';p.handlers.popstate[0]();
  assert.equal(p.active(),'game');
  assert.equal(p.window.location.hash,'#/game');
  const almost=runAt(7);
  almost.aptitude_games.attempts.push({type:'potion',mode:'quick',status:'complete'});
  p.publish(almost);p.nav('interview');assert.equal(p.active(),'game');
  p.publish(runAt(8));p.nav('interview');assert.equal(p.active(),'interview');
  const repeating=runAt(8);
  repeating.aptitude_games.attempts.push({type:'path',mode:'practice',status:'active'});
  p.publish(repeating);assert.equal(p.active(),'game');
  p.publish({...runAt(2),status:'completed'});p.nav('interview');assert.equal(p.active(),'interview');
  p.publish({...runAt(2),flow_version:undefined});p.nav('interview');assert.equal(p.active(),'interview');
});

test('game page keeps a recoverable destination after card three and resumes without a game mutation',async()=>{
  const p=page('#/game');
  p.publish(runAt(2));
  const el=id=>p.elements.get(id);
  assert.ok(el('game-journey'),'the game view must include permanent recovery controls');
  assert.equal(el('game-journey').hidden,false);
  assert.match(el('journey-progress').textContent,/2\s*\/\s*8/);
  assert.match(el('journey-progress').textContent,/요일/);
  assert.equal(el('journey-interview').hidden,true);
  el('appointment-games').hidden=true;
  await el('journey-resume').click();
  assert.match(el('journey-notice').textContent,/불러|새로고침/);
  el('appointment-games').hidden=false;el('appointment-games').children.push({});
  await el('journey-resume').click();assert.equal(el('appointment-games').focused,true);
  p.pointGet(async()=>runAt(5));await el('journey-refresh').click();
  assert.match(el('journey-progress').textContent,/5\s*\/\s*8/);
  assert.match(el('journey-progress').textContent,/회전/);
  assert.ok(p.calls.every(c=>!c.options?.method||c.options.method==='GET'));
  assert.equal(p.calls.at(-1).path,'/runs/demo');
  el('journey-leave').click();assert.equal(p.active(),'records');
  p.publish(runAt(8));p.nav('game');assert.equal(el('journey-interview').hidden,false);
  el('journey-interview').click();assert.equal(p.active(),'interview');
});
