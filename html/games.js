/* Server-scored rule games. No survey intensity, personality score or local reward. */
(function () {
  'use strict';
  const $ = id => document.getElementById(id);
  const hands = {rock: '✊', paper: '✋', scissors: '✌️'};
  const labels = {rock: '바위', paper: '보', scissors: '가위'};
  const titles = {rsp: '가위바위보', card: '카드'};
  const surveyIds = () => window.AstraClient.requiredSurveyIds(state.run);
  const state = {scope: null, run: null, context: null, epoch: 0, loaded: false, busy: false, pending: null,
    type: 'rsp', definitions: null, serverAt: 0, clientAt: 0, timer: null, visibility: [], lastScope: null,
    gameTab: false, visibilityRound: null, lastVisibility: null};
  let api;
  const path = () => `/runs/${encodeURIComponent(state.scope.run_id)}/rule-games`;
  const storageKey = scope => `astra.rule-games.v1:${scope.user_id}:${scope.run_id}`;
  const rounds = type => state.run?.rule_games?.games?.[type]?.rounds || [];
  const active = () => ['rsp', 'card'].flatMap(type => rounds(type).map(round => ({type, round}))).find(({round}) => round.status === 'in_progress');
  const current = () => rounds(state.type).at(-1);
  const finished = type => rounds(type).filter(round => round.status === 'completed').length;
  const surveysDone = () => surveyIds().length>0 && surveyIds().every(id => state.run?.records.some(r => r.source_type === 'survey' && r.item_id === id && ['submitted', 'timed_out', 'skipped'].includes(r.status)));
  const serverNow = () => state.serverAt + performance.now() - state.clientAt;
  const gameHidden = () => !state.gameTab || document.visibilityState === 'hidden';
  const locked = () => !state.loaded || !state.scope || state.busy || Boolean(state.pending) || state.context?.busy || state.context?.locked || state.context?.appointmentGameLocked || state.context?.aptitudeGameLocked || state.context?.interviewLocked || state.context?.reportLocked || state.run?.status === 'completed';
  function node(tag, text, className) {
    const element = document.createElement(tag); if (text !== undefined) element.textContent = text; if (className) element.className = className; return element;
  }
  function notice(text = '') { $('game-error').textContent = text; $('game-error').hidden = !text; }
  function persist() {
    try { window.sessionStorage.setItem(storageKey(state.scope), JSON.stringify({type: state.type, pending: state.pending, visibility: state.visibility})); return true; }
    catch (_) { notice('게임의 임시 제출을 보관하지 못했습니다. 브라우저 저장 설정을 확인한 뒤 다시 시도해 주세요.'); return false; }
  }
  function readPending() {
    try {
      const saved = JSON.parse(window.sessionStorage.getItem(storageKey(state.scope)) || '{}');
      state.type = saved.type === 'card' ? 'card' : 'rsp'; state.pending = saved.pending || null;
      state.visibility = Array.isArray(saved.visibility) ? saved.visibility.filter(event => event &&
        typeof event.round_id === 'string' && ['rsp', 'card'].includes(event.game_type) && typeof event.hidden === 'boolean') : [];
    } catch (_) { state.pending = null; notice('임시 제출 상태를 읽지 못했습니다. 서버의 저장된 기록을 먼저 확인해 주세요.'); }
  }
  function setClock(iso) {
    const timestamp = Date.parse(iso); if (!Number.isFinite(timestamp)) throw Error('invalid_server_time');
    state.serverAt = timestamp; state.clientAt = performance.now();
  }
  function checkedRun(run) {
    if (!run || run.user_id !== state.scope?.user_id || run.run_id !== state.scope?.run_id || !Number.isInteger(run.revision)) throw Error('wrong_run');
    return run;
  }
  function applyRun(run, serverTime) {
    checkedRun(run);
    if (run.revision < state.run.revision) return;
    state.run = run;
    if (serverTime) setClock(serverTime);
    else {
      const latest = ['rsp', 'card'].flatMap(type => rounds(type)).flatMap(r => r.events).map(e => Date.parse(e.server_at)).filter(Number.isFinite);
      if (latest.length) setClock(new Date(Math.max(serverNow(), ...latest)).toISOString());
    }
    window.AstraPractice.updateRun(run);
    const inProgress = active(); if (inProgress) state.type = inProgress.type;
    render();
  }
  function eventText(event) {
    const names = {round_started: '라운드 시작', stimulus_issued: '문제 제시', rule_revealed: '규칙 변경 공개', response_selected: '선택', round_ended: '라운드 종료', visibility_reported: '화면 전환 신고'};
    const when = new Date(event.server_at).toLocaleTimeString('ko-KR');
    if (event.type === 'response_selected') {
      const stimulus = event.stimulus || {};
      const card = stimulus.cards?.find(c => c.card_id === event.choice);
      const choice = labels[event.choice] || (card ? `카드 ${card.value}` : event.choice);
      return `${when} · ${event.rule?.label || '규칙 선택'} · ${stimulus.opponent_hand ? '상대 ' + labels[stimulus.opponent_hand] + ' · ' : ''}${choice} · ${event.correct ? '정답' : '오답'} · ${event.score_before} → ${event.score_after}점`;
    }
    return `${when} · ${names[event.type] || '게임 기록'}${event.type === 'visibility_reported' ? (event.hidden ? ' · 화면을 벗어남' : ' · 화면으로 돌아옴') : ''}`;
  }
  function renderHistory() {
    $('game-round-records').replaceChildren();
    for (const type of ['rsp', 'card']) for (const round of rounds(type)) {
      const detail = node('details');
      detail.append(node('summary', `${titles[type]} ${round.index}라운드 · ${round.status === 'completed' ? '종료 저장됨' : '진행 기록 저장됨'} · ${round.score}점 · 정답 ${round.correct_count} / 오답 ${round.incorrect_count}`));
      if (round.quality_flags?.includes('rule_reveal_not_recorded')) detail.append(node('p', '규칙 변경 공개 기록이 없습니다. 기록된 선택만 채점했습니다.'));
      const list = node('ol');
      for (const event of round.events) list.append(node('li', eventText(event)));
      detail.append(list); $('game-round-records').append(detail);
    }
  }
  function render() {
    if (state.run?.flow_version === 'five-game-v2' && state.type === 'rsp' && finished('rsp') === 3 && finished('card') < 3 && !state.busy && !state.pending && !active()) state.type = 'card';
    const inProgress = active(), round = current();
    const finishedRuleGames = state.run?.flow_version === 'five-game-v2' && finished('rsp') === 3 && finished('card') === 3;
    const rulePanel = $('rule-game-panel');
    if (rulePanel) rulePanel.hidden = finishedRuleGames && !state.busy && !state.pending;
    const visibilityRound = inProgress?.round.round_id || null;
    if (state.visibilityRound !== visibilityRound) {
      state.visibilityRound = visibilityRound; state.lastVisibility = gameHidden();
    }
    const gated = locked() || !surveysDone();
    const playing = round?.status === 'in_progress' && !gated;
    const due = round?.status === 'in_progress' && serverNow() >= Date.parse(round.deadline_at);
    const revealDue = round?.status === 'in_progress' && round.phase === 'initial' && serverNow() >= Date.parse(round.reveal_due_at);
    $('game-status').textContent = !state.scope ? '성향 설문에서 로그인한 계정의 연습 회차를 선택해 주세요.' :
      !state.loaded ? '게임 기록을 불러오는 중입니다.' : !surveysDone() ? `현재 회차의 성향 설문 ${surveyIds().length}문항을 먼저 저장해 주세요.` :
        `현재 회차: ${state.scope.run_id} · ${state.pending ? '제출 결과 확인 대기' : state.busy ? '서버 저장 확인 중' : '서버 기록 연결됨'}`;
    $('game-saved-count').textContent = `라운드 종료 서버 저장: 가위바위보 ${finished('rsp')} / 3 · 카드 ${finished('card')} / 3`;
    $('game-refresh').disabled = !state.scope || state.busy;
    $('game-retry').hidden = !state.pending; $('game-retry').disabled = state.busy || !state.loaded;
    for (const type of ['rsp', 'card']) {
      $('game-tab-' + type).hidden = state.run?.flow_version === 'five-game-v2' && finished(type) === 3;
      $('game-tab-' + type).disabled = Boolean(inProgress) || state.busy || Boolean(state.pending) || Boolean(state.context?.appointmentGameLocked) || (type === 'card' && state.run?.flow_version === 'five-game-v2' && finished('rsp') !== 3);
      $('game-tab-' + type).classList.toggle('active', state.type === type);
      $('game-tab-' + type).setAttribute('aria-pressed', String(state.type === type));
      $('gameUI-' + type).style.display = state.type === type ? 'block' : 'none';
    }
    $('roundLabel').textContent = `${titles[state.type]} · ${round?.index || 1} / 3라운드`;
    $('gamePhaseText').textContent = round?.status === 'in_progress' ? '게임 진행 중' : round ? '라운드 저장됨' : '시작 전';
    $('gameScore').textContent = String(round?.score || 0);
    $('gameTimer').textContent = round?.status === 'in_progress' ? String(Math.max(0, Math.ceil((Date.parse(round.deadline_at) - serverNow()) / 1000))) : '20';
    $('btnStartGame').style.display = 'inline-flex';
    $('btnStartGame').disabled = gated || Boolean(inProgress) || rounds(state.type).length >= 3;
    $('btnStartGame').textContent = `${finished(state.type) < 3 ? finished(state.type) + 1 : 3}라운드 시작`;
    $('btnNextStep').style.display = finished(state.type) === 3 ? 'inline-flex' : 'none';
    $('btnNextStep').disabled = state.busy || Boolean(state.pending);
    $('btnNextStep').textContent = finished('rsp') === 3 && finished('card') === 3 ? (state.run?.flow_version === 'five-game-v2' ? '약속 기억 게임으로' : '기본 면접 화면으로') : `${state.type === 'rsp' ? '카드' : '가위바위보'} 게임으로`;
    $('revealBox').style.display = round?.revealed_at ? 'block' : 'none';
    $('revealText').textContent = round?.revealed_at ? `적용된 규칙: ${round.rule.label}` : '';
    if (state.type === 'rsp') {
      $('rspRuleBadge').textContent = round?.rule.label || '라운드를 시작하면 지시어가 표시됩니다.';
      $('oppHand').textContent = hands[round?.stimulus.opponent_hand] || '—';
      $('oppHandText').textContent = labels[round?.stimulus.opponent_hand] || '시작 대기';
    } else $('cardRuleText').textContent = round?.rule.label || '라운드를 시작하면 카드 규칙이 표시됩니다.';
    for (const hand of Object.keys(hands)) $('game-choice-' + hand).disabled = !playing || due || revealDue || state.type !== 'rsp';
    $('cardTileGrid').replaceChildren();
    if (state.type === 'card' && round) for (const card of round.stimulus.cards || []) {
      const button = node('button', String(card.value), 'game-tile'); button.type = 'button';
      const selected = round.stimulus.selected_card_ids.includes(card.card_id);
      const result = round.events.findLast(event => event.type === 'response_selected' &&
        event.stimulus?.stimulus_id === round.stimulus.stimulus_id && event.choice === card.card_id);
      const feedback = result?.correct === true ? '정답' : result?.correct === false ? '오답' : '';
      button.disabled = !playing || due || revealDue || selected;
      button.setAttribute('aria-label', `카드 ${card.value}${selected ? ' · 선택 저장됨' : ''}${feedback ? ' · ' + feedback : ''}`);
      button.classList.toggle('confirmed-correct', selected && result?.correct === true);
      button.classList.toggle('confirmed-incorrect', selected && result?.correct === false);
      button.classList.toggle('selected', selected);
      button.addEventListener('click', () => answer(card.card_id)); $('cardTileGrid').append(button);
    }
    renderHistory();
    if (state.scope) window.AstraPractice.setGameLock({...state.scope, locked: state.busy || Boolean(state.pending) || Boolean(inProgress)});
  }
  async function task(action) {
    if (!state.scope || state.busy) return;
    const epoch = state.epoch; state.busy = true; notice(); render();
    try { await action(() => epoch === state.epoch); }
    catch (error) {
      if (epoch !== state.epoch) return;
      if (error.status === 401 || error.status === 404 || error.status === 410 || error.message === 'wrong_run') {
        state.loaded = false;
        const previous = {...state.scope};
        if (error.status !== 401) { try { window.sessionStorage.removeItem(storageKey(previous)); } catch (_) {} }
        window.AstraPractice.invalidateRun(previous);
        if (error.status === 401 || error.message === 'wrong_run') window.AstraAuth?.recheck();
        notice('로그인 또는 회차 상태를 확인하지 못했습니다. 성향 설문 화면에서 로그인과 저장된 회차를 다시 확인해 주세요.');
      } else notice('서버 처리 결과를 확인하지 못했습니다. 선택을 보관했습니다. 연결을 확인한 뒤 같은 요청을 다시 시도해 주세요.');
    } finally { if (epoch === state.epoch) { state.busy = false; render(); } }
  }
  async function fetchCurrent(allow) {
    if (!state.definitions) {
      const definitions = await api('/rule-game-definitions'); if (!allow()) return;
      if (definitions.duration_ms !== 20000 || definitions.rounds_per_game !== 3) throw Error('unsupported_definition');
      state.definitions = definitions;
    }
    const result = await api(path()); if (!allow()) return;
    checkedRun(result.run); state.loaded = true; applyRun(result.run, result.server_time);
    if (state.timer === null) state.timer = setInterval(tick, 200);
  }
  async function sendPending(allow, retrying = false) {
    const pending = structuredClone(state.pending);
    try {
      const run = await api(path(), {method: 'POST', body: pending});
      if (!allow()) return;
      checkedRun(run); state.pending = null; persist(); applyRun(run);
      if (retrying) await fetchCurrent(allow);
    } catch (error) {
      if (!allow()) return;
      if (error.status >= 400 && error.status < 500 && ![401,404,410].includes(error.status)) {
        // A definitive rejection is reconciled before unlocking. Never blindly
        // replay an expired choice with a new revision or idempotency key.
        await fetchCurrent(allow); if (!allow()) return;
        state.pending = null; persist();
        const codes = {rule_game_round_expired: '선택이 서버에 도착했을 때 제한 시간이 끝나 채점하지 않았습니다.',
          rule_game_reveal_required: '규칙 변경 시간이 지나 이전 규칙의 선택을 채점하지 않았습니다. 변경된 규칙을 불러옵니다.',
          rule_game_duplicate_choice: '이미 저장된 카드 선택입니다.', rule_game_stale_stimulus: '문제가 변경되어 이전 선택을 채점하지 않았습니다.',
          revision_conflict: '다른 화면에서 변경된 최신 게임 기록을 불러왔습니다.', survey_responses_required: `먼저 성향 설문 ${surveyIds().length}문항을 저장해 주세요.`};
        notice(codes[error.code] || '요청이 적용되지 않아 서버의 저장 상태를 다시 확인했습니다. 현재 상태에서 이어가 주세요.');
      } else throw error;
    }
  }
  function send(action, values = {}) {
    if (locked() || !surveysDone()) return;
    return task(async allow => {
      state.pending = {action, game_type: state.type, ...values, expected_revision: state.run.revision, idempotency_key: crypto.randomUUID()};
      if (!persist()) return;
      render(); await sendPending(allow);
    });
  }
  function answer(choice) {
    const round = current(); if (locked() || round?.status !== 'in_progress') return;
    if (serverNow() >= Date.parse(round.deadline_at) || (round.phase === 'initial' && serverNow() >= Date.parse(round.reveal_due_at))) return tick();
    if (state.type === 'card' && round.stimulus.selected_card_ids.includes(choice)) return;
    return send('answer', {round_id: round.round_id, stimulus_id: round.stimulus.stimulus_id, choice});
  }
  function tick() {
    const visibleRound = current();
    if (visibleRound?.status === 'in_progress') $('gameTimer').textContent = String(Math.max(0, Math.ceil((Date.parse(visibleRound.deadline_at) - serverNow()) / 1000)));
    if (locked()) return;
    const running = active(); if (!running) return;
    state.type = running.type;
    const round = running.round;
    // Keep transitions bound to their round. Moving one into pending and saving
    // both together lets an uncertain request retain its exact retry payload.
    while (state.visibility.length) {
      const event = state.visibility.shift();
      if (event.round_id === round.round_id && event.game_type === running.type) return send('visibility', {round_id: event.round_id, hidden: event.hidden});
      persist();
    }
    if (serverNow() >= Date.parse(round.deadline_at)) return send('finish', {round_id: round.round_id});
    if (round.phase === 'initial' && serverNow() >= Date.parse(round.reveal_due_at)) return send('reveal', {round_id: round.round_id});
  }
  function switchType(type) { if (state.busy || state.pending || active()) return; state.type = type; if (state.scope) persist(); render(); }
  function contextChanged(context) {
    const scope = context.user && context.run ? {user_id: context.user.user_id, run_id: context.run.run_id} : null;
    const same = scope && state.scope && scope.user_id === state.scope.user_id && scope.run_id === state.scope.run_id;
    const changed = same && (context.run.revision > state.run.revision || context.busy !== state.context?.busy || context.locked !== state.context?.locked || context.appointmentGameLocked !== state.context?.appointmentGameLocked || context.aptitudeGameLocked !== state.context?.aptitudeGameLocked || context.interviewLocked !== state.context?.interviewLocked || context.reportLocked !== state.context?.reportLocked);
    state.context = context;
    if (same) { if (context.run.revision >= state.run.revision) state.run = context.run; if (changed) render(); return; }
    const previous = state.scope;
    state.epoch++; state.scope = scope; state.run = context.run; state.loaded = false; state.busy = false;
    state.pending = null; state.visibility = []; state.type = 'rsp'; state.visibilityRound = null; state.lastVisibility = null;
    if (state.timer !== null) clearInterval(state.timer); state.timer = null;
    if (previous) state.lastScope = previous;
    if (context.authStatus === 'guest' && state.lastScope) {
      try { window.sessionStorage.removeItem(storageKey(state.lastScope)); } catch (_) {}
      state.lastScope = null;
    }
    notice(); render();
    if (!scope) return;
    readPending();
    task(async allow => {
      const [definitions, result] = await Promise.all([api('/rule-game-definitions'), api(path())]); if (!allow()) return;
      if (definitions.duration_ms !== 20000 || definitions.rounds_per_game !== 3) throw Error('unsupported_definition');
      state.definitions = definitions; state.loaded = true; applyRun(result.run, result.server_time);
      state.timer = setInterval(tick, 200);
    });
  }
  function visibility() {
    const running = active(); if (!running) return;
    const hidden = gameHidden(); if (hidden === state.lastVisibility) return;
    state.lastVisibility = hidden;
    state.visibility.push({round_id: running.round.round_id, game_type: running.type, hidden});
    persist(); return tick();
  }
  window.AstraGames = {onNavigation: tab => { state.gameTab = tab === 'game'; return visibility(); }};
  document.addEventListener('DOMContentLoaded', () => {
    api = window.AstraClient.createApi();
    $('btnStartGame').addEventListener('click', () => send('start'));
    $('btnNextStep').addEventListener('click', () => {
      if (state.busy || state.pending) return;
      if (finished('rsp') === 3 && finished('card') === 3) {
        if (state.run?.flow_version === 'five-game-v2') $('appointment-games')?.scrollIntoView?.({behavior: 'smooth'});
        else navigateTab('interview');
      }
      else switchType(state.type === 'rsp' ? 'card' : 'rsp');
    });
    for (const type of ['rsp', 'card']) $('game-tab-' + type).addEventListener('click', () => switchType(type));
    for (const hand of Object.keys(hands)) $('game-choice-' + hand).addEventListener('click', () => answer(hand));
    $('game-retry').addEventListener('click', () => task(async allow => { if (state.pending && persist()) await sendPending(allow, true); }));
    $('game-refresh').addEventListener('click', () => task(fetchCurrent));
    document.addEventListener('visibilitychange', visibility);
    window.AstraPractice.subscribe(contextChanged);
  });
})();
