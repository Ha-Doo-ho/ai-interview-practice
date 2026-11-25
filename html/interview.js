/* Basic text interview persistence. Server-confirmed answers remain evidence;
   drafts and uncertain requests are scoped to the owned run in this tab. */
(function () {
  'use strict';
  const $ = id => document.getElementById(id);
  const state = {scope: null, run: null, context: null, epoch: 0, loaded: false, loadFailed: false, busy: false,
    journal: {drafts: {}, pending: null, rejected: null}, storageOK: true, lastScope: null};
  let api;
  const path = () => `/runs/${encodeURIComponent(state.scope.run_id)}`;
  const storageKey = scope => `astra.interview.v1:${scope.user_id}:${scope.run_id}`;
  const baselineQuestions = () => (state.run?.questions || []).filter(question =>
    question.question_mode === 'baseline' && question.conditioned_on_prior_evidence === false);
  const followupQuestions = () => (state.run?.evidence_linkage?.questions || []).filter(question =>
    question.question_mode === 'adaptive_followup' && question.conditioned_on_prior_evidence === true &&
    (state.run?.questions||[]).some(saved=>saved.question_id===question.question_id&&saved.question_version===question.question_version));
  const supplementalQuestions = () => (state.run?.questions || []).filter(question =>
    question.question_mode === 'supplemental');
  const supplementalGroups = {
    'working-memory-interview-v1': {label:'요청 변경',prefix:'wm-experience',count:5},
    'spatial-work-interview-v1': {label:'공간 배치',prefix:'spatial-work-experience',count:4},
    'repeated-work-interview-v1': {label:'반복 업무'},
    'repeated-work-interview-v2': {label:'반복 업무'}
  };
  const currentSetVersion='curated-work-interview-v2';
  const currentSupplementalIds=['wm-experience-0','wm-experience-3','spatial-work-experience-0',
    'repeated-work-experience-v2-0','repeated-work-experience-v2-1'];
  const supplementalMissing = () => {
    const ids=new Set(supplementalQuestions().map(q=>q.question_id));
    return state.run?.supplemental_interview_set_version!==currentSetVersion || currentSupplementalIds.some(id=>!ids.has(id));
  };
  const displayedQuestions = () => [...baselineQuestions(),...supplementalQuestions(),...followupQuestions()];
  const questionUpgradePending=()=>state.run?.status!=='completed'&&supplementalQuestions().length>0&&state.run?.supplemental_interview_set_version!==currentSetVersion;
  const staleQuestion = questionId => Boolean(state.run?.evidence_linkage_stale &&
    (state.run?.questions||[]).some(q=>q.question_id===questionId&&q.question_mode==='adaptive_followup'));
  const latest = questionId => window.AstraClient.latestAnswer(state.run || {records: []}, questionId);
  const currentCount = () => baselineQuestions().filter(question => latest(question.question_id)).length;
  const gamesIncomplete = () => state.run?.flow_version === 'five-game-v2' && (
    ['rsp','card'].some(type => (state.run?.rule_games?.games?.[type]?.rounds || []).filter(r=>r.status==='completed').length!==3) ||
    (state.run?.appointment_games?.games || []).filter(g=>g.status==='complete' && g.questions?.length===10).length!==3);
  const writeBlocked = () => !state.loaded || !state.scope || state.busy || Boolean(state.journal.pending) ||
    Boolean(state.journal.rejected) || !state.storageOK || state.context?.busy || state.context?.locked ||
    state.context?.gameLocked || state.context?.reportLocked || gamesIncomplete() || questionUpgradePending() || state.run?.status === 'completed';

  function element(tag, text, className) {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = text;
    if (className) node.className = className;
    return node;
  }
  function notice(text = '') {
    $('interview-error').textContent = text;
    $('interview-error').hidden = !text;
  }
  function validJournal(value) {
    const journal = value && typeof value === 'object' && !Array.isArray(value) ? value : {};
    const drafts = journal.drafts && typeof journal.drafts === 'object' && !Array.isArray(journal.drafts) ? journal.drafts : {};
    return {drafts, pending: journal.pending && typeof journal.pending === 'object' ? journal.pending : null,
      rejected: journal.rejected && typeof journal.rejected === 'object' ? journal.rejected : null};
  }
  function persist() {
    if (!state.scope) return false;
    try {
      window.sessionStorage.setItem(storageKey(state.scope), JSON.stringify(state.journal));
      state.storageOK = true;
      return true;
    } catch (_) {
      state.storageOK = false;
      notice('임시 저장 공간을 사용할 수 없습니다. 브라우저 저장 설정을 확인해 주세요. 초안을 안전하게 보관할 수 있을 때까지 제출할 수 없습니다.');
      return false;
    }
  }
  function readJournal() {
    try {
      state.journal = validJournal(JSON.parse(window.sessionStorage.getItem(storageKey(state.scope)) || '{}'));
      state.storageOK = true;
      // Probe before enabling writes: a frozen retry body must be durable before a POST.
      persist();
    } catch (_) {
      state.journal = {drafts: {}, pending: null, rejected: null};
      state.storageOK = false;
      notice('임시 저장 상태를 읽을 수 없습니다. 서버에 저장된 답변만 확인할 수 있습니다.');
    }
  }
  function clearUserJournals(userId, fallbackScope) {
    try {
      const prefix = `astra.interview.v1:${userId}:`;
      if (Number.isInteger(window.sessionStorage.length) && typeof window.sessionStorage.key === 'function') {
        const keys = [];
        for (let index = 0; index < window.sessionStorage.length; index++) {
          const key = window.sessionStorage.key(index);
          if (key?.startsWith(prefix)) keys.push(key);
        }
        for (const key of keys) window.sessionStorage.removeItem(key);
      } else if (fallbackScope) window.sessionStorage.removeItem(storageKey(fallbackScope));
    } catch (_) {}
  }
  function checkedRun(run) {
    if (!run || run.user_id !== state.scope?.user_id || run.run_id !== state.scope?.run_id ||
        !Number.isInteger(run.revision) || !Array.isArray(run.records) || !Array.isArray(run.questions)) throw Error('wrong_run');
    return run;
  }
  function applyRun(run) {
    checkedRun(run);
    if (state.run && run.revision < state.run.revision) return false;
    state.run = run;
    window.AstraPractice.updateRun(run);
    render();
    return true;
  }
  function statusLabel(status) {
    return {asked_answered: '답변 저장', asked_no_text: '답변 없음', skipped: '건너뜀'}[status] || status;
  }
  function renderSaved() {
    $('interview-saved').replaceChildren();
    const archived=(state.run?.interview_question_history||[]).flatMap(item=>item.questions||[]);
    const questionById = new Map([...archived,...(state.run?.questions||[])].map(question => [question.question_id, question]));
    const activeIds=new Set((state.run?.questions||[]).map(q=>q.question_id));
    for (const record of state.run?.records || []) {
      if (record.source_type !== 'typed_answer' || !questionById.has(record.data?.question_id)) continue;
      const detail = element('details');
      const question = questionById.get(record.data.question_id);
      const questionText = record.data.question_text_snapshot || question.question_text;
      detail.append(element('summary', `${activeIds.has(question.question_id)?'':'이전 문항 기록 · '}${questionText} · ${statusLabel(record.data.status)} · 버전 ${record.data.answer_version}`));
      const body = element('pre', record.data.status === 'asked_answered' ? record.data.text : statusLabel(record.data.status), 'interview-saved-text');
      detail.append(body);
      if(question.conditioned_on_prior_evidence===true)detail.append(element('p','조건부 후속 자기보고 · 중립 기본 면접과 별도','survey-help'));
      $('interview-saved').append(detail);
    }
    for(const [id,draft] of Object.entries(state.journal.drafts)){
      if(activeIds.has(id)||!String(draft.text??''))continue;
      const detail=element('details');
      detail.append(element('summary','이전 문항의 임시 입력 · '+(questionById.get(id)?.question_text||'보존된 입력')));
      detail.append(element('pre',String(draft.text),'interview-saved-text'));
      $('interview-saved').append(detail);
    }
  }
  function baseFor(questionId) {
    const record = latest(questionId)?.data;
    return record ? {answer_id: record.answer_id, answer_version: record.answer_version} : null;
  }
  function publishDrafts() {
    if(!state.scope)return;
    const activeIds=new Set(displayedQuestions().map(q=>q.question_id));
    const count=Object.entries(state.journal.drafts).filter(([questionId,draft])=>activeIds.has(questionId)&&String(draft.text??'')!==(latest(questionId)?.data.text||'')).length;
    window.AstraPractice.setInterviewDraftState?.({...state.scope,count});
  }
  function sameBase(draft, record) {
    const data = record?.data;
    return data ? draft.base_answer_id === data.answer_id && draft.base_answer_version === data.answer_version :
      draft.base_answer_id == null && draft.base_answer_version == null;
  }
  function updateRow(index, questionId) {
    const textarea = $(`interview-answer-${index}`);
    if (!textarea) return;
    const blocked = writeBlocked() || staleQuestion(questionId);
    const nonblank = Boolean(textarea.value.trim());
    textarea.disabled = blocked;
    $(`interview-save-${index}`).disabled = blocked || !nonblank;
    $(`interview-skip-${index}`).disabled = blocked || nonblank;
    $(`interview-empty-${index}`).disabled = blocked || nonblank;
  }
  function updateAllRows() {
    displayedQuestions().forEach((question, index) => updateRow(index, question.question_id));
  }
  function renderQuestions() {
    $('interview-items').replaceChildren();
    $('interview-followups')?.replaceChildren();
    $('interview-supplemental')?.replaceChildren();
    displayedQuestions().forEach((question, index) => {
      const conditioned=question.conditioned_on_prior_evidence===true;
      const supplemental=question.question_mode==='supplemental';
      if(conditioned&&!$('interview-followups'))return;
      if(supplemental&&!$('interview-supplemental'))return;
      const card = element('section', undefined, 'interview-q-group');
      const groupLabel=supplementalGroups[question.question_group]?.label||'업무';
      const followupNumber=supplementalQuestions().filter(q=>q.parent_question_id===question.parent_question_id)
        .findIndex(q=>q.question_id===question.question_id)+1;
      const label=conditioned?'조건부 후속 질문 '+(followupQuestions().findIndex(q=>q.question_id===question.question_id)+1):
        supplemental&&state.run?.supplemental_interview_set_version!==currentSetVersion?
          (question.parent_question_id?groupLabel+' 후속 질문 '+followupNumber:groupLabel+' 경험 질문'):'질문 '+(index+1);
      card.append(element('h3', `${label}. ${question.question_text}`, 'q-label-title'));
      if(supplemental)card.append(element('p',question.parent_question_id?
        '위 경험 질문에서 설명한 같은 사례를 이어서 답해 주세요.':'직장·학업·일상에서 경험한 사례로 답할 수 있습니다. 해당 경험이 없으면 건너뛸 수 있습니다.','survey-help'));
      if(conditioned){
        card.append(element('p','선택 후속 질문 · 사전 근거를 공개한 후의 답변은 중립 기본 면접 추출과 별도로 저장됩니다.','survey-help'));
        card.append(element('p',`질문 조건: ${question.question_mode} · conditioned_on_prior_evidence=true · ${question.question_id}@${question.question_version}`,'survey-help'));
        if(question.disclosed_prior_information)card.append(element('p',`공개된 사전 정보: ${typeof question.disclosed_prior_information==='string'?question.disclosed_prior_information:JSON.stringify(question.disclosed_prior_information)}`,'survey-help'));
        if((question.generated_from_evidence_refs||[]).length)card.append(element('p',`생성 근거 출처: ${JSON.stringify(question.generated_from_evidence_refs)}`,'survey-help'));
        if(state.run?.evidence_linkage_stale)card.append(element('p','이 질문은 이전 입력 기준입니다. 보고서에서 근거 연결을 갱신해 주세요.','survey-help'));
      }
      const saved = latest(question.question_id)?.data;
      const draft = state.journal.drafts[question.question_id];
      const textarea = element('textarea');
      textarea.setAttribute('id', `interview-answer-${index}`);
      textarea.setAttribute('aria-label', `질문 ${index + 1} 답변`);
      textarea.className = 'textarea-box';
      textarea.value = draft ? String(draft.text ?? '') : saved?.text || '';
      textarea.addEventListener('input', () => {
        const existing = state.journal.drafts[question.question_id];
        const base = existing ? {answer_id: existing.base_answer_id, answer_version: existing.base_answer_version} : baseFor(question.question_id);
        state.journal.drafts[question.question_id] = {text: textarea.value,
          base_answer_id: base?.answer_id ?? null, base_answer_version: base?.answer_version ?? null};
        persist();
        updateAllRows();
        publishDrafts();
      });
      card.append(textarea);
      const actions = element('div', undefined, 'practice-actions');
      const save = element('button', saved ? '수정 답변 저장' : '답변 저장', 'btn-action btn-gradient');
      save.setAttribute('id', `interview-save-${index}`); save.type = 'button';
      save.addEventListener('click', () => submit(question.question_id, index, 'asked_answered'));
      const empty = element('button', '답변 없이 기록', 'btn-action btn-light');
      empty.setAttribute('id', `interview-empty-${index}`); empty.type = 'button';
      empty.addEventListener('click', () => submit(question.question_id, index, 'asked_no_text'));
      const skip = element('button', '이 문항 건너뛰기', 'btn-action btn-light');
      skip.setAttribute('id', `interview-skip-${index}`); skip.type = 'button';
      skip.addEventListener('click', () => submit(question.question_id, index, 'skipped'));
      actions.append(save, empty, skip); card.append(actions); $(conditioned?'interview-followups':supplemental?'interview-supplemental':'interview-items').append(card);
      updateRow(index, question.question_id);
    });
  }
  function render() {
    const hasScope = Boolean(state.scope);
    $('interview-status').textContent = !hasScope ? '설문 화면에서 로그인한 계정의 연습 회차를 선택해 주세요.' :
      !state.loaded ? (state.loadFailed ? '기본 면접 질문을 불러오지 못했습니다.' : '기본 면접 질문과 저장 기록을 불러오는 중입니다.') :
      gamesIncomplete() ? '다섯 게임을 모두 완료한 뒤 기본 면접을 시작해 주세요.' :
      questionUpgradePending() ? '면접 질문 목록을 갱신하고 있습니다. 완료되지 않으면 저장된 면접 다시 불러오기를 눌러 주세요.' :
      `현재 회차: ${state.scope.run_id} · ${state.journal.pending ? '제출 결과 확인 대기' : state.busy ? '서버 저장 확인 중' : '서버 기록 연결됨'}`;
    const count = state.loaded ? currentCount() : 0;
    const total = state.loaded ? baselineQuestions().length : 0;
    $('interview-progress').textContent = `서버 저장 ${count} / ${total}문항`;
    const supplemental=state.loaded?supplementalQuestions():[];
    if($('interview-supplemental-progress'))$('interview-supplemental-progress').textContent=supplemental.length?
      `업무 경험 면접 저장 ${supplemental.filter(q=>latest(q.question_id)).length} / ${supplemental.length}문항 · 선택 답변`:
      state.run?.status==='completed'?'이 회차에는 업무 경험 면접 문항이 없습니다. 새 회차에서 답할 수 있습니다.':'기존 회차에는 아래 버튼으로 업무 경험 면접 문항을 추가할 수 있습니다.';
    if($('interview-supplemental-add')){
      $('interview-supplemental-add').hidden=!supplementalMissing()||state.run?.status==='completed';
      $('interview-supplemental-add').disabled=writeBlocked();
    }
    if($('interview-followup-progress')){const followups=state.loaded?followupQuestions():[];const answered=followups.filter(q=>latest(q.question_id)).length;$('interview-followup-progress').textContent=followups.length?`조건부 후속 저장 ${answered} / ${followups.length}문항 · 미응답도 최종 보고서에 명시됩니다.`:'보고서에서 근거 연결·후속 질문 만들기를 요청하면 선택 질문이 표시됩니다.';}
    $('interview-refresh').disabled = !hasScope || state.busy || Boolean(state.context?.reportLocked);
    $('interview-retry').hidden = !state.journal.pending;
    $('interview-retry').disabled = state.busy || !state.loaded || !state.storageOK;
    $('interview-resolve').hidden = !state.journal.rejected;
    $('interview-resolve').disabled = state.busy || !state.loaded || !state.storageOK;
    $('interview-complete').hidden = !(state.loaded && total > 0 && count === total);
    $('interview-complete').textContent = count === total && total > 0 ? `기본 면접 ${total}문항이 모두 서버에 저장되었습니다.` : '';
    if (state.loaded) { renderQuestions(); renderSaved(); }
    else { $('interview-items').replaceChildren(); $('interview-saved').replaceChildren();$('interview-followups')?.replaceChildren();$('interview-supplemental')?.replaceChildren(); }
    if (state.scope) window.AstraPractice.setInterviewLock({...state.scope, locked: state.busy || Boolean(state.journal.pending)});
    publishDrafts();
  }
  async function work(action) {
    if (!state.scope || state.busy || state.context?.reportLocked) return;
    const epoch = state.epoch;
    state.busy = true;
    if (!state.loaded) state.loadFailed = false;
    if (state.storageOK) notice();
    render();
    try { await action(() => epoch === state.epoch); }
    catch (error) {
      if (epoch !== state.epoch) return;
      if (error.status === 401 || error.status === 404 || error.status === 410 || error.message === 'wrong_run') {
        const previous = state.scope ? {...state.scope} : null;
        if (previous && error.status !== 401) {
          try { window.sessionStorage.removeItem(storageKey(previous)); } catch (_) {}
        }
        state.loaded = false; state.run = null;
        if (previous) window.AstraPractice.invalidateRun(previous);
        if (error.status === 401 || error.message === 'wrong_run') window.AstraAuth?.recheck();
        notice('로그인 또는 회차 상태를 확인할 수 없습니다. 설문 화면에서 저장된 회차를 다시 확인해 주세요.');
      } else {
        if (!state.loaded) state.loadFailed = true;
        notice(state.journal.pending ?
          '서버 처리 결과를 확인하지 못했습니다. 입력은 보존되어 있습니다. 같은 요청 다시 시도를 눌러 주세요.' :
          '면접 질문과 저장 기록을 불러오지 못했습니다. 서버 연결을 확인하고 저장된 면접 다시 불러오기를 눌러 주세요. 작성 중인 입력은 보존됩니다.');
      }
    } finally {
      if (epoch === state.epoch) { state.busy = false; render(); }
    }
  }
  async function fetchCurrent(allow) {
    let run = await api(path());
    if (!allow()) return;
    checkedRun(run);
    for(let attempt=0;attempt<2 && run.status!=='completed' && run.supplemental_interview_set_version!==currentSetVersion &&
        run.questions.some(q=>q.question_mode==='supplemental') && !state.journal.pending && !state.journal.rejected &&
        !state.context?.reportLocked && !state.context?.gameLocked && !state.context?.locked && !state.context?.busy;attempt++){
      try{
        run=await api(path()+'/supplemental-interview',{method:'POST',body:{expected_revision:run.revision,idempotency_key:crypto.randomUUID()}});
      }catch(error){
        if(error.status!==409||error.code!=='revision_conflict'||attempt===1)throw error;
        run=await api(path());
      }
      if(!allow())return;checkedRun(run);
    }
    state.loaded = true; applyRun(run);
  }
  function draftFor(questionId, index) {
    let draft = state.journal.drafts[questionId];
    if (!draft) {
      const base = baseFor(questionId);
      draft = {text: $(`interview-answer-${index}`).value, base_answer_id: base?.answer_id ?? null,
        base_answer_version: base?.answer_version ?? null};
      state.journal.drafts[questionId] = draft;
    }
    return draft;
  }
  function buildPayload(questionId, index, status) {
    const draft = draftFor(questionId, index);
    if (status !== 'asked_answered' && draft.text.trim()) throw Error('draft_not_empty');
    const current = latest(questionId);
    if (!sameBase(draft, current)) throw Error('draft_base_changed');
    // answerPayload supplies the immutable predecessor reference and preserves
    // exact text for answered submissions.
    return window.AstraClient.answerPayload(state.run, questionId, draft.text, status);
  }
  function submit(questionId, index, status) {
    if (writeBlocked() || staleQuestion(questionId)) return;
    let payload;
    try { payload = buildPayload(questionId, index, status); }
    catch (error) {
      if (error.message === 'draft_base_changed') {
        state.journal.rejected = {question_id: questionId, status}; persist(); render();
        notice('다른 화면에서 이 답변이 바뀌었습니다. 서버 저장본과 보존된 입력을 확인한 뒤 “최신 저장본 확인 후 입력 이어가기”를 눌러 주세요.');
      } else notice(error.message === 'draft_not_empty' ? '작성 중인 글을 비운 뒤 답변 없음 또는 건너뛰기를 선택해 주세요.' : '답변 내용을 입력해 주세요.');
      return;
    }
    const body = {...payload, expected_revision: state.run.revision, idempotency_key: crypto.randomUUID()};
    state.journal.pending = {question_id: questionId, status, body};
    if (!persist()) { state.journal.pending = null; render(); return; }
    return work(allow => sendPending(allow, false));
  }
  async function sendPending(allow, retrying) {
    const pending = structuredClone(state.journal.pending);
    try {
      const run = await api(`${path()}/answers`, {method: 'POST', body: pending.body});
      if (!allow()) return;
      checkedRun(run);
      state.journal.pending = null; state.journal.rejected = null;
      delete state.journal.drafts[pending.question_id];
      persist(); applyRun(run);
      if (retrying || (run.status!=='completed'&&run.supplemental_interview_set_version!==currentSetVersion&&
          run.questions.some(q=>q.question_mode==='supplemental'))) await fetchCurrent(allow);
    } catch (error) {
      if (!allow()) return;
      const definitive = error.status >= 400 && error.status < 500 && ![401,404,410].includes(error.status);
      if (definitive) {
        state.journal.pending = null;
        persist();
        await fetchCurrent(allow);
        if (!allow()) return;
        const correctionConflict = error.status === 409 &&
          ['revision_conflict','answer_version_conflict','record_already_submitted','stale_after_finalize','idempotency_conflict'].includes(error.code);
        state.journal.rejected = correctionConflict ?
          {question_id: pending.question_id, status: pending.status, error: error.code} : null;
        persist(); render();
        notice(correctionConflict ?
          '서버의 최신 답변과 현재 입력이 충돌했습니다. 두 내용을 확인한 뒤 명시적으로 입력을 이어가 주세요.' :
          '요청 형식을 서버가 받아들이지 않았습니다. 입력은 보존되어 있습니다. 내용을 확인하고 수정한 뒤 새로 저장해 주세요.');
      } else throw error;
    }
  }
  function resolveRejected() {
    if (!state.journal.rejected || state.busy || !state.storageOK) return;
    const rejected = {...state.journal.rejected};
    const questionIndex = displayedQuestions().findIndex(question => question.question_id === rejected.question_id);
    if (questionIndex < 0) {
      state.journal.rejected=null;
      if(!persist())return;
      render();notice('이전 문항의 입력을 저장 기록 아래에 보존했습니다. 현재 질문에 이어서 답할 수 있습니다.');
      return;
    }
    const draft = draftFor(rejected.question_id, questionIndex);
    const base = baseFor(rejected.question_id);
    draft.base_answer_id = base?.answer_id ?? null;
    draft.base_answer_version = base?.answer_version ?? null;
    state.journal.rejected = null;
    if (!persist()) return;
    render();
    notice('최신 서버 저장본을 기준으로 보존된 입력을 이어갑니다. 내용을 확인한 뒤 저장 버튼을 눌러 주세요.');
    if(questionUpgradePending())work(fetchCurrent);
  }
  function contextChanged(context) {
    const wasExternallyLocked=Boolean(state.context?.busy||state.context?.locked||state.context?.gameLocked||state.context?.reportLocked);
    const externallyUnlocked=wasExternallyLocked&&!context.busy&&!context.locked&&!context.gameLocked&&!context.reportLocked;
    const scope = context.user && context.run ? {user_id: context.user.user_id, run_id: context.run.run_id} : null;
    const same = scope && state.scope && scope.user_id === state.scope.user_id && scope.run_id === state.scope.run_id;
    const changed = same && (context.run.revision > (state.run?.revision ?? -1) || context.busy !== state.context?.busy ||
      context.locked !== state.context?.locked || context.gameLocked !== state.context?.gameLocked || context.reportLocked !== state.context?.reportLocked || context.run.status !== state.run?.status);
    state.context = context;
    if (same) {
      if (context.run.revision >= (state.run?.revision ?? -1)) state.run = context.run;
      if (changed) render();
      if(externallyUnlocked&&state.loaded&&!state.busy&&!state.journal.pending&&!state.journal.rejected&&
          context.run.status!=='completed'&&context.run.supplemental_interview_set_version!==currentSetVersion&&
          context.run.questions.some(q=>q.question_mode==='supplemental')&&
          !context.busy&&!context.locked&&!context.gameLocked&&!context.reportLocked)work(fetchCurrent);
      return;
    }
    const previous = state.scope;
    state.epoch++; state.scope = scope; state.run = context.run; state.loaded = false; state.loadFailed = false; state.busy = false;
    state.journal = {drafts: {}, pending: null, rejected: null}; state.storageOK = true;
    if (previous) state.lastScope = previous;
    if (context.authStatus === 'guest' && state.lastScope) {
      clearUserJournals(state.lastScope.user_id, state.lastScope); state.lastScope = null;
    }
    notice(); render();
    if (!scope) return;
    readJournal();
    work(fetchCurrent);
  }

  window.AstraInterview = {};
  document.addEventListener('DOMContentLoaded', () => {
    const bridge = window.AstraPractice;
    if (!['subscribe', 'updateRun', 'invalidateRun', 'setInterviewLock'].every(name => typeof bridge?.[name] === 'function') ||
        !['createApi', 'latestAnswer', 'answerPayload'].every(name => typeof window.AstraClient?.[name] === 'function')) {
      $('interview-status').textContent = '기본 면접 화면을 불러오지 못했습니다.';
      $('interview-refresh').disabled = true;
      notice('화면 파일 일부가 이전 버전이거나 불러오지 못했습니다. Ctrl + F5로 화면을 새로고침해 주세요. 저장된 설문과 게임 기록은 유지됩니다.');
      return;
    }
    api = window.AstraClient.createApi();
    $('interview-refresh').addEventListener('click', () => work(fetchCurrent));
    $('interview-retry').addEventListener('click', () => work(allow => sendPending(allow, true)));
    $('interview-resolve').addEventListener('click', resolveRejected);
    $('interview-supplemental-add')?.addEventListener('click', () => {
      if(writeBlocked())return;
      work(async allow=>{
        // Reconcile a lost add response before retrying; adding is set-like on the server.
        await fetchCurrent(allow);
        if(!allow()||!supplementalMissing()||state.run?.status==='completed')return;
        const run=await api(path()+'/supplemental-interview',{method:'POST',body:{
          expected_revision:state.run.revision,idempotency_key:crypto.randomUUID()}});
        if(allow())applyRun(run);
      });
    });
    window.AstraPractice.subscribe(contextChanged);
  });
})();
