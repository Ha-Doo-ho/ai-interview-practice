// Current HTML tabs + actual interview module; offline DOM/history/transport double.
// This exercises navigation boundaries, not a real browser or accessibility audit.
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const {webcrypto}=require('node:crypto');
const C=require('../html/client.js');
const clone=value=>JSON.parse(JSON.stringify(value));
const flush=async()=>{for(let i=0;i<10;i++)await new Promise(resolve=>setImmediate(resolve));};
class Element {
  constructor(tag='div') {
    this.tagName=tag;this.children=[];this.events={};this.attrs={};this.value='';this.disabled=false;
    this.hidden=false;this.style={};this.dataset={};this._text='';
    const classes=new Set();this.classList={add:value=>classes.add(value),remove:value=>classes.delete(value),contains:value=>classes.has(value)};
  }
  set textContent(value){this._text=String(value);this.children=[];}
  get textContent(){return this._text+this.children.map(child=>child.textContent).join('');}
  append(...nodes){this.children.push(...nodes);}
  appendChild(node){this.append(node);return node;}
  replaceChildren(...nodes){this._text='';this.children=nodes;}
  setAttribute(key,value){this.attrs[key]=String(value);if(key==='id')this.id=String(value);}
  addEventListener(type,fn){(this.events[type]||=[]).push(fn);}
  async fire(type){for(const fn of this.events[type]||[])await fn({target:this,preventDefault(){}});await flush();}
  querySelectorAll(selector){return this.children.flatMap(child=>[...(selector.split(',').map(x=>x.trim()).includes(child.tagName)?[child]:[]),...child.querySelectorAll(selector)]);}
  querySelector(selector){return this.querySelectorAll(selector)[0]||null;}
  focus(){}
}

async function setup({hash='#/interview',storage=new Map(),handler}={}) {
  const html=fs.readFileSync('html/index.html','utf8');
  const roots=Object.fromEntries([...html.matchAll(/id="([^"]+)"/g)].map(match=>[match[1],new Element()]));
  const tabs=['survey','game','interview','report','records','guide'];
  const nav=tabs.map(()=>new Element('button'));roots['view-survey'].classList.add('active');nav[0].classList.add('active');
  const docEvents={},winEvents={},calls=[],gameNavigation=[];
  const find=(node,id)=>node.id===id?node:node.children.map(child=>find(child,id)).find(Boolean);
  const document={getElementById:id=>roots[id]||Object.values(roots).map(node=>find(node,id)).find(Boolean),createElement:tag=>new Element(tag),
    querySelectorAll:selector=>selector==='.tab-view'?tabs.map(tab=>roots['view-'+tab]):selector==='.nav-tab-btn'?nav:[],
    addEventListener(type,fn){(docEvents[type]||=[]).push(fn);}};
  const location={hash};const entries=[hash];let position=0;
  const emit=async type=>{for(const fn of winEvents[type]||[])await fn();await flush();};
  const history={
    replaceState(_state,_title,url){location.hash=url;entries[position]=url;},
    pushState(_state,_title,url){location.hash=url;entries.splice(position+1);entries.push(url);position++;},
    async back(){if(position===0)return;location.hash=entries[--position];await emit('popstate');await emit('hashchange');},
    async forward(){if(position===entries.length-1)return;location.hash=entries[++position];await emit('popstate');await emit('hashchange');}
  };
  let run={run_id:'navigation-run',user_id:'navigation-owner',revision:1,status:'in_progress',records:[],questions:[{question_id:'q1',question_version:'1.0.0',question_mode:'baseline',conditioned_on_prior_evidence:false,question_text:'합성 면접 질문'}]};
  let listener;
  let scope={user:{user_id:run.user_id},run:clone(run),authStatus:'authenticated',ready:true,busy:false,locked:false,gameLocked:false,reportLocked:false,interviewLocked:false};
  const transport=async(url,options)=>{
    const call={path:url.slice(4),method:options.method,body:options.body?JSON.parse(options.body):undefined};calls.push(call);
    const override=handler&&await handler(call);if(override)return override;
    if(call.path==='/runs/navigation-run'&&call.method==='GET')return Response.json(run);
    if(call.path==='/runs/navigation-run/answers'&&call.method==='POST'){
      assert.equal(call.body.expected_revision,run.revision);
      run.records.push({source_type:'typed_answer',data:{question_id:'q1',question_version:'1.0.0',answer_id:'saved-answer',answer_version:'1.0.0',status:call.body.status,text:call.body.text}});
      run.revision++;return Response.json(run);
    }
    throw Error('Unexpected request '+call.path);
  };
  const bridge={active:()=>true,subscribe(fn){listener=fn;fn(clone(scope));},
    updateRun(value){assert.equal(value.run_id,scope.run.run_id);scope.run=clone(value);listener(clone(scope));return true;},
    setInterviewLock(value){scope.interviewLocked=value.locked;},invalidateRun(){scope.run=null;listener(clone(scope));}};
  const sessionStorage={getItem:key=>storage.get(key)||null,setItem:(key,value)=>storage.set(key,value),removeItem:key=>storage.delete(key)};
  const window={location,history,AstraPractice:bridge,AstraGames:{onNavigation:tab=>gameNavigation.push(tab)},AstraClient:{...C,createApi:()=>C.createApi(transport)},sessionStorage,addEventListener(type,fn){(winEvents[type]||=[]).push(fn);}};
  const context=vm.createContext({window,document,location,history,crypto:webcrypto,structuredClone,console,performance,localStorage:{getItem:()=>null}});
  for(const file of ['html/script.js','html/interview.js'])vm.runInContext(fs.readFileSync(file,'utf8'),context);
  for(const fn of docEvents.DOMContentLoaded||[])await fn();await flush();
  return {roots,document,context,location,history,calls,storage,gameNavigation,entries,
    active:()=>tabs.find(tab=>roots['view-'+tab].classList.contains('active')),
    run:()=>run,scope:()=>scope,
    async navigate(tab){context.navigateTab(tab);await flush();},
    async hashChange(next){location.hash=next;await emit('hashchange');},
    async input(text){const input=document.getElementById('interview-answer-0');assert.ok(input);input.value=text;await input.fire('input');},
    async save(){await document.getElementById('interview-save-0').fire('click');}
  };
}

test('browser Back and Forward preserve the same unsaved answer and reload restores its tab and draft',async()=>{
  const env=await setup();assert.equal(env.active(),'interview');
  const exact='  미저장 원문 🙂\n둘째 줄  ';
  await env.input(exact);const input=env.document.getElementById('interview-answer-0');
  await env.navigate('report');assert.equal(env.location.hash,'#/report');
  await env.history.back();assert.equal(env.active(),'interview');
  assert.equal(env.document.getElementById('interview-answer-0'),input);assert.equal(input.value,exact);
  await env.history.forward();assert.equal(env.active(),'report');
  assert.equal(env.calls.filter(call=>call.method==='POST').length,0);
  const reloaded=await setup({hash:env.location.hash,storage:env.storage});
  assert.equal(reloaded.active(),'report');await reloaded.navigate('interview');
  assert.equal(reloaded.document.getElementById('interview-answer-0').value,exact);
});

test('navigation hides the previous pane while an interview fetch is delayed and completion cannot switch tabs',async()=>{
  let release;const env=await setup({handler:async call=>{if(call.method==='GET')await new Promise(resolve=>release=resolve);}});
  assert.equal(env.active(),'interview');await env.navigate('guide');
  assert.equal(env.active(),'guide');assert.equal(env.roots['view-interview'].classList.contains('active'),false);
  release();await flush();assert.equal(env.active(),'guide');
  assert.ok(env.document.getElementById('interview-answer-0'));
  assert.equal(env.calls.filter(call=>call.method==='POST').length,0);
});

test('Back during answer save preserves the initiating run and does not duplicate or lose the saved answer',async()=>{
  let release;const env=await setup({hash:'#/survey',handler:async call=>{if(call.method==='POST')await new Promise(resolve=>release=resolve);}});
  await env.navigate('interview');await env.input('저장 중인 원문');
  const saving=env.save();await flush();assert.equal(env.scope().interviewLocked,true);
  await env.history.back();assert.equal(env.active(),'survey');
  assert.equal(env.scope().run.run_id,'navigation-run');
  release();await saving;
  assert.equal(env.active(),'survey');assert.equal(env.run().records.length,1);
  assert.equal(env.run().records[0].data.text,'저장 중인 원문');
  await env.history.forward();assert.equal(env.active(),'interview');
  assert.match(env.roots['interview-progress'].textContent,/1 \/ 1/);
  assert.equal(env.calls.filter(call=>call.method==='POST').length,1);
});

test('invalid tabs fall back safely and a repeated navigation does not add duplicate history or game events',async()=>{
  const env=await setup({hash:'#/not-a-tab'});assert.equal(env.active(),'survey');assert.equal(env.location.hash,'#/survey');
  await env.navigate('game');await env.navigate('game');
  assert.equal(env.entries.length,2);assert.equal(env.gameNavigation.filter(tab=>tab==='game').length,1);
  await env.navigate('does-not-exist');assert.equal(env.active(),'game');assert.equal(env.location.hash,'#/game');
  await env.history.back();assert.equal(env.active(),'survey');
  await env.hashChange('#/report');assert.equal(env.active(),'report');
  await env.hashChange('#/unknown');assert.equal(env.active(),'survey');assert.equal(env.location.hash,'#/survey');
});
