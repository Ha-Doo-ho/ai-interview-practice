// Synthetic DOM/transport checks of the actual browser scripts, not visual tests.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const {webcrypto} = require('node:crypto');
const C = require('../html/client.js');
const definitions = require('./fixtures/survey_definitions.json');
const user = {user_id: 'synthetic-owner', username: 'practice-user'};
const clone = x => JSON.parse(JSON.stringify(x));
const flush = async () => { for (let i=0;i<8;i++) await new Promise(r => setImmediate(r)); };
class Element {
  constructor(tag='div') { this.tagName=tag; this.children=[]; this.events={}; this.attrs={}; this.value=''; this.checked=false; this.disabled=false; this.hidden=false; this.style={}; this.dataset={}; this._text=''; this.classList={toggle(){},add(){},remove(){}}; }
  set textContent(x) {this._text=String(x);this.children=[];}
  get textContent() {return this._text+this.children.map(x=>x.textContent).join('');}
  append(...x) {this.children.push(...x);}
  appendChild(x) {this.append(x);return x;}
  replaceChildren(...x) {this._text='';this.children=x;}
  setAttribute(k,v) {this.attrs[k]=String(v);if(k==='id')this.id=String(v);}
  addEventListener(k,f) {(this.events[k] ||= []).push(f);}
  async fire(k) {for(const f of this.events[k]||[]) await f({target:this,preventDefault(){}});await flush();}
  focus() {this.focused=true;}
  querySelectorAll(s) {const tags=s.split(',').map(x=>x.trim());return this.children.flatMap(x=>[...(tags.includes(x.tagName)?[x]:[]),...x.querySelectorAll(s)]);}
  querySelector(s) {return this.querySelectorAll(s)[0]||null;}
}
async function setup({storage=new Map(), runs=[], handler, loggedIn=true, startTime=100000, withGames=false, withInterview=false, withReport=false, withRecords=false, questions=[]}={}) {
  const html=fs.readFileSync('html/index.html','utf8');
  const roots=Object.fromEntries([...html.matchAll(/id="([^"]+)"/g)].map(m=>[m[1],new Element()]));
  const events={}, winEvents={}, calls=[], navigation=[]; let now=startTime, listener;
  const find=(n,id)=>n.id===id?n:n.children.map(x=>find(x,id)).find(Boolean);
  const document={getElementById:id=>roots[id]||Object.values(roots).map(x=>find(x,id)).find(Boolean),createElement:t=>new Element(t),addEventListener(k,f){(events[k]||=[]).push(f);}};
  const transport=async (url,opts)=>{
    const call={path:url.slice(4),method:opts.method,body:opts.body?JSON.parse(opts.body):undefined};calls.push(call);
    const custom=handler && await handler(call);if(custom) return custom;
    if(call.path==='/definitions') return Response.json(definitions);
    if(call.path==='/runs'&&call.method==='GET') return Response.json({runs});
    if(call.path==='/runs'&&call.method==='POST') {const run={run_id:'real-run-'+runs.length,user_id:user.user_id,attempt_id:'attempt',revision:0,status:'in_progress',records:[],questions:clone(questions),created_at:'2026-10-10T00:00:00Z'};runs.push(run);return Response.json(run,{status:201});}
    const changing=runs.find(r=>call.path==='/runs/'+r.run_id+'/surveys');
    if(changing) {
      const b=call.body, item=(changing.survey_definition_snapshot||definitions.surveys).find(x=>x.item_id===b.item_id), label=p=>item.ordered_options.find(o=>o.position===p)?.label;
      let data={...clone(b.response),prompt_snapshot:item.prompt};
      if(item.type==='ordinal_6') data.selected_label_snapshot=label(b.response?.selected_position);
      if(b.nonresponse_reason) {data.nonresponse_reason=b.nonresponse_reason;data.nonresponse_label_snapshot=item.nonresponse_options.find(o=>o.id===b.nonresponse_reason).label;}
      if(item.type==='paired_perspective') for(const p of ['self','imagined_others'])data[p].selected_label_snapshot=label(data[p].selected_position);
      if(item.type==='bipolar_slider') Object.assign(data,{left_anchor_label:item.left_anchor.label,right_anchor_label:item.right_anchor.label});
      if(item.type==='top_k_rank') Object.assign(data,{candidate_snapshots:item.candidates,ranked_selection:b.response.ranked_selection});
      changing.revision++;changing.records.push({source_type:'survey',item_id:item.item_id,status:b.status,context:{response_type:item.type},data});
      return Response.json(changing);
    }
    const run=runs.find(r=>call.path==='/runs/'+r.run_id);
    if(run&&call.method==='DELETE'){runs.splice(runs.indexOf(run),1);return new Response(null,{status:204});}
    if(run) return Response.json(run);
    throw Error('Unexpected '+call.path);
  };
  const window={confirm:()=>true,AstraClient:{...C,createApi:()=>C.createApi(transport)},AstraAuth:{subscribe(f){listener=f;f({status:loggedIn?'authenticated':'guest',user:loggedIn?user:null});},recheck(){}},sessionStorage:{getItem:k=>storage.get(k)||null,setItem:(k,v)=>storage.set(k,v),removeItem:k=>storage.delete(k)},addEventListener(k,f){(winEvents[k]||=[]).push(f);}};
  const timers=new Set();
  const context=vm.createContext({window,document,crypto:webcrypto,structuredClone,performance:{timeOrigin:0,now:()=>now},Date,console,setInterval:f=>{timers.add(f);return f;},clearInterval:f=>timers.delete(f)});
  vm.runInContext(fs.readFileSync('html/script.js','utf8'),context);
  context.navigateTab=t=>navigation.push(t);
  if(fs.existsSync('html/practice.js')) vm.runInContext(fs.readFileSync('html/practice.js','utf8'),context);
  if(withGames)vm.runInContext(fs.readFileSync('html/games.js','utf8'),context);
  if(withInterview)vm.runInContext(fs.readFileSync('html/interview.js','utf8'),context);
  if(withReport)vm.runInContext(fs.readFileSync('html/report.js','utf8'),context);
  if(withRecords)vm.runInContext(fs.readFileSync('html/records.js','utf8'),context);
  for(const f of events.DOMContentLoaded||[]) await f();await flush();
  return {roots,document,context,calls,runs,storage,navigation,async click(id){const el=document.getElementById(id);assert.ok(el?.events.click?.length,'Missing working control: '+id);await el.fire('click');},async choose(id,value,event='change'){const el=document.getElementById(id);assert.ok(el,'Missing '+id);if(['checkbox','radio'].includes(el.type))el.checked=!!value;else el.value=String(value);await el.fire(event);},advance(ms){now+=ms;},async tick(ms){now+=ms;for(const timer of [...timers])await timer();await flush();},async auth(state){listener(state);await flush();}};
}

test('new practice requests the approved set and resumes five six-label questions without changing legacy runs',async()=>{
  const items=clone(require('./fixtures/work_survey_definitions.json'));
  const current={run_id:'work-new',user_id:user.user_id,revision:0,status:'in_progress',records:[],questions:[],
    survey_set_version:'work-behavior-v2',survey_definition_snapshot:items};
  const legacy={run_id:'work-old',user_id:user.user_id,revision:0,status:'in_progress',records:[],questions:[]};
  const env=await setup({runs:[current,legacy],handler:call=>call.path==='/runs'&&call.method==='POST'?Response.json(current,{status:201}):undefined});
  await env.click('practice-new');
  assert.equal(env.calls.find(c=>c.path==='/runs'&&c.method==='POST').body.survey_set_version,'work-behavior-v2');
  assert.match(env.roots['practice-progress'].textContent,/0 \/ 5/);
  for(const [index,item] of items.entries()) {
    await env.click('practice-start-item');
    const field=env.roots['practice-items'];
    assert.ok(item.ordered_options.every(o=>field.textContent.includes(o.label)));
    assert.equal(field.querySelectorAll('input').filter(x=>x.type==='range').length,0);
    assert.equal(field.querySelectorAll('input').filter(x=>x.checked).length,0);
    if(index<2)await env.click(index===0?'survey-nonresponse-no_experience':'survey-nonresponse-unsure');
    else {await env.choose(item.item_id+'-selected_position-5',true);await env.click('practice-submit');}
  }
  assert.match(env.roots['practice-progress'].textContent,/5 \/ 5/);
  assert.match(env.roots['practice-runs'].children.find(o=>o.value==='work-new').textContent,/5\/5/);
  assert.match(env.roots['practice-saved'].textContent,/해당 경험 없음/);
  assert.match(env.roots['practice-saved'].textContent,/판단하기 어려움/);
  const sent=env.calls.filter(c=>c.path.endsWith('/surveys'));
  assert.deepEqual(sent.slice(0,2).map(c=>c.body.nonresponse_reason),['no_experience','unsure']);
  assert.ok(sent.slice(0,2).every(c=>c.body.status==='skipped'&&!('selected_position' in c.body.response)));
  await env.choose('practice-runs','work-old');await env.click('practice-open');
  assert.match(env.roots['practice-progress'].textContent,/0 \/ 6/);
  await env.click('practice-start-item');assert.ok(env.document.getElementById('O-B01-selected_position-5'));
  assert.equal(Boolean(env.document.getElementById('survey-nonresponse-no_experience')),false);
});

test('a nonresponse survives revision conflict and deadline without reviving an old agreement choice',async()=>{
  const items=clone(require('./fixtures/work_survey_definitions.json'));
  const current={run_id:'nonresponse-conflict',user_id:user.user_id,revision:0,status:'in_progress',records:[],questions:[],
    survey_set_version:'work-behavior-v2',survey_definition_snapshot:items};
  let conflict=true;
  const env=await setup({runs:[current],handler:call=>{
    if(call.path==='/runs'&&call.method==='POST')return Response.json(current,{status:201});
    if(call.path.endsWith('/surveys')&&conflict){conflict=false;current.revision++;return Response.json({error:'revision_conflict'},{status:409});}
  }});
  await env.click('practice-new');await env.click('practice-start-item');
  await env.choose('O-B01-selected_position-6',true);
  await env.click('survey-nonresponse-unsure');
  const first=env.calls.find(c=>c.path.endsWith('/surveys')).body;
  await env.tick(31000);
  assert.equal(env.calls.filter(c=>c.path.endsWith('/surveys')).length,1);
  assert.equal(env.roots['practice-retry'].hidden,false);
  await env.click('practice-retry');
  const last=env.calls.filter(c=>c.path.endsWith('/surveys')).at(-1).body;
  assert.equal(last.status,'skipped');assert.equal(last.nonresponse_reason,'unsure');
  assert.deepEqual(last.response,{});assert.equal(last.elapsed_ms,first.elapsed_ms);
  assert.notEqual(last.idempotency_key,first.idempotency_key);assert.equal(last.expected_revision,1);
  assert.match(env.roots['practice-saved'].textContent,/판단하기 어려움/);
  assert.doesNotMatch(env.roots['practice-saved'].textContent,/매우 그렇다/);
});

test('owned server records resume an existing run and confirmed delete clears every selected evidence pane',async()=>{
  assert.equal(fs.existsSync('html/records.js'),true,'server records adapter must exist');
  const run={run_id:'server-owned',user_id:user.user_id,revision:0,status:'in_progress',records:[],questions:[],created_at:'2026-10-13T00:00:00Z'};
  const env=await setup({runs:[run],withRecords:true});
  assert.match(env.roots.recordsTbody.textContent,/server-owned/);assert.doesNotMatch(env.roots.recordsTbody.textContent,/점|score/);
  await env.click('records-open-0');assert.equal(env.context.window.AstraPractice.active(),true);
  assert.equal(env.navigation.at(-1),'survey');assert.equal(env.calls.filter(c=>c.method==='POST').length,0);
  await env.click('records-delete-0');assert.equal(env.calls.filter(c=>c.method==='DELETE').length,1);
  assert.equal(env.context.window.AstraPractice.active(),false);assert.equal(env.roots.recordsTbody.textContent,'');assert.match(env.roots['records-status'].textContent,/0개/);
});

test('server records confirm cancellation and clear private list on logout; late account list responses cannot repopulate it',async()=>{
  assert.equal(fs.existsSync('html/records.js'),true,'server records adapter must exist');
  const run={run_id:'server-owned',user_id:user.user_id,revision:0,status:'in_progress',records:[],questions:[],created_at:'2026-10-13T00:00:00Z'};
  const env=await setup({runs:[run],withRecords:true});env.context.window.confirm=()=>false;
  await env.click('records-delete-0');assert.equal(env.calls.filter(c=>c.method==='DELETE').length,0);
  let release;const original=env.context.window.AstraPractice;
  // The actual practice load protects its epoch when an account changes during GET /runs.
  const delayed=await setup({runs:[run],withRecords:true,handler:call=>call.path==='/runs'&&call.method==='GET'?new Promise(resolve=>{release=()=>resolve(Response.json({runs:[run]}));}):undefined});
  await delayed.auth({status:'guest',user:null});release();await flush();assert.equal(delayed.roots.recordsTbody.textContent,'');assert.match(delayed.roots['records-status'].textContent,/로그인/);
  await env.auth({status:'guest',user:null});assert.equal(env.roots.recordsTbody.textContent,'');assert.equal(original.active(),false);
});

test('server records account switch ignores a late deletion response and a rejected delete displays an actionable error',async()=>{
  const run={run_id:'server-owned',user_id:user.user_id,revision:0,status:'in_progress',records:[],questions:[],created_at:'2026-10-13T00:00:00Z'};
  const other={...run,run_id:'other-owned',user_id:'other-user'};let switched=false,release;
  const env=await setup({runs:[run],withRecords:true,handler:call=>{
    if(call.method==='DELETE')return new Promise(resolve=>{release=()=>resolve(new Response(null,{status:204}));});
    if(switched&&call.path==='/runs')return Response.json({runs:[other]});
  }});
  const deleting=env.click('records-delete-0');await flush();switched=true;await env.auth({status:'authenticated',user:{user_id:'other-user'}});
  assert.match(env.roots.recordsTbody.textContent,/other-owned/);assert.doesNotMatch(env.roots.recordsTbody.textContent,/server-owned/);
  release();await deleting;assert.match(env.roots.recordsTbody.textContent,/other-owned/);
  const rejected=await setup({runs:[run],withRecords:true,handler:call=>call.method==='DELETE'?Promise.reject(Error('offline')):undefined});
  await rejected.click('records-delete-0');assert.match(rejected.roots['records-error'].textContent,/결과.*확인.*다시/);assert.match(rejected.roots.recordsTbody.textContent,/server-owned/);
});
test('guest cannot create a run; authenticated new practice creates one real run and opens timed survey',async()=>{
  const guest=await setup({loggedIn:false});assert.ok(guest.roots['practice-new']);assert.equal(guest.roots['practice-new'].disabled,true);
  const env=await setup();await env.click('practice-new');
  assert.equal(env.calls.filter(x=>x.path==='/runs'&&x.method==='POST').length,1);
  const create=env.calls.find(x=>x.method==='POST');assert.ok(create.body.idempotency_key);assert.equal(create.body.expected_user_id,user.user_id);
  assert.match(env.roots['practice-status'].textContent,/real-run-0/);
  assert.equal(env.roots['survey-form'].hidden,true);
  await env.click('practice-start-item');
  assert.equal(env.roots['practice-items'].children.length,1);
  assert.ok(env.document.getElementById('O-B01-selected_position-5'));
  assert.match(env.roots['practice-timer'].textContent,/30/);
});

async function submitSix(env) {
  const choices=[
    [['O-B01-selected_position-5',true]], [['O-B02-selected_position-2',true]], [['O-B03-selected_position-6',true]],
    [['P-B01-self-4',true],['P-B01-imagined_others-5',true]], [['S-B02-confirm',true]],
    [['R-UNMAPPED-rank-1','helping'],['R-UNMAPPED-rank-2','growth'],['R-UNMAPPED-rank-3','autonomy']]
  ];
  for(const group of choices){await env.click('practice-start-item');for(const args of group)await env.choose(...args);await env.tick(1200);await env.click('practice-submit');}
}
test('six actual UI submissions preserve exact values, sequential revision and saved readback [SCN-001,004,007,009]',async()=>{
  const env=await setup();await env.click('practice-new');await submitSix(env);
  const bodies=env.calls.filter(c=>c.path.endsWith('/surveys')).map(c=>c.body);
  assert.deepEqual(bodies.map(b=>b.expected_revision),[0,1,2,3,4,5]);
  assert.equal(new Set(bodies.map(b=>b.idempotency_key)).size,6);
  assert.ok(bodies.every(b=>b.elapsed_ms===1200&&b.status==='submitted'));
  assert.equal(bodies[3].response.self.selected_position,4);assert.equal(bodies[3].response.imagined_others.selected_position,5);
  assert.deepEqual(bodies[4].response,{final_value:0,interaction_occurred:false,explicit_confirmation:true,change_count:0});
  assert.deepEqual(bodies[5].response.ranked_selection,[{option_id:'helping',rank:1},{option_id:'growth',rank:2},{option_id:'autonomy',rank:3}]);
  assert.ok(bodies[5].response.selection_events.every(e=>['select','remove','move'].includes(e.action)));
  assert.match(env.roots['practice-progress'].textContent,/서버 저장 6 \/ 6/);
  assert.match(env.roots['practice-saved'].textContent,/그렇다.*그렇지 않다.*매우 그렇다/);
  assert.equal(env.roots['practice-game'].hidden,false);await env.click('practice-game');assert.equal(env.navigation.at(-1),'game');
  const payloads=bodies.map(({expected_revision,idempotency_key,...body})=>body);
  const fixture='tests/fixtures/practice_ui_payloads.json';
  if(process.env.UPDATE_PRACTICE_FIXTURE==='1')fs.writeFileSync(fixture,JSON.stringify(payloads,null,2)+'\n');
  assert.deepEqual(payloads,JSON.parse(fs.readFileSync(fixture,'utf8')));
  const resumed=await setup({runs:clone(env.runs),storage:env.storage});
  assert.match(resumed.roots['practice-progress'].textContent,/6 \/ 6/);assert.match(resumed.roots['practice-saved'].textContent,/중앙/);
  assert.equal(resumed.calls.filter(c=>c.method==='POST').length,0);
});
test('lost create response survives reload and retry uses the same creation key',async()=>{
  let lost=true, posted; const runs=[], committed=new Map();
  const handler=call=>{if(call.method==='POST'&&call.path==='/runs'){
    posted=call.body;
    if(!committed.has(call.body.idempotency_key)){
      const run={run_id:'committed-run',user_id:user.user_id,attempt_id:'attempt',revision:0,status:'in_progress',records:[],created_at:'2026-10-10T00:00:00Z'};
      committed.set(call.body.idempotency_key,run);runs.push(run);
    }
    if(lost){lost=false;throw Error('synthetic lost response after commit');}
    return Response.json(committed.get(call.body.idempotency_key),{status:201});
  }};
  const env=await setup({runs,handler});
  await env.click('practice-new');assert.equal(env.roots['practice-new'].disabled,true);assert.equal(env.roots['practice-retry'].hidden,false);
  const first=clone(posted);assert.equal(runs.length,1);
  const resumed=await setup({storage:env.storage,runs,handler});await resumed.click('practice-retry');
  assert.deepEqual(resumed.calls.find(c=>c.method==='POST').body,first);assert.equal(resumed.runs.length,1);
  assert.match(resumed.roots['practice-status'].textContent,/committed-run/);
});
test('lost survey response keeps frozen answer and elapsed across reload [SCN-012]',async()=>{
  let first;
  const env=await setup({handler:call=>{if(call.path.endsWith('/surveys')){first=clone(call.body);throw Error('synthetic offline');}}});
  await env.click('practice-new');await env.click('practice-start-item');await env.choose('O-B01-selected_position-5',true);await env.tick(2345);await env.click('practice-submit');
  assert.equal(env.roots['practice-submit'].disabled,true);assert.match(env.roots['practice-progress'].textContent,/0 \/ 6/);
  const resumed=await setup({storage:env.storage,runs:clone(env.runs),startTime:150000});await resumed.click('practice-retry');
  assert.deepEqual(resumed.calls.find(c=>c.path.endsWith('/surveys')).body,first);
  assert.match(resumed.roots['practice-progress'].textContent,/1 \/ 6/);
});
test('reload preserves active choice and deadline; late submit records timeout without a second timer window',async()=>{
  const env=await setup();await env.click('practice-new');await env.click('practice-start-item');await env.choose('O-B01-selected_position-6',true);
  const resumed=await setup({storage:env.storage,runs:clone(env.runs),startTime:129000});
  assert.equal(resumed.document.getElementById('O-B01-selected_position-6').checked,true);
  await resumed.tick(2000);
  const body=resumed.calls.find(c=>c.path.endsWith('/surveys')).body;
  assert.equal(body.status,'timed_out');assert.equal(body.elapsed_ms,31000);assert.equal(body.response.selected_position,6);
  assert.match(resumed.roots['practice-saved'].textContent,/시간 초과/);
});
test('partial paired, untouched slider and rank slot timeout remain distinguishable [SCN-004,006,009]',async()=>{
  const env=await setup();await env.click('practice-new');
  for(let i=0;i<3;i++){await env.click('practice-start-item');await env.click('practice-skip');}
  await env.click('practice-start-item');await env.choose('P-B01-self-4',true);await env.tick(45000);
  const paired=env.calls.at(-1).body;assert.equal(paired.response.self.selected_position,4);assert.equal(paired.response.imagined_others.status,'timed_out');
  await env.click('practice-start-item');await env.tick(30000);
  const slider=env.calls.at(-1).body;assert.equal(slider.response.final_value,null);assert.equal(slider.response.explicit_confirmation,false);
  await env.click('practice-start-item');await env.choose('R-UNMAPPED-rank-2','growth');await env.tick(45000);
  assert.deepEqual(env.calls.at(-1).body.response.ranked_selection,[{option_id:'growth',rank:2}]);
});
test('a guest transition clears private response DOM and rejects a late run response',async()=>{
  let resolve;
  const env=await setup({handler:c=>c.path==='/runs'&&c.method==='POST'?new Promise(r=>{resolve=r;}):undefined});
  const pending=env.click('practice-new');await flush();
  await env.auth({status:'guest',user:null});
  resolve(Response.json({run_id:'old-private',user_id:user.user_id,revision:0,records:[]}));await pending;
  assert.equal(env.roots['practice-survey'].hidden,true);assert.doesNotMatch(env.roots['practice-status'].textContent,/old-private/);assert.equal(env.roots['practice-new'].disabled,true);
});
test('empty required input cannot post; a second click while saving cannot duplicate a mutation',async()=>{
  let resolve;
  const env=await setup({handler:c=>c.path.endsWith('/surveys')?new Promise(r=>{resolve=r;}):undefined});
  await env.click('practice-new');await env.click('practice-start-item');await env.click('practice-submit');
  assert.equal(env.calls.filter(c=>c.path.endsWith('/surveys')).length,0);
  await env.choose('O-B01-selected_position-4',true);const pending=env.click('practice-submit');await flush();await env.click('practice-submit');
  assert.equal(env.calls.filter(c=>c.path.endsWith('/surveys')).length,1);
  resolve(Response.json(env.runs[0]));await pending;
});
test('input after deadline is excluded even if timer callback was delayed by the browser',async()=>{
  const env=await setup();await env.click('practice-new');await env.click('practice-start-item');await env.choose('O-B01-selected_position-4',true);
  env.advance(31000);await env.choose('O-B01-selected_position-6',true);
  const body=env.calls.find(c=>c.path.endsWith('/surveys')).body;
  assert.equal(body.status,'timed_out');assert.equal(body.response.selected_position,4);
});
test('session checking then confirmed logout clears the account journal and saved DOM',async()=>{
  const env=await setup();await env.click('practice-new');await env.click('practice-start-item');await env.choose('O-B01-selected_position-4',true);
  assert.ok(env.storage.size);await env.auth({status:'checking',user});await env.auth({status:'guest',user:null});
  assert.equal(env.storage.size,0);assert.equal(env.roots['practice-survey'].hidden,true);assert.equal(env.roots['practice-saved'].textContent,'');
});
test('definitive validation rejection can reconcile a new definition and explicitly discard the invalid pending draft',async()=>{
  const handler=c=>c.path.endsWith('/surveys')?Response.json({error:'validation_error'},{status:422}):undefined;
  const env=await setup({handler});await env.click('practice-new');await env.click('practice-start-item');await env.choose('O-B01-selected_position-4',true);await env.click('practice-submit');
  assert.equal(env.roots['practice-resolve']?.hidden,false,'Validation failure must have a recovery control');
  const updated=clone(definitions);updated.surveys[0].item_version='2.0.0';
  const resumed=await setup({runs:clone(env.runs),storage:env.storage,handler:c=>c.path==='/definitions'?Response.json(updated):c.path.endsWith('/surveys')&&c.body.item_version!=='2.0.0'?handler(c):undefined});
  await resumed.click('practice-resolve');
  assert.equal(resumed.roots['practice-retry'].hidden,true);assert.equal(resumed.roots['practice-new'].disabled,false);
  assert.equal(resumed.calls.filter(c=>c.method==='POST').length,0,'Reconciliation must not silently resubmit');
  await resumed.click('practice-start-item');await resumed.choose('O-B01-selected_position-6',true);await resumed.click('practice-submit');
  assert.equal(resumed.calls.find(c=>c.path.endsWith('/surveys')).body.item_version,'2.0.0');
  assert.match(resumed.roots['practice-progress'].textContent,/1 \/ 6/);
});
test('offline reload with a pending active response still offers a working refresh after reconnection',async()=>{
  const env=await setup({handler:c=>{if(c.path.endsWith('/surveys'))throw Error('synthetic offline');}});
  await env.click('practice-new');await env.click('practice-start-item');await env.choose('O-B01-selected_position-4',true);await env.click('practice-submit');
  let offline=true;
  const resumed=await setup({storage:env.storage,runs:clone(env.runs),handler:()=>{if(offline)throw Error('synthetic offline on startup');}});
  assert.equal(resumed.roots['practice-refresh'].disabled,false,'Reconnect must be possible while journal is active but server is not loaded');
  offline=false;await resumed.click('practice-refresh');await resumed.click('practice-retry');
  assert.match(resumed.roots['practice-progress'].textContent,/1 \/ 6/);
});
test('game bridge exposes the owned selected run and rejects stale or cross-run updates',async()=>{
  const env=await setup();await env.click('practice-new');
  const bridge=env.context.window.AstraPractice;
  assert.equal(typeof bridge.subscribe,'function');
  const seen=[];bridge.subscribe(value=>seen.push(value));
  assert.equal(seen.at(-1).run.run_id,env.runs[0].run_id);
  const changed={...clone(env.runs[0]),revision:1,rule_games:{version:'1.0.0',games:{}}};
  assert.equal(bridge.updateRun(changed),true);
  assert.equal(bridge.updateRun({...changed,user_id:'someone-else'}),false);
  assert.equal(bridge.updateRun({...changed,run_id:'another-run'}),false);
  assert.equal(bridge.updateRun({...changed,revision:0}),false);
  assert.equal(seen.at(-1).run.revision,1);
  const scope={run_id:changed.run_id,user_id:changed.user_id};
  bridge.setGameLock({...scope,locked:true});
  assert.equal(env.roots['practice-new'].disabled,true);
  bridge.setGameLock({...scope,run_id:'other-run',locked:false});
  assert.equal(env.roots['practice-new'].disabled,true);
  bridge.setGameLock({...scope,locked:false});
  assert.equal(env.roots['practice-new'].disabled,false);
});
test('interview and game locks remain separate and protect the same owned practice run',async()=>{
  const env=await setup();await env.click('practice-new');
  const bridge=env.context.window.AstraPractice,seen=[];bridge.subscribe(value=>seen.push(value));
  const scope={user_id:user.user_id,run_id:env.runs[0].run_id};
  bridge.setInterviewLock({...scope,locked:true});
  assert.equal(seen.at(-1).interviewLocked,true);assert.equal(seen.at(-1).gameLocked,false);
  assert.equal(seen.at(-1).locked,false,'A module must not gate itself through the survey-only lock');
  assert.equal(env.roots['practice-new'].disabled,true);assert.equal(env.roots['practice-open'].disabled,true);assert.equal(env.roots['practice-refresh'].disabled,true);
  const count=env.calls.length;await env.click('practice-new');await env.click('practice-refresh');await env.click('practice-open');
  assert.equal(env.calls.length,count,'Disabled controls must also be guarded at the handler boundary');
  bridge.setInterviewLock({...scope,user_id:'another-user',locked:false});assert.equal(seen.at(-1).interviewLocked,true);
  bridge.setGameLock({...scope,locked:true});bridge.setInterviewLock({...scope,locked:false});
  assert.equal(seen.at(-1).gameLocked,true);assert.equal(env.roots['practice-new'].disabled,true);
  bridge.setGameLock({...scope,locked:false});assert.equal(env.roots['practice-new'].disabled,false);
});

test('report work locks owned practice controls and cannot release the other module locks',async()=>{
  const env=await setup();await env.click('practice-new');
  const bridge=env.context.window.AstraPractice,seen=[];
  bridge.subscribe(value=>seen.push(value));
  const scope={user_id:user.user_id,run_id:env.runs[0].run_id};
  bridge.setReportLock({...scope,locked:true});
  assert.equal(seen.at(-1).reportLocked,true);
  assert.equal(seen.at(-1).locked,false,'Report lock must not recursively block its own subscription');
  for(const id of ['practice-new','practice-refresh','practice-open','practice-start-item'])assert.equal(env.roots[id].disabled,true,id);
  const count=env.calls.length;
  for(const id of ['practice-new','practice-refresh','practice-open','practice-start-item'])await env.click(id);
  assert.equal(env.calls.length,count);
  bridge.setReportLock({...scope,user_id:'other',locked:false});assert.equal(seen.at(-1).reportLocked,true);
  bridge.setInterviewLock({...scope,locked:true});bridge.setReportLock({...scope,locked:false});
  assert.equal(seen.at(-1).interviewLocked,true);assert.equal(env.roots['practice-new'].disabled,true);
  bridge.setInterviewLock({...scope,locked:false});assert.equal(env.roots['practice-new'].disabled,false);
});
test('actual practice and game scripts share the six-survey run, latest revision and round lock without feedback loops',async()=>{
  let env;
  const at=ms=>new Date(ms).toISOString();
  const handler=call=>{
    if(call.path==='/rule-game-definitions')return Response.json({version:'1.0.0',duration_ms:20000,rounds_per_game:3});
    if(call.path.endsWith('/rule-games')){
      const run=env.runs[0];
      if(call.method==='GET')return Response.json({run,server_time:at(100000)});
      const b=call.body;
      assert.equal(b.expected_revision,run.revision,'The shared bridge must use the latest survey/game revision');
      if(b.action==='start')run.rule_games={games:{rsp:{rounds:[{round_id:'shared-round',index:1,status:'in_progress',phase:'initial',started_at:at(100000),deadline_at:at(120000),reveal_due_at:at(110000),score:0,correct_count:0,incorrect_count:0,rule:{label:'이겨라'},stimulus:{stimulus_id:'shared-stimulus',opponent_hand:'scissors'},events:[{type:'round_started',server_at:at(100000)}]}]},card:{rounds:[]}}};
      else if(b.action==='finish'){const round=run.rule_games.games.rsp.rounds[0];round.status='completed';round.phase='completed';round.events.push({type:'round_ended',server_at:at(120000)});}
      run.revision++;return Response.json(run);
    }
  };
  env=await setup({withGames:true,handler});await env.click('practice-new');await submitSix(env);await env.click('btnStartGame');
  assert.equal(env.roots['practice-new'].disabled,true);assert.equal(env.roots['practice-runs'].disabled,true);
  assert.match(env.roots['game-status'].textContent,/real-run-0/);assert.match(env.roots['practice-progress'].textContent,/6 \/ 6/);
  await env.tick(20000);
  assert.match(env.roots['game-saved-count'].textContent,/가위바위보 1 \/ 3/);assert.equal(env.roots['practice-new'].disabled,false);
  const seen=[];env.context.window.AstraPractice.subscribe(value=>seen.push(value));assert.equal(seen.at(-1).run.revision,8);
  assert.equal(env.runs[0].records.length,6);
});
test('new practice opts into five games and appointment lock cannot be cleared by rule game',async()=>{
  const env=await setup();await env.click('practice-new');
  const request=env.calls.find(call=>call.path==='/runs'&&call.method==='POST');
  assert.equal(request.body.flow_version,'five-game-v2');
  const scope={user_id:user.user_id,run_id:env.runs[0].run_id};
  env.context.window.AstraPractice.setAppointmentGameLock({...scope,locked:true});
  env.context.window.AstraPractice.setGameLock({...scope,locked:false});
  assert.equal(env.roots['practice-new'].disabled,true);
  env.context.window.AstraPractice.setAppointmentGameLock({...scope,locked:false});
  assert.equal(env.roots['practice-new'].disabled,false);
});
test('actual practice, game and interview scripts preserve one run and exchange locks through answer save and reload',async()=>{
  let env,release;
  const at=ms=>new Date(ms).toISOString();
  const questions=[1,2,3].map(i=>({question_id:'owned-question-'+i,question_version:'1.0.0',question_text:'서버 회차 질문 '+i,question_mode:'baseline',conditioned_on_prior_evidence:false}));
  const handler=async call=>{
    if(call.path==='/rule-game-definitions')return Response.json({version:'1.0.0',duration_ms:20000,rounds_per_game:3});
    if(call.path.endsWith('/rule-games')){
      const run=env.runs[0];
      if(call.method==='GET')return Response.json({run,server_time:at(100000)});
      assert.equal(call.body.expected_revision,run.revision);
      if(call.body.action==='start')run.rule_games={games:{rsp:{rounds:[{round_id:'shared-round',index:1,status:'in_progress',phase:'initial',deadline_at:at(120000),reveal_due_at:at(110000),score:0,correct_count:0,incorrect_count:0,rule:{label:'이겨라'},stimulus:{stimulus_id:'shared-stimulus',opponent_hand:'scissors'},events:[{type:'round_started',server_at:at(100000)}]}]},card:{rounds:[]}}};
      if(call.body.action==='finish'){const round=run.rule_games.games.rsp.rounds[0];round.status='completed';round.phase='completed';round.events.push({type:'round_ended',server_at:at(120000)});}
      run.revision++;return Response.json(run);
    }
    if(call.path.endsWith('/answers')){
      await new Promise(resolve=>release=resolve);
      const run=env.runs[0],body=call.body;assert.equal(body.expected_revision,run.revision);
      run.records.push({source_type:'typed_answer',status:body.status,data:{answer_id:'shared-answer',answer_version:'1.0.0',question_id:body.question_id,question_text_snapshot:questions[0].question_text,text:body.text,status:body.status,previous_answer_version_ref:null}});
      run.revision++;return Response.json(run);
    }
  };
  env=await setup({withGames:true,withInterview:true,questions,handler});
  await env.click('practice-new');await submitSix(env);await env.click('btnStartGame');
  assert.equal(env.document.getElementById('interview-save-0').disabled,true,'Active game gates interview writes');
  await env.tick(20000);const originalGame=clone(env.runs[0].rule_games);
  const exact='  동일 회차 경험 🐱\n다음 줄  ';
  await env.choose('interview-answer-0',exact,'input');const saving=env.click('interview-save-0');await flush();
  assert.equal(env.roots['practice-new'].disabled,true);assert.equal(env.roots.btnStartGame.disabled,true);
  release();await saving;
  assert.equal(env.runs[0].records.at(-1).data.text,exact);assert.equal(env.runs[0].records.filter(r=>r.source_type==='survey').length,6);
  assert.deepEqual(env.runs[0].rule_games,originalGame);assert.equal(env.runs[0].revision,9);
  assert.match(env.roots['interview-progress'].textContent,/1 \/ 3/);assert.equal(env.roots['practice-new'].disabled,false);
  const bridge=env.context.window.AstraPractice,scope={user_id:user.user_id,run_id:env.runs[0].run_id};
  bridge.setReportLock({...scope,locked:true});
  assert.equal(env.roots.btnStartGame.disabled,true,'Report request gates game writes');
  assert.equal(env.document.getElementById('interview-answer-0').disabled,true,'Report request gates answer changes');
  const beforeReport=env.calls.length;
  await env.click('interview-save-0');await env.click('btnStartGame');
  assert.equal(env.calls.length,beforeReport,'Handler guards agree with the disabled controls');
  bridge.setReportLock({...scope,locked:false});
  assert.equal(env.document.getElementById('interview-answer-0').disabled,false);
  const savedRuns=clone(env.runs),storage=env.storage;
  const restored=await setup({withGames:true,withInterview:true,runs:savedRuns,storage,handler:c=>c.path==='/rule-game-definitions'?Response.json({version:'1.0.0',duration_ms:20000,rounds_per_game:3}):c.path.endsWith('/rule-games')?Response.json({run:savedRuns[0],server_time:at(125000)}):undefined});
  assert.equal(restored.document.getElementById('interview-answer-0').value,exact);
  assert.match(restored.roots['game-saved-count'].textContent,/가위바위보 1 \/ 3/);
  assert.equal(restored.calls.filter(c=>c.method==='POST').length,0);
});

test('four actual modules save a report for the same run, guard writes and restore it without a new analysis',async()=>{
  let env,release;
  const questions=[1,2,3].map(i=>({question_id:'report-question-'+i,question_version:'1.0.0',question_text:'중립 질문 '+i,question_mode:'baseline',conditioned_on_prior_evidence:false}));
  const handler=async call=>{
    if(call.path==='/rule-game-definitions')return Response.json({version:'1.0.0',duration_ms:20000,rounds_per_game:3});
    if(call.path==='/interview-analysis-capabilities')return Response.json({live_available:false,reason:'live_disabled',model_id:null,max_calls_per_run:0,max_cost_microusd:0});
    if(call.path.endsWith('/rule-games'))return Response.json({run:env.runs[0],server_time:new Date(100000).toISOString()});
    if(call.path.endsWith('/interview-analysis')){
      await new Promise(resolve=>release=resolve);
      const run=env.runs[0];assert.equal(call.body.expected_revision,run.revision);
      assert.equal(call.body.mode,'mock');assert.ok(call.body.idempotency_key);
      run.interview_report={report_id:'shared-report',report_version:'1.0.0',runtime_mode:'mock',requested_mode:'mock',provider_execution:'not_called',cards:[],surveys:[],rule_games:[],limitations:['합성 보고서 결합 검사']};
      run.interview_analysis={runtime_mode:'mock',requested_mode:'mock',provider_execution:'not_called'};
      run.interview_report_stale=false;run.revision++;return Response.json(run);
    }
  };
  env=await setup({withGames:true,withInterview:true,withReport:true,questions,handler});
  await env.click('practice-new');await submitSix(env);
  assert.equal(env.roots['report-mock'].disabled,false,'Initial loading must release the shared report lock');
  const before=clone(env.runs[0]);
  const saving=env.click('report-mock');await flush();
  assert.equal(env.roots['practice-new'].disabled,true);
  assert.equal(env.roots.btnStartGame.disabled,true);
  assert.equal(env.document.getElementById('interview-answer-0').disabled,true);
  const callCount=env.calls.length;
  await env.click('practice-new');await env.click('btnStartGame');await env.click('interview-save-0');await env.click('report-mock');
  assert.equal(env.calls.length,callCount,'An in-flight report must guard all mutation handlers');
  release();await saving;
  assert.deepEqual(env.runs[0].records,before.records);
  assert.equal(env.runs[0].run_id,before.run_id);
  assert.equal(env.runs[0].revision,before.revision+1);
  assert.equal(env.roots['practice-new'].disabled,false);
  assert.match(env.roots['report-content'].textContent,/shared-report/);
  assert.match(env.roots['report-status'].textContent,/AI 미사용/);
  const savedRuns=clone(env.runs);
  const restored=await setup({withGames:true,withInterview:true,withReport:true,runs:savedRuns,storage:env.storage,handler:call=>call.path.endsWith('/rule-games')?Response.json({run:savedRuns[0],server_time:new Date(100000).toISOString()}):handler(call)});
  assert.match(restored.roots['report-content'].textContent,/shared-report/);
  assert.equal(restored.calls.filter(c=>c.method==='POST').length,0);
});

test('five actual modules carry survey and baseline evidence through linkage, optional followup, final freeze, server reopen and deletion',async()=>{
  let env;
  const questions=[1,2,3].map(i=>({question_id:'completion-baseline-'+i,question_version:'1.0.0',question_text:'중립 기본 질문 '+i,question_mode:'baseline',conditioned_on_prior_evidence:false}));
  const conditioned={question_id:'completion-followup',question_version:'1.0.0',question_text:'설문 응답에 관련한 실제 경험은?',question_mode:'adaptive_followup',conditioned_on_prior_evidence:true,disclosed_prior_information:[{source_id:'survey-1',source_version:'1.0.0',response:'매우 그렇다'}],generated_from_evidence_refs:[{source_id:'survey-1',source_version:'1.0.0'}]};
  const handler=call=>{
    if(call.path==='/rule-game-definitions')return Response.json({version:'1.0.0',duration_ms:20000,rounds_per_game:3});
    if(call.path==='/interview-analysis-capabilities')return Response.json({live_available:false,reason:'live_disabled',max_calls_per_run:0});
    const run=env?.runs[0];
    if(call.path.endsWith('/rule-games'))return Response.json({run,server_time:new Date(100000).toISOString()});
    if(call.method==='POST'&&call.path!=='/runs'&&!call.path.endsWith('/surveys')){
      assert.equal(call.body.expected_revision,run.revision,'Every module must use the shared latest server revision');
      if(call.path.endsWith('/answers')){
        const question=run.questions.find(q=>q.question_id===call.body.question_id);
        run.records.push({source_type:'typed_answer',data:{...clone(question),question_text_snapshot:question.question_text,answer_id:'a-'+run.records.length,answer_version:'1.0.0',text:call.body.text,status:call.body.status,previous_answer_version_ref:null}});
      }else if(call.path.endsWith('/interview-analysis')){
        assert.equal(call.body.mode,'mock');run.interview_report={report_id:'completion-neutral',report_version:'1.0.0',runtime_mode:'mock',requested_mode:'mock',provider_execution:'not_called',cards:[],surveys:[],rule_games:[],limitations:['모의 서버']};run.interview_report_stale=false;
      }else if(call.path.endsWith('/evidence-linkage')){
        run.evidence_linkage={linkage_id:'completion-linkage',version:'1.0.0',source_report_id:'completion-neutral',input_snapshot:{},links:[],observations:[],questions:[conditioned],limitations:['게임은 규칙 과제 사실']};run.evidence_linkage_stale=false;run.questions.push(clone(conditioned));
      }else if(call.path.endsWith('/interview-finalize')){
        const answer=run.records.find(r=>r.data?.question_id===conditioned.question_id);
        run.interview_report.status='finalized';run.interview_report.evidence_linkage=clone(run.evidence_linkage);run.interview_report.followup_answers=[{...clone(conditioned),...clone(answer.data)}];run.status='completed';
      }else throw Error('Unexpected mutation '+call.path);
      run.revision++;return Response.json(run);
    }
  };
  env=await setup({withGames:true,withInterview:true,withReport:true,withRecords:true,questions,handler});
  await env.click('practice-new');await submitSix(env);
  // Completed server-scored game fixtures; existing games tests exercise the actual start/answer/reveal/finish controls.
  env.runs[0].rule_games={games:Object.fromEntries(['rsp','card'].map(type=>[type,{rounds:[1,2,3].map(index=>({round_id:type+'-'+index,index,status:'completed',score:0,correct_count:0,incorrect_count:0,rule:{label:'규칙'},stimulus:{opponent_hand:'rock',cards:[],selected_card_ids:[]},events:[]}))}]))};
  env.context.window.AstraPractice.updateRun(clone(env.runs[0]));
  for(let i=0;i<3;i++){await env.choose('interview-answer-'+i,'기본 원문 '+i,'input');await env.click('interview-save-'+i);}
  const preserved=clone(env.runs[0].records);
  await env.click('report-mock');await env.click('report-linkage');
  assert.match(env.roots['interview-followups'].textContent,/조건부.*매우 그렇다/);
  assert.equal(env.roots['report-finalize'].disabled,false,'Unanswered optional followup does not block finalization');
  const exact='  후속 원문🙂\n ';
  await env.choose('interview-answer-3',exact,'input');
  assert.equal(env.roots['report-finalize'].disabled,true,'An unsaved conditioned answer must block final freeze');
  const beforeFinalize=env.calls.filter(c=>c.method==='POST').length;await env.click('report-finalize');assert.equal(env.calls.filter(c=>c.method==='POST').length,beforeFinalize);
  assert.match(env.roots['report-completion'].textContent,/미저장 면접 입력 1개/);
  await env.click('interview-save-3');assert.equal(env.roots['report-finalize'].disabled,false);
  assert.match(env.roots['interview-progress'].textContent,/3 \/ 3/);assert.match(env.roots['interview-followup-progress'].textContent,/1 \/ 1/);
  assert.deepEqual(env.runs[0].records.slice(0,preserved.length),preserved,'Conditioned work never modifies neutral source versions');
  await env.click('report-finalize');assert.equal(env.runs[0].status,'completed');assert.match(env.roots['report-content'].textContent,/최종 보고서.*후속 원문🙂/);
  assert.equal(env.document.getElementById('interview-save-3').disabled,true);assert.equal(env.roots.btnStartGame.disabled,true);assert.equal(env.roots['report-mock'].disabled,true);
  await env.click('records-open-0');assert.equal(env.navigation.at(-1),'report');assert.equal(env.runs.length,1);
  await env.click('records-delete-0');assert.equal(env.runs.length,0);assert.equal(env.roots['report-content'].textContent,'');assert.equal(env.roots['interview-saved'].textContent,'');assert.equal(env.roots['game-round-records'].textContent,'');
  assert.equal(env.calls.some(c=>c.body?.mode==='live'),false);
});
