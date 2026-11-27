// Offline synthetic DOM/transport boundary of the real basic interview UI; not a browser.
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const {webcrypto}=require('node:crypto');
const C=require('../html/client.js');
const clone=value=>JSON.parse(JSON.stringify(value));
const flush=async()=>{for(let i=0;i<10;i++)await new Promise(resolve=>setImmediate(resolve));};

class Element {
  constructor(tag='div') { this.tagName=tag;this.children=[];this.events={};this.value='';this.hidden=false;this.disabled=false;this.attrs={};this.dataset={};this.className='';this._text=''; }
  set textContent(value){this._text=String(value);this.children=[];}
  get textContent(){return this._text+this.children.map(child=>child.textContent).join('');}
  append(...children){this.children.push(...children);}
  replaceChildren(...children){this._text='';this.children=children;}
  setAttribute(name,value){this.attrs[name]=String(value);}
  addEventListener(type,fn){(this.events[type]||=[]).push(fn);}
  async fire(type){for(const fn of this.events[type]||[])await fn({target:this,preventDefault(){}});await flush();}
}

const questions=[
  {question_id:'baseline-b01',question_version:'1.0.0',question_text:'다른 사람에게 정보를 구한 경험을 설명해 주세요.',question_mode:'baseline',conditioned_on_prior_evidence:false},
  {question_id:'baseline-b02',question_version:'1.0.0',question_text:'의견 차이를 조율한 경험을 설명해 주세요.',question_mode:'baseline',conditioned_on_prior_evidence:false},
  {question_id:'baseline-b03',question_version:'1.0.0',question_text:'판단을 바꾼 경험을 설명해 주세요.',question_mode:'baseline',conditioned_on_prior_evidence:false},
  {question_id:'followup-hidden',question_version:'1.0.0',question_text:'숨겨야 하는 후속 질문',question_mode:'adaptive_followup',conditioned_on_prior_evidence:true},
];
const baseRun=()=>({run_id:'interview-run',user_id:'interview-user',revision:12,status:'in_progress',questions:clone(questions),records:[]});
const wmQuestions=()=>['요청의 변경과 처리 경험','동시에 기억한 정보','변경과 유지 조건','혼동과 확인','메모와 도구'].map((text,i)=>({
  question_id:'wm-experience-'+i,question_version:'1.0.0',question_text:text,
  question_mode:'supplemental',question_group:'working-memory-interview-v1',
  parent_question_id:i?'wm-experience-0':null,conditioned_on_prior_evidence:false
}));
const workQuestions=()=>['spatial-work','repeated-work'].flatMap(prefix=>Array.from({length:4},(_,i)=>({
  question_id:prefix+'-experience-'+i,question_version:'1.0.0',question_text:prefix+' 업무 질문 '+i,
  question_mode:'supplemental',question_group:prefix+'-interview-v1',
  parent_question_id:i?prefix+'-experience-0':null,conditioned_on_prior_evidence:false
})));
const curatedQuestions=()=>[
  wmQuestions()[0],wmQuestions()[3],workQuestions()[0],
  {...workQuestions()[4],question_id:'repeated-work-experience-v2-0',
    question_group:'repeated-work-interview-v2',question_version:'2.0.0',
    parent_question_id:null,
    question_text:'다음 업무에서는 어떤 방식을 선택했나요? 기존 방식을 유지하거나 바꾸기로 한 기준은 무엇이었나요?'}
];

test('old question 8 is hidden even before a blocked migration can run',async()=>{
  const run=baseRun();run.supplemental_interview_set_version='curated-work-interview-v2';
  run.questions.push(...curatedQuestions(),{...curatedQuestions()[3],question_id:'repeated-work-experience-v2-1',
    question_text:'예상과 실제 결과',parent_question_id:'repeated-work-experience-v2-0'});
  run.records.push({source_type:'typed_answer',data:{question_id:'repeated-work-experience-v2-1',
    answer_id:'old-8',answer_version:'1.0.0',status:'asked_answered',text:'보관된 답변'}});
  const env=await setup({run,gameLocked:true});
  assert.doesNotMatch(env.roots['interview-supplemental'].textContent,/예상과 실제 결과/);
  assert.equal(env.roots['interview-supplemental'].children.length,4);
  assert.match(env.roots['interview-saved'].textContent,/이전 문항 기록 · 예상과 실제 결과.*보관된 답변/);
});

test('current seven fixed questions never offer the retired thirteen-question expansion',async()=>{
  const run=baseRun();run.supplemental_interview_set_version='curated-work-interview-v3';run.questions.push(...curatedQuestions());
  const env=await setup({run});
  assert.equal(env.roots['interview-items'].children.length+env.roots['interview-supplemental'].children.length,7);
  assert.equal(env.roots['interview-supplemental-add'].hidden,true);
  assert.match(env.roots['interview-supplemental'].textContent,/질문 4/);
  assert.match(env.roots['interview-supplemental'].textContent,/질문 7/);
});

test('active sixteen-question legacy run upgrades once before rendering and preserves history',async()=>{
  const run=baseRun();run.questions.push(...wmQuestions(),...workQuestions());
  const env=await setup({run,handler(call,{server}){
    if(call.path.endsWith('/supplemental-interview')){
      server.interview_question_history=[{questions:clone(server.questions)}];
      server.questions=[...clone(questions),...curatedQuestions()];
      server.supplemental_interview_set_version='curated-work-interview-v3';server.revision++;
      return Response.json(server);
    }
  }});
  assert.equal(env.roots['interview-supplemental'].children.length,4);
  assert.equal(env.calls.filter(c=>c.path.endsWith('/supplemental-interview')).length,1);
  await env.click('interview-refresh');
  assert.equal(env.calls.filter(c=>c.path.endsWith('/supplemental-interview')).length,1);
});

test('retired draft and rejected request remain readable without locking current questions or report',async()=>{
  const run=baseRun();run.supplemental_interview_set_version='curated-work-interview-v3';run.questions.push(...curatedQuestions());
  run.interview_question_history=[{questions:wmQuestions()}];
  const storage=new Map([['astra.interview.v1:interview-user:interview-run',JSON.stringify({drafts:{
    'wm-experience-1':{text:'퇴역 문항에 작성 중이던 원문',base_answer_id:null,base_answer_version:null}},
    pending:null,rejected:{question_id:'wm-experience-1',status:'asked_answered'}})]]);
  const env=await setup({run,storage});
  await env.click('interview-resolve');
  assert.equal(env.document.getElementById('interview-answer-0').disabled,false);
  assert.match(env.roots['interview-saved'].textContent,/퇴역 문항에 작성 중이던 원문/);
  assert.equal(env.draftStates.at(-1).count,0);
  assert.match(storage.get('astra.interview.v1:interview-user:interview-run'),/퇴역 문항에 작성 중이던 원문/);
});

test('legacy curation waits for the game mutation lock and resumes when it clears',async()=>{
  const run=baseRun();run.questions.push(...wmQuestions(),...workQuestions());
  const env=await setup({run,gameLocked:true,handler(call,{server}){
    if(call.path.endsWith('/supplemental-interview')){
      server.questions=[...clone(questions),...curatedQuestions()];server.supplemental_interview_set_version='curated-work-interview-v3';server.revision++;
      return Response.json(server);
    }
  }});
  assert.equal(env.calls.filter(c=>c.method==='POST').length,0);
  await env.changeScope({user:{user_id:'interview-user'},run:clone(env.server()),busy:false,locked:false,gameLocked:false,reportLocked:false,authStatus:'authenticated'});
  assert.equal(env.roots['interview-supplemental'].children.length,4);
  assert.equal(env.calls.filter(c=>c.method==='POST').length,1);
});

test('legacy curation reconciles a competing revision once instead of leaving an unusable interview',async()=>{
  const run=baseRun();run.questions.push(...wmQuestions(),...workQuestions());let attempts=0;
  const env=await setup({run,handler(call,{server}){
    if(call.path.endsWith('/supplemental-interview')){
      if(attempts++===0){server.revision++;return Response.json({error:'revision_conflict'},{status:409});}
      assert.equal(call.body.expected_revision,server.revision);
      server.questions=[...clone(questions),...curatedQuestions()];server.supplemental_interview_set_version='curated-work-interview-v3';server.revision++;
      return Response.json(server);
    }
  }});
  assert.equal(attempts,2);
  assert.equal(env.roots['interview-supplemental'].children.length,4);
});

test('own interview lock notifications cannot restart a twice-conflicted curation request',async()=>{
  const run=baseRun();run.questions.push(...wmQuestions(),...workQuestions());let attempts=0;
  const env=await setup({run,gameLocked:true,notifyLocks:true,handler(call,{server}){
    if(call.path.endsWith('/supplemental-interview')){
      if(attempts++<6){server.revision++;return Response.json({error:'revision_conflict'},{status:409});}
      server.questions=[...clone(questions),...curatedQuestions()];server.supplemental_interview_set_version='curated-work-interview-v3';server.revision++;
      return Response.json(server);
    }
  }});
  await env.changeScope({user:{user_id:'interview-user'},run:clone(env.server()),busy:false,locked:false,gameLocked:false,reportLocked:false,interviewLocked:false,authStatus:'authenticated'});
  assert.equal(attempts,2);
  assert.equal(env.document.getElementById('interview-answer-0').disabled,true);
});

test('working-memory-only run upgrades to four work questions and can save and reload',async()=>{
  const run=baseRun();run.questions.push(...wmQuestions());
  const env=await setup({run,handler(call,{server}){
    if(call.path.endsWith('/supplemental-interview')){
      server.interview_question_history=[{questions:clone(server.questions)}];
      server.questions=[...clone(questions),...curatedQuestions()];
      server.supplemental_interview_set_version='curated-work-interview-v3';server.revision++;
      return Response.json(server);
    }
  }});
  assert.equal(env.roots['interview-supplemental'].children.length,4);
  assert.equal(env.roots['interview-supplemental-add'].hidden,true);
  assert.match(env.roots['interview-supplemental'].textContent,/질문 6/);
  assert.match(env.roots['interview-supplemental'].textContent,/질문 7/);
  for(let i=3;i<7;i++){
    await env.input('interview-answer-'+i,'업무 답변 '+i);
    await env.click('interview-save-'+i);
  }
  assert.equal(env.server().records.length,4);
  assert.match(env.roots['interview-progress'].textContent,/0 \/ 3/);
  const restored=await setup({run:env.server()});
  assert.equal(restored.document.getElementById('interview-answer-6').value,'업무 답변 6');
});

test('supplemental questions save separately and remain editable when game linkage is stale',async()=>{
  const run=baseRun();run.questions.push(...curatedQuestions());run.supplemental_interview_set_version='curated-work-interview-v3';run.evidence_linkage_stale=true;
  const env=await setup({run});
  assert.equal(env.roots['interview-supplemental'].children.length,4);
  assert.equal(env.roots['interview-items'].children.length,3);
  assert.match(env.roots['interview-progress'].textContent,/0 \/ 3/);
  for(let i=3;i<7;i++){
    assert.equal(env.document.getElementById('interview-answer-'+i).disabled,false);
    await env.input('interview-answer-'+i,'  개별 응답 '+i+' 🙂\n ');
    await env.click('interview-save-'+i);
  }
  assert.equal(env.server().records.length,4);
  assert.match(env.roots['interview-supplemental-progress'].textContent,/4 \/ 4/);
  assert.match(env.roots['interview-progress'].textContent,/0 \/ 3/);
  const restored=await setup({run:env.server()});
  assert.equal(restored.document.getElementById('interview-answer-6').value,'  개별 응답 6 🙂\n ');
  const completed=await setup({run:{...env.server(),status:'completed'}});
  assert.equal(completed.document.getElementById('interview-answer-3').disabled,true);
});

test('existing runs can add optional questions without replacing baseline answers',async()=>{
  const env=await setup({handler(call,{server}){
    if(call.path.endsWith('/supplemental-interview')){
      server.questions.push(...curatedQuestions());server.supplemental_interview_set_version='curated-work-interview-v3';server.revision++;
      return Response.json(server);
    }
  }});
  await env.click('interview-supplemental-add');
  assert.equal(env.roots['interview-supplemental'].children.length,4);
  assert.equal(env.roots['interview-supplemental-add'].hidden,true);
  assert.equal(env.roots['interview-items'].children.length,3);
});

test('five-game run prevents interview editing until all games are complete',async()=>{
  const run=baseRun();run.flow_version='five-game-v2';run.rule_games={games:{rsp:{rounds:[]},card:{rounds:[]}}};
  run.appointment_games={games:[{type:'day',status:'pending',questions:[]},{type:'place',status:'pending',questions:[]},{type:'bus',status:'pending',questions:[]}]};
  const env=await setup({run});
  assert.match(env.roots['interview-status'].textContent,/여덟 종류의 본게임/);
  assert.equal(env.document.getElementById('interview-answer-0').disabled,true);
});

async function setup({run=baseRun(),storage=new Map(),handler,afterCommit,replays=new Map(),guest=false,storageFails=false,legacyBridge=false,gameLocked=false,notifyLocks=false}={}) {
  const ids=['interview-status','interview-progress','interview-error','interview-refresh','interview-retry','interview-resolve','interview-items','interview-saved','interview-complete','interview-followups','interview-followup-progress','interview-supplemental','interview-supplemental-progress','interview-supplemental-add'];
  const roots=Object.fromEntries(ids.map(id=>[id,new Element(id.includes('retry')||id.includes('refresh')||id.includes('resolve')||id.includes('complete')?'button':'div')]));
  const events={},calls=[],locks=[],draftStates=[];let listener;let server=clone(run);let scope={user:guest?null:{user_id:'interview-user'},run:guest?null:clone(run),ready:!guest,busy:false,locked:false,gameLocked,interviewLocked:false,authStatus:guest?'guest':'authenticated'};
  const find=(node,id)=>node.attrs.id===id?node:node.children.map(child=>find(child,id)).find(Boolean);
  const document={getElementById:id=>roots[id]||Object.values(roots).map(node=>find(node,id)).find(Boolean),createElement:tag=>new Element(tag),addEventListener(type,fn){(events[type]||=[]).push(fn);}};
  const transport=async(url,options)=>{
    const call={path:url.slice(4),method:options.method,body:options.body?JSON.parse(options.body):undefined};calls.push(call);
    const override=handler&&await handler(call,{server});if(override)return override;
    if(call.path==='/runs/interview-run'&&call.method==='GET')return Response.json(server);
    if(call.path==='/runs/interview-run/answers'&&call.method==='POST'){
      const body=call.body;
      if(replays.has(body.idempotency_key))return Response.json(replays.get(body.idempotency_key));
      if(body.expected_revision!==server.revision)return Response.json({error:'revision_conflict'},{status:409});
      const records=server.records.filter(record=>record.source_type==='typed_answer'&&record.data.question_id===body.question_id);
      const replaced=new Set(records.map(record=>record.data.previous_answer_version_ref?.answer_id));
      const latest=records.find(record=>!replaced.has(record.data.answer_id));
      if(latest&&body.replaces_answer_id!==latest.data.answer_id)return Response.json({error:'record_already_submitted'},{status:409});
      if(latest&&body.expected_answer_version!==latest.data.answer_version)return Response.json({error:'answer_version_conflict'},{status:409});
      if(!latest&&body.replaces_answer_id)return Response.json({error:'answer_version_conflict'},{status:409});
      const version=latest?`${Number(latest.data.answer_version.split('.')[0])+1}.0.0`:'1.0.0';
      const answerId=`answer-${server.records.length+1}`;
      server.records.push({record_id:`record-${server.records.length+1}`,source_type:'typed_answer',status:body.status,data:{question_id:body.question_id,answer_id:answerId,answer_version:version,text:body.text,status:body.status,previous_answer_version_ref:latest?{answer_id:latest.data.answer_id,answer_version:latest.data.answer_version}:null}});
      server.revision++;
      replays.set(body.idempotency_key,clone(server));
      if(afterCommit)await afterCommit(call,server);
      return Response.json(server);
    }
    throw Error('Unexpected request '+call.path);
  };
  const bridge={subscribe(fn){listener=fn;fn(clone(scope));},updateRun(value){if(!scope.run||value.run_id!==scope.run.run_id||value.user_id!==scope.user?.user_id||value.revision<scope.run.revision)return false;scope.run=clone(value);listener(clone(scope));return true;},setInterviewLock(value){locks.push(value);scope.interviewLocked=value.locked;},invalidateRun(){scope.run=null;listener(clone(scope));return true;}};
  if(notifyLocks)bridge.setInterviewLock=value=>{locks.push(value);scope.interviewLocked=value.locked;listener(clone(scope));};
  if(legacyBridge)delete bridge.setInterviewLock;
  bridge.setInterviewDraftState=value=>draftStates.push(value);
  const sessionStorage={getItem:key=>storage.get(key)||null,setItem(key,value){if(storageFails)throw Error('quota');storage.set(key,value);},removeItem:key=>storage.delete(key)};
  const window={AstraPractice:bridge,AstraClient:{...C,createApi:()=>C.createApi(transport)},AstraAuth:{recheck(){}},sessionStorage};
  const context=vm.createContext({window,document,crypto:webcrypto,structuredClone,console});
  assert.equal(fs.existsSync('html/interview.js'),true,'html/interview.js must exist');
  vm.runInContext(fs.readFileSync('html/interview.js','utf8'),context);
  for(const fn of events.DOMContentLoaded||[])await fn();await flush();
  return {roots,document,window,context,calls,locks,storage,draftStates,server:()=>server,async click(id){const el=document.getElementById(id);assert.ok(el?.events.click?.length,'Missing control '+id);await el.fire('click');},async input(id,value){const el=document.getElementById(id);assert.ok(el?.events.input?.length,'Missing input '+id);el.value=value;await el.fire('input');},async changeScope(value){scope=value;listener(clone(scope));await flush();}};
}

test('renders only neutral baseline questions and saves exact whitespace/Unicode from server-confirmed response',async()=>{
  const env=await setup();
  assert.equal(env.roots['interview-items'].children.length,3);
  assert.doesNotMatch(env.roots['interview-items'].textContent,/숨겨야 하는/);
  const exact='  동료에게 🐱 정보를 물었습니다.\n둘째 줄  ';
  await env.input('interview-answer-0',exact);await env.click('interview-save-0');
  const post=env.calls.find(call=>call.method==='POST');
  assert.deepEqual(post.body,{question_id:'baseline-b01',text:exact,status:'asked_answered',expected_revision:12,idempotency_key:post.body.idempotency_key});
  assert.equal(env.server().records[0].data.text,exact);
  assert.match(env.roots['interview-progress'].textContent,/1 \/ 3/);
  assert.match(env.roots['interview-saved'].textContent,/동료에게 🐱/);
});

test('active linkage followups show conditioned disclosure and sources separately while preserving baseline count and exact text',async()=>{
  const run=baseRun();const question={question_id:'followup-current',question_version:'1.0.0',question_text:'공개 정보에 대해 구체적인 경험을 설명해 주세요.',question_mode:'adaptive_followup',conditioned_on_prior_evidence:true,disclosed_prior_information:{survey:'매우 그렇다'},generated_from_evidence_refs:[{source_id:'survey-1',source_version:'1.0.0'}]};
  run.questions.push(question);run.evidence_linkage={questions:[clone(question)]};
  const env=await setup({run});
  assert.equal(env.roots['interview-items'].children.length,3);
  assert.match(env.roots['interview-followups'].textContent,/조건부.*공개 정보.*매우 그렇다.*survey-1/);
  assert.doesNotMatch(env.roots['interview-followups'].textContent,/숨겨야 하는/);
  const exact='  추가 경험🙂\n  ';
  await env.input('interview-answer-3',exact);await env.click('interview-save-3');
  assert.equal(env.calls.find(c=>c.method==='POST').body.text,exact);assert.equal(env.calls.find(c=>c.method==='POST').body.question_id,'followup-current');
  assert.match(env.roots['interview-progress'].textContent,/0 \/ 3/);
  assert.match(env.roots['interview-followup-progress'].textContent,/1 \/ 1/);
  const final=clone(env.server());final.status='completed';const readonly=await setup({run:final});assert.equal(readonly.document.getElementById('interview-save-3').disabled,true);
});

test('conditioned followup response loss retries the identical question/body and optional explicit absence never changes baseline progress',async()=>{
  const run=baseRun();const question={question_id:'followup-current',question_version:'1.0.0',question_text:'추가 경험',question_mode:'adaptive_followup',conditioned_on_prior_evidence:true,disclosed_prior_information:'사전 설문 응답',generated_from_evidence_refs:['s1@1']};run.questions.push(question);run.evidence_linkage={questions:[question]};
  let lose=true;const env=await setup({run,afterCommit:()=>{if(lose){lose=false;throw Error('lost');}}});
  await env.click('interview-empty-3');const original=env.calls.find(c=>c.method==='POST').body;
  await env.click('interview-retry');assert.deepEqual(env.calls.filter(c=>c.method==='POST')[1].body,original);
  assert.equal(env.server().records.length,1);assert.equal(env.server().records[0].data.status,'asked_no_text');assert.match(env.roots['interview-progress'].textContent,/0 \/ 3/);
});

test('skip and explicit no-text remain distinct and never discard a nonblank draft',async()=>{
  const env=await setup();
  await env.input('interview-answer-0','보존할 초안');
  assert.equal(env.document.getElementById('interview-skip-0').disabled,true);
  assert.equal(env.document.getElementById('interview-empty-0').disabled,true);
  await env.input('interview-answer-0','');await env.click('interview-skip-0');await env.click('interview-empty-1');
  const posts=env.calls.filter(call=>call.method==='POST');
  assert.deepEqual(posts.map(call=>[call.body.question_id,call.body.status,call.body.text]),[['baseline-b01','skipped',''],['baseline-b02','asked_no_text','']]);
  assert.match(env.roots['interview-saved'].textContent,/건너뜀/);
  assert.match(env.roots['interview-saved'].textContent,/답변 없음/);
});

test('correction references the immutable latest answer and completed runs are read-only',async()=>{
  const initial=baseRun();initial.records.push({record_id:'r1',source_type:'typed_answer',status:'asked_answered',data:{question_id:'baseline-b01',answer_id:'old',answer_version:'1.0.0',text:'원래 답변',status:'asked_answered',previous_answer_version_ref:null}});initial.revision=13;
  const env=await setup({run:initial});assert.equal(env.document.getElementById('interview-answer-0').value,'원래 답변');
  await env.input('interview-answer-0','수정 답변');await env.click('interview-save-0');
  const body=env.calls.find(call=>call.method==='POST').body;
  assert.equal(body.replaces_answer_id,'old');assert.equal(body.expected_answer_version,'1.0.0');
  const completed=clone(env.server());completed.status='completed';
  const readonly=await setup({run:completed});assert.equal(readonly.document.getElementById('interview-answer-0').disabled,true);assert.equal(readonly.document.getElementById('interview-save-0').disabled,true);
});

test('failed request retains exact draft and does not display premature saved success',async()=>{
  const env=await setup({handler:call=>call.method==='POST'?Promise.reject(Error('offline')):undefined});
  await env.input('interview-answer-0','  연결 실패 초안\n');await env.click('interview-save-0');
  assert.equal(env.document.getElementById('interview-answer-0').value,'  연결 실패 초안\n');
  assert.match(env.roots['interview-progress'].textContent,/0 \/ 3/);
  assert.equal(env.roots['interview-retry'].hidden,false);
  assert.equal(env.locks.at(-1).locked,true);
});

test('post-commit response loss retries frozen body/key then reads current state without duplicating answer',async()=>{
  const storage=new Map(),replays=new Map();let lose=true;
  const first=await setup({storage,replays,afterCommit:call=>{if(lose&&call.method==='POST'){lose=false;throw Error('lost after commit');}}});
  await first.input('interview-answer-0','응답 유실 초안');await first.click('interview-save-0');
  const original=first.calls.find(call=>call.method==='POST').body;
  const restored=await setup({run:clone(first.server()),storage,replays});await restored.click('interview-retry');
  assert.deepEqual(restored.calls.find(call=>call.method==='POST').body,original);
  assert.equal(restored.calls.at(-1).method,'GET');
  assert.equal(restored.server().records.length,1);
  assert.match(restored.roots['interview-progress'].textContent,/1 \/ 3/);
});

test('revision or answer conflict preserves local draft and requires explicit rebase before correction',async()=>{
  const initial=baseRun();initial.records.push({record_id:'r1',source_type:'typed_answer',status:'asked_answered',data:{question_id:'baseline-b01',answer_id:'old',answer_version:'1.0.0',text:'서버 원본',status:'asked_answered',previous_answer_version_ref:null}});initial.revision=13;
  let conflicted=false;
  const env=await setup({run:initial,handler:(call,{server})=>{
    if(call.method==='POST'&&!conflicted){conflicted=true;server.records.push({record_id:'r2',source_type:'typed_answer',status:'asked_answered',data:{question_id:'baseline-b01',answer_id:'other',answer_version:'2.0.0',text:'다른 화면 수정',status:'asked_answered',previous_answer_version_ref:{answer_id:'old',answer_version:'1.0.0'}}});server.revision++;return Response.json({error:'answer_version_conflict'},{status:409});}
  }});
  await env.input('interview-answer-0','내 보존 초안');await env.click('interview-save-0');
  assert.equal(env.document.getElementById('interview-answer-0').value,'내 보존 초안');
  assert.match(env.roots['interview-saved'].textContent,/다른 화면 수정/);
  assert.equal(env.roots['interview-resolve'].hidden,false);
  assert.equal(env.calls.filter(call=>call.method==='POST').length,1,'No automatic rebase');
  await env.click('interview-resolve');
  assert.equal(env.calls.filter(call=>call.method==='POST').length,1,'Explicit resolution unlocks editing but does not submit');
  await env.click('interview-save-0');
  const posts=env.calls.filter(call=>call.method==='POST');assert.equal(posts.length,2);
  assert.equal(posts[1].body.replaces_answer_id,'other');assert.equal(posts[1].body.expected_answer_version,'2.0.0');
  assert.equal(env.server().records.length,3);
});

test('definitive validation rejection reconciles, preserves draft and allows an edited new request',async()=>{
  let reject=true;
  const env=await setup({handler:call=>{
    if(call.method==='POST'&&reject){reject=false;return Response.json({error:'validation_error'},{status:422});}
  }});
  await env.input('interview-answer-0','거절된 초안');await env.click('interview-save-0');
  assert.equal(env.document.getElementById('interview-answer-0').value,'거절된 초안');
  assert.equal(env.roots['interview-retry'].hidden,true);
  assert.equal(env.roots['interview-resolve'].hidden,true);
  assert.match(env.roots['interview-progress'].textContent,/0 \/ 3/);
  await env.input('interview-answer-0','수정한 새 초안');await env.click('interview-save-0');
  const posts=env.calls.filter(call=>call.method==='POST');assert.equal(posts.length,2);
  assert.notEqual(posts[0].body.idempotency_key,posts[1].body.idempotency_key);
  assert.equal(env.server().records[0].data.text,'수정한 새 초안');
});

test('offline initial load can recover through refresh',async()=>{
  let offline=true;
  const env=await setup({handler:call=>call.method==='GET'&&offline?Promise.reject(Error('offline')):undefined});
  assert.equal(env.roots['interview-refresh'].disabled,false);
  assert.match(env.roots['interview-status'].textContent,/불러오지 못했습니다/);
  assert.match(env.roots['interview-error'].textContent,/저장된 면접 다시 불러오기/);
  assert.equal(env.roots['interview-retry'].hidden,true);
  offline=false;await env.click('interview-refresh');
  assert.equal(env.roots['interview-items'].children.length,3);
});

test('an older cached practice module shows a refresh instruction instead of throwing during interview startup',async()=>{
  const env=await setup({legacyBridge:true});
  assert.match(env.roots['interview-status'].textContent,/불러오지 못했습니다/);
  assert.match(env.roots['interview-error'].textContent,/Ctrl\s*\+\s*F5/);
  assert.equal(env.roots['interview-refresh'].disabled,true);
  assert.equal(env.calls.length,0,'Do not read or write answers through an incompatible bridge');
});

test('late private response after logout cannot repopulate UI; confirmed guest clears journal',async()=>{
  let resolve;
  const env=await setup({handler:call=>call.method==='POST'?new Promise(done=>{resolve=done;}):undefined});
  await env.input('interview-answer-0','개인 초안');const saving=env.click('interview-save-0');await flush();
  await env.changeScope({user:null,run:null,ready:false,busy:false,locked:false,gameLocked:false,interviewLocked:false,authStatus:'guest'});
  resolve(Response.json(baseRun()));await saving;
  assert.equal(env.roots['interview-items'].textContent,'');assert.doesNotMatch(env.roots['interview-status'].textContent,/interview-run/);assert.equal(env.storage.size,0);
});

test('deleted run invalidates scope; storage failure blocks writes; bridge lock follows pending work',async()=>{
  let deleted=false;
  const env=await setup({handler:call=>deleted&&call.method==='GET'?Response.json({error:'not_found'},{status:404}):undefined});
  deleted=true;await env.click('interview-refresh');assert.equal(env.roots['interview-items'].textContent,'');
  const unavailable=await setup({storageFails:true});
  assert.equal(unavailable.document.getElementById('interview-save-0').disabled,true);
  assert.equal(unavailable.calls.filter(call=>call.method==='POST').length,0);
  assert.equal(unavailable.locks.at(-1).locked,false);
  assert.match(unavailable.roots['interview-error'].textContent,/임시 저장 공간/);
});

test('other active survey/game work gates interview writes without hiding saved evidence',async()=>{
  const initial=baseRun();initial.records.push({record_id:'r1',source_type:'typed_answer',status:'asked_answered',data:{question_id:'baseline-b01',answer_id:'old',answer_version:'1.0.0',text:'이미 저장됨',status:'asked_answered',previous_answer_version_ref:null}});
  const env=await setup({run:initial});
  await env.changeScope({user:{user_id:'interview-user'},run:clone(initial),ready:true,busy:false,locked:false,gameLocked:true,interviewLocked:false,authStatus:'authenticated'});
  assert.match(env.roots['interview-saved'].textContent,/이미 저장됨/);
  assert.equal(env.document.getElementById('interview-save-0').disabled,true);
});

test('saved history preserves the question snapshot and completion text uses the actual baseline total',async()=>{
  const initial=baseRun();initial.questions=initial.questions.slice(0,2);
  initial.records.push({record_id:'r1',source_type:'typed_answer',status:'asked_answered',data:{question_id:'baseline-b01',question_text_snapshot:'당시 제시된 질문 원문',answer_id:'old',answer_version:'1.0.0',text:'첫 답변',status:'asked_answered',previous_answer_version_ref:null}});
  initial.records.push({record_id:'r2',source_type:'typed_answer',status:'skipped',data:{question_id:'baseline-b02',question_text_snapshot:'당시 두 번째 질문',answer_id:'skip',answer_version:'1.0.0',text:'',status:'skipped',previous_answer_version_ref:null}});
  const env=await setup({run:initial});
  assert.match(env.roots['interview-saved'].textContent,/당시 제시된 질문 원문/);
  assert.equal(env.roots['interview-complete'].textContent,'기본 면접 2문항이 모두 서버에 저장되었습니다.');
});
