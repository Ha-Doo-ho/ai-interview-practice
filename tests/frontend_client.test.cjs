const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const modulePath=path.resolve(__dirname,'../html/client.js');
const C=fs.existsSync(modulePath)?require(modulePath):{};

test('cookie transport protects writes and preserves untrimmed data',async()=>{
  assert.equal(typeof C.createApi,'function');
  const requests=[];
  const api=C.createApi(async (url,options)=>{requests.push({url,...options});return new Response(JSON.stringify({ok:true}),{status:200});});
  await api('/runs/r/answers',{method:'POST',body:{text:'  원문 🐱\n'}});
  assert.equal(requests[0].url,'/api/runs/r/answers');
  assert.equal(requests[0].credentials,'same-origin');
  assert.equal(requests[0].headers['X-Requested-With'],'interview-app');
  assert.equal(JSON.parse(requests[0].body).text,'  원문 🐱\n');
});
test('uncertain write freezes full body and retry reuses original key',async()=>{
  assert.equal(typeof C.createMutation,'function');
  const sent=[];let count=0;
  const m=C.createMutation(async(path,options)=>{sent.push(structuredClone(options.body));if(count++===0)throw Object.assign(new Error('network_error'),{code:'network_error'});return {run_id:'r',revision:2};},()=> 'fixed-key');
  const run={run_id:'r',revision:1};const input={text:'original'};
  await assert.rejects(m.send(run,'answers',input));input.text='changed';
  await assert.rejects(m.send(run,'answers',input),{message:'pending_request'});
  assert.equal(m.pending.body.text,'original');
  await m.retry();assert.deepEqual(sent[1],sent[0]);assert.equal(m.pending,null);
});
test('definite conflict clears request while transient failure retains retry',async()=>{
  assert.equal(typeof C.createMutation,'function');
  for(const [status,pending] of [[409,false],[500,true]]){
    const m=C.createMutation(async()=>{throw Object.assign(new Error('http'),{status});},()=> 'k');
    await assert.rejects(m.send({run_id:'r',revision:1},'analyze',{}));
    assert.equal(Boolean(m.pending),pending);
  }
});
test('survey partial perspectives keep actual selected positions and missing status',()=>{
  assert.equal(typeof C.buildSurveyResponse,'function');
  assert.deepEqual(C.buildSurveyResponse({type:'ordinal_6'},'timed_out',{}),null);
  assert.deepEqual(C.buildSurveyResponse({type:'paired_perspective'},'timed_out',{self:6}),{self:{selected_position:6,status:'submitted'},imagined_others:{status:'timed_out'}});
  assert.deepEqual(C.buildSurveyResponse({type:'ordinal_6'},'skipped',{selected_position:2}),{selected_position:2});
});
test('slider untouched middle is an explicit choice only on confirmation',()=>{
  assert.equal(typeof C.buildSurveyResponse,'function');
  const item={type:'bipolar_slider'};
  assert.deepEqual(C.buildSurveyResponse(item,'submitted',{value:0,touched:false,changes:0}),{final_value:0,interaction_occurred:false,explicit_confirmation:true,change_count:0});
  assert.deepEqual(C.buildSurveyResponse(item,'timed_out',{value:0,touched:false,changes:0}),{final_value:null,interaction_occurred:false,explicit_confirmation:false,change_count:0});
  assert.equal(C.buildSurveyResponse(item,'timed_out',{value:-3,touched:true,changes:2}).final_value,-3);
});
test('rank order/events preserved without assigning rejection to unselected options',()=>{
  assert.equal(typeof C.buildSurveyResponse,'function');
  const input={selected_ids:['helping','growth','autonomy'],selection_events:[{action:'move',option_id:'helping',rank:1}]};
  const result=C.buildSurveyResponse({type:'top_k_rank',requested_k:3},'submitted',input);
  assert.deepEqual(result,input);input.selected_ids.reverse();assert.equal(result.selected_ids[0],'helping');
  assert.throws(()=>C.buildSurveyResponse({type:'top_k_rank',requested_k:3},'submitted',{selected_ids:[]}),/rank_count/);
});
test('answer correction uses latest version without trimming original text',()=>{
  assert.equal(typeof C.answerPayload,'function');
  const a={source_type:'typed_answer',data:{question_id:'q',answer_id:'a',answer_version:'1.0.0'}};
  const b={source_type:'typed_answer',data:{question_id:'q',answer_id:'b',answer_version:'2.0.0',previous_answer_version_ref:{answer_id:'a',answer_version:'1.0.0'}}};
  const run={records:[b,a]};assert.equal(C.latestAnswer(run,'q'),b);
  assert.deepEqual(C.answerPayload(run,'q','  원문 🐱\n','asked_answered'),{question_id:'q',text:'  원문 🐱\n',status:'asked_answered',replaces_answer_id:'b',expected_answer_version:'2.0.0'});
  assert.equal(C.answerPayload(run,'q','discard','skipped').text,'');
  assert.throws(()=>C.answerPayload(run,'q',' \n','asked_answered'),/answer_required/);
});
test('main round completion enables interim analysis but not incomplete finalization',()=>{
  assert.equal(typeof C.progress,'function');
  const defs={surveys:[{item_id:'s'}],version:'v'};
  const run={status:'in_progress',records:[],questions:[{question_id:'q',question_mode:'baseline'}],game:{phase:'allocate',rounds:[{practice_or_main:'practice',status:'completed'},{practice_or_main:'main',status:'started'}]}};
  assert.equal(C.progress(run,defs).canAnalyze,false);
  run.game.rounds[1].status='completed';assert.equal(C.progress(run,defs).canAnalyze,true);assert.equal(C.progress(run,defs).canFinalize,false);
  run.records=[{source_type:'survey',item_id:'s',status:'timed_out'},{source_type:'typed_answer',data:{question_id:'q',status:'asked_no_text'}}];
  run.game.phase='complete';run.analysis={};run.report_draft={};assert.equal(C.progress(run,defs).canFinalize,true);
  run.status='completed';assert.equal(C.progress(run,defs).canAnalyze,false);assert.equal(C.progress(run,defs).canFinalize,false);
});
test('quotes verify Unicode offsets against the exact stored answer version',()=>{
  assert.equal(typeof C.verifyQuote,'function');
  const records=[{source_type:'typed_answer',data:{answer_id:'a',answer_version:'1.0.0',text:'앞🐱뒤'}}];
  const quote={source_id:'a',source_version:'1.0.0',start:1,end:2,quote:'🐱'};
  assert.equal(C.verifyQuote(quote,records).valid,true);
  assert.equal(C.verifyQuote({...quote,source_version:'2.0.0'},records).valid,false);
  assert.equal(C.verifyQuote({...quote,end:3},records).valid,false);
});
test('report becomes stale after changed record or game version',()=>{
  assert.equal(typeof C.analysisStale,'function');
  const run={generation:1,records:[],game:{state_version:2},analysis:{input_snapshot:{generation:1,record_refs:[],game_state_version:2,definitions_version:'v'}}};
  assert.equal(C.analysisStale(run,{version:'v'}),false);
  run.game.state_version=3;assert.equal(C.analysisStale(run,{version:'v'}),true);
});
