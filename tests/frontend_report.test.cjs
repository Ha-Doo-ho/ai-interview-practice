// Offline synthetic DOM/transport boundary of the real integrated report UI; no browser or live AI.
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const {webcrypto}=require('node:crypto');
const C=require('../html/client.js');
function completeGameStages(run){
  run.rule_games={games:Object.fromEntries(['rsp','card'].map(k=>[k,{rounds:Array.from({length:3},()=>({status:'completed'}))}]))};
  run.appointment_games={games:['day','place','bus'].map(type=>({type,status:'complete',questions:Array.from({length:10},()=>({}))}))};
  run.aptitude_games={attempts:['rotation','path','potion'].map(type=>({type,mode:'main',status:'complete'}))};
}
test('partial eight-game runs hide cached report and all result controls',async()=>{
  const run=runWithReport();run.flow_version='five-game-v2';
  const env=await setup({run});
  assert.doesNotMatch(env.roots['report-content'].textContent,/report-1|저장 근거 보고서/);
  assert.match(env.roots['report-content'].textContent,/8종|8개/);
  for(const id of ['report-mock','report-analyze','report-synthesis-prompt','report-synthesis-mock','report-finalize'])assert.equal(env.roots[id].disabled,true,id);
  await env.click('report-synthesis-prompt');
  assert.equal(env.calls.filter(c=>c.path.endsWith('/synthesis-prompt')).length,0);
});
const clone=value=>JSON.parse(JSON.stringify(value));
const flush=async()=>{for(let i=0;i<12;i++)await new Promise(resolve=>setImmediate(resolve));};

class Element {
  constructor(tag='div'){this.tagName=tag;this.children=[];this.events={};this.hidden=false;this.disabled=false;this.attrs={};this.className='';this._text='';}
  set textContent(value){this._text=String(value);this.children=[];}
  get textContent(){return this._text+this.children.map(child=>child.textContent).join('');}
  set innerHTML(_){throw Error('report UI must not use innerHTML');}
  append(...children){this.children.push(...children);}
  replaceChildren(...children){this._text='';this.children=children;}
  setAttribute(name,value){this.attrs[name]=String(value);}
  addEventListener(type,fn){(this.events[type]||=[]).push(fn);}
  async fire(type){for(const fn of this.events[type]||[])await fn({target:this,preventDefault(){}});await flush();}
}

const criteria=['situation','role','other_information','action','reasoning','result','learning'];
const answerText='앞🙂행동 뒤 <script>globalThis.pwned=true</script>';

test('survey nonresponse reasons remain visible without an agreement position',async()=>{
  const run=runWithReport();
  run.interview_report.surveys=['no_experience','unsure'].map((reason,i)=>({
    item_id:'new-'+i,item_version:'1.0.0',record_id:'nonresponse-'+i,record_version:'1.0.0',source_version:'1.0.0',status:'skipped',
    data:{definition_snapshot:{type:'ordinal_6'},prompt_snapshot:'업무 행동',nonresponse_reason:reason,
      nonresponse_label_snapshot:i===0?'해당 경험 없음':'판단하기 어려움'}}));
  const env=await setup({run});
  assert.match(env.roots['report-content'].textContent,/해당 경험 없음/);
  assert.match(env.roots['report-content'].textContent,/판단하기 어려움/);
});
test('supplemental self-reports show saved answers and frozen final versions without AI attribution',async()=>{
  const run=runWithReport();
  run.questions.push({question_id:'wm-experience-0',question_text:'요청 변경 경험',
    question_mode:'supplemental',question_group:'working-memory-interview-v1'});
  run.records.push({source_type:'typed_answer',data:{question_id:'wm-experience-0',answer_id:'wm-a',
    answer_version:'1.0.0',text:'<script>작업기억 답변</script>',status:'asked_answered'}});
  for(const prefix of ['spatial-work','repeated-work']){
    run.questions.push({question_id:prefix+'-experience-0',question_text:prefix+' 경험',
      question_mode:'supplemental',question_group:prefix+'-interview-v1'});
    run.records.push({source_type:'typed_answer',data:{question_id:prefix+'-experience-0',answer_id:prefix,
      answer_version:'1.0.0',text:prefix+' 저장 원문',status:'asked_answered'}});
  }
  const preview=await setup({run});
  assert.match(preview.roots['report-content'].textContent,/<script>작업기억 답변<\/script>/);
  assert.match(preview.roots['report-content'].textContent,/spatial-work 저장 원문/);
  assert.match(preview.roots['report-content'].textContent,/repeated-work 저장 원문/);
  assert.match(preview.roots['report-content'].textContent,/능력 점수/);
  run.status='completed';
  run.report={...clone(run.interview_report),status:'finalized',
    supplemental_answers:[{question_id:'wm-experience-0',question_text:'확정된 질문',status:'asked_answered',text:'확정된 답변'},
      {question_id:'wm-experience-1',question_text:'미응답 질문',status:'not_answered',text:''}]};
  const final=await setup({run});
  assert.match(final.roots['report-content'].textContent,/확정된 답변/);
  assert.match(final.roots['report-content'].textContent,/미응답/);
  assert.doesNotMatch(final.roots['report-content'].textContent,/<script>작업기억 답변/);
  assert.doesNotMatch(final.roots['report-content'].textContent,/spatial-work 저장 원문|repeated-work 저장 원문/);
});
test('feedback uses verified evidence and gives clearly labelled practice without a new AI request',async()=>{
  const run=runWithReport();
  const env=await setup({run}); const text=env.roots['report-content'].textContent;
  assert.match(text,/잘 드러난 부분/);assert.match(text,/행동.*배움/);
  assert.match(text,/보완할 부분/);assert.match(text,/다음 연습 제안/);
  assert.match(text,/정해진 안내/);
  assert.equal(env.calls.filter(c=>c.method==='POST').length,0);
});
test('unverified or missing answers do not become strengths',async()=>{
  const run=runWithReport();const card=run.interview_report.cards[0];
  card.criteria.action.evidence_spans[0].quote='조작된 문장';
  card.criteria.learning.evidence_spans=[];
  const env=await setup({run});const text=env.roots['report-content'].textContent;
  assert.match(text,/확인된 인용이 없어 잘 드러난 부분을 제시할 수 없습니다/);
  assert.doesNotMatch(text,/조작된 문장/);
});
test('an answer with every element present still receives a neutral practice exercise',async()=>{
  const run=runWithReport();const card=run.interview_report.cards[0];
  for(const name of criteria){card.criteria[name].status='explicit';card.criteria[name].evidence_spans=[{source_id:'answer-current',source_version:'2.0.0',start:1,end:4,quote:'🙂행동',offset_unit:'unicode_code_point'}];}
  card.practice_suggestions=[];
  const env=await setup({run});const text=env.roots['report-content'].textContent;
  assert.match(text,/각 항목이 답변에서 확인되었습니다/);
  assert.match(text,/행동과 결과를 연결해 짧게 다시 말해 보세요/);
});
test('Gemini authentication errors are explained without exposing provider details',async()=>{
  const env=await setup({handler:call=>call.method==='POST'?Response.json({error:'gemini_auth_failed'},{status:422}):undefined});
  await env.click('report-analyze');
  assert.match(env.roots['report-error'].textContent,/키.*인증/);
});
test('Gemini HTTP 400 does not falsely claim a proven request format error',async()=>{
  const env=await setup({handler:call=>call.method==='POST'?Response.json({error:'gemini_request_invalid'},{status:422}):undefined});
  await env.click('report-analyze');
  assert.match(env.roots['report-error'].textContent,/원인을 확인/);
  assert.doesNotMatch(env.roots['report-error'].textContent,/형식을 거절했습니다/);
});
test('Gemini server error shows the safe status code',async()=>{
  const env=await setup({handler:call=>call.method==='POST'?Response.json({error:'gemini_http_503'},{status:422}):undefined});
  await env.click('report-analyze');
  assert.match(env.roots['report-error'].textContent,/HTTP 503/);
});
test('each practice suggestion is visible while shared provenance is shown once',async()=>{
  const run=runWithReport();
  run.interview_report.cards[0].practice_suggestions=[
    {text:'상황을 설명해 보세요.',template_version:'v1',basis_refs:['answer-current@2.0.0']},
    {text:'역할을 설명해 보세요.',template_version:'v1',basis_refs:['answer-current@2.0.0']},
    {text:'결과를 설명해 보세요.',template_version:'v2',basis_refs:['answer-other@1.0.0']}];
  const env=await setup({run});const text=env.roots['report-content'].textContent;
  assert.match(text,/상황을 설명해 보세요/);assert.match(text,/역할을 설명해 보세요/);assert.match(text,/결과를 설명해 보세요/);
  assert.equal((text.match(/제안 버전: v1/g)||[]).length,1);
  assert.equal((text.match(/근거 참조: answer-current@2.0.0/g)||[]).length,1);
  assert.match(text,/제안 버전: v2/);assert.match(text,/근거 참조: answer-other@1.0.0/);
});
test('synthesis preview is read only and AI is explicit with source details and stale handling',async()=>{
  const run=runWithReport();run.flow_version='five-game-v2';completeGameStages(run);run.interview_report.five_games={games:[]};
  const prompt={prompt_text:'<script>원척도와 전체 답변</script>',evidence:[{id:'interview:a',text:'실제 원문'}]};
  const result={provider_execution:'test_double',report:{prompt,feedback:{strengths:[{text:'기록된 행동',evidence_ids:['interview:a']}],gaps:[],practice_plan:[],clarifying_questions:[]}}};
  const env=await setup({run,handler:call=>call.path.endsWith('/synthesis-prompt')?Response.json(prompt):call.path.endsWith('/synthesis-analysis')?Response.json({...run,revision:21,synthesis_analysis:result}):undefined});
  assert.equal(env.calls.filter(c=>c.method==='POST').length,0);
  await env.click('report-synthesis-prompt');
  assert.equal(env.roots['report-synthesis-preview'].children[1].value,prompt.prompt_text);
  assert.equal(env.calls.filter(c=>c.method==='POST').length,0);
  await env.click('report-synthesis-ai');
  const posted=env.calls.find(c=>c.method==='POST');
  assert.equal(posted.path,'/runs/report-run/synthesis-analysis');assert.equal(posted.body.mode,'live');
  assert.match(env.roots['report-content'].textContent,/기록된 행동/);
  assert.match(env.roots['report-content'].textContent,/실제 원문/);
  assert.equal(env.roots['report-synthesis-preview'].children.length,0);
  const stale=await setup({run:{...run,synthesis_analysis:result,synthesis_analysis_stale:true}});
  assert.match(stale.roots['report-content'].textContent,/이 종합 평가는 이전 입력 기준/);
  assert.doesNotMatch(stale.roots['report-content'].textContent,/기록된 행동/);
});

test('grounded synthesis shows game records, an interview criterion and the exact quote',async()=>{
  const run=runWithReport();run.flow_version='five-game-v2';completeGameStages(run);
  run.synthesis_analysis={report:{report_version:'three-source-practice-v3',prompt:{evidence:[{id:'interview:a',text:'요청표를 대조했습니다.'},{id:'game:p',source:'game'}]},
    game_observations:[{evidence_id:'game:p',label:'마법약 만들기',text:'제조 결과 적중 7/10회 · 가능성이 더 높은 색 선택 9/10회'}],
    feedback:{strengths:[{text:'‘어떤 자료를 무엇과 대조해 확인했는지’에 관한 근거로 AI가 선택한 문장입니다.',
      quote:'요청표를 대조했습니다.',evidence_ids:['interview:a']}],gaps:[],practice_plan:[],clarifying_questions:[]}}};
  const env=await setup({run});const text=env.roots['report-content'].textContent;
  assert.match(text,/본게임 수행 기록.*마법약 만들기.*제조 결과 적중 7\/10회.*가능성이 더 높은 색 선택 9\/10회/);
  assert.match(text,/저장된 면접 답변 인용.*요청표를 대조했습니다\./);
  assert.match(text,/어떤 자료를 무엇과 대조해 확인했는지/);
});

test('game analysis is an explicit separate request after the baseline report',async()=>{
  const run=runWithReport();run.flow_version='five-game-v2';completeGameStages(run);run.interview_report.five_games={version:'five-game-report-v1',source_digest:'digest',games:[]};
  const env=await setup({run,handler:call=>call.path.endsWith('/game-analysis')?Response.json({...run,revision:21}):undefined});
  assert.equal(env.calls.filter(c=>c.method==='POST').length,0);
  await env.click('report-game-ai');
  const posted=env.calls.find(c=>c.method==='POST');
  assert.equal(posted.path,'/runs/report-run/game-analysis');assert.equal(posted.body.mode,'live');
  assert.equal(posted.body.expected_revision,20);assert.ok(posted.body.idempotency_key);
});
test('five game report shows each saved game and its separate conditions and results',async()=>{
  const run=runWithReport();
  run.interview_report.five_games={version:'five-game-report-v1',games:[
    {type:'rsp',status:'completed',conditions:{round_limit:3},totals:{completed_rounds:3,missing_rounds:0},evidence:[{round_index:1,score:10,correct_count:1,incorrect_count:0}]},
    {type:'card',status:'completed',conditions:{round_limit:3},totals:{completed_rounds:3,missing_rounds:0},evidence:[]},
    {type:'day',status:'complete',conditions:{difficulty:'easy',question_limit:10,question_conditions:[{answer_ms:6000,reveal_ms:[3000,3000,3000]}]},totals:{settled:10,missing:0,correct:6,wrong:3,timeout:1,score:45},evidence:[{number:1,outcome:'correct',sets:[[0,1,2],[0,3,4],[0,5,6]],choices:[0,1,2,3,4,5,6],selection:0,answer:0,score_before:0,score_after:10,source_ref:{question_id:'q1',question_version:'v1'}}]},
    {type:'place',status:'pending',conditions:{difficulty:null,question_limit:10},totals:{settled:0,missing:10,correct:0,wrong:0,timeout:0,score:0},evidence:[]},
    {type:'bus',status:'pending',conditions:{difficulty:null,question_limit:10},totals:{settled:0,missing:10,correct:0,wrong:0,timeout:0,score:0},evidence:[]}
  ]};
  const env=await setup({run});const text=env.roots['report-content'].textContent;
  assert.match(text,/가위바위보/);assert.match(text,/숫자 카드/);assert.match(text,/약속 요일/);assert.match(text,/약속 장소/);assert.match(text,/버스/);
  assert.match(text,/쉬움/);assert.match(text,/정답 6.*오답 3.*시간 초과 1/);assert.match(text,/45점/);assert.match(text,/q1@v1/);assert.match(text,/미완료/);
  assert.match(text,/A: 월요일.*화요일.*수요일/);assert.match(text,/선택 월요일.*정답 월요일/);
});
function report({runtime='mock',requested='mock',provider='not_called'}={}){
  const criterion=Object.fromEntries(criteria.map(name=>[name,{criterion:name,status:['action','learning'].includes(name)?'explicit':name==='other_information'?'not_asked':'not_mentioned',evidence_spans:name==='action'?[{source_id:'answer-current',source_version:'2.0.0',start:1,end:4,quote:'🙂행동',offset_unit:'unicode_code_point'}]:name==='learning'?[{source_id:'answer-current',source_version:'2.0.0',start:7,end:Array.from(answerText).length,quote:'<script>globalThis.pwned=true</script>',offset_unit:'unicode_code_point'}]:[],limitations:[],missing_reason:name==='other_information'?'criterion_not_asked':null}]));
  return {report_id:'report-1',report_version:'1.0.0',created_at:'2026-10-11T00:00:00Z',runtime_mode:runtime,requested_mode:requested,provider_execution:provider,model_id:provider==='provider_completed'?'model-approved':null,input_snapshot:{generation:1,definitions_version:'1.0.0'},limitations:['자기보고는 실제 발생 사실을 인증하지 않습니다.'],cards:[
    {behavior_id:'B01',behavior_name:'정보 요청',question_id:'baseline-b01',question_version:'1.0.0',question_text:'정보를 구한 경험',answer_id:'answer-current',answer_version:'2.0.0',answer_status:'asked_answered',criteria:criterion,comparison:{status:'insufficient_evidence',reason:'no_comparable_game_mapping',limitations:['비교 가능한 게임 매핑이 없습니다.']},practice_suggestions:[{criterion:'result',text:'결과를 수치나 관찰로 덧붙여 보세요.',template_version:'1.0.0',basis_refs:['answer-current@2.0.0']}]},
    {behavior_id:'B02',behavior_name:'관점 조율',question_id:'baseline-b02',question_version:'1.0.0',question_text:'조율 경험',answer_id:'answer-empty',answer_version:'1.0.0',answer_status:'asked_no_text',criteria:Object.fromEntries(criteria.map(name=>[name,{criterion:name,status:name==='other_information'?'not_asked':'unassessable',evidence_spans:[],limitations:[],missing_reason:'no_answer_text'}])),comparison:{status:'insufficient_evidence',reason:'no_answer_text',limitations:[]},practice_suggestions:[]},
    {behavior_id:'B03',behavior_name:'판단 수정',question_id:'baseline-b03',question_version:'1.0.0',question_text:'판단을 바꾼 경험',answer_id:'answer-skip',answer_version:'1.0.0',answer_status:'skipped',criteria:Object.fromEntries(criteria.map(name=>[name,{criterion:name,status:'unassessable',evidence_spans:[],limitations:[],missing_reason:'skipped'}])),comparison:{status:'insufficient_evidence',reason:'skipped',limitations:[]},practice_suggestions:[]}
  ],surveys:[
    {record_id:'survey-ordinal',record_version:1,source_version:'1.0.0',status:'submitted',item_id:'O-B01',item_version:'1.0.0',presentation_order:1,data:{response_type:'ordinal_6',prompt_snapshot:'필요한 정보를 먼저 묻는 편이다.',selected_position:6,selected_label_snapshot:'매우 그렇다',direction:'higher_more'}},
    {record_id:'survey-pair',record_version:1,source_version:'1.0.0',status:'submitted',item_id:'P-B01',item_version:'1.0.0',presentation_order:2,data:{response_type:'paired_perspective',self:{status:'submitted',selected_position:4,selected_label_snapshot:'그런 편이다'},imagined_others:{status:'submitted',selected_position:2,selected_label_snapshot:'그렇지 않은 편이다'}}},
    {record_id:'survey-slider',record_version:1,source_version:'1.0.0',status:'submitted',item_id:'S-B02',item_version:'1.0.0',presentation_order:3,data:{response_type:'bipolar_slider',final_value:-2,min:-3,max:3,left_label_snapshot:'신중히 검토',right_label_snapshot:'빠르게 실행',direction:'left_to_right',interaction_occurred:true,explicit_confirmation:true}},
    {record_id:'survey-rank',record_version:1,source_version:'1.0.0',status:'submitted',item_id:'R-UNMAPPED',item_version:'1.0.0',presentation_order:4,data:{response_type:'top_k_rank',requested_k:3,candidate_snapshots:[{option_id:'helping',label:'다른 사람을 도울 기회'},{option_id:'growth',label:'새로운 것을 배울 기회'},{option_id:'autonomy',label:'스스로 정할 수 있는 범위'},{option_id:'stability',label:'예측 가능한 일정'}],selected_ids:['helping','growth','autonomy'],ranked_options:[{rank:1,option_id:'helping',label_snapshot:'다른 사람을 도울 기회'},{rank:2,option_id:'growth',label_snapshot:'새로운 것을 배울 기회'},{rank:3,option_id:'autonomy',label_snapshot:'스스로 정할 수 있는 범위'}]}}
  ],rule_games:[{game_id:'rule-rsp',game_version:'1.0.0',state_version:3,mapping_status:'unmapped',comparison_status:'not_comparable',rounds:[{round_id:'round-1',round_index:1,status:'completed',score:10,correct_count:1,incorrect_count:0,quality_flags:[],event_refs:['event-1']}]}]};
}

function runWithReport(options={}){
  return {run_id:options.run_id||'report-run',user_id:options.user_id||'report-user',generation:1,revision:options.revision??20,status:options.status||'in_progress',questions:[
    {question_id:'baseline-b01',question_version:'1.0.0',behavior_id:'B01'},
    {question_id:'baseline-b02',question_version:'1.0.0',behavior_id:'B02'},
    {question_id:'baseline-b03',question_version:'1.0.0',behavior_id:'B03'}],records:[
    {record_id:'r-current',source_type:'typed_answer',data:{question_id:'baseline-b01',question_version:'1.0.0',behavior_id:'B01',answer_id:'answer-current',answer_version:'2.0.0',status:'asked_answered',text:answerText}},
    {record_id:'r-empty',source_type:'typed_answer',data:{question_id:'baseline-b02',question_version:'1.0.0',behavior_id:'B02',answer_id:'answer-empty',answer_version:'1.0.0',status:'asked_no_text',text:''}},
    {record_id:'r-skip',source_type:'typed_answer',data:{question_id:'baseline-b03',question_version:'1.0.0',behavior_id:'B03',answer_id:'answer-skip',answer_version:'1.0.0',status:'skipped',text:''}}
  ],interview_analysis:options.analysis===false?null:{runtime_mode:options.runtime||'mock',requested_mode:options.requested||'mock',provider_execution:options.provider||'not_called'},interview_report:options.report===false?null:report({runtime:options.runtime,requested:options.requested,provider:options.provider}),interview_report_stale:Boolean(options.stale)};
}

async function setup({run=runWithReport(),capabilities={live_available:true,reason:null,model_id:'model-approved',max_calls_per_run:3,max_cost_microusd:50000},storage=new Map(),handler,guest=false,legacyBridge=false,storageFails=false,initialBusy=false}={}){
  const ids=['report-status','report-error','report-capability','report-refresh','report-mock','report-analyze','report-game-ai','report-game-mock','report-retry','report-content','report-linkage','report-finalize','report-followups','report-completion','report-synthesis-prompt','report-synthesis-preview','report-synthesis-mock','report-synthesis-ai'];
  const roots=Object.fromEntries(ids.map(id=>[id,new Element(id.includes('refresh')||id.includes('mock')||id.includes('analyze')||id.includes('retry')?'button':'div')]));
  const events={},calls=[],locks=[];let listener;let server=clone(run);
  let scope={user:guest?null:{user_id:run.user_id},run:guest?null:clone(run),authStatus:guest?'guest':'authenticated',ready:!guest,busy:initialBusy,locked:false,gameLocked:false,interviewLocked:false,reportLocked:false};
  const document={getElementById:id=>roots[id],createElement:tag=>new Element(tag),addEventListener(type,fn){(events[type]||=[]).push(fn);}};
  const transport=async(url,options)=>{
    const call={path:url.slice(4),method:options.method,body:options.body?JSON.parse(options.body):undefined};calls.push(call);
    const override=handler&&await handler(call,{server,setServer:value=>{server=clone(value);}});if(override)return override;
    if(call.path==='/interview-analysis-capabilities'&&call.method==='GET')return Response.json(capabilities);
    if(call.path===`/runs/${server.run_id}`&&call.method==='GET')return Response.json(server);
    if(call.path===`/runs/${server.run_id}/interview-analysis`&&call.method==='POST'){
      server=runWithReport({run_id:server.run_id,user_id:server.user_id,revision:server.revision+1,runtime:call.body.mode,requested:call.body.mode,provider:call.body.mode==='live'?'provider_completed':'not_called'});
      return Response.json(server);
    }
    throw Error(`Unexpected request ${call.method} ${call.path}`);
  };
  const bridge={subscribe(fn){listener=fn;fn(clone(scope));},updateRun(value){if(!scope.run||value.user_id!==scope.user?.user_id||value.run_id!==scope.run.run_id||value.revision<scope.run.revision)return false;scope.run=clone(value);listener(clone(scope));return true;},invalidateRun(){scope.run=null;listener(clone(scope));return true;},setReportLock(value){locks.push(clone(value));scope.reportLocked=value.locked;}};
  if(legacyBridge)delete bridge.setReportLock;
  const sessionStorage={get length(){return storage.size;},key:index=>[...storage.keys()][index]??null,getItem:key=>storage.get(key)||null,setItem(key,value){if(storageFails)throw Error('quota');storage.set(key,value);},removeItem(key){if(storageFails)throw Error('quota');storage.delete(key);}};
  const window={AstraPractice:bridge,AstraClient:{...C,createApi:()=>C.createApi(transport)},AstraAuth:{recheck(){}},sessionStorage};
  const context=vm.createContext({window,document,crypto:webcrypto,structuredClone,console});
  assert.equal(fs.existsSync('html/report.js'),true,'html/report.js must exist');
  vm.runInContext(fs.readFileSync('html/report.js','utf8'),context);
  for(const fn of events.DOMContentLoaded||[])await fn();await flush();
  return {roots,window,context,calls,locks,storage,server:()=>server,async click(id){assert.ok(roots[id]?.events.click?.length,`Missing control ${id}`);await roots[id].fire('click');},async changeScope(value){scope=value;listener(clone(scope));await flush();}};
}

function completeRun() {
  const run=runWithReport();
  run.questions.forEach(q=>{q.question_mode='baseline';q.conditioned_on_prior_evidence=false;});
  for(const item_id of ['O-B01','P-B01','O-B02','S-B02','O-B03','R-UNMAPPED'])run.records.push({source_type:'survey',item_id,status:'skipped'});
  run.rule_games={games:Object.fromEntries(['rsp','card'].map(type=>[type,{rounds:[1,2,3].map(index=>({index,status:'completed'}))}]))};
  return run;
}
const linkageFixture=()=>({linkage_id:'link-1',version:'1.0.0',source_report_id:'report-1',input_snapshot:{},limitations:['설문은 자기보고입니다.'],links:[{behavior_id:'B01',behavior_name:'정보 요청',summary:'원본 연결',comparison_status:'insufficient_evidence',survey_refs:[{record_id:'s1',record_version:1,item_id:'O-B01',item_version:'1.0.0',response_text:'매우 그렇다',perspective:'self',use:'question_context'}],interview_refs:[{answer_id:'answer-current',answer_version:'2.0.0',question_id:'baseline-b01',question_version:'1.0.0',criterion:'action',status:'explicit',evidence_spans:[{source_id:'answer-current',source_version:'2.0.0',start:1,end:4,quote:'🙂행동',offset_unit:'unicode_code_point'}]}],limitations:['비교 제한']}],observations:[{game_type:'rsp',game_id:'rule-rsp',game_version:'1.0.0',round_id:'round-1',round_index:1,status:'completed',before:{accepted_count:1,correct_count:1,event_refs:['event-before']},after:{accepted_count:0,correct_count:0,event_refs:[]},overlap:{new_only:0,old_only:0,both:0,neither:0},disclosure_status:'recorded',missing_reason:'no_accepted_response_after_disclosure',event_refs:['event-before'],limitations:['행동 B03 비교 제외']}],questions:[]});

test('final readiness uses five work-survey visits and still blocks a missing new question',async()=>{
  const run=completeRun();run.survey_set_version='work-behavior-v2';
  run.survey_definition_snapshot=clone(require('./fixtures/work_survey_definitions.json'));
  run.records=run.records.filter(r=>r.source_type!=='survey').concat(run.survey_definition_snapshot.map(q=>({source_type:'survey',item_id:q.item_id,status:'skipped'})));
  run.evidence_linkage=linkageFixture();
  const env=await setup({run});
  assert.equal(env.roots['report-finalize'].disabled,false);
  assert.match(env.roots['report-completion'].textContent,/설문 방문 5\/5/);
  const missing=clone(run);missing.records.pop();
  const blocked=await setup({run:missing});assert.equal(blocked.roots['report-finalize'].disabled,true);
});

test('completion actions use frozen endpoint/body retries and final gate tracks visited surveys, both games and baseline only',async()=>{
  let lose=true;
  const run=completeRun();
  const env=await setup({run,handler:(call,{server,setServer})=>{
    if(call.method==='POST'&&call.path.endsWith('/evidence-linkage')){
      const result={...clone(server),revision:server.revision+1,evidence_linkage:linkageFixture(),evidence_linkage_stale:false};setServer(result);
      if(lose){lose=false;throw Error('response lost');}return Response.json(result);
    }
    if(call.method==='POST'&&call.path.endsWith('/interview-finalize')){const result={...clone(server),revision:server.revision+1,status:'completed'};result.interview_report.status='finalized';result.interview_report.evidence_linkage=linkageFixture();result.interview_report.followup_answers=[{question_id:'optional',question_version:'1.0.0',question_text:'추가 경험',question_mode:'adaptive_followup',conditioned_on_prior_evidence:true,status:'not_answered',text:null}];setServer(result);return Response.json(result);}
  }});
  assert.equal(env.roots['report-finalize'].disabled,true);
  assert.equal(env.calls.filter(c=>c.method==='POST').length,0);
  await env.click('report-linkage');
  assert.equal(env.roots['report-retry'].hidden,false);assert.equal(env.roots['report-finalize'].disabled,true);
  await env.click('report-retry');
  const posts=env.calls.filter(c=>c.method==='POST');assert.equal(posts[0].path,posts[1].path);assert.deepEqual(posts[0].body,posts[1].body);assert.deepEqual(Object.keys(posts[0].body).sort(),['expected_revision','idempotency_key']);
  assert.equal(env.roots['report-finalize'].disabled,false);
  assert.match(env.roots['report-content'].textContent,/s1@1.*O-B01@1\.0\.0/);
  assert.match(env.roots['report-content'].textContent,/🙂행동/);
  assert.match(env.roots['report-content'].textContent,/규칙 공개 전.*1.*규칙 공개 후.*0/);
  assert.match(env.roots['report-content'].textContent,/no_accepted_response_after_disclosure/);
  assert.match(env.roots['report-content'].textContent,/공개 후 응답 없음.*관찰할 수 없습니다/);
  await env.click('report-finalize');
  assert.equal(env.roots['report-linkage'].disabled,true);assert.equal(env.roots['report-finalize'].disabled,true);
  assert.match(env.roots['report-content'].textContent,/최종 보고서.*후속 질문.*미응답/);
});

test('linkage preserves mapping exclusion IDs and reasons without hiding the original baseline or fabricating evidence',async()=>{
  const run=completeRun();run.evidence_linkage=linkageFixture();run.evidence_linkage.links[0].exclusions=[{record_id:'source-excluded',record_version:2,item_id:'O-B01',item_version:'1.0.0',mapping_id:'mapping-old',reason:'mapping_version_incompatible'},{answer_id:'answer-excluded',question_id:'question-excluded',mapping_id:'interview-map',reason:'mapping_inactive'}];
  const env=await setup({run});assert.match(env.roots['report-content'].textContent,/비교 제외 사유: source-excluded@2.*O-B01@1\.0\.0.*mapping-old.*mapping_version_incompatible/);assert.match(env.roots['report-content'].textContent,/answer-excluded.*question-excluded.*interview-map.*mapping_inactive/);assert.doesNotMatch(env.roots['report-content'].textContent,/undefined@undefined/);assert.match(env.roots['report-content'].textContent,/🙂행동/);
});

test('completion cannot finalize missing surveys, incomplete card game, stale linkage or unprocessed baseline',async()=>{
  const complete=completeRun();complete.evidence_linkage=linkageFixture();
  for(const mutate of [r=>r.records.pop(),r=>r.rule_games.games.card.rounds.pop(),r=>r.evidence_linkage_stale=true,r=>r.records.shift(),r=>r.interview_report_stale=true]){
    const run=clone(complete);mutate(run);const env=await setup({run});assert.equal(env.roots['report-finalize'].disabled,true);await env.click('report-finalize');assert.equal(env.calls.filter(c=>c.method==='POST').length,0);
  }
});

test('renders grounded cards, original survey semantics and unmapped game facts while discarding invalid citations',async()=>{
  const initial=runWithReport();
  initial.interview_report.cards[0].criteria.result={criterion:'result',status:'explicit',evidence_spans:[{source_id:'answer-current',source_version:'2.0.0',start:0,end:3,quote:'조작된 인용',offset_unit:'unicode_code_point'}],limitations:[],missing_reason:null};
  const env=await setup({run:initial});const text=env.roots['report-content'].textContent;
  assert.match(text,/B01/);assert.match(text,/상황.*역할.*다른 정보.*행동.*이유.*결과.*배움/);
  assert.match(text,/🙂행동인용 출처: answer-current@2\.0\.0 · code-point \[1,4\)/);assert.doesNotMatch(text,/조작된 인용/);
  assert.match(text,/필요한 정보를 먼저 묻는 편이다.*매우 그렇다/);assert.match(text,/나의 관점.*그런 편이다/);assert.match(text,/상상한 타인 관점.*그렇지 않은 편이다/);
  assert.match(text,/신중히 검토.*-2.*빠르게 실행.*-3.*3/);assert.match(text,/1위.*다른 사람을 도울 기회/);
  assert.match(text,/제시 후보.*예측 가능한 일정/);assert.match(text,/3개만 순위.*미선택.*싫어함이 아님/);
  assert.match(text,/S-B02.*비교 제외/);assert.match(text,/R-UNMAPPED.*비교 제외/);
  assert.match(text,/unmapped.*not_comparable/);assert.match(text,/10점.*정답 1.*오답 0/);
  assert.match(text,/비교 근거 부족/);assert.match(text,/결과를 수치나 관찰로 덧붙여 보세요.*제안 버전: 1\.0\.0.*근거 참조: answer-current@2\.0\.0/);
  assert.match(text,/<script>globalThis\.pwned=true<\/script>/);
  assert.equal(env.context.pwned,undefined);
  assert.equal(env.roots['report-status'].textContent.includes('AI 미사용 · 저장 근거'),true);
});

test('never auto-posts and sends exact explicit mock/live bodies with separate controls',async()=>{
  const env=await setup({run:runWithReport({report:false,analysis:false})});
  assert.equal(env.calls.filter(call=>call.method==='POST').length,0);
  await env.click('report-mock');
  const mock=env.calls.find(call=>call.method==='POST');
  assert.deepEqual(Object.keys(mock.body).sort(),['expected_revision','idempotency_key','mode']);assert.equal(mock.body.mode,'mock');assert.equal(mock.body.expected_revision,20);
  const next=runWithReport({revision:21,report:false,analysis:false});
  await env.changeScope({user:{user_id:'report-user'},run:next,authStatus:'authenticated',ready:true,busy:false,locked:false,gameLocked:false,interviewLocked:false,reportLocked:false});
  await env.click('report-analyze');
  const posts=env.calls.filter(call=>call.method==='POST');assert.equal(posts[1].body.mode,'live');assert.notEqual(posts[0].body.idempotency_key,posts[1].body.idempotency_key);
});

test('missing live configuration stays safe and explains why without model or key input UI',async()=>{
  const env=await setup({run:runWithReport({report:false,analysis:false}),capabilities:{live_available:false,reason:'live_not_configured',model_id:null,max_calls_per_run:0,max_cost_microusd:0}});
  assert.equal(env.roots['report-analyze'].disabled,true);assert.equal(env.roots['report-mock'].disabled,false);
  assert.match(env.roots['report-capability'].textContent,/서버.*설정/);assert.doesNotMatch(env.roots['report-content'].textContent,/API\s*키|모델 선택/);
});

test('response loss keeps one frozen request, restores per-run journal, retries same body then reads current',async()=>{
  const storage=new Map();let committed=false;let saved;
  const first=await setup({run:runWithReport({report:false,analysis:false}),storage,handler:(call,{server,setServer})=>{
    if(call.method==='POST'&&!committed){committed=true;saved=runWithReport({revision:server.revision+1});setServer(saved);return Promise.reject(Error('lost response'));}
  }});
  await first.click('report-mock');const original=first.calls.find(call=>call.method==='POST').body;
  assert.equal(first.roots['report-retry'].hidden,false);assert.equal(first.locks.at(-1).locked,true);assert.match(first.roots['report-status'].textContent,/결과 확인 대기/);
  const restored=await setup({run:saved,storage});await restored.click('report-retry');
  const replay=restored.calls.find(call=>call.method==='POST').body;assert.deepEqual(replay,original);assert.equal(restored.calls.at(-1).method,'GET');
  assert.equal(restored.storage.size,0);assert.equal(restored.locks.at(-1).locked,false);assert.match(restored.roots['report-content'].textContent,/B01/);
});

test('running reservation remains retryable but definitive failure clears pending and requires a new explicit request',async()=>{
  let branch='running';
  const env=await setup({run:runWithReport({report:false,analysis:false}),handler:call=>call.method==='POST'?Response.json({error:branch==='running'?'analysis_request_running':'analysis_request_failed'},{status:409}):undefined});
  await env.click('report-mock');assert.equal(env.roots['report-retry'].hidden,false);assert.equal(env.storage.size,1);
  branch='failed';await env.click('report-retry');assert.equal(env.roots['report-retry'].hidden,true);assert.equal(env.storage.size,0);assert.match(env.roots['report-error'].textContent,/새로.*요청/);
  assert.equal(env.calls.filter(call=>call.method==='POST').length,2,'no blind third request');
  await env.click('report-mock');const posts=env.calls.filter(call=>call.method==='POST');assert.notEqual(posts[1].body.idempotency_key,posts[2].body.idempotency_key);
});

test('stale and execution modes are labeled conservatively and completed runs stay read-only',async()=>{
  const stale=await setup({run:runWithReport({stale:true,runtime:'mock',requested:'live',provider:'test_double'})});
  assert.match(stale.roots['report-status'].textContent,/테스트 대역/);assert.match(stale.roots['report-error'].textContent,/이전 입력 기준.*새 분석/);
  assert.equal(stale.calls.filter(call=>call.method==='POST').length,0);
  const live=await setup({run:runWithReport({runtime:'live',requested:'live',provider:'provider_completed',status:'completed'})});
  assert.match(live.roots['report-status'].textContent,/AI 분석 완료/);assert.equal(live.roots['report-mock'].disabled,true);assert.equal(live.roots['report-analyze'].disabled,true);assert.match(live.roots['report-content'].textContent,/B01/);
});

test('other workflow locks gate requests while this module ignores its own published report lock',async()=>{
  const env=await setup({run:runWithReport({report:false,analysis:false})});
  await env.changeScope({user:{user_id:'report-user'},run:runWithReport({report:false,analysis:false}),authStatus:'authenticated',ready:true,busy:false,locked:false,gameLocked:true,interviewLocked:false,reportLocked:false});
  assert.equal(env.roots['report-mock'].disabled,true);
  await env.changeScope({user:{user_id:'report-user'},run:runWithReport({report:false,analysis:false}),authStatus:'authenticated',ready:true,busy:false,locked:false,gameLocked:false,interviewLocked:false,reportLocked:true});
  assert.equal(env.roots['report-mock'].disabled,false);
});

test('late private responses and older cached runs cannot replace current scope or newer report',async()=>{
  let resolveRun;
  const storage=new Map([['astra.report.v1:report-user:report-run',JSON.stringify({pending:{body:{expected_revision:20,idempotency_key:'frozen-key',mode:'mock'}}})]]);
  const env=await setup({storage,handler:call=>call.method==='GET'&&call.path==='/runs/report-run'?new Promise(resolve=>{resolveRun=resolve;}):undefined});
  await env.changeScope({user:null,run:null,authStatus:'guest',ready:false,busy:false,locked:false,gameLocked:false,interviewLocked:false,reportLocked:false});
  resolveRun(Response.json(runWithReport()));await flush();
  assert.equal(env.roots['report-content'].textContent,'');assert.doesNotMatch(env.roots['report-status'].textContent,/report-run/);assert.equal(env.storage.size,0);
  const newer=runWithReport({revision:30});const cache=runWithReport({revision:29,provider:'test_double',requested:'live'});
  const current=await setup({run:newer,handler:call=>call.method==='GET'&&call.path==='/runs/report-run'?Response.json(cache):undefined});
  assert.doesNotMatch(current.roots['report-status'].textContent,/테스트 대역/);assert.match(current.roots['report-status'].textContent,/AI 미사용/);
});

test('incompatible practice bridge fails closed instead of issuing private requests',async()=>{
  const env=await setup({legacyBridge:true});assert.match(env.roots['report-error'].textContent,/Ctrl\s*\+\s*F5/);assert.equal(env.calls.length,0);assert.equal(env.roots['report-refresh'].disabled,true);
});

test('unavailable session storage blocks a request before a non-durable idempotency key can be sent',async()=>{
  const env=await setup({run:runWithReport({report:false,analysis:false}),storageFails:true});
  assert.equal(env.roots['report-mock'].disabled,true);assert.match(env.roots['report-error'].textContent,/임시 저장 공간/);
  await env.click('report-mock');assert.equal(env.calls.filter(call=>call.method==='POST').length,0);
});

test('initial loading deferred by another workflow starts when the same run becomes unlocked',async()=>{
  const initial=runWithReport({report:false,analysis:false});const env=await setup({run:initial,initialBusy:true});
  assert.equal(env.calls.length,0);assert.equal(env.roots['report-mock'].disabled,true);
  await env.changeScope({user:{user_id:'report-user'},run:initial,authStatus:'authenticated',ready:true,busy:false,locked:false,gameLocked:false,interviewLocked:false,reportLocked:false});
  assert.equal(env.calls.filter(call=>call.method==='GET').length,2);assert.equal(env.roots['report-mock'].disabled,false);
});
