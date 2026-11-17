/* Server-authoritative appointment memory games; no question generation or scoring here. */
import {placeArt} from './appointment-town.mjs';
(function () {
  'use strict';
  const state = {scope:null, run:null, context:null, epoch:0, busy:false, pending:null, loaded:false, timer:null, sampledAt:0, remaining:0, error:'', boundary:false};
  const names = {day:'약속 요일 정하기', place:'약속 장소 정하기', bus:'버스 기억하기'};
  const days = ['월요일','화요일','수요일','목요일','금요일','토요일','일요일'];
  let root, api;
  const key = s => `astra.appointment-games.v1:${s.user_id}:${s.run_id}`;
  const path = () => `/runs/${encodeURIComponent(state.scope.run_id)}/appointment-games`;
  const data = () => state.run?.appointment_games;
  const games = () => data()?.games || [];
  const current = () => games().find(g => g.status === 'active') || games().find(g => g.status !== 'complete');
  const ready = () => ['rsp','card'].every(t => (state.run?.rule_games?.games?.[t]?.rounds || []).filter(r => r.status === 'completed').length >= 3);
  const disabled = () => !state.loaded || state.busy || !!state.pending || state.context?.busy || state.context?.locked || state.context?.ruleGameLocked || state.context?.aptitudeGameLocked || state.context?.interviewLocked || state.context?.reportLocked || state.run?.status === 'completed';
  const label = (type, value) => type === 'day' ? (days[value] || String(value)) : type === 'place' ? `장소 ${Number(value)+1}` : `${value}번`;
  function node(tag, text, className) { const e=document.createElement(tag); if (text !== undefined) e.textContent=text; if(className)e.className=className; return e; }
  function button(id,text,fn,off=false) { const e=node('button',text,'btn-action btn-light'); e.id=id; e.type='button'; e.disabled=off; e.addEventListener('click',fn); return e; }
  function dayCards(values, q, selectable) {
    const group=node('div',undefined,'appointment-day-cards');
    for(const value of values || []) {
      const card=node(selectable?'button':'div',undefined,`appointment-day-card${value===5?' saturday':value===6?' sunday':''}`);
      card.id=selectable?`appointment-choice-${value}`:`appointment-day-${value}`;
      card.append(node('strong',days[value]?.slice(0,1) || String(value)),node('span','요일'));
      card.setAttribute('aria-label',label('day',value));
      if(selectable){card.type='button';card.disabled=disabled()||q.phase!=='answer'||left()<=0;card.addEventListener('click',()=>send('answer',{question_id:q.id,choice:value}));}
      group.append(card);
    }
    return group;
  }
  function busCards(values, q, selectable) {
    const group=node('div',undefined,'appointment-bus-cards');
    for(const value of values || []) {
      const card=node(selectable?'button':'div',undefined,'appointment-bus-card');
      if(selectable){card.id=`appointment-choice-${value}`;card.type='button';card.disabled=disabled()||q.phase!=='answer'||left()<=0;card.addEventListener('click',()=>send('answer',{question_id:q.id,choice:value}));}
      card.setAttribute('aria-label',label('bus',value));
      card.append(node('span','🚌'),node('strong',`${value}번`));group.append(card);
    }
    return group;
  }
  function placeMap(q) {
    const map=node('div'); map.id='appointment-map'; map.setAttribute('aria-label','16개 장소 지도');
    Object.assign(map.style,{position:'relative',width:'100%',maxWidth:'520px',aspectRatio:'520 / 350',background:'#585e66',borderRadius:'12px',overflow:'hidden',margin:'1rem auto'});
    const answering=q.phase==='answer'||q.phase==='timeout';
    for(let i=0;i<16;i++){
      const selectable=answering && (q.choices||[]).includes(i);
      const highlighted=!answering && (q.person||[]).includes(i);
      const tile=node(selectable?'button':'div'); tile.id=selectable?`appointment-choice-${i}`:`appointment-place-${i}`;
      tile.className=`appointment-place${highlighted?' highlight':''}`;
      const col=i%4,row=Math.floor(i/4), x=[7,120,293,406][col],y=[6,81,200,275][row];
      Object.assign(tile.style,{position:'absolute',left:`${x/520*100}%`,top:`${y/350*100}%`,width:`${107/520*100}%`,height:`${69/350*100}%`,padding:'0',border:highlighted?'4px solid #32a75b':'2px solid #e7eee8',borderRadius:'5px',background:'#e3e7e1',overflow:'hidden',opacity:!answering&&!highlighted?'0.48':'1'});
      // placeArt is static trusted source artwork indexed only by the local 0–15 loop.
      tile.innerHTML=placeArt(i);
      if(tile.firstElementChild){tile.firstElementChild.style.width='100%';tile.firstElementChild.style.height='100%';}
      if(selectable){tile.type='button';tile.disabled=disabled()||q.phase!=='answer'||left()<=0;tile.setAttribute('aria-label',`장소 ${i+1}`);tile.addEventListener('click',()=>send('answer',{question_id:q.id,choice:i}));const n=node('span',String(i+1));Object.assign(n.style,{position:'absolute',right:'3px',bottom:'2px',background:'#fff',color:'#222',borderRadius:'3px',padding:'0 3px'});tile.append(n);}
      else tile.setAttribute('aria-label',`장소 ${i+1}${highlighted?' 표시됨':''}`);
      map.append(tile);
    }
    return map;
  }
  function save() { try { window.sessionStorage.setItem(key(state.scope),JSON.stringify({pending:state.pending})); return true; } catch (_) {state.error='임시 저장 공간을 사용할 수 없습니다. 브라우저 설정을 확인해 주세요.'; return false;} }
  function render() {
    if(!root)return;
    root.replaceChildren(); root.hidden = !state.scope || state.run?.flow_version !== 'five-game-v2' || !ready();
    if(root.hidden)return;
    const heading=node('h2','3–5. 약속 기억 게임'); root.append(heading);
    root.append(node('p','요일 → 장소 → 버스 순서로 각 10문항을 진행합니다. 난이도는 세 게임에 한 번만 선택합니다.'));
    if(state.error){const e=node('p',state.error,'error');e.setAttribute('role','alert');root.append(e);}
    if(state.pending)root.append(button('appointment-retry','같은 요청 다시 시도',()=>task(sendPending),state.busy));
    else if(state.error)root.append(button('appointment-refresh','서버 상태 다시 불러오기',()=>task(fetchCurrent),state.busy));
    if(!state.loaded){root.append(button('appointment-refresh','서버 상태 다시 불러오기',()=>task(fetchCurrent),state.busy)); lock();return;}
    if(!data()?.difficulty){root.append(node('p','난이도를 선택해 주세요. 쉬움은 제시 시간이 각 3초, 어려움은 각 1.5초입니다.'));root.append(button('appointment-easy','쉬움',()=>send('configure',{difficulty:'easy'}),disabled()),button('appointment-hard','어려움',()=>send('configure',{difficulty:'hard'}),disabled()));lock();return;}
    const game=current();
    for(const g of games()) root.append(node('p',`${names[g.type]} · ${g.status === 'complete' ? '완료' : g.status === 'active' ? '진행 중' : '대기'} · ${g.questions.length}/10문항 · ${g.score}점`));
    if(!game){root.append(node('p','세 게임을 모두 완료했습니다.'),button('appointment-interview','면접 연습으로 이동',()=>navigateTab('interview'),disabled()));lock();return;}
    root.append(node('h3',names[game.type]));
    root.append(node('p',`난이도: ${data().difficulty === 'easy' ? '쉬움' : '어려움'} · 서버 저장 점수: ${game.score}점`));
    const q=game.current_question, last=game.questions.at(-1);
    if(!q && game.status==='pending') root.append(button('appointment-start',`${names[game.type]} 시작`,()=>send('start',{game_type:game.type}),disabled()));
    else if(!q && last){
      const result={correct:'정답',wrong:'오답',timeout:'시간 초과'}[last.outcome] || last.outcome;
      root.append(node('p',`${last.number || game.questions.length}번 문항: ${result} · 정답 ${label(game.type,last.answer)}${last.selection == null ? '' : ' · 선택 '+label(game.type,last.selection)}`));
      root.append(button('appointment-next',game.questions.length===10?'게임 결과 확인':'다음 문항',()=>send('next',{question_id:last.id}),disabled()));
    } else if(q){
      root.append(node('p',`${q.number} / 10문항`)); const clock=node('p','','');clock.id='appointment-timer';root.append(clock);
      if(q.phase==='countdown')root.append(node('p','준비하세요. A → B → C 순서로 정보를 보여 드립니다.'));
      if(q.phase==='reveal') {root.append(node('h4',`${['A','B','C'][q.person_index]}의 정보`));if(game.type==='place')root.append(node('p','초록색 테두리의 장소를 기억해 주세요.'),placeMap(q));else if(game.type==='day')root.append(dayCards(q.person,q,false));else root.append(busCards(q.person,q,false));}
      if(q.phase==='answer' || q.phase==='timeout') {
        root.append(node('h4',game.type==='bus'?'아무도 타지 않는 버스는?':game.type==='day'?'모두가 원하는 공통 요일은?':'모두가 원하는 공통 장소는?'));
        if(game.type==='place')root.append(placeMap(q));else if(game.type==='day')root.append(dayCards(q.choices,q,true));else root.append(busCards(q.choices,q,true));
      }
      updateClock();
    }
    lock();
  }
  function lock(){if(state.scope)window.AstraPractice.setAppointmentGameLock({...state.scope,locked:state.busy || !!state.pending || games().some(g=>g.status==='active')});}
  function left(){return Math.max(0,state.remaining-(performance.now()-state.sampledAt));}
  function updateClock(){const e=document.getElementById('appointment-timer');if(e)e.textContent=`남은 시간 ${Math.ceil(left()/1000)}초`;}
  function accept(run){if(!state.scope || run?.user_id!==state.scope.user_id || run?.run_id!==state.scope.run_id || !Number.isInteger(run.revision))throw Error('wrong_run');state.run=run;window.AstraPractice.updateRun(run);}
  async function fetchCurrent(allow){const requestedAt=performance.now();const result=await api(path());if(!allow())return;const receivedAt=performance.now();accept(result.run);const q=current()?.current_question;state.sampledAt=receivedAt;state.remaining=Math.max(0,(Number(q?.remaining_ms)||0)-Math.max(0,receivedAt-requestedAt));state.loaded=true;state.boundary=false;render();}
  async function sendPending(allow){if(!state.pending)return;const body=structuredClone(state.pending);try{const run=await api(path(),{method:'POST',body});if(!allow())return;accept(run);state.pending=null;save();await fetchCurrent(allow);}catch(e){if(!allow())return;if(e.status>=400 && e.status<500 && ![401,404,410].includes(e.status)){await fetchCurrent(allow);if(!allow())return;state.pending=null;save();if(body.action==='timeout')state.boundary=true;state.error='요청이 적용되지 않아 서버의 최신 상태를 확인했습니다. 현재 상태에서 이어가 주세요.';return;}throw e;}}
  async function task(fn){if(!state.scope || state.busy)return;const epoch=state.epoch;state.busy=true;state.error='';render();try{await fn(()=>state.epoch===epoch);}catch(e){if(epoch!==state.epoch)return;if([401,404,410].includes(e.status)||e.message==='wrong_run'){const scope={...state.scope};if(e.status!==401)try{window.sessionStorage.removeItem(key(scope));}catch(_){}window.AstraPractice.invalidateRun(scope);if(e.status===401||e.message==='wrong_run')window.AstraAuth?.recheck();state.error='로그인 또는 회차 상태를 다시 확인해 주세요.';}else state.error='서버 응답을 확인하지 못했습니다. 보관된 요청을 같은 내용으로 다시 시도해 주세요.';}finally{if(epoch===state.epoch){state.busy=false;render();}}}
  function send(action,values={}){if(disabled() || !ready())return;return task(async allow=>{state.pending={action,...values,expected_revision:state.run.revision,idempotency_key:crypto.randomUUID()};if(!save()){state.pending=null;return;}render();await sendPending(allow);});}
  function tick(){updateClock();const q=current()?.current_question;if(!q||left()>0||disabled()||state.boundary)return;state.boundary=true;if(q.phase==='timeout')return send('timeout',{question_id:q.id});const epoch=state.epoch;return task(fetchCurrent).then(()=>{if(epoch!==state.epoch)return;const latest=current()?.current_question;if(latest?.phase==='timeout' && !state.pending && !state.error)send('timeout',{question_id:latest.id});});}
  function changed(context){const scope=context.user&&context.run?{user_id:context.user.user_id,run_id:context.run.run_id}:null;const same=scope&&state.scope&&scope.user_id===state.scope.user_id&&scope.run_id===state.scope.run_id;state.context=context;if(same){if(context.run.revision>=state.run.revision)state.run=context.run;render();return;}state.epoch++;state.scope=scope;state.run=context.run;state.busy=false;state.loaded=false;state.pending=null;state.error='';state.boundary=false;if(state.timer!==null)clearInterval(state.timer);state.timer=null;render();if(!scope||context.run.flow_version!=='five-game-v2')return;try{state.pending=JSON.parse(window.sessionStorage.getItem(key(scope))||'{}').pending||null;}catch(_){state.error='임시 진행 상태를 읽지 못했습니다.';render();return;}task(fetchCurrent);state.timer=setInterval(tick,200);}
  document.addEventListener('DOMContentLoaded',()=>{root=document.getElementById('appointment-games');if(!root)return;api=window.AstraClient.createApi();window.AstraPractice.subscribe(changed);});
})();
