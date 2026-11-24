/* 아이콘 초기화 및 기본 로드 */
document.addEventListener('DOMContentLoaded', () => {
  refreshIcons();
  initializeTabNavigation();
  if (!window.AstraGames) generateCardTiles();
  return loadSurveys();
});

function refreshIcons() {
  if (typeof lucide !== 'undefined') lucide.createIcons();
}

/* 글로벌 실행 상태 */
let currentRun = {
  run_id: 'run-' + Math.random().toString(36).substring(2, 10),
  revision: 1,
  status: 'in_progress',
  roundIndex: 1, // 연습 없이 바로 1라운드 시작
  score: 0,
  gameActive: false
};

let gameTimerInterval = null;
let currentGameType = 'rsp';

/* 가위바위보 상태 */
const rspRules = [
  { ruleText: "지시어: 무조건 [이겨라!]", type: "win" },
  { ruleText: "지시어: 무조건 [져라!]", type: "lose" },
  { ruleText: "지시어: 무조건 [비겨라!]", type: "draw" }
];
let currentRspRuleIndex = 0;
let currentOppHand = 'paper';

/* 카드 뒤집기 규칙 상태 */
const cardRules = [
  { text: "현재 규칙: [짝수] 카드를 모두 선택하세요!", eval: (v) => v % 2 === 0 },
  { text: "현재 규칙: [3의 배수] 카드를 모두 선택하세요!", eval: (v) => v % 3 === 0 },
  { text: "현재 규칙: [7 이상의 숫자]를 선택하세요!", eval: (v) => v >= 7 }
];
let currentCardRuleIndex = 0;

/* 1. 서버의 원본 문항을 사용하는 설문 화면 체험 (서버 저장과 분리) */
const surveyState = {definitions: null, drafts: []};
const surveyTypeNames = {
  ordinal_6: '나 알아보기', paired_perspective: '두 관점에서 보기',
  bipolar_slider: '두 방향 사이에서 선택하기', top_k_rank: '중요한 순서 정하기'
};

function surveyElement(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined) element.textContent = text;
  return element;
}

async function loadSurveys() {
  if (window.AstraPractice?.active()) return;
  const submit = document.getElementById('survey-submit');
  const retry = document.getElementById('survey-retry');
  const error = document.getElementById('survey-error');
  const items = document.getElementById('survey-items');
  submit.disabled = true;
  retry.hidden = true;
  error.hidden = true;
  items.replaceChildren();
  surveyState.definitions = null;
  surveyState.drafts = [];
  currentRun.surveyPreview = null;
  document.getElementById('survey-progress').textContent = '문항을 불러오는 중입니다.';
  try {
    const definitions = await window.AstraClient.createApi()('/definitions');
    if (Array.isArray(definitions.current_surveys)) definitions.surveys = definitions.current_surveys;
    if (!Array.isArray(definitions.surveys) || !definitions.surveys.length ||
        definitions.surveys.some(item => !surveyTypeNames[item.type])) throw Error('invalid_definitions');
    surveyState.definitions = definitions;
    surveyState.drafts = definitions.surveys.map(item => ({item, values: item.type === 'bipolar_slider'
      ? {value: item.initial_value, touched: false, changes: 0, confirmed: false}
      : item.type === 'top_k_rank' ? {selected_ids: Array(item.requested_k).fill(''), selection_events: []} : {}}));
    if (!window.AstraPractice?.active()) surveyState.drafts.forEach((draft, index) => items.append(renderSurveyItem(draft, index)));
    if (!window.AstraPractice?.active()) {
      document.getElementById('survey-title').textContent = `성향 파악 · ${surveyState.drafts.length}문항`;
      const intro = document.getElementById('survey-intro');
      if (intro && definitions.current_survey_set_version === 'work-behavior-v2') intro.textContent =
        '업무 행동에 관한 5문항입니다. 각 문장의 동의 정도를 여섯 문구 중 하나로 선택합니다. 정답이나 성향 점수를 정하는 검사가 아닙니다.';
    }
    submit.disabled = false;
    updateSurveyProgress();
  } catch (_) {
    surveyState.definitions = null;
    surveyState.drafts = [];
    items.replaceChildren();
    error.textContent = '설문 문항을 불러오지 못했습니다. 서버 연결을 확인한 뒤 다시 불러와 주세요.';
    error.hidden = false;
    retry.hidden = false;
    document.getElementById('survey-progress').textContent = '문항 불러오기 실패';
  }
}

function renderSurveyItem(draft, index, changed = updateSurveyProgress, uniqueRanks = false, canChange = () => true, onNonresponse = null) {
  const {item, values} = draft;
  const card = surveyElement('fieldset', 'survey-item');
  const legend = surveyElement('legend', 'survey-q', `${index + 1}. ${item.prompt}`);
  legend.id = `${item.item_id}-legend`;
  card.append(legend, surveyElement('p', 'survey-type', surveyTypeNames[item.type]));
  let clearNonresponse = () => {};
  const agreement = (field, title) => {
    const group = surveyElement('fieldset', 'survey-perspective');
    group.append(surveyElement('legend', 'survey-group-label', title));
    const choices = surveyElement('div', 'survey-options');
    for (const option of item.ordered_options) {
      const label = surveyElement('label', 'radio-label');
      const input = surveyElement('input');
      input.type = 'radio'; input.name = `${item.item_id}-${field}`;
      input.id = `${item.item_id}-${field}-${option.position}`;
      input.value = String(option.position);
      input.checked = values[field] === option.position;
      input.addEventListener('change', () => {
        if (!canChange()) {
          for (const choice of choices.querySelectorAll('input')) choice.checked = values[field] === Number(choice.value);
          return;
        }
        values[field] = Number(input.value);
        if (field === 'selected_position') {delete values.nonresponse_reason;clearNonresponse();}
        changed();
      });
      label.append(input, surveyElement('span', '', option.label));
      choices.append(label);
    }
    group.append(choices);
    return group;
  };
  if (item.type === 'ordinal_6') card.append(agreement('selected_position', '나의 응답'));
  if (item.type === 'paired_perspective') {
    card.append(surveyElement('p', 'survey-help', '두 응답 모두 본인이 작성합니다. 타인 관점은 내가 상상한 모습이며 실제 제3자의 평가가 아닙니다.'));
    for (const perspective of item.perspective_presentation_order) {
      card.append(agreement(perspective, perspective === 'self' ? '나의 관점' : '내가 상상한 타인의 관점'));
    }
  }
  if (item.type === 'bipolar_slider') {
    const anchors = surveyElement('div', 'survey-anchors');
    anchors.append(surveyElement('span', '', item.left_anchor.label), surveyElement('span', '', item.right_anchor.label));
    const range = surveyElement('input', 'slider-range');
    range.type = 'range'; range.id = `${item.item_id}-value`;
    range.min = item.min; range.max = item.max; range.step = item.step; range.value = String(values.value);
    range.setAttribute('aria-labelledby', legend.id);
    const output = surveyElement('p', 'slider-val-label');
    output.id = `${item.item_id}-position`;
    range.setAttribute('aria-describedby', output.id);
    const confirmation = surveyElement('label', 'survey-confirm');
    const check = surveyElement('input');
    check.type = 'checkbox'; check.id = `${item.item_id}-confirm`;
    check.checked = values.confirmed === true;
    const showPosition = () => {
      const value = Number(range.value);
      const text = value === 0 ? '중앙 · 어느 쪽으로도 기울이지 않은 위치' :
        `${value < 0 ? '왼쪽' : '오른쪽'} ${Math.abs(value / item.step)}단계 · ${value < 0 ? item.left_anchor.label : item.right_anchor.label}`;
      output.textContent = text; range.setAttribute('aria-valuetext', text);
    };
    range.addEventListener('input', () => {
      if (!canChange()) { range.value = String(values.value); showPosition(); return; }
      if (values.value !== Number(range.value)) values.changes += 1;
      values.value = Number(range.value); values.touched = true; values.confirmed = false; check.checked = false;
      showPosition(); changed();
    });
    check.addEventListener('change', () => {
      if (!canChange()) { check.checked = values.confirmed === true; return; }
      values.confirmed = check.checked; changed();
    });
    confirmation.append(check, surveyElement('span', '', '표시된 위치를 내 응답으로 확정합니다. 중앙도 선택할 수 있습니다.'));
    showPosition();
    card.append(anchors, range, output, confirmation);
  }
  if (item.type === 'top_k_rank') {
    card.append(surveyElement('p', 'survey-help', `서로 다른 ${item.requested_k}개를 1순위부터 지정해 주세요. 선택하지 않은 항목을 싫어한다는 뜻은 아닙니다.`));
    const ranks = surveyElement('div', 'survey-ranks');
    for (let index = 0; index < item.requested_k; index++) {
      const label = surveyElement('label', 'survey-rank');
      label.append(surveyElement('span', '', `${index + 1}순위`));
      const select = surveyElement('select');
      select.id = `${item.item_id}-rank-${index + 1}`;
      const placeholder = surveyElement('option', '', '항목을 선택해 주세요');
      placeholder.value = ''; select.append(placeholder);
      for (const id of item.display_order) {
        const candidate = item.candidates.find(candidate => candidate.option_id === id);
        const option = surveyElement('option', '', candidate.label);
        option.value = candidate.option_id; select.append(option);
      }
      select.value = values.selected_ids[index] || '';
      select.addEventListener('change', () => {
        const previous = values.selected_ids[index];
        if (!canChange()) { select.value = previous; return; }
        if (uniqueRanks && select.value && values.selected_ids.some((id, position) => position !== index && id === select.value)) {
          select.value = previous; return;
        }
        values.selected_ids[index] = select.value;
        values.selection_events.push({action: 'set_rank', rank: index + 1, option_id: select.value || null, previous_option_id: previous || null, order: values.selection_events.length + 1});
        changed();
        if (uniqueRanks) for (const input of ranks.querySelectorAll('select')) {
          for (const option of input.querySelectorAll('option')) option.disabled = Boolean(option.value && option.value !== input.value && values.selected_ids.includes(option.value));
        }
      });
      label.append(select); ranks.append(label);
    }
    card.append(ranks);
  }
  if (item.nonresponse_options?.length) {
    const stateLabel=surveyElement('p','survey-help');stateLabel.setAttribute('role','status');
    const buttons=[];
    const update = () => {
      const selected=item.nonresponse_options.find(o=>o.id===values.nonresponse_reason);
      stateLabel.textContent=selected?`응답: ${selected.label}`:'경험이 없거나 판단하기 어려우면 동의 정도 대신 아래에서 선택해 주세요.';
      for(const [button,option] of buttons)button.setAttribute('aria-pressed',String(option.id===values.nonresponse_reason));
    };
    clearNonresponse=update;
    card.append(stateLabel);
    for (const option of item.nonresponse_options) {
      const button=surveyElement('button','btn-action btn-light',option.label);
      button.type='button';button.id=`${onNonresponse?'survey':item.item_id}-nonresponse-${option.id}`;
      button.addEventListener('click',()=>{
        if(!canChange())return;
        values.nonresponse_reason=option.id;delete values.selected_position;
        for(const input of card.querySelectorAll('input'))input.checked=false;
        update();
        if(onNonresponse)onNonresponse(option.id);else changed();
      });
      buttons.push([button,option]);card.append(button);
    }
    update();
  }
  draft.card = card;
  return card;
}

function surveyComplete({item, values}) {
  const validPosition = value => item.ordered_options.some(option => option.position === value);
  if (item.type === 'ordinal_6') return validPosition(values.selected_position) ||
    (values.selected_position===undefined && item.nonresponse_options?.some(o=>o.id===values.nonresponse_reason));
  if (item.type === 'paired_perspective') return validPosition(values.self) && validPosition(values.imagined_others);
  if (item.type === 'bipolar_slider') return values.confirmed === true;
  if (item.type === 'top_k_rank') return values.selected_ids.length === item.requested_k &&
    new Set(values.selected_ids).size === item.requested_k && values.selected_ids.every(id => item.candidates.some(option => option.option_id === id));
  return false;
}

function updateSurveyProgress() {
  currentRun.surveyPreview = null;
  document.getElementById('survey-error').hidden = true;
  const count = surveyState.drafts.filter(surveyComplete).length;
  document.getElementById('survey-progress').textContent = `응답 ${count} / ${surveyState.drafts.length} · 아직 서버에 저장되지 않았습니다.`;
}

function submitSurveys() {
  const error = document.getElementById('survey-error');
  if (!surveyState.drafts.length) return;
  const missing = surveyState.drafts.findIndex(draft => !surveyComplete(draft));
  if (missing !== -1) {
    error.textContent = `${missing + 1}번 문항의 응답을 확인해 주세요. `+
      (surveyState.drafts[missing].item.type==='ordinal_6'?'여섯 문구 중 하나를 선택해 주세요.'+
       (surveyState.drafts[missing].item.nonresponse_options?.length?' 경험이 없거나 판단하기 어려우면 해당 버튼으로 기록할 수 있습니다.':''):
       '두 관점은 각각 선택하고, 슬라이더는 위치를 확정하며, 순위는 서로 다른 항목으로 지정해 주세요.');
    error.hidden = false;
    surveyState.drafts[missing].card.querySelector('input, select')?.focus();
    error.focus();
    return;
  }
  currentRun.surveyPreview = {
    server_saved: false, context: 'untimed_screen_preview', definitions_version: surveyState.definitions.version,
    responses: surveyState.drafts.map(({item, values}) => ({item_id: item.item_id, item_version: item.item_version,
      definition: structuredClone(item), status: values.nonresponse_reason?'skipped':'submitted',
      ...(values.nonresponse_reason?{nonresponse_reason:values.nonresponse_reason}:{}),
      response: values.nonresponse_reason?{}:window.AstraClient.buildSurveyResponse(item, 'submitted', values)}))
  };
  navigateTab('game');
}

/* 2. 게임 방식 전환 */
function switchGameType(type, el) {
  document.querySelectorAll('.game-tab-btn').forEach(b => b.classList.remove('active'));
  el.classList.add('active');

  currentGameType = type;
  document.getElementById('gameUI-rsp').style.display = type === 'rsp' ? 'block' : 'none';
  document.getElementById('gameUI-card').style.display = type === 'card' ? 'block' : 'none';
}

/* 실전 라운드 시작 (start) */
function startGameRound() {
  currentRun.gameActive = true;
  document.getElementById('btnStartGame').style.display = 'none';

  let timeLeft = 20;
  document.getElementById('gameTimer').innerText = timeLeft;

  // 가위바위보 초기 세팅
  nextRspProblem();

  if (gameTimerInterval) clearInterval(gameTimerInterval);

  gameTimerInterval = setInterval(() => {
    timeLeft -= 1;
    document.getElementById('gameTimer').innerText = timeLeft;

    // 10초 남았을 때 Reveal (규칙 급변) 발동
    if (timeLeft === 10) {
      triggerReveal();
    }

    if (timeLeft <= 0) {
      clearInterval(gameTimerInterval);
      currentRun.gameActive = false;
      alert(`실전 라운드 ${currentRun.roundIndex} 마감!`);
      
      // 다음 라운드 진행 버튼 표시
      document.getElementById('btnNextStep').style.display = 'inline-flex';
    }
  }, 1000);
}

/* A. 가위바위보 로직 */
const handMap = { rock: '✊', paper: '✋', scissors: '✌️' };
const handTextMap = { rock: '바위', paper: '보', scissors: '가위' };

function nextRspProblem() {
  const keys = ['rock', 'paper', 'scissors'];
  currentOppHand = keys[Math.floor(Math.random() * 3)];
  document.getElementById('oppHand').innerText = handMap[currentOppHand];
  document.getElementById('oppHandText').innerText = handTextMap[currentOppHand];
}

function playRspChoice(myChoice) {
  if (!currentRun.gameActive) {
    alert("먼저 '실전 라운드 시작' 버튼을 눌러주세요!");
    return;
  }

  const rule = rspRules[currentRspRuleIndex].type;
  let isWin = false;

  if (
    (myChoice === 'rock' && currentOppHand === 'scissors') ||
    (myChoice === 'scissors' && currentOppHand === 'paper') ||
    (myChoice === 'paper' && currentOppHand === 'rock')
  ) {
    isWin = true;
  }

  let isDraw = (myChoice === currentOppHand);
  let isSuccess = false;

  if (rule === 'win' && isWin) isSuccess = true;
  if (rule === 'lose' && !isWin && !isDraw) isSuccess = true;
  if (rule === 'draw' && isDraw) isSuccess = true;

  if (isSuccess) {
    currentRun.score += 10;
  } else {
    currentRun.score = Math.max(0, currentRun.score - 5);
  }

  document.getElementById('gameScore').innerText = currentRun.score;
  document.getElementById('scoreStrategy').innerText = currentRun.score + "점";

  // 다음 무작위 제시
  nextRspProblem();
}

/* B. 카드 타일 로직 */
function generateCardTiles() {
  const grid = document.getElementById('cardTileGrid');
  grid.innerHTML = '';
  for (let i = 0; i < 8; i++) {
    const num = Math.floor(Math.random() * 12) + 1;
    const tile = document.createElement('div');
    tile.className = 'game-tile';
    tile.innerText = num;
    tile.onclick = () => clickCardTile(tile, num);
    grid.appendChild(tile);
  }
}

function clickCardTile(el, val) {
  if (!currentRun.gameActive) {
    alert("먼저 '실전 라운드 시작' 버튼을 눌러주세요!");
    return;
  }

  const isCorrect = cardRules[currentCardRuleIndex].eval(val);
  if (isCorrect) {
    currentRun.score += 10;
    el.style.background = '#A7F3D0';
  } else {
    currentRun.score = Math.max(0, currentRun.score - 5);
    el.style.background = '#FCA5A5';
  }

  document.getElementById('gameScore').innerText = currentRun.score;
  document.getElementById('scoreStrategy').innerText = currentRun.score + "점";
}

/* Reveal (규칙 변동) */
function triggerReveal() {
  const box = document.getElementById('revealBox');
  box.style.display = 'block';

  if (currentGameType === 'rsp') {
    currentRspRuleIndex = (currentRspRuleIndex + 1) % rspRules.length;
    document.getElementById('rspRuleBadge').innerText = rspRules[currentRspRuleIndex].ruleText;
    document.getElementById('revealText').innerText = `[규칙 변경] 지시어가 변경되었습니다! ${rspRules[currentRspRuleIndex].ruleText}`;
  } else {
    currentCardRuleIndex = (currentCardRuleIndex + 1) % cardRules.length;
    document.getElementById('cardRuleText').innerText = cardRules[currentCardRuleIndex].text;
    document.getElementById('revealText').innerText = `[규칙 변경] ${cardRules[currentCardRuleIndex].text}`;
    generateCardTiles();
  }
}

/* 다음 실전 라운드 진행 */
function nextGameRound() {
  if (currentRun.roundIndex < 3) {
    currentRun.roundIndex += 1;
    currentRun.revision += 1;

    document.getElementById('roundLabel').innerText = `실전 라운드 ${currentRun.roundIndex} / 3`;
    document.getElementById('gamePhaseText').innerText = `MAIN ROUND ${currentRun.roundIndex}`;
    document.getElementById('revealBox').style.display = 'none';
    document.getElementById('btnNextStep').style.display = 'none';
    document.getElementById('btnStartGame').style.display = 'inline-flex';

    generateCardTiles();
    alert(`실전 라운드 ${currentRun.roundIndex}를 시작할 준비가 되었습니다. 시작 버튼을 누르세요.`);
  } else {
    currentRun.status = 'game_completed';
    alert("실전 역량게임 3개 라운드가 모두 완료되었습니다! 면접 탭으로 이동합니다.");
    navigateTab('interview');
  }
}

/* 서버 기록 화면 갱신 */
function renderRecordsTable() {
  window.AstraRecords?.render();
}

/* 탭 전환 */
const tabNames = ['survey', 'game', 'interview', 'report', 'records', 'guide'];
let activeTabName = null;
let tabNavigationInitialized = false;

function initializeTabNavigation() {
  if (tabNavigationInitialized || !window.location || !window.history ||
      typeof document.querySelectorAll !== 'function') return;
  tabNavigationInitialized = true;
  const restore = () => {
    const requested = window.location.hash.replace(/^#\//, '');
    const valid = tabNames.includes(requested);
    navigateTab(valid ? requested : 'survey', {fromHistory: valid, replace: true});
  };
  window.addEventListener('popstate', restore);
  window.addEventListener('hashchange', restore);
  restore();
}

function navigateTab(tabName, {fromHistory = false, replace = false} = {}) {
  const tabIndex = tabNames.indexOf(tabName);
  const target = document.getElementById(`view-${tabName}`);
  if (tabIndex < 0 || !target) return false;
  const hash = `#/${tabName}`;
  if (!fromHistory && window.location && window.history && window.location.hash !== hash) {
    try { window.history[replace ? 'replaceState' : 'pushState'](null, '', hash); }
    catch (_) { /* The visible tab still works if browser history is unavailable. */ }
  }
  if (activeTabName === tabName) return true;
  activeTabName = tabName;
  window.AstraGames?.onNavigation(tabName);
  document.querySelectorAll('.tab-view').forEach(v => v.classList.remove('active'));
  document.querySelectorAll('.nav-tab-btn').forEach(b => b.classList.remove('active'));

  target.classList.add('active');
  document.querySelectorAll('.nav-tab-btn')[tabIndex]?.classList.add('active');

  if (tabName === 'records') {
    renderRecordsTable();
  }

  refreshIcons();
  return true;
}
