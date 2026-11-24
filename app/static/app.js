(() => {
  "use strict";

  const $ = (selector, root = document) => root.querySelector(selector);
  const app = $("#app");
  const alertBox = $("#alert");
  const liveStatus = $("#status");
  const sessionNav = $("#session-nav");
  const modeBanner = $("#mode-banner");

  const state = {
    me: null,
    definitions: null,
    runs: [],
    run: null,
    pending: new Map(),
    timer: null,
    startedAt: 0,
    sliderTouched: false,
    sliderChanges: 0,
    rankSelection: [],
    rankEvents: [],
    gameAllocation: 5,
  };

  const ERROR_MESSAGES = {
    unauthorized: "로그인이 필요합니다.",
    invalid_credentials: "아이디 또는 비밀번호를 확인해 주세요.",
    username_taken: "이미 사용 중인 아이디입니다.",
    revision_conflict: "다른 화면에서 기록이 바뀌었습니다. 최신 상태를 불러왔습니다.",
    stale_after_finalize: "이미 완료된 연습은 변경할 수 없습니다.",
    idempotency_conflict: "같은 제출 요청의 내용이 달라 저장하지 않았습니다.",
    not_found: "요청한 기록을 찾을 수 없습니다.",
    invalid_state: "현재 단계에서는 이 동작을 할 수 없습니다.",
    validation_error: "입력 내용을 확인해 주세요.",
  };

  /** Unicode code point offsets [start, end), safe for Korean and emoji. */
  function codepointSlice(text, start, end) {
    return Array.from(String(text ?? "")).slice(start, end).join("");
  }

  function h(tag, attrs = {}, children = []) {
    const node = document.createElement(tag);
    Object.entries(attrs).forEach(([key, value]) => {
      if (value === undefined || value === null || value === false) return;
      if (key === "className") node.className = value;
      else if (key === "text") node.textContent = String(value);
      else if (key === "on") Object.entries(value).forEach(([event, handler]) => node.addEventListener(event, handler));
      else if (/^aria[A-Z]/.test(key)) node.setAttribute(key.replace(/[A-Z]/g, (letter) => `-${letter.toLowerCase()}`), String(value));
      else if (key in node && !key.startsWith("aria")) node[key] = value;
      else node.setAttribute(key, value === true ? "" : String(value));
    });
    (Array.isArray(children) ? children : [children]).flat(Infinity).forEach((child) => {
      if (child === null || child === undefined || child === false) return;
      node.append(child instanceof Node ? child : document.createTextNode(String(child)));
    });
    return node;
  }

  const button = (label, onClick, variant = "") => h("button", {
    type: "button",
    className: `btn ${variant}`.trim(),
    text: label,
    on: { click: onClick },
  });

  function replace(node) {
    clearTimer();
    app.replaceChildren(node);
    app.setAttribute("aria-busy", "false");
    window.scrollTo({ top: 0, behavior: "smooth" });
    requestAnimationFrame(() => $("h1", app)?.focus?.({ preventScroll: true }));
  }

  function announce(message) {
    liveStatus.textContent = "";
    requestAnimationFrame(() => { liveStatus.textContent = message; });
  }

  function showError(error, retry) {
    const code = error?.code || error?.message || "unknown";
    const message = ERROR_MESSAGES[code] || error?.detail || "요청을 처리하지 못했습니다. 잠시 후 다시 시도해 주세요.";
    alertBox.replaceChildren(h("strong", { text: "처리하지 못했어요. " }), document.createTextNode(message));
    if (retry) alertBox.append(" ", button("다시 시도", retry, "quiet"));
    alertBox.hidden = false;
    alertBox.focus();
  }

  function clearError() { alertBox.hidden = true; alertBox.replaceChildren(); }

  function keyFor(operation) {
    if (!state.pending.has(operation)) {
      const id = crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
      state.pending.set(operation, id);
    }
    return state.pending.get(operation);
  }

  async function api(path, options = {}) {
    const method = options.method || "GET";
    const headers = { Accept: "application/json", ...(options.headers || {}) };
    if (method !== "GET" && method !== "HEAD") headers["X-Requested-With"] = "interview-app";
    if (options.body !== undefined) headers["Content-Type"] = "application/json";
    let response;
    try {
      response = await fetch(`/api${path}`, {
        method,
        headers,
        credentials: "same-origin",
        body: options.body === undefined ? undefined : JSON.stringify(options.body),
      });
    } catch (cause) {
      const error = new Error("network_error"); error.code = "network_error"; error.cause = cause; throw error;
    }
    const data = response.status === 204 ? null : await response.json().catch(() => ({}));
    if (!response.ok) {
      const error = new Error(data?.error || `http_${response.status}`);
      error.code = data?.error || `http_${response.status}`;
      error.detail = data?.detail;
      error.status = response.status;
      throw error;
    }
    return data;
  }

  async function mutate(path, operation, payload = {}, onSuccess) {
    clearError();
    const request = { ...payload, idempotency_key: keyFor(operation) };
    try {
      const result = await api(path, { method: "POST", body: request });
      state.pending.delete(operation);
      if (result?.run_id) state.run = result;
      announce("서버에 저장했습니다.");
      onSuccess?.(result);
      return result;
    } catch (error) {
      if (error.code === "revision_conflict" && state.run?.run_id) {
        state.pending.delete(operation);
        try { state.run = await api(`/runs/${encodeURIComponent(state.run.run_id)}`); renderRun(); } catch (_) { /* original error remains */ }
        showError(error);
        throw error;
      }
      showError(error, () => mutate(path, operation, payload, onSuccess));
      throw error;
    }
  }

  function setMode(mode) {
    if (!mode) { modeBanner.hidden = true; return; }
    const mock = String(mode).toLowerCase() === "mock";
    modeBanner.textContent = mock
      ? "모의 분석 모드 · 외부 AI를 호출하지 않으며 결과는 연습용입니다."
      : `분석 실행 모드: ${mode} · 보고서에서 근거 출처를 확인하세요.`;
    modeBanner.hidden = false;
  }

  function updateNav() {
    sessionNav.replaceChildren();
    if (!state.me) return;
    sessionNav.append(
      h("span", { className: "meta", text: `${state.me.username || state.me.user_id || "사용자"}님` }),
      button("기록", () => navigate("#/runs"), "quiet"),
      button("로그아웃", logout, "secondary")
    );
  }

  function navigate(hash) {
    if (location.hash === hash) route();
    else location.hash = hash;
  }

  function authView(mode = "login") {
    const isRegister = mode === "register";
    const form = h("form", { className: "card auth-wrap" });
    const username = h("input", { id: "username", name: "username", type: "text", required: true, minLength: 2, maxLength: 64, autocomplete: "username" });
    const password = h("input", { id: "password", name: "password", type: "password", required: true, minLength: 8, autocomplete: isRegister ? "new-password" : "current-password" });
    form.append(
      h("p", { className: "eyebrow", text: "Practice archive" }),
      h("h1", { tabindex: "-1", text: isRegister ? "연습 기록을 시작해요" : "다시 이어서 연습해요" }),
      h("p", { className: "lede", text: "답변과 결과는 로그인한 본인의 회차에만 저장됩니다." }),
      h("div", { className: "field" }, [h("label", { htmlFor: "username", text: "아이디" }), username]),
      h("div", { className: "field" }, [h("label", { htmlFor: "password", text: "비밀번호" }), password, h("p", { className: "hint", text: "8자 이상 입력해 주세요." })]),
      h("div", { className: "actions" }, [
        h("button", { className: "btn", type: "submit", text: isRegister ? "가입하고 시작" : "로그인" }),
        button(isRegister ? "이미 계정이 있어요" : "처음 왔어요", () => authView(isRegister ? "login" : "register"), "quiet")
      ])
    );
    form.addEventListener("submit", async (event) => {
      event.preventDefault(); clearError();
      const submit = $("button[type=submit]", form); submit.disabled = true;
      try {
        await api(isRegister ? "/register" : "/login", { method: "POST", body: { username: username.value.trim(), password: password.value } });
        state.me = await api("/me"); updateNav(); await loadDefinitions(); navigate("#/runs");
      } catch (error) { showError(error, () => form.requestSubmit()); }
      finally { submit.disabled = false; }
    });
    replace(form); username.focus();
  }

  async function logout() {
    clearError();
    try { await api("/logout", { method: "POST", body: {} }); }
    catch (error) { showError(error, logout); return; }
    state.pending.clear();
    state.me = null; state.run = null; state.runs = []; updateNav(); setMode(null); navigate("#/login");
  }

  async function deleteAccount() {
    if (!window.confirm("계정과 모든 연습 원본·분석·보고서를 삭제할까요? 삭제 후에는 복구할 수 없습니다.")) return;
    clearError();
    try {
      await api("/account", { method: "DELETE" });
      state.pending.clear();
      state.me = null; state.run = null; state.runs = []; updateNav(); setMode(null); authView("register"); announce("계정과 연습 기록을 삭제했습니다.");
    } catch (error) { showError(error, deleteAccount); }
  }

  async function loadDefinitions() {
    state.definitions = await api("/definitions");
    setMode(state.definitions?.runtime_mode);
  }

  function homeView() {
    const view = h("section", { className: "hero" }, [
      h("div", {}, [
        h("p", { className: "eyebrow", text: "Evidence-led practice" }),
        h("h1", { tabindex: "-1", text: "선택에는 맥락이, 경험에는 근거가 있어요." }),
        h("p", { className: "lede", text: "네 가지 방식으로 나의 선택을 기록하고, 상황 과제와 면접 답변을 연결해 다음 설명을 연습해 보세요." }),
        h("div", { className: "actions" }, [button("연습 기록 보기", () => navigate("#/runs")), button("이 도구가 하는 일", () => $("#about")?.focus(), "secondary")]),
        h("div", { id: "about", tabindex: "-1", className: "disclosure" }, [
          h("strong", { text: "판정보다 설명을 돕습니다." }),
          h("p", { className: "hint", text: "응답 강도, 과제에서 관찰된 사실, 답변의 정확한 인용을 나란히 보여 줍니다. 서로 다른 맥락은 성급히 모순으로 결론 내리지 않습니다." })
        ])
      ]),
      h("div", { className: "hero-art", ariaHidden: "true" }, [h("p", { className: "hero-note", text: "누구에게 무엇을 물었고, 그 정보가 선택에 어떻게 이어졌나요?" }), h("span", { className: "hero-number", text: "01" })])
    ]);
    replace(view);
  }

  async function runsView() {
    clearError();
    try { state.runs = (await api("/runs"))?.runs || []; }
    catch (error) { showError(error, runsView); return; }
    const view = h("section", {}, [
      h("p", { className: "eyebrow", text: "My practice" }),
      h("h1", { tabindex: "-1", text: "나의 연습 기록" }),
      h("p", { className: "lede", text: "회차별 기록은 서로 섞이지 않습니다. 진행 중인 회차는 저장된 단계부터 이어집니다." }),
      h("div", { className: "actions" }, [button("새 연습 시작", createRun), button("계정과 모든 기록 삭제", deleteAccount, "danger")])
    ]);
    if (!state.runs.length) view.append(h("div", { className: "empty card" }, [h("h2", { text: "아직 기록이 없어요" }), h("p", { text: "첫 회차는 약 15~20분 동안 진행됩니다." })]));
    else {
      const grid = h("div", { className: "run-grid" });
      state.runs.forEach((run, index) => {
        const completed = ["complete", "completed", "finalized"].includes(run.status);
        grid.append(h("article", { className: "run-card" }, [
          h("span", { className: "status-pill", text: completed ? "완료" : "진행 중" }),
          h("h2", { text: `${index + 1}번째 연습` }),
          h("p", { className: "meta", text: formatDate(run.created_at || run.started_at) }),
          h("div", { className: "actions" }, [button(completed ? "보고서 보기" : "이어서 하기", () => openRun(run.run_id)), button("회차 삭제", () => deleteRun(run.run_id), "danger")])
        ]));
      });
      view.append(grid);
    }
    replace(view);
  }

  async function createRun() {
    clearError();
    const operation = "create-run";
    try {
      const run = await mutate("/runs", operation, {}, null);
      state.run = run; navigate(`#/runs/${encodeURIComponent(run.run_id)}`);
    } catch (_) { /* mutate displays retry */ }
  }

  async function openRun(id) {
    clearError(); app.setAttribute("aria-busy", "true");
    try { state.run = await api(`/runs/${encodeURIComponent(id)}`); navigate(`#/runs/${encodeURIComponent(id)}`); if (location.hash.includes(id)) renderRun(); }
    catch (error) { showError(error, () => openRun(id)); }
  }

  async function deleteRun(id) {
    if (!window.confirm("이 연습 회차의 원본 응답과 파생 보고서를 모두 삭제할까요?")) return;
    try {
      await api(`/runs/${encodeURIComponent(id)}`, { method: "DELETE" });
      if (state.run?.run_id === id) state.run = null;
      state.pending.clear();
      state.runs = state.runs.filter((run) => run.run_id !== id);
      announce("회차를 삭제했습니다.");
      navigate("#/runs");
    }
    catch (error) { showError(error, () => deleteRun(id)); }
  }

  function formatDate(value) {
    if (!value) return "저장 시각 정보 없음";
    const date = new Date(value);
    return Number.isNaN(date.valueOf()) ? String(value) : new Intl.DateTimeFormat("ko-KR", { dateStyle: "medium", timeStyle: "short" }).format(date);
  }

  function surveyDefinitions() {
    const surveys = state.definitions?.surveys;
    if (Array.isArray(surveys)) return surveys;
    if (surveys && typeof surveys === "object") return Object.values(surveys).flatMap((v) => Array.isArray(v) ? v : [v]);
    return [];
  }

  function answeredItemIds() {
    return new Set((state.run?.records || []).filter((r) => r.source_type === "survey" || r.item_id).map((r) => r.item_id || r.data?.item_id));
  }

  function answerRecords() {
    return (state.run?.records || []).filter((r) => ["answer", "interview_answer", "typed_answer"].includes(r.source_type) || r.data?.answer_id || r.data?.question_id);
  }

  function answeredQuestionIds() {
    return new Set(answerRecords().map((r) => r.item_id || r.data?.question_id || r.question_id));
  }

  function allQuestions() {
    const runQuestions = state.run?.questions || [];
    const baseDefinitions = state.definitions?.questions || [];
    const list = Array.isArray(runQuestions) ? runQuestions : Object.values(runQuestions || {});
    const base = Array.isArray(baseDefinitions) ? baseDefinitions : Object.values(baseDefinitions || {});
    const map = new Map([...base, ...list].map((q) => [q.question_id, q]));
    return [...map.values()];
  }

  function runStage() {
    if (state.run?.report || ["complete", "completed", "finalized"].includes(state.run?.status)) return "report";
    const surveys = surveyDefinitions();
    if (surveys.some((item) => !answeredItemIds().has(item.item_id))) return "survey";
    if (state.run?.game?.phase !== "complete") return "game";
    const questions = allQuestions();
    const answered = answeredQuestionIds();
    const baseline = questions.filter((q) => !q.question_mode || q.question_mode === "baseline");
    if (baseline.some((q) => !answered.has(q.question_id))) return "baseline";
    const conditioned = questions.filter((q) => q.question_mode === "adaptive_followup");
    const analysisReady = conditioned.length > 0 || state.run?.analysis || state.run?.report_draft;
    if (!analysisReady) return "analyze";
    if (conditioned.some((q) => !answered.has(q.question_id))) return "followup";
    return "finalize";
  }

  function shell(content, active) {
    const stages = [["survey", "나 알아보기"], ["game", "상황 과제"], ["baseline", "기본 면접"], ["followup", "확인 질문"], ["report", "근거 보고서"]];
    const aliases = { analyze: "baseline", finalize: "followup" };
    const normalized = aliases[active] || active;
    const current = Math.max(0, stages.findIndex(([id]) => id === normalized));
    const rail = h("aside", { className: "rail", ariaLabel: "연습 단계" }, [
      h("p", { className: "eyebrow", text: "Practice flow" }),
      h("ol", {}, stages.map(([id, label], i) => h("li", { className: i < current ? "done" : id === normalized ? "current" : "", text: label, ariaCurrent: id === normalized ? "step" : null }))),
      button("기록 목록", () => navigate("#/runs"), "quiet")
    ]);
    return h("div", { className: "workspace" }, [rail, h("div", { className: "content" }, [h("div", { className: "progress", ariaLabel: `전체 5단계 중 ${current + 1}단계` }, h("span", { style: `width:${((current + 1) / 5) * 100}%` })), content])]);
  }

  function renderRun() {
    clearError();
    if (!state.run) return runsView();
    if (state.run.survey_set_version) {
      replace(h('section', {className:'card'}, [
        h('h1', {text:'이 회차는 새 화면에서 이어갈 수 있습니다.',tabIndex:-1}),
        h('p', {text:'저장된 문항과 답변을 유지하려면 새 연습 화면에서 해당 회차를 선택해 주세요.'}),
        h('a', {href:'/#survey',text:'새 화면으로 이동',className:'btn'}),
      ]));
      return;
    }
    const stage = runStage();
    if (stage === "survey") renderSurvey();
    else if (stage === "game") renderGame();
    else if (stage === "baseline" || stage === "followup") renderInterview(stage);
    else if (stage === "analyze") renderAnalyze();
    else if (stage === "finalize") renderFinalize();
    else renderReport();
  }

  function optionsFor(item) {
    return item.ordered_options || item.options || state.definitions?.scale?.ordered_options || state.definitions?.scale?.options || [];
  }

  function renderSurvey() {
    const surveys = surveyDefinitions();
    const answered = answeredItemIds();
    const item = surveys.find((entry) => !answered.has(entry.item_id));
    if (!item) return renderRun();
    state.startedAt = performance.now();
    const index = surveys.indexOf(item);
    const type = item.type || item.response_type;
    const card = h("section", { className: "card question-card" }, [
      h("p", { className: "eyebrow", text: `선택 ${index + 1} / ${surveys.length}` }),
      h("h1", { tabindex: "-1", text: surveyTitle(type) }),
      h("p", { className: "lede", text: item.prompt || item.prompt_snapshot || "제시된 문항에 답해 주세요." })
    ]);
    const form = h("form");
    if (type === "ordinal_6") form.append(ordinalField(item, "selected_position", "나의 응답"));
    else if (type === "paired_perspective") form.append(pairedField(item));
    else if (type === "bipolar_slider") form.append(sliderField(item));
    else if (type === "top_k_rank") form.append(rankField(item));
    else form.append(h("p", { className: "error-text", text: `지원하지 않는 입력 형식입니다: ${type || "알 수 없음"}` }));
    const timer = h("p", { className: "timer", ariaLive: "polite" });
    if (item.time_limit_ms) card.append(timer);
    form.append(h("div", { className: "actions" }, h("button", { type: "submit", className: "btn", text: type === "bipolar_slider" ? "이 위치로 확정" : "응답 저장" })));
    form.addEventListener("submit", (event) => { event.preventDefault(); submitSurvey(item, form, false); });
    card.append(form, h("p", { className: "hint", text: "응답 강도와 선택 순서를 그대로 저장하며, 이를 능력 점수로 바꾸지 않습니다." }));
    replace(shell(card, "survey"));
    if (item.time_limit_ms) startTimer(item.time_limit_ms, timer, () => submitSurvey(item, form, true));
  }

  function surveyTitle(type) {
    return ({ ordinal_6: "나 알아보기", paired_perspective: "두 관점에서 보기", bipolar_slider: "두 방향 사이에서 선택하기", top_k_rank: "중요한 순서 정하기" })[type] || "선택 기록하기";
  }

  function ordinalField(item, name, legend) {
    const fieldset = h("fieldset", {}, h("legend", { text: legend }));
    const scale = h("div", { className: "scale" });
    optionsFor(item).forEach((option, i) => {
      const position = Number(option.position ?? i + 1);
      const id = `${name}-${position}`;
      scale.append(h("div", { className: "choice" }, [h("input", { id, type: "radio", name, value: position, required: true }), h("label", { htmlFor: id, text: option.label || option.text || String(position) })]));
    });
    fieldset.append(scale);
    return fieldset;
  }

  function pairedField(item) {
    return h("div", { className: "perspectives" }, [
      h("section", { className: "perspective" }, [h("h2", { text: "내가 보는 나" }), h("p", { className: "hint", text: "현재 나의 관점으로 답해 주세요." }), ordinalField(item, "self_position", "자기 관점 응답")]),
      h("section", { className: "perspective" }, [h("h2", { text: "타인이 볼 것 같은 나" }), h("p", { className: "hint", text: "실제 타인의 평가가 아니라, 내가 상상한 관점입니다." }), ordinalField(item, "others_position", "상상한 타인 관점 응답")])
    ]);
  }

  function sliderField(item) {
    state.sliderTouched = false; state.sliderChanges = 0;
    const min = Number(item.min ?? item.range?.min ?? -6), max = Number(item.max ?? item.range?.max ?? 6), step = Number(item.step ?? item.range?.step ?? 1), initial = Number(item.initial_value ?? item.range?.initial_value ?? 0);
    const slider = h("input", { id: "bipolar", name: "final_value", type: "range", min, max, step, value: initial, ariaDescribedby: "slider-help slider-value" });
    const value = h("output", { id: "slider-value", className: "slider-value", htmlFor: "bipolar", text: `현재 위치 ${initial}` });
    slider.addEventListener("input", () => { state.sliderTouched = true; state.sliderChanges += 1; value.textContent = `현재 위치 ${slider.value}`; });
    const left = item.left_anchor?.label || item.left_anchor_label || item.left_label || "왼쪽 방향";
    const right = item.right_anchor?.label || item.right_anchor_label || item.right_label || "오른쪽 방향";
    return h("div", { className: "slider-wrap" }, [h("label", { htmlFor: "bipolar", text: "두 방향 사이의 현재 선택" }), slider, h("div", { className: "anchors" }, [h("span", { text: left }), h("span", { text: right })]), value, h("p", { id: "slider-help", className: "hint", text: "가운데도 유효한 선택입니다. 슬라이더를 움직이지 않았더라도 ‘이 위치로 확정’을 누르면 의도적인 응답으로 저장됩니다." })]);
  }

  function rankField(item) {
    state.rankSelection = []; state.rankEvents = [];
    const candidates = item.candidates || item.all_candidates || item.options || [];
    const k = Number(item.requested_k || item.k || Math.min(3, candidates.length));
    const candidateList = h("div", { className: "candidate-list", ariaLabel: "선택 가능한 후보" });
    const rankList = h("ol", { className: "rank-list", ariaLabel: "선택한 최종 순위", ariaLive: "polite" });
    const help = h("p", { className: "hint", text: `${candidates.length}개 중 ${k}개를 고른 뒤 화살표 버튼으로 순서를 조정하세요. 고르지 않은 항목은 싫다는 뜻이 아닙니다.` });
    const render = () => {
      candidateList.replaceChildren(); rankList.replaceChildren();
      candidates.filter((c) => !state.rankSelection.includes(c.option_id || c.candidate_id || c.id)).forEach((candidate) => {
        const id = candidate.option_id || candidate.candidate_id || candidate.id;
        const add = h("button", { type: "button", className: "candidate", text: candidate.label || candidate.text || id, disabled: state.rankSelection.length >= k });
        add.addEventListener("click", () => { state.rankSelection.push(id); state.rankEvents.push({ action: "select", option_id: id, order: state.rankEvents.length + 1 }); render(); announce(`${candidate.label || candidate.text || id} 항목을 ${state.rankSelection.length}순위로 선택했습니다.`); });
        candidateList.append(add);
      });
      state.rankSelection.forEach((id, index) => {
        const candidate = candidates.find((c) => (c.option_id || c.candidate_id || c.id) === id) || {};
        const move = (delta) => { const target = index + delta; if (target < 0 || target >= state.rankSelection.length) return; [state.rankSelection[index], state.rankSelection[target]] = [state.rankSelection[target], state.rankSelection[index]]; state.rankEvents.push({ action: "move", option_id: id, rank: target + 1 }); render(); announce(`${candidate.label || candidate.text || id} 항목을 ${target + 1}순위로 옮겼습니다.`); };
        const remove = () => { state.rankSelection.splice(index, 1); state.rankEvents.push({ action: "remove", option_id: id }); render(); };
        rankList.append(h("li", { className: "ranked" }, [h("span", { className: "rank-no", text: `${index + 1}` }), h("span", { text: candidate.label || candidate.text || id }), h("span", { className: "rank-controls" }, [h("button", { type: "button", className: "icon-btn", ariaLabel: `${index + 1}순위 항목을 위로`, text: "↑", disabled: index === 0, on: { click: () => move(-1) } }), h("button", { type: "button", className: "icon-btn", ariaLabel: `${index + 1}순위 항목을 아래로`, text: "↓", disabled: index === state.rankSelection.length - 1, on: { click: () => move(1) } }), h("button", { type: "button", className: "icon-btn", ariaLabel: `${index + 1}순위 항목 선택 해제`, text: "×", on: { click: remove } })]) ]));
      });
    };
    render();
    return h("fieldset", {}, [h("legend", { text: `나에게 중요한 ${k}개 순위` }), help, h("div", { className: "rank-layout" }, [h("section", {}, [h("h2", { text: "후보" }), candidateList]), h("section", {}, [h("h2", { text: "나의 순위" }), rankList])])]);
  }

  async function submitSurvey(item, form, timedOut) {
    if (form.dataset.submitting) return;
    const type = item.type || item.response_type;
    const elapsed = Math.max(0, Math.round(performance.now() - state.startedAt));
    let response;
    if (type === "ordinal_6") {
      const selected = form.elements.selected_position?.value;
      if (!timedOut && !selected) return form.reportValidity();
      response = selected ? { selected_position: Number(selected) } : null;
    } else if (type === "paired_perspective") {
      const self = form.elements.self_position?.value, others = form.elements.others_position?.value;
      if (!timedOut && (!self || !others)) return form.reportValidity();
      response = { self: { selected_position: self ? Number(self) : null, status: self ? "submitted" : "timed_out" }, imagined_others: { selected_position: others ? Number(others) : null, status: others ? "submitted" : "timed_out" } };
    } else if (type === "bipolar_slider") {
      response = { final_value: timedOut && !state.sliderTouched ? null : Number(form.elements.final_value.value), interaction_occurred: state.sliderTouched, explicit_confirmation: !timedOut, change_count: state.sliderChanges };
    } else if (type === "top_k_rank") {
      const k = Number(item.requested_k || item.k || 3);
      if (!timedOut && state.rankSelection.length !== k) { showError({ detail: `${k}개를 모두 선택해 주세요.` }); return; }
      response = { selected_ids: [...state.rankSelection], selection_events: [...state.rankEvents] };
    }
    clearTimer(); form.dataset.submitting = "true"; $("button[type=submit]", form).disabled = true;
    const payload = { item_id: item.item_id, item_version: item.item_version, response, status: timedOut ? "timed_out" : "submitted", elapsed_ms: elapsed, expected_revision: state.run.revision };
    try { await mutate(`/runs/${encodeURIComponent(state.run.run_id)}/surveys`, `survey:${state.run.run_id}:${item.item_id}`, payload, renderRun); }
    catch (_) { form.dataset.submitting = ""; $("button[type=submit]", form).disabled = false; }
  }

  function startTimer(ms, output, onTimeout) {
    clearTimer(); const end = performance.now() + ms;
    const tick = () => { const remaining = Math.max(0, end - performance.now()); output.textContent = `남은 시간 ${Math.ceil(remaining / 1000)}초`; if (!remaining) { clearTimer(); announce("제한 시간이 끝났습니다. 현재 응답 상태를 저장합니다."); onTimeout(); } };
    state.timer = setInterval(tick, 1000); tick();
  }
  function clearTimer() { if (state.timer) clearInterval(state.timer); state.timer = null; }

  function gameDefinitions() {
    return state.definitions?.game || {};
  }

  function currentRound() {
    const game = state.run.game || {};
    const rounds = game.rounds || [];
    return rounds[game.round_index || 0] || gameDefinitions().rounds?.[game.round_index || 0] || {};
  }

  function renderGame() {
    const game = state.run.game || { phase: "awaiting_start", round_index: 0, rounds: [] };
    const round = currentRound();
    const total = Number(round.total_resources ?? 10);
    state.gameAllocation = Number(round.current_allocation?.personal ?? round.initial_decision?.personal ?? Math.floor(total / 2));
    const phase = game.phase || "awaiting_start";
    const section = h("section", { className: "card" }, [
      h("div", { className: "round-dots", ariaLabel: `현재 ${Number(game.round_index || 0) + 1}번째 라운드` }, (game.rounds?.length ? game.rounds : gameDefinitions().rounds || [1,2,3,4]).map((_, i) => h("span", { className: i < (game.round_index || 0) ? "done" : i === (game.round_index || 0) ? "active" : "" }))),
      h("p", { className: "eyebrow", text: round.practice_or_main === "practice" ? "연습 라운드 · 집계에서 분리" : `본 라운드 ${Number(game.round_index || 0)}` }),
      h("h1", { tabindex: "-1", text: round.title || "자원 다리 과제" }),
      h("p", { className: "lede", text: round.instructions || gameDefinitions().instructions || "제한된 자원을 개인 과제와 팀 과제에 나누고, 새 정보가 주어지면 선택을 다시 확인합니다." })
    ]);
    const board = h("div", { className: "game-board" });
    const main = h("div");
    const side = h("aside", { className: "info-panel" }, [h("h2", { text: "라운드 정보" }), h("p", { text: visibleInformation(round) })]);
    if (phase === "awaiting_start") main.append(h("p", { text: "준비가 되면 라운드를 시작하세요. 라운드별 조건과 선택 기회는 서버에 순서대로 기록됩니다." }), button("라운드 시작", () => gameAction("start")));
    else if (phase === "decision") {
      main.append(h("h2", { text: "결정 전 정보 확인" }), h("p", { text: "팀 과제 정보를 열어볼 수 있습니다. 열지 않는 선택도 가능하며, 정보를 열었다고 이해했다고 간주하지 않습니다." }), button("팀원 과제 정보 열기", () => gameAction("open_info"), "secondary"), allocationControl(total, false), button("초기 배분 확정", () => gameAction("allocate", { personal: state.gameAllocation, reason: $("#allocation-reason")?.value || "" })));
    } else if (phase === "allocated") main.append(h("h2", { text: "초기 선택이 저장됐어요" }), h("p", { text: allocationText(round, total) }), button("새 정보 확인", () => gameAction("reveal")));
    else if (phase === "revision") {
      main.append(h("h2", { text: "새 정보 이후 선택" }), h("div", { className: "info-panel" }, [h("strong", { text: "새로 공개된 정보" }), h("p", { text: round.new_information?.text || round.new_information || "새 정보가 공개되었습니다." })]), h("p", { text: "처음 선택을 유지해도 괜찮습니다. 유지와 시간 초과는 서로 다르게 기록됩니다." }), allocationControl(total, true), button("최종 선택 확정", () => gameAction("revise", { personal: state.gameAllocation, reason: $("#allocation-reason")?.value || "" })));
    } else if (phase === "round_complete") main.append(h("h2", { text: "라운드 기록 완료" }), h("p", { text: round.missing_reason ? "제한 시간이 끝났습니다. 확정하지 못한 선택은 미응답으로 기록했습니다." : "이 결과는 게임 규칙 안의 결과이며 협업 점수로 바꾸지 않습니다." }), button("다음 라운드", () => gameAction("next")));
    else if (phase === "complete") { state.run.game.phase = "complete"; return renderRun(); }
    board.append(main, side); section.append(board, rewardTable(round.reward_table));
    const timer = h("p", { className: "timer", ariaLive: "polite" });
    const remaining = Date.parse(round.deadline_at) - Date.now();
    const timedPhase = ["decision", "allocated", "revision"].includes(phase);
    if (timedPhase && Number.isFinite(remaining)) section.append(timer);
    replace(shell(section, "game"));
    if (timedPhase && Number.isFinite(remaining)) startTimer(Math.max(0, remaining), timer, () => gameAction("timeout"));
  }

  function visibleInformation(round) {
    const info = round.information;
    if (!info) return "현재 공개된 기본 조건을 확인하세요.";
    if (typeof info === "string") return info;
    if (Array.isArray(info)) return info.map((v) => typeof v === "string" ? v : v.text || v.label).filter(Boolean).join(" · ");
    return info.opened ? info.text || info.opened_text || "팀 과제 정보를 확인했습니다." : info.summary || info.closed_text || "선택하면 상세 정보를 확인할 수 있습니다.";
  }

  function allocationControl(total, revision) {
    const input = h("input", { id: "allocation", type: "range", min: 0, max: total, step: 1, value: state.gameAllocation, ariaDescribedby: "allocation-values" });
    const personal = h("strong", { text: state.gameAllocation });
    const team = h("strong", { text: total - state.gameAllocation });
    input.addEventListener("input", () => { state.gameAllocation = Number(input.value); personal.textContent = input.value; team.textContent = total - Number(input.value); });
    return h("div", {}, [
      h("label", { htmlFor: "allocation", text: revision ? "최종 자원 배분" : "초기 자원 배분" }), input,
      h("div", { id: "allocation-values", className: "allocation" }, [h("div", {}, [h("span", { text: "개인 과제" }), personal]), h("span", { text: "↔" }), h("div", {}, [h("span", { text: "팀 과제" }), team])]),
      h("label", { htmlFor: "allocation-reason", text: "선택 이유 (선택 입력)" }), h("textarea", { id: "allocation-reason", rows: 3, placeholder: "어떤 조건을 보고 이렇게 나눴는지 적어 보세요." })
    ]);
  }

  function allocationText(round, total) {
    const personal = round.initial_decision?.personal ?? round.personal ?? state.gameAllocation;
    return `개인 과제 ${personal}, 팀 과제 ${total - Number(personal)}로 저장했습니다.`;
  }

  function rewardTable(table) {
    if (!table) return null;
    const rows = Array.isArray(table) ? table : Object.entries(table).map(([condition, reward]) => ({ condition, reward }));
    const tbody = h("tbody");
    rows.forEach((row) => tbody.append(h("tr", {}, [h("td", { text: row.condition || row.label || row.allocation || "조건" }), h("td", { text: row.reward ?? row.result ?? row.value ?? "-" })])));
    return h("details", { className: "disclosure" }, [h("summary", { text: "보상 규칙 보기" }), h("table", { className: "reward-table" }, [h("thead", {}, h("tr", {}, [h("th", { scope: "col", text: "조건" }), h("th", { scope: "col", text: "과제 결과" })])), tbody])]);
  }

  async function gameAction(action, extra = {}) {
    const op = `game:${state.run.run_id}:${state.run.revision}:${action}`;
    const controls = [...app.querySelectorAll("button, input, textarea")].filter((control) => !control.disabled);
    controls.forEach((control) => { control.disabled = true; });
    try { await mutate(`/runs/${encodeURIComponent(state.run.run_id)}/game`, op, { action, ...extra, expected_revision: state.run.revision }, renderRun); }
    catch (_) { /* retry shown */ }
    finally { controls.forEach((control) => { if (control.isConnected) control.disabled = false; }); }
  }

  function renderInterview(mode) {
    const answered = answeredQuestionIds();
    const questions = allQuestions().filter((q) => mode === "baseline" ? (!q.question_mode || q.question_mode === "baseline") : q.question_mode === "adaptive_followup");
    const question = questions.find((q) => !answered.has(q.question_id));
    if (!question) return renderRun();
    state.startedAt = performance.now();
    const form = h("form", { className: "card question-card" });
    const answer = h("textarea", { id: "answer", name: "answer", required: true, minLength: 1, maxLength: 12000, ariaDescribedby: "answer-help" });
    form.append(
      h("p", { className: "eyebrow", text: mode === "baseline" ? `기본 질문 ${questions.indexOf(question) + 1} / ${questions.length}` : `확인 질문 ${questions.indexOf(question) + 1} / ${questions.length}` }),
      h("h1", { tabindex: "-1", text: question.question_text || question.prompt || "경험을 설명해 주세요." }),
      mode === "followup" ? h("p", { className: "hint", text: "앞선 선택과 과제 기록을 바탕으로 확인하는 질문입니다. 후속 답변은 기본 답변과 분리해 저장됩니다." }) : document.createDocumentFragment(),
      h("div", { className: "field" }, [h("label", { htmlFor: "answer", text: "나의 답변" }), answer, h("p", { id: "answer-help", className: "hint", text: "상황, 나의 역할, 확인한 정보, 선택 이유, 결과를 기억나는 범위에서 적어 보세요. 저장 전까지 브라우저에 별도로 보관하지 않습니다." })]),
      h("div", { className: "actions" }, [
        h("button", { type: "submit", className: "btn", text: "답변 저장" }),
        button("이 질문 건너뛰기", async () => {
          try {
            await mutate(`/runs/${encodeURIComponent(state.run.run_id)}/answers`, `answer:${state.run.run_id}:${question.question_id}`,
              { question_id: question.question_id, text: "", status: "skipped", expected_revision: state.run.revision }, renderRun);
          } catch (_) { /* retry shown */ }
        }, "quiet")
      ])
    );
    if (question.disclosure_refs?.length || question.conditioned_on_prior_evidence) form.append(h("details", { className: "disclosure" }, [h("summary", { text: "이 질문에 사용된 앞선 근거" }), h("p", { text: disclosureText(question) })]));
    form.addEventListener("submit", async (event) => {
      event.preventDefault(); if (!form.reportValidity()) return;
      const payload = { question_id: question.question_id, text: answer.value, elapsed_ms: Math.max(0, Math.round(performance.now() - state.startedAt)), expected_revision: state.run.revision };
      $("button[type=submit]", form).disabled = true;
      try { await mutate(`/runs/${encodeURIComponent(state.run.run_id)}/answers`, `answer:${state.run.run_id}:${question.question_id}`, payload, renderRun); }
      catch (_) { $("button[type=submit]", form).disabled = false; }
    });
    replace(shell(form, mode)); answer.focus();
  }

  function disclosureText(question) {
    const refs = question.disclosure_refs || question.disclosed_evidence || [];
    if (typeof refs === "string") return refs;
    if (!refs.length) return "이 질문은 앞선 응답과 과제 관찰을 조건으로 생성되었습니다.";
    return refs.map((r) => typeof r === "string" ? r : r.label || r.summary || r.record_id).filter(Boolean).join(" · ");
  }

  function renderAnalyze() {
    const view = h("section", { className: "card question-card" }, [h("p", { className: "eyebrow", text: "Baseline saved" }), h("h1", { tabindex: "-1", text: "기본 답변을 먼저 살펴볼게요" }), h("p", { className: "lede", text: "기본 답변은 설문 강도나 게임 결과로 내용을 보충하지 않고 따로 추출합니다. 이후 필요한 경우에만 확인 질문을 만듭니다." }), h("div", { className: "actions" }, button("확인 질문 만들기", analyzeRun))]);
    replace(shell(view, "analyze"));
  }

  async function analyzeRun() {
    try { await mutate(`/runs/${encodeURIComponent(state.run.run_id)}/analyze`, `analyze:${state.run.run_id}`, { expected_revision: state.run.revision }, renderRun); }
    catch (_) { /* retry shown */ }
  }

  function renderFinalize() {
    const view = h("section", { className: "card question-card" }, [h("p", { className: "eyebrow", text: "Ready to connect" }), h("h1", { tabindex: "-1", text: "근거를 연결할 준비가 됐어요" }), h("p", { className: "lede", text: "저장된 응답, 과제의 실제 조건, 답변 원문을 대조해 행동별 근거 카드를 만듭니다. 확인되지 않은 내용은 빈칸을 채우지 않고 남겨 둡니다." }), h("div", { className: "actions" }, button("근거 보고서 만들기", finalizeRun))]);
    replace(shell(view, "finalize"));
  }

  async function finalizeRun() {
    try { await mutate(`/runs/${encodeURIComponent(state.run.run_id)}/finalize`, `finalize:${state.run.run_id}`, { expected_revision: state.run.revision }, renderRun); }
    catch (_) { /* retry shown */ }
  }

  function renderReport() {
    const report = state.run.report || {};
    setMode(report.runtime_mode || state.run.runtime_mode || state.definitions?.runtime_mode);
    const section = h("section", {}, [h("p", { className: "eyebrow", text: "Evidence report" }), h("h1", { tabindex: "-1", text: report.title || "나의 근거 연결 보고서" }), h("p", { className: "lede", text: report.summary || "응답, 상황 과제, 면접 답변에서 확인된 사실을 행동별로 연결했습니다." })]);
    const cards = report.cards || report.evidence_cards || report.behaviors || [];
    const list = Array.isArray(cards) ? cards : Object.entries(cards).map(([behavior_id, card]) => ({ behavior_id, ...card }));
    const grid = h("div", { className: "report-grid" });
    if (!list.length) grid.append(h("div", { className: "card empty" }, [h("h2", { text: "표시할 근거 카드가 없습니다" }), h("p", { text: "근거가 충분하지 않거나 보고서 구조를 확인할 수 없습니다." })]));
    list.forEach((card) => grid.append(reportCard(card)));
    section.append(grid);
    if (report.limitations?.length) section.append(h("section", { className: "card disclosure" }, [
      h("h2", { text: "이 보고서의 해석 범위" }),
      h("ul", {}, report.limitations.map((limit) => h("li", { text: limit })))
    ]));
    const originals = h("details", { className: "card disclosure" }, h("summary", { text: "저장된 원본 응답 모두 보기" }));
    (state.run.records || []).forEach((record) => {
      const data = record.data || {};
      originals.append(h("section", { className: "source" }, [
        h("h3", { text: data.prompt_snapshot || data.question_snapshot?.question_text || record.item_id || "원본 기록" }),
        h("p", { className: "hint", text: ({ submitted: "제출됨", timed_out: "시간 초과", skipped: "건너뜀" })[record.status] || record.status }),
        data.text !== undefined ? h("blockquote", { className: "quote", text: data.text }) : renderObject(data),
        h("p", { className: "meta", text: `원본 ${record.record_id} · 버전 ${record.source_version}` }),
      ]));
    });
    section.append(originals);
    const details = h("details", { className: "card disclosure" }, [h("summary", { text: "원본 기록과 분석 계보 보기" }), renderObject(report.lineage || report.provenance || { runtime_mode: report.runtime_mode || state.definitions?.runtime_mode, report_version: report.report_version || report.version })]);
    section.append(details, h("div", { className: "actions" }, [button("기록 목록으로", () => navigate("#/runs")), button("이 회차 삭제", () => deleteRun(state.run.run_id), "danger")]));
    replace(shell(section, "report"));
  }

  function reportCard(card) {
    const article = h("article", { className: "evidence-card" }, [
      h("span", { className: "status-pill", text: comparisonLabel(card.comparison_status || card.status) }),
      h("h2", { text: card.behavior_name || card.title || card.behavior_id || "행동 근거" }),
      card.operational_definition ? h("p", { className: "hint", text: card.operational_definition }) : null
    ]);
    const survey = card.survey_evidence || card.survey || card.responses;
    const game = card.game_evidence || card.game || card.observation;
    const interview = card.interview_evidence || card.interview || card.quotes;
    if (survey) article.append(sourceBlock("내가 선택한 응답", survey));
    if (game) article.append(sourceBlock("상황 과제에서 관찰된 사실", game));
    if (interview) article.append(interviewBlock(interview));
    if (card.comparison || card.interpretation || card.limitation) article.append(sourceBlock("함께 볼 때의 제한", card.comparison || card.interpretation || card.limitation));
    if (card.limitations?.length) article.append(sourceBlock("해석할 때 기억할 점", card.limitations));
    if (card.open_question || card.next_question) article.append(sourceBlock("아직 확인할 질문", card.open_question || card.next_question));
    if (card.practice_suggestion || card.next_practice) article.append(sourceBlock("다음 연습", card.practice_suggestion || card.next_practice));
    if (!survey && !game && !interview) article.append(renderObject(card));
    return article;
  }

  function sourceBlock(title, value) {
    const section = h("section", { className: "source" }, h("h3", { text: title }));
    if (typeof value === "string" || typeof value === "number") section.append(h("p", { text: value }));
    else if (value?.selected_label_snapshot) {
      const incomplete = value.record_status && value.record_status !== "submitted";
      section.append(h("p", { text: incomplete
        ? `“${value.selected_label_snapshot}”는 종료 전 선택한 미확정 응답입니다. 시간 초과·건너뛰기 상태를 보존하며 확정 응답과 비교하지 않습니다.`
        : `“${value.selected_label_snapshot}”라고 응답했습니다. 이 응답은 본인의 자기보고입니다.` }));
      section.append(h("details", { className: "disclosure" }, [h("summary", { text: "응답 원본과 버전" }), renderObject(value)]));
    } else if (value?.metric_id) {
      const label = { B01: "결정 전에 정보를 연 횟수", B02: "배분을 확정한 횟수", B03: "새 정보 뒤 선택을 바꾼 횟수" }[value.behavior_id] || "관찰 횟수";
      section.append(h("p", { text: value.denominator ? `${label}: 적격 기회 ${value.denominator}회 중 ${value.numerator}회` : "평가할 수 있는 관찰 기회가 없습니다." }));
      if (value.interpretation_limit) section.append(h("p", { className: "hint", text: value.interpretation_limit }));
      section.append(h("details", { className: "disclosure" }, [h("summary", { text: "과제 조건과 집계 근거" }), renderObject(value)]));
    } else if (value?.status && value?.reason) {
      section.append(h("p", { text: comparisonLabel(value.status) }), h("details", { className: "disclosure" }, [h("summary", { text: "판단 근거 상세" }), renderObject(value)]));
    } else section.append(renderObject(value));
    return section;
  }

  function interviewBlock(value) {
    const section = h("section", { className: "source" }, h("h3", { text: "면접 답변 근거" }));
    const entries = Array.isArray(value) ? value : [value];
    entries.forEach((entry) => {
      if (typeof entry === "string") section.append(h("blockquote", { className: "quote", text: entry }));
      else {
        const quote = entry.quote || entry.text || (entry.answer_text !== undefined && Number.isInteger(entry.start) && Number.isInteger(entry.end) ? codepointSlice(entry.answer_text, entry.start, entry.end) : null);
        if (quote) section.append(h("blockquote", { className: "quote", text: quote }));
        section.append(h("details", { className: "disclosure" }, [h("summary", { text: "인용 원문·범위 확인" }), h("p", { text: entry.answer_text || "" }), renderObject(Object.fromEntries(Object.entries(entry).filter(([key]) => !["quote", "text", "answer_text"].includes(key))))]));
      }
    });
    return section;
  }

  function renderObject(value) {
    if (value === null || value === undefined) return h("p", { className: "hint", text: "확인된 내용 없음" });
    if (["string", "number", "boolean"].includes(typeof value)) return h("p", { text: String(value) });
    if (Array.isArray(value)) return h("ul", {}, value.map((item) => h("li", {}, renderObject(item))));
    const dl = h("dl", { className: "meta" });
    Object.entries(value).forEach(([key, item]) => {
      if (item === null || item === undefined) return;
      dl.append(h("dt", { text: humanKey(key) }), h("dd", {}, renderObject(item)));
    });
    return dl;
  }

  function humanKey(key) {
    const labels = { selected_label: "선택 라벨", selected_label_snapshot: "선택 라벨", selected_position: "선택 위치", perspective: "관점", numerator: "관찰 횟수", denominator: "기회 횟수", missing: "빠진 설명", limitations: "해석 제한", runtime_mode: "분석 모드", report_version: "보고서 버전", source_type: "출처" };
    return labels[key] || key.replaceAll("_", " ");
  }

  function comparisonLabel(status) {
    return ({ supports_statement: "같은 맥락에서 뒷받침", contextual_difference: "맥락 차이", needs_clarification: "추가 확인 필요", insufficient_evidence: "근거 부족", not_comparable: "직접 비교 어려움" })[status] || status || "근거 확인";
  }

  async function route() {
    clearError();
    const path = location.hash || "#/";
    if (!state.me) { authView(path === "#/register" ? "register" : "login"); return; }
    if (!state.definitions) { try { await loadDefinitions(); } catch (error) { showError(error, route); return; } }
    if (path === "#/" || path === "#") homeView();
    else if (path === "#/runs") await runsView();
    else if (path.startsWith("#/runs/")) {
      const id = decodeURIComponent(path.slice("#/runs/".length));
      try { state.run = await api(`/runs/${encodeURIComponent(id)}`); }
      catch (error) { state.run = null; replace(h("p", { text: "이 회차를 불러올 수 없습니다." })); showError(error, () => openRun(id)); return; }
      renderRun();
    } else navigate("#/runs");
  }

  async function boot() {
    window.InterviewApp = Object.freeze({ codepointSlice });
    try { state.me = await api("/me"); }
    catch (error) { if (error.status !== 401) showError(error, boot); }
    updateNav();
    if (state.me) { try { await loadDefinitions(); } catch (error) { showError(error, boot); } }
    await route();
  }

  window.addEventListener("hashchange", route);
  boot();
})();
