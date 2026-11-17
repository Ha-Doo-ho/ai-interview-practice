/* Account-owned runs. Session storage holds only this tab's pending survey work,
   never authentication tokens. Confirmed evidence is always fetched from server. */
(function () {
  'use strict';
  const $ = id => document.getElementById(id);
  const state = {user: null, auth: '', epoch: 0, busy: false, ready: false, definitions: null,
    runs: [], run: null, draft: null, timer: null, journal: {}, storageOK: true, lastUser: null, gameLocked: false, appointmentGameLocked: false, interviewLocked: false, reportLocked: false, interviewDrafts:0,error:''};
  const listeners = new Set();
  const publicState = () => ({user: state.user ? {...state.user} : null, run: state.run ? structuredClone(state.run) : null,
    error:state.error,interviewDrafts:state.interviewDrafts,runs: state.runs.map(run=>({run_id:run.run_id,user_id:run.user_id,revision:run.revision,status:run.status,created_at:run.created_at})),
    authStatus: state.auth.split(':')[0], ready: state.ready, busy: state.busy, gameLocked: gameLocked(), ruleGameLocked: state.gameLocked, appointmentGameLocked: state.appointmentGameLocked, aptitudeGameLocked: Boolean(state.aptitudeGameLocked), interviewLocked: state.interviewLocked, reportLocked: state.reportLocked,
    locked: Boolean(state.journal.active || state.journal.pending || state.journal.create)});
  let api;
  const gameLocked = () => state.gameLocked || state.appointmentGameLocked || Boolean(state.aptitudeGameLocked);
  const clock = () => performance.timeOrigin + performance.now();
  const key = user => 'astra.practice.v1:' + user.user_id;
  const records = () => (state.run?.records || []).filter(r => r.source_type === 'survey');
  const nextItem = () => state.definitions?.surveys.find(item => !records().some(r => r.item_id === item.item_id));
  const stopTimer = () => { if (state.timer !== null) clearInterval(state.timer); state.timer = null; };
  function notice(text = '') { state.error=text;$('practice-error').textContent = text; $('practice-error').hidden = !text; }
  function persist() {
    try { window.sessionStorage.setItem(key(state.user), JSON.stringify(state.journal)); state.storageOK = true; return true; }
    catch (_) { state.storageOK = false; notice('이 탭의 임시 저장 공간을 사용할 수 없습니다. 브라우저 저장 설정을 확인해 주세요. 서버에 이미 저장된 응답은 유지됩니다.'); return false; }
  }
  function readJournal() {
    try {
      const saved = JSON.parse(window.sessionStorage.getItem(key(state.user)) || '{}');
      state.journal = saved && typeof saved === 'object' && !Array.isArray(saved) ? saved : {};
      state.storageOK = true;
    } catch (_) { state.journal = {}; state.storageOK = false; notice('임시 진행 상태를 읽지 못했습니다. 저장된 회차를 다시 불러와 주세요.'); }
  }
  function controls() {
    const locked = !state.user || !state.ready || state.busy || state.reportLocked;
    const pending = Boolean(state.journal.pending || state.journal.create);
    const active = Boolean(state.journal.active);
    $('practice-new').disabled = locked || pending || active || !state.storageOK || gameLocked() || state.interviewLocked;
    $('practice-refresh').disabled = !state.user || state.busy || (active && state.ready) || gameLocked() || state.interviewLocked || state.reportLocked;
    $('practice-runs').disabled = locked || pending || active || !state.runs.length || gameLocked() || state.interviewLocked;
    $('practice-open').disabled = $('practice-runs').disabled;
    $('practice-retry').hidden = !pending;
    $('practice-retry').disabled = locked;
    $('practice-resolve').hidden = !(state.journal.pending && state.journal.rejected);
    $('practice-resolve').disabled = locked;
    $('practice-start-item').disabled = locked || pending || active || !state.storageOK || state.interviewLocked;
    $('practice-submit').disabled = locked || pending || !active || !state.storageOK;
    $('practice-skip').disabled = $('practice-submit').disabled;
    $('practice-game').disabled = locked || pending;
    if (state.draft?.card) state.draft.card.disabled = locked || pending;
    for (const listener of listeners) listener(publicState());
  }
  function checkedRun(run) {
    if (!run || run.user_id !== state.user?.user_id || typeof run.run_id !== 'string' ||
        !Number.isInteger(run.revision) || !Array.isArray(run.records)) throw Error('wrong_owner');
    return run;
  }
  function recordsLocked() { return !state.user||state.busy||gameLocked()||state.interviewLocked||state.reportLocked||Boolean(state.journal.active||state.journal.pending||state.journal.create); }
  function openRun(runId) {
    if(recordsLocked()||!state.ready||!state.runs.some(r=>r.run_id===runId))return;
    return work(async allow=>{
      const run=await api('/runs/'+encodeURIComponent(runId));
      if(allow()){acceptRun(run);navigateTab(run.status==='completed'?'report':'survey');}
    });
  }
  function refreshRuns() {
    if(recordsLocked())return;
    return work(load);
  }
  function deleteRun(runId) {
    if(recordsLocked()||!state.ready||!state.runs.some(r=>r.run_id===runId))return;
    return work(async allow=>{
      try { await api('/runs/'+encodeURIComponent(runId),{method:'DELETE'}); }
      catch(error){if(![404,410].includes(error.status))throw error;}
      if(!allow())return;
      state.runs=state.runs.filter(r=>r.run_id!==runId);
      for(const prefix of ['astra.interview.v1','astra.report.v1','astra.rule-games.v1','astra.appointment-games.v1']){try{window.sessionStorage.removeItem(`${prefix}:${state.user.user_id}:${runId}`);}catch(_) {}}
      if(state.run?.run_id===runId){state.journal.selectedId=null;state.journal.active=null;state.journal.pending=null;persist();resetDisplay();$('practice-status').textContent='선택한 회차를 삭제했습니다. 새 연습 또는 다른 회차를 선택해 주세요.';}
      runOptions();controls();
    });
  }
  function resetDisplay() {
    stopTimer(); state.run = null; state.draft = null; state.gameLocked = false; state.appointmentGameLocked = false; state.aptitudeGameLocked = false; state.interviewLocked = false; state.reportLocked = false;state.interviewDrafts=0;
    $('practice-items').replaceChildren(); $('practice-saved').replaceChildren();
    $('practice-survey').hidden = true; $('practice-runs').replaceChildren();
    $('practice-timer').textContent = ''; $('survey-form').hidden = false;
  }
  function runOptions() {
    $('practice-runs').replaceChildren();
    for (const run of state.runs) {
      const count = run.records.filter(r => r.source_type === 'survey').length;
      const option = surveyElement('option', '', `${new Date(run.created_at).toLocaleString('ko-KR')} · 설문 ${count}/6 · ${run.run_id.slice(0, 8)}`);
      option.value = run.run_id; $('practice-runs').append(option);
    }
    $('practice-runs').value = state.run?.run_id || state.runs[0]?.run_id || '';
  }
  function savedText(record) {
    const d = record.data;
    const missing = value => value || '응답 없음';
    if (record.context.response_type === 'ordinal_6') return missing(d.selected_label_snapshot);
    if (record.context.response_type === 'paired_perspective') return `나의 관점: ${missing(d.self.selected_label_snapshot)} / 내가 상상한 타인의 관점: ${missing(d.imagined_others.selected_label_snapshot)}`;
    if (record.context.response_type === 'bipolar_slider') return d.final_value === null ? '응답 없음' :
      `${d.final_value === 0 ? '중앙' : (d.final_value < 0 ? d.left_anchor_label : d.right_anchor_label) + ' 방향 ' + Math.abs(d.final_value) + '단계'} · ${d.explicit_confirmation ? '위치 확정함' : '위치 미확정'}`;
    return d.ranked_selection.map(r => `${r.rank}순위: ${d.candidate_snapshots.find(c => c.option_id === r.option_id)?.label || r.option_id}`).join(' / ') || '응답 없음';
  }
  function renderRun() {
    stopTimer(); state.draft = null;
    $('survey-form').hidden = true; $('survey-items').replaceChildren();
    $('survey-progress').textContent = '위의 내 연습 회차에서 응답하고 저장할 수 있습니다.';
    $('survey-preview-note').textContent = '실제 연습 회차를 선택했습니다. 이전 화면 체험 응답은 이 회차로 옮겨 저장하지 않습니다.';
    $('practice-survey').hidden = false;
    $('practice-status').textContent = `현재 회차: ${state.run.run_id}`;
    $('practice-items').replaceChildren(); $('practice-saved').replaceChildren();
    const saved = records();
    $('practice-progress').textContent = `서버 저장 ${saved.length} / ${state.definitions.surveys.length}문항`;
    for (const r of saved) {
      const detail = surveyElement('details');
      const status = {submitted: '응답 제출', timed_out: '시간 초과', skipped: '건너뜀'}[r.status] || r.status;
      detail.append(surveyElement('summary', '', `${r.data.prompt_snapshot} · ${status} · 저장됨`), surveyElement('p', '', savedText(r)));
      $('practice-saved').append(detail);
    }
    const next = nextItem();
    const complete = !next || state.run.status === 'completed';
    $('practice-start-item').hidden = complete;
    $('practice-start-item').textContent = next ? `${saved.length + 1}번 문항 시작 · ${next.time_limit_ms / 1000}초` : '설문 저장 완료';
    $('practice-submit').hidden = true; $('practice-skip').hidden = true;
    $('practice-game').hidden = Boolean(next);
    $('practice-timer').textContent = complete ? '저장된 응답을 펼쳐 확인할 수 있습니다.' : '문항 시작 버튼을 누르면 제한 시간이 시작됩니다.';
    if (state.journal.active) {
      const active = state.journal.active;
      if (active.run_id !== state.run.run_id || active.item_id !== next?.item_id || active.item_version !== next?.item_version) {
        state.journal.active = null; persist();
      } else showActive(next);
    }
    runOptions(); controls();
  }
  function acceptRun(run) {
    state.run = checkedRun(run);
    state.runs = [run, ...state.runs.filter(r => r.run_id !== run.run_id)];
    state.journal.selectedId = run.run_id; persist(); renderRun();
  }
  async function work(action) {
    if (!state.user || state.busy || state.reportLocked) return;
    const epoch = state.epoch;
    state.busy = true; notice(); controls();
    try { await action(() => state.epoch === epoch); }
    catch (error) {
      if (epoch !== state.epoch) return;
      if (error.status === 401 || error.code === 'current_user_changed' || error.message === 'wrong_owner') {
        resetDisplay(); state.runs=[];state.ready = false;
        notice('로그인 상태가 변경되었습니다. 로그인 상태를 다시 확인해 주세요.');
        window.AstraAuth.recheck();
      } else notice(error.message === 'storage_unavailable' ? '임시 저장 공간을 사용할 수 없습니다. 브라우저 저장 설정을 확인해 주세요.' :
        '서버 처리 결과를 확인하지 못했습니다. 입력을 유지하고 있습니다. 같은 요청 다시 시도 또는 저장된 회차 다시 불러오기를 눌러 주세요.');
    } finally { if (epoch === state.epoch) { state.busy = false; controls(); } }
  }
  async function load(allow) {
    const [definitions, result] = await Promise.all([api('/definitions'), api('/runs')]);
    if (!allow()) return;
    if (!Array.isArray(definitions.surveys) || !Array.isArray(result.runs)) throw Error('unreadable_response');
    state.definitions = definitions; state.runs = result.runs.map(checkedRun); state.ready = true;
    const selected = state.runs.find(r => r.run_id === state.journal.selectedId);
    if (selected) acceptRun(selected);
    else {
      state.journal.selectedId = null; state.journal.active = null;
      if (state.journal.pending) {
        state.journal.pending = null;
        notice('이전에 사용한 회차를 찾을 수 없습니다. 삭제되었을 수 있습니다. 저장된 회차 목록을 확인해 주세요.');
      }
      persist(); resetDisplay(); runOptions();
      $('practice-status').textContent = '새 연습을 시작하거나 저장된 회차를 선택해 주세요.';
    }
  }
  function newPractice() {
    if (!state.ready || state.journal.active || state.journal.pending || state.journal.create || gameLocked() || state.interviewLocked) return;
    return work(async allow => {
      state.journal.create = {idempotency_key: crypto.randomUUID(), expected_user_id: state.user.user_id, flow_version: 'five-game-v2'};
      if (!persist()) throw Error('storage_unavailable');
      await sendCreate(allow);
    });
  }
  async function sendCreate(allow) {
    const body = structuredClone(state.journal.create);
    let run;
    try { run = await api('/runs', {method: 'POST', body}); }
    catch (error) {
      if (allow() && error.status >= 400 && error.status < 500 && error.status !== 401) { state.journal.create = null; persist(); }
      throw error;
    }
    if (!allow()) return;
    checkedRun(run); state.journal.create = null; state.journal.selectedId = run.run_id; persist();
    const current = await api('/runs/' + encodeURIComponent(run.run_id));
    if (allow()) { acceptRun(current); navigateTab('survey'); }
  }
  function freshValues(item) {
    return item.type === 'bipolar_slider' ? {value: item.initial_value, touched: false, changes: 0, confirmed: false} :
      item.type === 'top_k_rank' ? {selected_ids: Array(item.requested_k).fill(''), selection_events: []} : {};
  }
  function startItem() {
    if (state.busy || !state.ready || state.journal.active || state.journal.pending || state.interviewLocked || state.reportLocked) return;
    const item = nextItem(); if (!item || state.run.status === 'completed') return;
    state.journal.active = {run_id: state.run.run_id, item_id: item.item_id, item_version: item.item_version, started: clock(), values: freshValues(item)};
    if (!persist()) { state.journal.active = null; controls(); return; }
    showActive(item); controls();
    state.draft.card.querySelector('input, select')?.focus();
  }
  function showActive(item) {
    const active = state.journal.active;
    state.draft = {item, values: active.values};
    const card = renderSurveyItem(state.draft, state.definitions.surveys.indexOf(item), changed, true, () => {
      if (!state.journal.active || state.busy || state.journal.pending) return false;
      if (elapsed() >= item.time_limit_ms) { tick(); return false; }
      return true;
    });
    $('practice-items').replaceChildren(card);
    $('practice-start-item').hidden = true; $('practice-submit').hidden = false; $('practice-skip').hidden = false;
    stopTimer(); state.timer = setInterval(tick, 200); tick();
  }
  function changed() {
    if (!state.journal.active || state.journal.pending) return;
    notice(); persist(); controls(); tick();
  }
  function elapsed() { return Math.max(0, Math.floor(clock() - state.journal.active.started)); }
  function tick() {
    if (!state.draft || !state.journal.active) return;
    const left = Math.max(0, state.draft.item.time_limit_ms - elapsed());
    $('practice-timer').textContent = `남은 시간 ${Math.ceil(left / 1000)}초`;
    if (left === 0 && !state.busy && !state.journal.pending && state.storageOK) return submitItem('timed_out');
  }
  function surveyResponse(item, values, status) {
    if (item.type === 'bipolar_slider') return {
      final_value: status === 'submitted' || values.touched || values.confirmed ? Number(values.value) : null,
      interaction_occurred: Boolean(values.touched), explicit_confirmation: Boolean(values.confirmed), change_count: values.changes || 0,
    };
    if (item.type !== 'top_k_rank') return window.AstraClient.buildSurveyResponse(item, status, values);
    // A partially filled rank keeps the actual slot numbers; do not compact a
    // second-place-only selection into first place on timeout.
    const selected = values.selected_ids;
    return {selected_ids: selected.filter(Boolean), ranked_selection: selected.flatMap((id, i) => id ? [{option_id: id, rank: i + 1}] : []),
      selection_events: (values.selection_events || []).flatMap(event => [
        ...(event.previous_option_id ? [{action: 'remove', option_id: event.previous_option_id, rank: event.rank, order: event.order}] : []),
        ...(event.option_id ? [{action: 'select', option_id: event.option_id, rank: event.rank, order: event.order}] : [])])};
  }
  function submitItem(status) {
    if (!state.draft || state.busy || state.journal.pending) return;
    if (elapsed() >= state.draft.item.time_limit_ms) status = 'timed_out';
    if (status === 'submitted' && !surveyComplete(state.draft)) {
      notice('응답을 확인해 주세요. 두 관점은 각각 선택하고, 슬라이더 위치를 확정하며, 순위는 서로 다른 항목으로 지정해 주세요.'); return;
    }
    const {item, values} = state.draft;
    return work(async allow => {
      state.journal.pending = {path: `/runs/${encodeURIComponent(state.run.run_id)}/surveys`, body: {
        item_id: item.item_id, item_version: item.item_version, status, elapsed_ms: elapsed(),
        response: surveyResponse(item, values, status), expected_revision: state.run.revision, idempotency_key: crypto.randomUUID()}};
      if (!persist()) throw Error('storage_unavailable');
      stopTimer(); controls(); await sendSurvey(allow);
    });
  }
  async function sendSurvey(allow) {
    const pending = structuredClone(state.journal.pending);
    try {
      const run = await api(pending.path, {method: 'POST', body: pending.body});
      if (!allow()) return;
      checkedRun(run); state.journal.pending = null; state.journal.active = null; state.journal.rejected = null; persist(); acceptRun(run);
    } catch (error) {
      if (!allow()) return;
      if (error.status === 409) {
        const current = await api('/runs/' + encodeURIComponent(state.run.run_id));
        if (!allow()) return;
        checkedRun(current); state.journal.pending = null; state.journal.rejected = null;
        const exists = current.records.some(r => r.source_type === 'survey' && r.item_id === pending.body.item_id);
        if (exists || current.status === 'completed') state.journal.active = null;
        persist(); acceptRun(current);
        notice(exists ? '이미 저장된 응답을 불러왔습니다. 서버의 원본을 확인해 주세요.' : '회차가 다른 화면에서 변경되었습니다. 입력을 유지했으니 응답을 확인하고 다시 저장해 주세요.');
      } else if (error.status === 404 || error.status === 410) {
        state.journal = {}; persist(); resetDisplay(); state.ready = false;
        notice('이 회차를 찾을 수 없습니다. 삭제되었을 수 있습니다. 저장된 회차를 다시 불러와 주세요.');
      } else if (error.status >= 400 && error.status < 500 && error.status !== 401) {
        // A definitive rejection can be explicitly reconciled; an uncertain
        // network result must retain its exact request for idempotent retry.
        state.journal.rejected = true; persist();
        notice('서버가 제출을 거부했습니다. 문항이 변경되었을 수 있습니다. 재시도해도 해결되지 않으면 ‘임시 응답을 버리고 회차 다시 불러오기’를 누르세요. 서버에 저장된 원본은 유지됩니다.');
      } else throw error;
    }
  }
  function retry() {
    return work(async allow => {
      if (!persist()) throw Error('storage_unavailable');
      if (state.journal.create) await sendCreate(allow);
      else if (state.journal.pending) await sendSurvey(allow);
    });
  }
  function resolveRejected() {
    if (!state.journal.pending || !state.journal.rejected || !state.run) return;
    return work(async allow => {
      const [definitions, run] = await Promise.all([api('/definitions'), api('/runs/' + encodeURIComponent(state.run.run_id))]);
      if (!allow()) return;
      checkedRun(run);
      if (!Array.isArray(definitions.surveys) || !definitions.surveys.length) throw Error('unreadable_response');
      state.definitions = definitions;
      state.journal.pending = null; state.journal.active = null; state.journal.rejected = null;
      persist(); acceptRun(run);
      notice('서버의 저장 상태를 확인했습니다. 임시 제출과 입력을 정리했으며, 저장된 응답은 유지됩니다. 남은 문항은 다시 시작해 주세요.');
    });
  }
  function sessionChanged(session) {
    const auth = session.status + ':' + (session.user?.user_id || '');
    if (state.auth === auth) return;
    state.auth = auth; state.epoch++; state.busy = false; state.ready = false;
    const hadRun = Boolean(state.run);
    resetDisplay(); state.runs = []; state.journal = {}; state.user = session.status === 'authenticated' ? session.user : null;
    if (session.status === 'guest' && state.lastUser) {
      try { window.sessionStorage.removeItem(key(state.lastUser)); } catch (_) {}
      state.lastUser = null;
    }
    if (state.user) state.lastUser = state.user;
    notice();
    $('practice-status').textContent = state.user ? '저장된 회차를 불러오는 중입니다.' : '로그인 후 새 연습을 시작할 수 있습니다.';
    controls();
    if (state.user) { readJournal(); work(load); }
    else if (hadRun) {
      $('survey-preview-note').textContent = '시간 제한 없는 화면 체험입니다. 이 화면의 답변은 서버에 저장되지 않습니다.';
      loadSurveys();
    }
  }
  window.AstraPractice = {
    active: () => Boolean(state.run),
    openRun,refreshRuns,deleteRun,
    subscribe(listener) { listeners.add(listener); listener(publicState()); return () => listeners.delete(listener); },
    updateRun(run) {
      if (!state.run || run.user_id !== state.user?.user_id || run.run_id !== state.run.run_id || run.revision < state.run.revision) return false;
      checkedRun(run); acceptRun(run); return true;
    },
    invalidateRun({user_id, run_id}) {
      if (state.run?.run_id !== run_id || state.user?.user_id !== user_id) return false;
      state.runs = state.runs.filter(run => run.run_id !== run_id);
      state.journal.selectedId = null; state.journal.active = null; state.journal.pending = null;
      persist(); resetDisplay(); runOptions(); controls();
      notice('이 회차를 사용할 수 없어 선택을 해제했습니다. 로그인 상태와 저장된 회차를 다시 확인해 주세요.');
      return true;
    },
    setGameLock({user_id, run_id, locked}) {
      if (!state.run || user_id !== state.user?.user_id || run_id !== state.run.run_id || state.gameLocked === Boolean(locked)) return;
      state.gameLocked = Boolean(locked); controls();
    },
    setAptitudeGameLock({user_id, run_id, locked}) {
      if (!state.run || user_id !== state.user?.user_id || run_id !== state.run.run_id || Boolean(state.aptitudeGameLocked) === Boolean(locked)) return;
      state.aptitudeGameLocked = Boolean(locked); controls();
    },
    setAppointmentGameLock({user_id, run_id, locked}) {
      if (!state.run || user_id !== state.user?.user_id || run_id !== state.run.run_id || state.appointmentGameLocked === Boolean(locked)) return;
      state.appointmentGameLocked = Boolean(locked); controls();
    },
    setInterviewLock({user_id, run_id, locked}) {
      if (!state.run || user_id !== state.user?.user_id || run_id !== state.run.run_id || state.interviewLocked === Boolean(locked)) return;
      state.interviewLocked = Boolean(locked); controls();
    },
    setInterviewDraftState({user_id,run_id,count}) {
      if(!state.run||user_id!==state.user?.user_id||run_id!==state.run.run_id||!Number.isInteger(count)||count<0||state.interviewDrafts===count)return;
      state.interviewDrafts=count;controls();
    },
    setReportLock({user_id, run_id, locked}) {
      if (!state.run || user_id !== state.user?.user_id || run_id !== state.run.run_id || state.reportLocked === Boolean(locked)) return;
      state.reportLocked = Boolean(locked); controls();
    },
  };
  document.addEventListener('DOMContentLoaded', () => {
    api = window.AstraClient.createApi();
    $('practice-new').addEventListener('click', newPractice);
    $('practice-refresh').addEventListener('click', () => { if (!gameLocked() && !state.interviewLocked) return work(load); });
    $('practice-open').addEventListener('click', () => work(async allow => {
      if (gameLocked() || state.interviewLocked || state.journal.active || state.journal.pending) return;
      const run = await api('/runs/' + encodeURIComponent($('practice-runs').value));
      if (allow()) acceptRun(run);
    }));
    $('practice-retry').addEventListener('click', retry);
    $('practice-resolve').addEventListener('click', resolveRejected);
    $('practice-start-item').addEventListener('click', startItem);
    $('practice-submit').addEventListener('click', () => submitItem('submitted'));
    $('practice-skip').addEventListener('click', () => submitItem('skipped'));
    $('practice-game').addEventListener('click', () => { if (!nextItem()) navigateTab('game'); });
    window.AstraAuth.subscribe(sessionChanged);
  });
})();
