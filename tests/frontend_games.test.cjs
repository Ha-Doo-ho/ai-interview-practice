// Offline synthetic DOM/transport boundary of the real game UI; not a browser.
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const {webcrypto}=require('node:crypto');
const C=require('../html/client.js');
const clone=x=>JSON.parse(JSON.stringify(x));
const flush=async()=>{for(let i=0;i<8;i++)await new Promise(r=>setImmediate(r));};
class Element {
  constructor(tag='div'){this.tagName=tag;this.children=[];this.events={};this.value='';this.hidden=false;this.disabled=false;this.attrs={};this.style={};this.dataset={};this._text='';const classes=new Set();this.classList={toggle:(name,on)=>on?classes.add(name):classes.delete(name),contains:name=>classes.has(name),add:name=>classes.add(name),remove:name=>classes.delete(name)};}
  set textContent(v){this._text=String(v);this.children=[];}
  get textContent(){return this._text+this.children.map(x=>x.textContent).join('');}
  append(...nodes){this.children.push(...nodes);}
  replaceChildren(...nodes){this._text='';this.children=nodes;}
  setAttribute(k,v){this.attrs[k]=String(v);}
  addEventListener(t,f){(this.events[t]||=[]).push(f);}
  focus(){this.focused=true;}
  async fire(t){for(const f of this.events[t]||[])await f({target:this,preventDefault(){}});await flush();}
}
const baseRun=()=>({run_id:'game-run',user_id:'game-user',revision:6,status:'in_progress',records:['O-B01','O-B02','O-B03','P-B01','S-B02','R-UNMAPPED'].map(item_id=>({item_id,source_type:'survey',status:'submitted'}))});
const definition={version:'1.0.0',rounds_per_game:3,duration_ms:20000,reveal_after_ms:10000,games:{rsp:{title:'가위바위보 판단 게임'},card:{title:'카드 규칙 게임'}}};

test('five work-survey visits unlock games without asking for legacy preference items',async()=>{
  const run=baseRun();run.survey_set_version='work-behavior-v2';
  run.survey_definition_snapshot=clone(require('./fixtures/work_survey_definitions.json'));
  run.records=run.survey_definition_snapshot.map(q=>({item_id:q.item_id,source_type:'survey',status:'skipped'}));
  const env=await setup({run});
  assert.equal(env.roots.btnStartGame.disabled,false);
  await env.click('btnStartGame');
  assert.equal(env.calls.filter(c=>c.body?.action==='start').length,1);
  const incomplete=clone(run);incomplete.records.pop();
  const blocked=await setup({run:incomplete});assert.equal(blocked.roots.btnStartGame.disabled,true);
  assert.match(blocked.roots['game-status'].textContent,/5문항/);
});
test('completed rule games leave space for the appointment games in new runs',async()=>{
  const run=baseRun();run.flow_version='five-game-v2';
  run.rule_games={games:{rsp:{rounds:Array.from({length:3},()=>({status:'completed',events:[],stimulus:{},rule:{label:'완료'}}))},card:{rounds:Array.from({length:3},()=>({status:'completed',events:[],stimulus:{},rule:{label:'완료'}}))}}};
  const env=await setup({run});assert.equal(env.roots['rule-game-panel'].hidden,true);
});
test('after rock paper scissors the unfinished card game is shown in new runs',async()=>{
  const run=baseRun();run.flow_version='five-game-v2';
  run.rule_games={games:{rsp:{rounds:Array.from({length:3},()=>({status:'completed',events:[],stimulus:{},rule:{label:'완료'}}))},card:{rounds:[]}}};
  const env=await setup({run});assert.equal(env.roots['game-tab-rsp'].hidden,true);assert.equal(env.roots['gameUI-card'].style.display,'block');
});
async function setup({run=baseRun(),storage=new Map(),handler,afterCommit,replays=new Map(),guest=false,serverTime=100000}={}){
  const roots=Object.fromEntries([...fs.readFileSync('html/index.html','utf8').matchAll(/id="([^"]+)"/g)].map(m=>[m[1],new Element()]));
  const events={},winEvents={},calls=[],locks=[],nav=[],timers=new Set();let listener,now=0,server=clone(run),lost=false;
  let scope={user:guest?null:{user_id:'game-user'},run:guest?null:clone(run),ready:!guest,busy:false,locked:false};
  const find=(node,id)=>node.id===id?node:node.children.map(n=>find(n,id)).find(Boolean);
  const document={visibilityState:'visible',getElementById:id=>roots[id]||Object.values(roots).map(n=>find(n,id)).find(Boolean),createElement:tag=>new Element(tag),addEventListener(t,f){(events[t]||=[]).push(f);}};
  const current=type=>server.rule_games?.games[type]?.rounds.at(-1);
  const stamp=()=>new Date(serverTime+now).toISOString();
  const transport=async(url,opts)=>{
    const call={path:url.slice(4),method:opts.method,body:opts.body?JSON.parse(opts.body):undefined};calls.push(call);
    const override=handler&&await handler(call,{server,now,stamp});if(override)return override;
    if(call.path==='/rule-game-definitions')return Response.json(definition);
    if(call.path==='/runs/game-run/rule-games'&&call.method==='GET')return Response.json({run:server,server_time:stamp()});
    if(call.path==='/runs/game-run/rule-games'&&call.method==='POST'){
      const b=call.body;
      if(replays.has(b.idempotency_key))return Response.json(replays.get(b.idempotency_key));
      server.rule_games||={version:'1.0.0',mapping_status:'unmapped',games:{rsp:{rounds:[]},card:{rounds:[]}}};
      if(b.action==='start'){
        const rounds=server.rule_games.games[b.game_type].rounds;
        rounds.push({round_id:`${b.game_type}-${rounds.length+1}`,index:rounds.length+1,status:'in_progress',phase:'initial',started_at:stamp(),deadline_at:new Date(serverTime+now+20000).toISOString(),reveal_due_at:new Date(serverTime+now+10000).toISOString(),duration_ms:20000,score:0,correct_count:0,incorrect_count:0,rule:{rule_id:b.game_type+'-initial',label:'초기 규칙'},stimulus:b.game_type==='rsp'?{stimulus_id:'problem-0',opponent_hand:'scissors'}:{stimulus_id:'board-0',cards:[{card_id:'c0',value:2},{card_id:'c1',value:3}],selected_card_ids:[]},events:[{type:'round_started',server_at:stamp(),sequence_no:1}]});
      } else {
        const r=current(b.game_type);
        if(b.action==='answer'){
          const stimulus=clone(r.stimulus),before=r.score;
          const correct=b.game_type==='rsp'||stimulus.cards.find(card=>card.card_id===b.choice).value%2===0;
          r[correct?'correct_count':'incorrect_count']++;r.score=Math.max(0,r.score+(correct?10:-5));
          r.events.push({type:'response_selected',server_at:stamp(),sequence_no:r.events.length+1,choice:b.choice,correct,score_before:before,score_after:r.score,rule:clone(r.rule),stimulus});
          if(b.game_type==='rsp')r.stimulus={stimulus_id:'problem-'+r.correct_count,opponent_hand:'scissors'};
          else r.stimulus.selected_card_ids.push(b.choice);
        } else if(b.action==='reveal') {r.phase='changed';r.revealed_at=stamp();r.rule={rule_id:'changed',label:'변경된 규칙'};r.events.push({type:'rule_revealed',server_at:stamp()});}
        else if(b.action==='finish'){r.status='completed';r.phase='completed';r.completed_at=stamp();r.events.push({type:'round_ended',server_at:stamp()});}
        else if(b.action==='visibility')r.events.push({type:'visibility_reported',hidden:b.hidden,server_at:stamp()});
      }
      server.revision++;replays.set(b.idempotency_key,clone(server));
      if(afterCommit)await afterCommit(call,server);
      return Response.json(server);
    }
    throw Error('Unexpected request '+call.path);
  };
  const bridge={subscribe(fn){listener=fn;fn(clone(scope));},updateRun(value){if(!scope.run||value.run_id!==scope.run.run_id||value.user_id!==scope.user?.user_id||value.revision<scope.run.revision)return false;scope.run=clone(value);listener(clone(scope));return true;},setGameLock(value){locks.push(value);},invalidateRun(){scope.run=null;listener(clone(scope));return true;}};
  const window={AstraPractice:bridge,AstraClient:{...C,createApi:()=>C.createApi(transport)},sessionStorage:{getItem:k=>storage.get(k)||null,setItem:(k,v)=>storage.set(k,v),removeItem:k=>storage.delete(k)},addEventListener(t,f){(winEvents[t]||=[]).push(f);}};
  const context=vm.createContext({window,document,crypto:webcrypto,structuredClone,Date,performance:{now:()=>now},setInterval:f=>{timers.add(f);return f;},clearInterval:f=>timers.delete(f),navigateTab:t=>nav.push(t)});
  if(fs.existsSync('html/games.js'))vm.runInContext(fs.readFileSync('html/games.js','utf8'),context);
  for(const f of events.DOMContentLoaded||[])await f();await flush();
  window.AstraGames.onNavigation('game');await flush();
  return {roots,document,context,calls,locks,storage,nav,server:()=>server,async click(id){const el=document.getElementById(id);assert.ok(el?.events.click?.length,'Missing game control '+id);await el.fire('click');},async tick(ms){now+=ms;for(const f of [...timers])await f();await flush();},async changeScope(value){scope=value;listener(clone(scope));await flush();},async visibility(hidden){document.visibilityState=hidden?'hidden':'visible';for(const f of events.visibilitychange||[])await f();await flush();}};
}
test('games require a real owned run and completed surveys; start posts real revision and no client score',async()=>{
  const guest=await setup({guest:true});assert.equal(guest.roots.btnStartGame.disabled,true);
  const incomplete=baseRun();incomplete.records=[];const blocked=await setup({run:incomplete});assert.equal(blocked.roots.btnStartGame.disabled,true);
  const env=await setup();await env.click('btnStartGame');
  const post=env.calls.find(c=>c.method==='POST');assert.equal(post.path,'/runs/game-run/rule-games');assert.equal(post.body.expected_revision,6);assert.equal(post.body.action,'start');assert.equal(post.body.game_type,'rsp');assert.ok(post.body.idempotency_key);assert.equal('score'in post.body,false);
  assert.match(env.roots['game-status'].textContent,/game-run/);assert.equal(env.roots.oppHand.textContent,'✌️');
});
test('server confirmed RPS selection, rule change, finish and reload show saved facts',async()=>{
  const env=await setup();await env.click('btnStartGame');await env.click('game-choice-rock');
  const answer=env.calls.find(c=>c.body?.action==='answer');assert.equal(answer.body.choice,'rock');assert.equal(answer.body.stimulus_id,'problem-0');assert.equal(answer.body.round_id,'rsp-1');assert.equal(env.roots.gameScore.textContent,'10');
  await env.tick(10000);assert.equal(env.calls.filter(c=>c.body?.action==='reveal').length,1);assert.match(env.roots.rspRuleBadge.textContent,/변경된 규칙/);
  await env.tick(10000);assert.equal(env.calls.filter(c=>c.body?.action==='finish').length,1);
  assert.match(env.roots['game-saved-count'].textContent,/가위바위보 1 \/ 3/);assert.match(env.roots['game-round-records'].textContent,/10점/);
  const restored=await setup({run:clone(env.server()),storage:env.storage,serverTime:130000});assert.match(restored.roots['game-saved-count'].textContent,/가위바위보 1 \/ 3/);assert.equal(restored.calls.filter(c=>c.method==='POST').length,0);
});
test('cards submit stable card IDs and disable a card after one confirmed selection',async()=>{
  const env=await setup();await env.click('game-tab-card');await env.click('btnStartGame');
  const card=env.roots.cardTileGrid.children[0];assert.equal(card.tagName,'button');await card.fire('click');
  assert.equal(env.calls.find(c=>c.body?.action==='answer').body.choice,'c0');assert.equal(env.roots.cardTileGrid.children[0].disabled,true);assert.equal(env.roots.gameScore.textContent,'10');
});
test('incorrect card feedback follows the server event rather than treating every selection as correct',async()=>{
  const env=await setup();await env.click('game-tab-card');await env.click('btnStartGame');
  await env.roots.cardTileGrid.children[1].fire('click');
  const wrong=env.roots.cardTileGrid.children[1];assert.equal(wrong.disabled,true);
  assert.match(wrong.attrs['aria-label'],/오답/);assert.equal(wrong.classList.contains('confirmed-incorrect'),true);
  assert.equal(wrong.classList.contains('confirmed-correct'),false);assert.equal(env.roots.gameScore.textContent,'0');
  await env.roots.cardTileGrid.children[0].fire('click');
  const correct=env.roots.cardTileGrid.children[0];assert.match(correct.attrs['aria-label'],/정답/);
  assert.equal(correct.classList.contains('confirmed-correct'),true);assert.equal(correct.classList.contains('confirmed-incorrect'),false);
});
test('timer refreshes the time text without repeatedly replacing keyboard-focusable cards',async()=>{
  const env=await setup();await env.click('game-tab-card');await env.click('btnStartGame');
  const card=env.roots.cardTileGrid.children[0];card.focus();await env.tick(200);
  assert.equal(env.roots.cardTileGrid.children[0],card);
});
test('offline startup can reconnect and restart its timing loop',async()=>{
  let offline=true;
  const env=await setup({handler:()=>{if(offline)throw Error('synthetic offline');}});
  assert.equal(env.roots['game-refresh'].disabled,false);offline=false;await env.click('game-refresh');await env.click('btnStartGame');await env.tick(20000);
  assert.equal(env.calls.filter(c=>c.body?.action==='finish').length,1);
});
test('uncertain answer is frozen across reload and retried with the same key and payload',async()=>{
  const replays=new Map();
  const env=await setup({replays,afterCommit:c=>{if(c.body?.action==='answer')throw Error('synthetic lost response after commit');}});
  await env.click('btnStartGame');await env.click('game-choice-rock');
  const original=env.calls.find(c=>c.body?.action==='answer').body;
  assert.equal(env.roots['game-retry'].hidden,false);assert.equal(env.roots['game-choice-rock'].disabled,true);
  assert.equal(env.server().rule_games.games.rsp.rounds[0].score,10,'The server committed before the response was lost');
  const restored=await setup({replays,run:clone(env.server()),storage:env.storage,serverTime:105000});await restored.click('game-retry');
  assert.deepEqual(restored.calls.find(c=>c.body?.action==='answer').body,original);assert.equal(restored.roots.gameScore.textContent,'10');
  assert.equal(restored.calls.at(-1).method,'GET','Retry must refresh after a historical idempotent result');
  assert.equal(restored.server().rule_games.games.rsp.rounds[0].events.filter(e=>e.type==='response_selected').length,1);
});
test('late result after switching accounts cannot repopulate a private game',async()=>{
  let resolve;
  const env=await setup({handler:c=>c.body?.action==='start'?new Promise(r=>resolve=r):undefined});
  const inFlight=env.click('btnStartGame');await flush();await env.changeScope({user:null,run:null,ready:false,busy:false,locked:false,authStatus:'guest'});
  resolve(Response.json(baseRun()));await inFlight;
  assert.equal(env.roots['game-round-records'].textContent,'');assert.doesNotMatch(env.roots['game-status'].textContent,/game-run/);assert.equal(env.roots.btnStartGame.disabled,true);
});
test('background transition is saved as a reported visibility fact and score is unchanged',async()=>{
  const env=await setup();await env.click('btnStartGame');await env.visibility(true);
  assert.equal(env.calls.find(c=>c.body?.action==='visibility').body.hidden,true);assert.equal(env.roots.gameScore.textContent,'0');
});
test('hidden and visible transitions during a slow answer are both saved in order',async()=>{
  let release;
  const env=await setup({handler:c=>c.body?.action==='answer'?new Promise(r=>release=r):undefined});
  await env.click('btnStartGame');const answering=env.click('game-choice-rock');await flush();
  await env.visibility(true);await env.visibility(false);release();await answering;
  await env.tick(0);await env.tick(0);
  assert.deepEqual(env.server().rule_games.games.rsp.rounds[0].events.filter(e=>e.type==='visibility_reported').map(e=>e.hidden),[true,false]);
  assert.equal(env.roots.gameScore.textContent,'10');
});
test('queued transitions survive reload while an uncertain answer awaits retry',async()=>{
  const env=await setup({handler:c=>{if(c.body?.action==='answer')throw Error('synthetic loss');}});
  await env.click('btnStartGame');await env.click('game-choice-rock');await env.visibility(true);await env.visibility(false);
  const restored=await setup({run:clone(env.server()),storage:env.storage,serverTime:105000});
  await restored.click('game-retry');await restored.tick(0);await restored.tick(0);
  assert.deepEqual(restored.server().rule_games.games.rsp.rounds[0].events.filter(e=>e.type==='visibility_reported').map(e=>e.hidden),[true,false]);
});
test('moving between other sections does not report leaving the game twice',async()=>{
  const env=await setup();await env.click('btnStartGame');
  await env.context.window.AstraGames.onNavigation('survey');await flush();
  await env.context.window.AstraGames.onNavigation('report');await flush();
  await env.context.window.AstraGames.onNavigation('game');await flush();
  assert.deepEqual(env.server().rule_games.games.rsp.rounds[0].events.filter(e=>e.type==='visibility_reported').map(e=>e.hidden),[true,false]);
});
test('returning to the game section while the document is hidden is not reported as visible',async()=>{
  const env=await setup();await env.click('btnStartGame');await env.visibility(true);
  await env.context.window.AstraGames.onNavigation('survey');await flush();
  await env.context.window.AstraGames.onNavigation('game');await flush();
  assert.deepEqual(env.server().rule_games.games.rsp.rounds[0].events.filter(e=>e.type==='visibility_reported').map(e=>e.hidden),[true]);
  await env.visibility(false);
  assert.deepEqual(env.server().rule_games.games.rsp.rounds[0].events.filter(e=>e.type==='visibility_reported').map(e=>e.hidden),[true,false]);
});
test('confirmed logout clears the pending journal; temporary auth checking preserves it',async()=>{
  const env=await setup({handler:c=>{if(c.body?.action==='answer')throw Error('synthetic loss');}});await env.click('btnStartGame');await env.click('game-choice-rock');
  assert.ok(env.storage.size);await env.changeScope({user:null,run:null,ready:false,busy:false,locked:false,authStatus:'checking'});assert.ok(env.storage.size);
  await env.changeScope({user:null,run:null,ready:false,busy:false,locked:false,authStatus:'guest'});assert.equal(env.storage.size,0);
});
test('deleted run invalidates the selected context and removes private game history',async()=>{
  let removed=false;
  const env=await setup({handler:c=>removed&&c.path.includes('/runs/')?Response.json({error:'not_found'},{status:404}):undefined});
  await env.click('btnStartGame');assert.ok(env.roots['game-round-records'].textContent);removed=true;await env.click('game-refresh');
  assert.equal(env.roots['game-round-records'].textContent,'');assert.equal(env.roots.btnStartGame.disabled,true);assert.doesNotMatch(env.roots['game-status'].textContent,/game-run/);
});
