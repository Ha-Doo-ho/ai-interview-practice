/* Read confirmed run state. Opening a panel never starts or stops a game. */
document.addEventListener('DOMContentLoaded', () => {
  'use strict';
  const byId = id => document.getElementById(id);
  const panel = byId('game-journey');
  if (!panel || !window.AstraPractice?.subscribe || !window.AstraClient?.createApi) return;
  const api = window.AstraClient.createApi();
  const titles = {rsp:'가위바위보', card:'카드 뒤집기', day:'약속 요일 정하기', place:'약속 장소 정하기',
    bus:'버스 기억하기', rotation:'도형 회전', path:'길 만들기', potion:'마법약'};
  let selectedRun = null;
  let nextGame = null;
  let refreshRequest = null;

  function setNotice(message, reload = false) {
    byId('journey-notice').textContent = message;
    byId('journey-reload').hidden = !reload;
  }
  function render({run}) {
    if (selectedRun?.run_id !== run?.run_id || selectedRun?.user_id !== run?.user_id) {
      refreshRequest = null;
      setNotice('');
    }
    selectedRun = run;
    const modern = run?.flow_version === 'five-game-v2';
    const ready = run && (run.status === 'completed' || window.AstraClient.allGamesComplete(run));
    byId('journey-interview').hidden = !ready;
    byId('journey-interview').textContent = run?.status === 'completed' ? '저장된 면접 보기' : '면접으로 이동';
    byId('journey-refresh').disabled = !run || Boolean(refreshRequest);
    byId('journey-resume').hidden = !run || !modern || run.status === 'completed' || ready;
    byId('journey-leave').hidden = !run;
    const progress = byId('journey-progress');
    nextGame = null;
    if (!modern) {
      progress.textContent = run ? '이전 형식의 연습 회차입니다.' : '설문 화면에서 로그인하고 연습 회차를 선택해 주세요.';
      return;
    }

    const done = new Set();
    const active = [];
    for (const kind of ['rsp','card']) {
      const rounds = run.rule_games?.games?.[kind]?.rounds || [];
      if (rounds.length === 3 && rounds.every(r => r.status === 'completed')) done.add(kind);
      if (rounds.some(r => r.status === 'in_progress')) active.push(kind);
    }
    for (const game of run.appointment_games?.games || []) {
      if (game.status === 'complete' && game.questions?.length === 10) done.add(game.type);
      if (game.status === 'active') active.push(game.type);
    }
    for (const attempt of run.aptitude_games?.attempts || []) {
      if (attempt.mode === 'main' && attempt.status === 'complete') done.add(attempt.type);
      if (attempt.status === 'active') active.push(attempt.type);
    }
    nextGame = active[0] || Object.keys(titles).find(kind => !done.has(kind));
    let detail = run.status === 'completed' ? '확정된 회차' : '면접을 시작할 수 있습니다.';
    if (run.status !== 'completed' && !ready && nextGame) {
      detail = (active.length ? '진행 중 · ' : '다음 게임 · ') + titles[nextGame];
    }
    progress.textContent = '게임 완료 ' + done.size + ' / 8 · ' + detail;
  }

  byId('journey-resume').addEventListener('click', () => {
    if (!nextGame) return;
    let target;
    if (['rsp','card'].includes(nextGame)) {
      if (window.AstraGames) target = byId('rule-game-panel');
    } else if (['day','place','bus'].includes(nextGame)) {
      target = byId('appointment-games');
    } else {
      target = byId('aptitude-games');
    }
    if (!target || target.hidden || !target.children.length) {
      setNotice('게임 화면을 불러오지 못했습니다. 저장 상태를 다시 불러온 뒤에도 열리지 않으면 화면을 새로고침해 주세요.', true);
      return;
    }
    setNotice('');
    target.focus();
    target.scrollIntoView?.({block:'start'});
  });

  byId('journey-refresh').addEventListener('click', async () => {
    if (!selectedRun || refreshRequest) return;
    const {user_id,run_id} = selectedRun;
    const request = {};
    refreshRequest = request;
    byId('journey-refresh').disabled = true;
    setNotice('서버에 저장된 진행 상태를 확인하고 있습니다.');
    try {
      const run = await api('/runs/' + encodeURIComponent(run_id));
      if (refreshRequest !== request) return;
      if (run?.user_id !== user_id || run.run_id !== run_id) throw Error('wrong_run');
      window.AstraPractice.updateRun(run);
      setNotice('현재 회차의 저장 상태를 확인했습니다.');
    } catch (_) {
      if (refreshRequest === request) setNotice('저장 상태를 읽지 못했습니다. 연결을 확인한 뒤 다시 시도해 주세요.', true);
    } finally {
      if (refreshRequest === request) {
        refreshRequest = null;
        byId('journey-refresh').disabled = false;
      }
    }
  });
  byId('journey-interview').addEventListener('click', () => navigateTab('interview'));
  byId('journey-leave').addEventListener('click', () => navigateTab('records'));
  setNotice('');
  window.AstraPractice.subscribe(render);
});
