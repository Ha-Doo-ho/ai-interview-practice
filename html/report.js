/* Same-run evidence report. Analysis is always an explicit user action;
   citations are rechecked against the owned immutable answer version before display. */
(function () {
  'use strict';
  const $ = id => document.getElementById(id);
  const state = {scope:null, run:null, context:null, capabilities:null, epoch:0, busy:false,
    loaded:false, loadFailed:false, pending:null, storageOK:true, lastScope:null};
  const criterionOrder = ['situation','role','other_information','action','reasoning','result','learning'];
  const criterionLabels = {situation:'상황',role:'역할',other_information:'다른 정보',action:'행동',reasoning:'이유',result:'결과',learning:'배움'};
  const criterionStatuses = {explicit:'명시됨',partial:'부분적으로 언급됨',not_mentioned:'언급 없음',not_asked:'질문하지 않음',unassessable:'판단할 수 없음'};
  let api;

  const runPath = () => `/runs/${encodeURIComponent(state.scope.run_id)}`;
  const storageKey = scope => `astra.report.v1:${scope.user_id}:${scope.run_id}`;
  const element = (tag, text, className) => { const node=document.createElement(tag); if(text!==undefined)node.textContent=String(text); if(className)node.className=className; return node; };
  const appendLine = (parent, label, value, className) => parent.append(element('p', `${label}: ${value}`, className));

  function notice(text='') { $('report-error').textContent=text; $('report-error').hidden=!text; }
  const analysisErrors = {
    interview_question_update_required:'면접 화면에서 저장된 면접을 다시 불러와 8문항 목록으로 갱신한 뒤 평가를 요청해 주세요.',
    gemini_auth_failed:'Gemini API 키 인증에 실패했습니다. 키를 새로 확인해 주세요.',
    gemini_access_denied:'Gemini가 이 계정의 요청을 거절했습니다. API 키 권한과 프로젝트 설정을 확인해 주세요.',
    gemini_model_unavailable:'Gemini 모델을 찾을 수 없거나 사용할 수 없습니다. 모델 ID와 계정 접근 권한을 확인해 주세요.',
    gemini_quota_exceeded:'Gemini 사용 한도 또는 요청 제한에 도달했습니다. Google AI Studio의 할당량과 결제 상태를 확인해 주세요.',
    gemini_request_invalid:'Gemini가 요청을 거절했습니다(HTTP 400). 원인을 확인해야 하므로 반복해서 요청하지 마세요.',
    gemini_service_unavailable:'Gemini 서비스에 일시적인 문제가 발생했습니다. 잠시 후 상태를 확인해 주세요.',
    provider_schema_invalid:'AI 응답의 형식이 올바르지 않아 결과를 표시하지 않았습니다.',
    provider_incomplete:'AI 응답이 끝까지 생성되지 않아 결과를 표시하지 않았습니다.',
    provider_failed:'AI 서비스에 연결하거나 응답을 처리하지 못했습니다. 네트워크와 서버 상태를 확인해 주세요.',
    citation_invalid:'AI 응답의 인용이 저장된 답변과 일치하지 않아 결과를 표시하지 않았습니다.',
    budget_exceeded:'설정된 회차별 AI 사용 한도를 초과해 요청이 거절되었습니다.',
    live_answer_required:'AI 분석에는 내용이 입력된 면접 답변이 한 개 이상 필요합니다.',
    analysis_request_failed:'이전 분석 요청은 실패했습니다. 실패 원인을 확인한 후 새로 요청해 주세요.'
  };
  function scopedRun(run) {
    if (!run || run.user_id !== state.scope?.user_id || run.run_id !== state.scope?.run_id || !Number.isInteger(run.revision) || !Array.isArray(run.records)) throw Error('wrong_run');
    return run;
  }
  function applyRun(run) {
    scopedRun(run);
    if (state.run && run.revision < state.run.revision) { state.loaded=true; render(); return false; }
    if(state.run?.revision!==run.revision)state.synthesisPrompt=null;
    state.run=run; state.loaded=true; window.AstraPractice.updateRun(run); render(); return true;
  }
  function validPending(value) {
    const pending=value?.pending;
    if (!pending || typeof pending!=='object' || !pending.body || typeof pending.body!=='object') return null;
    const body=pending.body;
    const action=pending.action||'interview-analysis';
    return Number.isInteger(body.expected_revision) && typeof body.idempotency_key==='string' &&
      ['interview-analysis','game-analysis','synthesis-analysis','evidence-linkage','interview-finalize'].includes(action) &&
      (!['interview-analysis','game-analysis','synthesis-analysis'].includes(action)||['mock','live'].includes(body.mode)) ? {action,body:{...body}} : null;
  }
  function persist() {
    if (!state.scope) return false;
    try {
      if (state.pending) window.sessionStorage.setItem(storageKey(state.scope), JSON.stringify({pending:state.pending}));
      else window.sessionStorage.removeItem(storageKey(state.scope));
      state.storageOK=true; return true;
    } catch (_) {
      state.storageOK=false;
      notice('임시 저장 공간을 사용할 수 없습니다. 분석 요청을 안전하게 보관할 수 있을 때까지 새 요청을 보낼 수 없습니다.');
      return false;
    }
  }
  function readPending() {
    try { state.pending=validPending(JSON.parse(window.sessionStorage.getItem(storageKey(state.scope))||'{}')); state.storageOK=true; persist(); }
    catch (_) { state.pending=null; state.storageOK=false; notice('임시 저장 상태를 읽을 수 없습니다. 서버에 저장된 보고서만 확인할 수 있습니다.'); }
  }
  function clearUserJournals(userId, fallback) {
    try {
      const prefix=`astra.report.v1:${userId}:`, keys=[];
      if (Number.isInteger(window.sessionStorage.length) && typeof window.sessionStorage.key==='function') {
        for(let index=0;index<window.sessionStorage.length;index++){const key=window.sessionStorage.key(index);if(key?.startsWith(prefix))keys.push(key);}
        for(const key of keys)window.sessionStorage.removeItem(key);
      } else if(fallback) window.sessionStorage.removeItem(storageKey(fallback));
    } catch (_) {}
  }
  function otherWorkLocked() {
    return Boolean(state.context?.busy || state.context?.locked || state.context?.gameLocked || state.context?.interviewLocked);
  }
  function requestBlocked(mode) {
    return !state.scope || !state.loaded || !state.storageOK || state.busy || Boolean(state.pending) || otherWorkLocked() ||
      resultsLocked() || state.run?.status==='completed' || (mode==='live' && !state.capabilities?.live_available);
  }
  const resultsLocked=()=>state.run?.status!=='completed'&&state.run?.flow_version==='five-game-v2'&&window.AstraClient.allGamesComplete?.(state.run)!==true;
  function completionProgress() {
    const run=state.run||{}, records=run.records||[];
    const surveys=window.AstraClient.requiredSurveyIds(run);
    const visited=new Set(records.filter(r=>r.source_type==='survey'&&['submitted','timed_out','skipped'].includes(r.status)).map(r=>r.item_id));
    const baseline=(run.questions||[]).filter(q=>q.question_mode==='baseline'&&q.conditioned_on_prior_evidence===false);
    const answers=baseline.filter(q=>['asked_answered','asked_no_text','skipped'].includes(window.AstraClient.latestAnswer(run,q.question_id)?.data.status)).length;
    const rounds=type=>(run.rule_games?.games?.[type]?.rounds||[]).filter(r=>r.status==='completed').length;
    return {surveys:surveys.filter(id=>visited.has(id)).length,surveyTotal:surveys.length,answers,total:baseline.length,rsp:rounds('rsp'),card:rounds('card'),appointment:(run.appointment_games?.games||[]).filter(g=>g.status==='complete' && g.questions?.length===10).length,aptitude:['rotation','path','potion'].filter(k=>(run.aptitude_games?.attempts||[]).some(a=>a.type===k&&a.mode==='main'&&a.status==='complete')).length};
  }
  function linkageBlocked() { return requestBlocked('mock')||!state.run?.interview_report||Boolean(state.run?.interview_report_stale); }
  function finalizeBlocked() {
    const p=completionProgress();
    return linkageBlocked()||Boolean(state.context?.interviewDrafts)||!state.run?.evidence_linkage||Boolean(state.run?.evidence_linkage_stale)||!p.surveyTotal||p.surveys!==p.surveyTotal||p.total!==3||p.answers!==3||p.rsp!==3||p.card!==3||(state.run?.flow_version==='five-game-v2'&&p.appointment!==3);
  }
  function modeLabel(report) {
    if (!report) return '보고서 없음';
    if (report.runtime_mode==='live' && report.requested_mode==='live' && report.provider_execution==='provider_completed') return 'AI 분석 완료';
    if (report.runtime_mode==='mock' && report.requested_mode==='mock' && report.provider_execution==='not_called') return 'AI 미사용 · 저장 근거';
    if (report.provider_execution==='test_double') return '테스트 대역 · AI 공급자 미사용';
    return '실행 상태 확인 필요';
  }
  function capabilityText() {
    const capability=state.capabilities;
    if (!capability) return state.scope ? 'AI 분석 가능 여부를 확인하는 중입니다.' : '';
    if (capability.live_available) return `AI 분석 사용 가능 · 서버 허용 모델 ${capability.model_id || '설정됨'} · 회차당 최대 ${capability.max_calls_per_run}회`;
    const reasons={live_not_configured:'서버에 AI 분석 설정이 준비되지 않았습니다.',live_disabled:'서버에서 AI 분석 사용이 꺼져 있습니다.',paid_ai_disabled:'서버에서 유료 AI 실행이 허용되지 않았습니다.',model_not_allowed:'서버 허용 모델 설정을 확인해 주세요.'};
    return reasons[capability.reason] || `서버 설정으로 AI 분석을 사용할 수 없습니다${capability.reason ? ` (${capability.reason})` : '.'}`;
  }

  function quoteFor(card, span) {
    if (!span || span.offset_unit!=='unicode_code_point' || span.source_id!==card.answer_id || span.source_version!==card.answer_version) return null;
    const record=(state.run.records||[]).find(item=>item.source_type==='typed_answer' && item.data?.answer_id===card.answer_id && item.data?.answer_version===card.answer_version);
    if (!record || record.data.question_id!==card.question_id || record.data.question_version!==card.question_version || (record.data.behavior_id && record.data.behavior_id!==card.behavior_id)) return null;
    const checked=window.AstraClient.verifyQuote(span,state.run.records);
    return checked.valid ? checked.quote : null;
  }

  // --- [핵심 수정: 길지 않고 깔끔하게 분석 결과만 출력하는 렌더링 함수] ---
  function renderCriteria(parent, card) {
    let hasQuotes = false;
    const group = element('div', undefined, 'report-criteria-clean');

    for (const key of criterionOrder) {
      const value = card.criteria?.[key];
      if (value && (value.status === 'explicit' || value.status === 'partial')) {
        for (const span of Array.isArray(value.evidence_spans) ? value.evidence_spans : []) {
          const quote = quoteFor(card, span);
          if (quote !== null) {
            hasQuotes = true;
            group.append(element('blockquote', `[${criterionLabels[key]}] ${quote}`, 'report-quote'));
            appendLine(group,'인용 출처',`${span.source_id}@${span.source_version} · code-point [${span.start},${span.end})`);
          }
        }
      }
    }
    if (hasQuotes) {
      parent.append(element('h4', '📝 답변 핵심 근거 인용'));
      parent.append(group);
    }
  }

  function renderPracticeFeedback(parent, card) {
    const section=element('section',undefined,'report-practice-feedback');
    section.append(element('p','아래 내용은 저장된 분석 항목과 원문 인용을 바탕으로 제공하는 정해진 안내입니다. 새로운 AI 문장 생성은 사용하지 않습니다.','survey-help'));
    const criteria=card.criteria||{};
    const verified=key=>(Array.isArray(criteria[key]?.evidence_spans)?criteria[key].evidence_spans:[]).some(span=>quoteFor(card,span)!==null);
    const shown=criterionOrder.filter(key=>criteria[key]?.status==='explicit' && verified(key));
    section.append(element('h4','잘 드러난 부분'));
    section.append(element('p',shown.length ? `${shown.map(key=>criterionLabels[key]).join(' · ')} 항목에서 답변 원문과 일치하는 인용이 확인되었습니다. 아래 인용을 살펴보세요.` : '확인된 인용이 없어 잘 드러난 부분을 제시할 수 없습니다.'));
    section.append(element('h4','보완할 부분'));
    const partial=criterionOrder.filter(key=>criteria[key]?.status==='partial' && verified(key));
    const unmentioned=criterionOrder.filter(key=>criteria[key]?.status==='not_mentioned');
    const unknown=criterionOrder.filter(key=>criteria[key]?.status==='unassessable' || !criteria[key] || (['explicit','partial'].includes(criteria[key]?.status) && !verified(key)));
    if(partial.length)section.append(element('p',`${partial.map(k=>criterionLabels[k]).join(' · ')} 항목은 일부만 확인되어, 실제 경험에 해당한다면 설명을 더해 보세요.`));
    if(unmentioned.length)section.append(element('p',`${unmentioned.map(k=>criterionLabels[k]).join(' · ')} 항목은 답변에서 명시적으로 확인되지 않았습니다. 실제 경험에 해당할 때만 덧붙여 보세요.`));
    if(unknown.length)section.append(element('p',`${unknown.map(k=>criterionLabels[k]).join(' · ')} 항목은 현재 자료로 확인할 수 없습니다.`));
    if(!partial.length&&!unmentioned.length&&!unknown.length)section.append(element('p',shown.length?'요청된 각 항목이 답변에서 확인되었습니다. 이것만으로 답변의 완성도를 판정하지는 않습니다.':'현재 확인 가능한 요청 항목이 없습니다.'));
    section.append(element('h4','다음 연습 제안'));
    const suggestions=Array.isArray(card.practice_suggestions)?card.practice_suggestions:[];
    if(suggestions.length){for(const suggestion of suggestions)if(suggestion.text)section.append(element('p',suggestion.text));}
    else if(shown.length)section.append(element('p','다음 연습에서는 행동과 결과를 연결해 짧게 다시 말해 보세요.'));
    else section.append(element('p','실제 경험이 있다면 당시 상황과 본인의 행동을 정리해 보세요.'));
    parent.append(section);
  }

  function renderCards(parent, cards) {
    const section = element('section', undefined, 'report-evidence-section');
    section.append(element('h3', '면접 행동별 분석 결과', 'report-section-title'));

    for (const card of Array.isArray(cards) ? cards : []) {
      const node = element('article', undefined, 'report-card clean-card');
      
      // 1. 헤더: 행동 ID + 행동명 + 상태 배지
      const comparison = card.comparison || {};
      const statusMap = {
        supports_statement: '일치함',
        contextual_difference: '맥락 차이',
        needs_clarification: '보완 필요',
        insufficient_evidence: '비교 근거 부족',
        not_comparable: '비교 불가'
      };
      const statusText = statusMap[comparison.status] || comparison.status || '근거 부족';

      const header = element('div', undefined, 'report-card-header');
      header.append(element('h3', `${card.behavior_id} · ${card.behavior_name}`));
      header.append(element('span', statusText, 'report-badge'));
      node.append(header);

      // 2. 질문 정보
      appendLine(node, '질문', card.question_text);
      node.append(element('p',criterionOrder.map(key=>`${criterionLabels[key]}: ${criterionStatuses[card.criteria?.[key]?.status] || '확인할 수 없음'}`).join(' · ')));

      // 3. 복잡한 유니코드 디버깅 문구 없이 원문 인용만 깔끔하게 출력
      renderCriteria(node, card);
      renderPracticeFeedback(node, card);

      // 4. 분석 이유 및 비교 결과 (있는 경우만 한 줄로 깔끔하게)
      if (comparison.reason) {
        const reasons={no_eligible_opportunity_or_relevant_evidence:'이 행동을 게임 기록과 비교할 수 있는 관찰 근거가 없습니다.',incompatible_behavior_mapping_unit_or_version:'현재 기록은 이 행동과 직접 비교할 수 없습니다.',recorded_observation_and_context_difference:'기록된 행동과 당시 조건에 차이가 있습니다.',relevant_evidence_requires_context:'비교에 필요한 추가 맥락이 있습니다.',compatible_observation_supports_statement_direction:'비교 가능한 관찰이 답변 내용과 같은 방향입니다.',evidence_direction_not_resolved:'현재 근거만으로는 비교 방향을 확정할 수 없습니다.'};
        appendLine(node, '비교 안내', reasons[comparison.reason] || '현재 기록의 비교 조건을 확인해 주세요.');
      }

      // 5. 추천 연습 가이드 (핵심 피드백만 출력)
      if (Array.isArray(card.practice_suggestions) && card.practice_suggestions.length) {
        const refs = new Map();
        for(const suggestion of card.practice_suggestions){const basis=Array.isArray(suggestion.basis_refs)?suggestion.basis_refs:[];const key=JSON.stringify([suggestion.template_version||null,basis]);if(!refs.has(key))refs.set(key,{version:suggestion.template_version,basis});}
        for(const ref of refs.values()){if(ref.version)appendLine(node,'제안 버전',ref.version);if(ref.basis.length)appendLine(node,'근거 참조',ref.basis.join(', '));}
      }

      section.append(node);
    }
    parent.append(section);
  }

  function missingLabel(data,status){return data?.missing_reason || status || '기록 없음';}
  function renderSurveyValue(node,survey) {
    const data=survey.data||{}, type=data.response_type||data.definition_snapshot?.type;
    if(data.prompt_snapshot)appendLine(node,'제시 문항',data.prompt_snapshot);
    if (data.nonresponse_label_snapshot) {appendLine(node,'응답 상태',data.nonresponse_label_snapshot);return;}
    if(type==='ordinal_6') appendLine(node,'선택',data.selected_label_snapshot?`${data.selected_label_snapshot} · 위치 ${data.selected_position}`:missingLabel(data,survey.status));
    else if(type==='paired_perspective'){
      appendLine(node,'나의 관점',data.self?.selected_label_snapshot?`${data.self.selected_label_snapshot} · 위치 ${data.self.selected_position}`:missingLabel(data.self,data.self?.status));
      appendLine(node,'상상한 타인 관점',data.imagined_others?.selected_label_snapshot?`${data.imagined_others.selected_label_snapshot} · 위치 ${data.imagined_others.selected_position}`:missingLabel(data.imagined_others,data.imagined_others?.status));
    } else if(type==='bipolar_slider'){
      const left=data.left_anchor_label||data.left_label_snapshot||'왼쪽 방향', right=data.right_anchor_label||data.right_label_snapshot||'오른쪽 방향';
      appendLine(node,'방향과 원본 위치',data.final_value===null||data.final_value===undefined?`${left} ↔ ${right} · ${missingLabel(data,survey.status)}`:`${left} ← ${data.final_value} → ${right}`);
      if(typeof data.min==='number'&&typeof data.max==='number')appendLine(node,'원본 범위',`${data.min} ~ ${data.max}`);
      appendLine(node,'응답 확인',`상호작용 ${Boolean(data.interaction_occurred)} · 명시 확인 ${Boolean(data.explicit_confirmation)}`);
    } else if(type==='top_k_rank'){
      const candidates=new Map((data.candidate_snapshots||[]).map(item=>[item.option_id,item.label]));
      const ranked=data.ranked_options||data.ranked_selection||[];
      if(candidates.size)appendLine(node,'제시 후보',[...candidates.values()].join(', '));
      if(!ranked.length)appendLine(node,'순위',missingLabel(data,survey.status));
      for(const item of ranked)appendLine(node,`${item.rank}위`,item.label_snapshot||item.label||candidates.get(item.option_id)||item.option_id);
      if(Number.isInteger(data.requested_k))appendLine(node,'순위 의미',`${data.requested_k}개만 순위로 저장됨 · 미선택 항목은 싫어함이 아님`,'survey-help');
    } else appendLine(node,'원본 상태',missingLabel(data,survey.status));
  }
  function renderSurveys(parent,surveys) {
    const section=element('section',undefined,'report-evidence-section');section.append(element('h3','같은 회차의 성향 설문 원본','report-section-title'));
    const ordered=[...(Array.isArray(surveys)?surveys:[])].sort((a,b)=>(a.presentation_order??0)-(b.presentation_order??0));
    for(const survey of ordered){const node=element('article',undefined,'report-source-card');node.append(element('h4',`${survey.item_id}@${survey.item_version} · ${survey.status}`));appendLine(node,'원본 버전',`${survey.record_id}@${survey.record_version} · source ${survey.source_version}`,'survey-help');renderSurveyValue(node,survey);if(survey.data?.direction)appendLine(node,'방향',survey.data.direction);if(survey.comparison_exclusion||['S-B02','R-UNMAPPED'].includes(survey.item_id))node.append(element('p',`${survey.item_id} · 행동 간 비교 제외`,'survey-help'));section.append(node);}
    parent.append(section);
  }
  function renderGames(parent,games) {
    const section=element('section',undefined,'report-evidence-section');section.append(element('h3','규칙 게임 저장 사실','report-section-title'));
    for(const game of Array.isArray(games)?games:[]){const node=element('article',undefined,'report-source-card');node.append(element('h4',`${game.game_id}@${game.game_version}`));appendLine(node,'상태 버전',game.state_version);appendLine(node,'행동 매핑',game.mapping_status||'unmapped');appendLine(node,'행동 비교',game.comparison_status||'not_comparable');for(const round of Array.isArray(game.rounds)?game.rounds:[]){const item=element('p',`라운드 ${round.round_index} · ${round.status} · ${round.score}점 · 정답 ${round.correct_count} · 오답 ${round.incorrect_count}`);node.append(item);if((round.quality_flags||[]).length)appendLine(node,'품질 표시',round.quality_flags.join(', '));if((round.event_refs||[]).length)appendLine(node,'이벤트 참조',round.event_refs.join(', '),'survey-help');}for(const limit of Array.isArray(game.limitations)?game.limitations:[])node.append(element('p',limit,'survey-help'));section.append(node);}
    parent.append(section);
  }
  function renderLinkage(parent,linkage) {
    if(!linkage)return;
    const section=element('section',undefined,'report-evidence-section');section.append(element('h3','설문·면접 근거 연결','report-section-title'));
    appendLine(section,'연결 버전',`${linkage.linkage_id}@${linkage.version} · 기본 보고서 ${linkage.source_report_id}`);
    for(const link of linkage.links||[]){
      const node=element('article',undefined,'report-card');node.append(element('h4',`${link.behavior_id} · ${link.behavior_name}`));
      appendLine(node,'비교 상태',{needs_clarification:'추가 맥락 확인 필요',not_comparable:'직접 비교할 수 없음',insufficient_evidence:'비교 근거 부족'}[link.comparison_status]||link.comparison_status);if(link.summary)node.append(element('p',link.summary));
      for(const ref of link.survey_refs||[]){appendLine(node,'설문 출처',`${ref.record_id}@${ref.record_version} · ${ref.item_id}@${ref.item_version}`,'survey-help');appendLine(node,'원본 응답',ref.response_text||'응답 없음');if(ref.perspective)appendLine(node,'관점',ref.perspective==='imagined_others'?'내가 상상한 타인의 관점':ref.perspective);if(ref.use)appendLine(node,'연결 용도',ref.use,'survey-help');}
      for(const ref of link.interview_refs||[]){
        appendLine(node,'중립 면접 출처',`${ref.answer_id}@${ref.answer_version} · ${ref.question_id}@${ref.question_version} · ${criterionLabels[ref.criterion]||ref.criterion} · ${criterionStatuses[ref.status]||ref.status}`,'survey-help');
        for(const span of ref.evidence_spans||[]){const quote=quoteFor({...ref,behavior_id:link.behavior_id},span);if(quote!==null)node.append(element('blockquote',quote,'report-quote'));}
      }
      for(const exclusion of link.exclusions||[]){const refs=[];for(const [id,version] of [['record_id','record_version'],['item_id','item_version'],['answer_id','answer_version'],['question_id','question_version']])if(exclusion[id])refs.push(exclusion[id]+(exclusion[version]!=null?'@'+exclusion[version]:''));appendLine(node,'비교 제외 사유',[...refs,exclusion.mapping_id||'매핑 없음',exclusion.reason||'사유 확인 필요'].join(' · '),'survey-help');}
      for(const limit of link.limitations||[])node.append(element('p',limit,'survey-help'));section.append(node);
    }
    for(const limit of linkage.limitations||[])section.append(element('p',limit,'survey-help'));parent.append(section);
    const observations=element('section',undefined,'report-evidence-section');observations.append(element('h3','라운드별 규칙 관찰 · 행동 비교와 별도','report-section-title'));
    for(const observation of linkage.observations||[]){
      const node=element('article',undefined,'report-source-card');node.append(element('h4',`${observation.game_id}@${observation.game_version} · 라운드 ${observation.round_index}`));
      appendLine(node,'라운드 출처',observation.round_id,'survey-help');
      for(const [key,label] of [['before','규칙 공개 전'],['after','규칙 공개 후']]){const fact=observation[key];if(fact)appendLine(node,label,`저장된 응답 ${fact.accepted_count}회 · 규칙 충족 ${fact.correct_count}회`);}
      appendLine(node,'규칙 공개 기록',observation.disclosure_status==='recorded'?'공개 기록 확인됨':observation.disclosure_status==='rule_reveal_not_recorded'?'공개 기록 없음':observation.disclosure_status);
      if(observation.missing_reason)appendLine(node,'관찰 제한',`${observation.missing_reason==='no_accepted_response_after_disclosure'?'공개 후 응답 없음 · 이후 선택을 관찰할 수 없습니다.':observation.missing_reason==='rule_reveal_not_recorded'?'규칙 공개 기록 없음 · 공개 전후 선택을 비교할 수 없습니다.':observation.missing_reason} (${observation.missing_reason})`);
      if(observation.overlap)appendLine(node,'공개 후 응답의 규칙 충족 분류',`새 규칙만 ${observation.overlap.new_only} · 이전 규칙만 ${observation.overlap.old_only} · 두 규칙 모두 ${observation.overlap.both} · 모두 미충족 ${observation.overlap.neither}`);
      if((observation.event_refs||[]).length)appendLine(node,'이벤트 출처',observation.event_refs.join(', '),'survey-help');
      for(const limit of observation.limitations||[])node.append(element('p',limit,'survey-help'));observations.append(node);
    }
    parent.append(observations);
  }
  function renderFinalFollowups(parent,report) {
    if(!Array.isArray(report.followup_answers))return;
    const section=element('section',undefined,'report-evidence-section');section.append(element('h3','조건부 후속 질문과 원본 답변','report-section-title'));
    section.append(element('p','사전 근거를 공개한 후의 자기보고입니다. 중립 기본 면접 추출과 별도로 보관합니다.','survey-help'));
    for(const answer of report.followup_answers){
      const node=element('article',undefined,'report-source-card');node.append(element('h4',answer.question_text));
      appendLine(node,'질문 출처',`${answer.question_id}@${answer.question_version} · ${answer.question_mode} · conditioned=${answer.conditioned_on_prior_evidence}`,'survey-help');
      if(answer.answer_id)appendLine(node,'답변 출처',`${answer.answer_id}@${answer.answer_version}`,'survey-help');
      appendLine(node,'응답 상태',{not_answered:'미응답 · 선택 후속 질문',asked_no_text:'답변 없음',skipped:'건너뜀',asked_answered:'답변 저장'}[answer.status]||answer.status);
      if(answer.status==='asked_answered')node.append(element('pre',answer.text,'interview-saved-text'));
      if(answer.disclosed_prior_information)appendLine(node,'공개된 사전 정보',typeof answer.disclosed_prior_information==='string'?answer.disclosed_prior_information:JSON.stringify(answer.disclosed_prior_information));
      if((answer.generated_from_evidence_refs||[]).length)appendLine(node,'생성 근거 출처',JSON.stringify(answer.generated_from_evidence_refs),'survey-help');section.append(node);
    }
    parent.append(section);
  }
  function renderFiveGames(parent, report) {
    const section=element('section',undefined,'report-evidence-section');section.append(element('h3','다섯 게임의 저장 결과','report-section-title'));
    const names={rsp:'가위바위보',card:'숫자 카드',day:'약속 요일',place:'약속 장소',bus:'버스 번호'};
    const days=['월요일','화요일','수요일','목요일','금요일','토요일','일요일'];
    const label=(type,value)=>value==null?'기록 없음':type==='day'?(days[value]||String(value)):type==='place'?`장소 ${Number(value)+1}`:type==='bus'?`${value}번`:String(value);
    for(const game of report.games||[]){
      const card=element('article',undefined,'report-source-card');card.append(element('h4',names[game.type]||game.type));
      const totals=game.totals||{}, conditions=game.conditions||{};
      appendLine(card,'상태',['complete','completed'].includes(game.status)?'완료':game.status==='pending'?'미완료 · 대기':'미완료 · 진행 중');
      if(['day','place','bus'].includes(game.type)){
        appendLine(card,'조건',`난이도 ${conditions.difficulty==='easy'?'쉬움':conditions.difficulty==='hard'?'어려움':'미선택'} · ${conditions.question_limit||10}문항`);
        appendLine(card,'결과',`정답 ${totals.correct??0} · 오답 ${totals.wrong??0} · 시간 초과 ${totals.timeout??0} · ${totals.score??0}점`);
        for(const item of game.evidence||[]){
          const detail=element('details');detail.append(element('summary',`${item.number}번 문항 · ${item.outcome||'미완료'}`));
          for(const [i,values] of (item.sets||[]).entries())appendLine(detail,['A','B','C'][i],(values||[]).map(v=>label(game.type,v)).join(' · '));
          if(item.choices)appendLine(detail,'보기',item.choices.map(v=>label(game.type,v)).join(' · '));
          appendLine(detail,'답변',`선택 ${label(game.type,item.selection)} · 정답 ${label(game.type,item.answer)}`);
          if(item.source_ref)appendLine(detail,'문항 출처',`${item.source_ref.question_id}@${item.source_ref.question_version}`);
          card.append(detail);
        }
        for(const c of conditions.question_conditions||[])if(c?.answer_ms!=null){appendLine(card,'제한 시간',`제시 ${(c.reveal_ms||[]).join(' / ')}ms · 답변 ${c.answer_ms}ms`);break;}
      }else{
        appendLine(card,'라운드',`${totals.completed_rounds??0} / ${conditions.round_limit||3} 완료`);
        for(const item of game.evidence||[])appendLine(card,`${item.round_index}라운드`,`${item.score}점 · 정답 ${item.correct_count} · 오답 ${item.incorrect_count}`);
      }
      section.append(card);
    }
    parent.append(section);
  }
  function renderGameAdvice(parent,report){
    const result=state.run?.game_analysis, advice=report.game_analysis||result?.report, provenance=report.game_analysis_provenance||result;
    if(state.run?.game_analysis_stale||!advice||advice.source_digest!==report.five_games?.source_digest||advice.baseline_report_id!==(report.source_report_id||report.report_id))return;
    const section=element('section',undefined,'report-evidence-section');section.append(element('h3','게임별 다음 연습 제안','report-section-title'));
    appendLine(section,'실행 구분',provenance?.provider_execution==='provider_completed'?'AI 분석':provenance?.provider_execution==='test_double'?'테스트 대역 · AI 공급자 미사용':'AI 미사용 · 고정 안내');
    const names={rsp:'가위바위보',card:'숫자 카드',day:'약속 요일',place:'약속 장소',bus:'버스 번호'};
    for(const game of advice.games||[]){const card=element('article',undefined,'report-source-card');card.append(element('h4',names[game.type]||game.type));for(const item of game.advice||[])card.append(element('p',item.text));section.append(card);}parent.append(section);
  }
  function renderSupplemental(parent,report) {
    const answers=report.status==='finalized'?(report.supplemental_answers||[]):
      (state.run?.questions||[]).filter(q=>q.question_mode==='supplemental').map(q=>{
        const answer=window.AstraClient.latestAnswer(state.run,q.question_id)?.data;
        return {...q,text:answer?.text||'',status:answer?.status||'not_answered'};
      });
    if(!answers.length)return;
    const section=element('section',undefined,'report-evidence-section');
    section.append(element('h3','업무 경험 면접 · 저장된 자기보고','report-section-title'),
      element('p','선택 면접 답변 원문입니다. 능력 점수나 기본 면접 AI 분석 결과가 아닙니다.'));
    for(const answer of answers){
      const card=element('article',undefined,'report-source-card');
      card.append(element('h4',answer.question_text));
      appendLine(card,'상태',({asked_answered:'답변 저장',asked_no_text:'답변 없음',skipped:'건너뜀',not_answered:'미응답'})[answer.status]||'미응답');
      if(answer.status==='asked_answered')card.append(element('pre',answer.text,'interview-saved-text'));
      section.append(card);
    }
    parent.append(section);
  }
  function renderSynthesis(parent,report) {
    const analysis=state.run?.status==='completed'?report.synthesis_analysis:state.run?.synthesis_analysis;
    if(!analysis)return;
    const section=element('section',undefined,'report-evidence-section');
    section.append(element('h3','세 활동 종합 피드백','report-section-title'));
    if(state.run?.status!=='completed'&&state.run?.synthesis_analysis_stale){
      section.append(element('p','이 종합 평가는 이전 입력 기준입니다. 최신 저장 자료로 다시 요청해 주세요.'));parent.append(section);return;
    }
    section.append(element('p',analysis.provider_execution==='provider_completed'?'AI가 작성한 연습 피드백 · 인용 근거와 함께 확인하세요.':analysis.provider_execution==='test_double'?'테스트 대역 · 실제 AI 미사용':'AI 미사용 · 종합 근거 저장'));
    const result=analysis.report||{},sources=new Map((result.prompt?.evidence||[]).map(e=>[e.id,e]));
    const labels={strengths:'잘한 점',gaps:'보완점과 비교 제한',practice_plan:'개선 계획',clarifying_questions:'추가 확인 질문'};
    for(const [key,label] of Object.entries(labels)){
      section.append(element('h4',label));
      const items=result.feedback?.[key]||[];
      if(!items.length)section.append(element('p','제시된 항목이 없습니다. 낮은 능력을 뜻하지 않습니다.'));
      for(const item of items){
        if(!item.evidence_ids?.length||item.evidence_ids.some(id=>!sources.has(id)))continue;
        section.append(element('p',item.text));
        for(const id of item.evidence_ids){const details=element('details');details.append(element('summary','인용 근거 확인: '+id),element('pre',JSON.stringify(sources.get(id),null,2),'interview-saved-text'));section.append(details);}
      }
    }
    for(const limit of result.limitations||[])section.append(element('p',limit));
    parent.append(section);
  }
  function renderReport() {
    const root=$('report-content');root.replaceChildren();if(resultsLocked()){root.append(element('p','전체 8종 본게임을 완료한 뒤 결과를 확인할 수 있습니다. 연습·빠른 연습·중단 기록은 완료로 인정하지 않습니다. 게임 화면에서 남은 본게임을 진행해 주세요.'));return;}const report=state.run?.status==='completed'&&state.run?.report?.status==='finalized'?state.run.report:state.run?.interview_report;if(!report)return;
    const header=element('section',undefined,'report-summary');header.append(element('h3',report.status==='finalized'?'최종 보고서 · 확정됨':'현재 회차 근거 보고서','report-section-title'));appendLine(header,'보고서 ID',`${report.report_id}@${report.report_version}`);appendLine(header,'실행 구분',modeLabel(report));if(report.created_at)appendLine(header,'생성 시각',report.created_at);if(report.finalized_at)appendLine(header,'확정 시각',report.finalized_at);root.append(header);
    renderCards(root,report.cards);renderSurveys(root,report.surveys);if(report.five_games){renderFiveGames(root,report.five_games);renderGameAdvice(root,report);}else renderGames(root,report.rule_games);
    renderLinkage(root,report.evidence_linkage||state.run?.evidence_linkage);renderFinalFollowups(root,report);
    renderSupplemental(root,report);
    renderSynthesis(root,report);
    const limits=element('section',undefined,'report-limitations');limits.append(element('h3','해석 제한','report-section-title'));for(const item of Array.isArray(report.limitations)?report.limitations:[])limits.append(element('p',item));limits.append(element('p','게임 점수는 해당 규칙의 저장 결과이며 합격, 성향, B01/B02/B03의 점수가 아닙니다.'));root.append(limits);
  }
  function render() {
    const report=state.run?.interview_report, stale=Boolean(report&&state.run?.interview_report_stale);
    $('report-status').textContent=!state.scope?'설문 화면에서 로그인한 계정의 연습 회차를 선택해 주세요.':state.pending?'분석 요청 결과 확인 대기 · 같은 요청만 다시 시도할 수 있습니다.':!state.loaded?(state.loadFailed?'보고서를 불러오지 못했습니다.':'현재 회차 보고서를 불러오는 중입니다.'):`현재 회차: ${state.scope.run_id} · ${modeLabel(report)}${stale?' · 이전 입력 기준':''}`;
    $('report-capability').textContent=capabilityText();
    $('report-refresh').disabled=!state.scope||state.busy||otherWorkLocked();
    $('report-mock').disabled=requestBlocked('mock'); $('report-analyze').disabled=requestBlocked('live');
    const gameAvailable=state.run?.flow_version==='five-game-v2' && Boolean(state.run?.interview_report?.five_games) && !state.run?.interview_report_stale;
    if($('report-game-mock'))$('report-game-mock').disabled=!gameAvailable||requestBlocked('mock');
    if($('report-game-ai'))$('report-game-ai').disabled=!gameAvailable||requestBlocked('live');
    if($('report-synthesis-mock'))$('report-synthesis-mock').disabled=!gameAvailable||requestBlocked('mock')||Boolean(state.context?.interviewDrafts);
    if($('report-synthesis-ai'))$('report-synthesis-ai').disabled=!gameAvailable||requestBlocked('live')||Boolean(state.context?.interviewDrafts);
    if($('report-synthesis-prompt'))$('report-synthesis-prompt').disabled=resultsLocked()||!state.scope||!state.loaded||state.busy||Boolean(state.pending)||otherWorkLocked();
    if($('report-synthesis-preview')){
      const panel=$('report-synthesis-preview');panel.replaceChildren();
      if(state.scope&&!resultsLocked()&&state.synthesisPrompt){const area=element('textarea');area.readOnly=true;area.className='textarea-box';area.setAttribute('aria-label','AI에 전달할 종합 평가 프롬프트');area.value=state.synthesisPrompt.prompt_text;panel.append(element('p','현재 저장 자료로 만든 프롬프트입니다. 필요한 경우 선택하여 복사할 수 있습니다.'),area);}
    }
    if($('report-linkage'))$('report-linkage').disabled=linkageBlocked();
    if($('report-finalize'))$('report-finalize').disabled=finalizeBlocked();
    if($('report-followups')){$('report-followups').hidden=!state.run?.evidence_linkage;$('report-followups').disabled=state.busy||Boolean(state.pending)||state.run?.status==='completed';}
    if($('report-completion')){const p=completionProgress();$('report-completion').textContent=state.scope?`최종 확정 준비: 설문 방문 ${p.surveys}/${p.surveyTotal} · 가위바위보 ${p.rsp}/3 · 카드 ${p.card}/3${state.run?.flow_version==='five-game-v2'?` · 약속 게임 ${p.appointment}/3 · 추가 본게임 ${p.aptitude}/3`:''} · 기본 면접 ${p.answers}/3 · ${state.run?.evidence_linkage_stale?'근거 연결 갱신 필요':state.run?.evidence_linkage?'근거 연결 저장됨':'근거 연결 필요'} · 후속 답변은 선택입니다.${state.context?.interviewDrafts?` 미저장 면접 입력 ${state.context.interviewDrafts}개: 면접에서 입력을 저장하거나 정리한 뒤 확정해 주세요.`:''}`:'';}
    $('report-retry').hidden=!state.pending; $('report-retry').disabled=!state.pending||state.busy||!state.storageOK||otherWorkLocked();
    if(state.loaded)renderReport();else $('report-content').replaceChildren();
    if(stale&&!state.pending)notice('이 보고서는 이전 입력 기준입니다. 현재 답변으로 바꾸려면 저장 근거 보고서 또는 새 분석을 명시적으로 요청해 주세요.');
    else if(state.run?.evidence_linkage_stale&&!state.pending)notice('근거 연결이 이전 입력 기준입니다. 근거 연결·후속 질문 만들기를 다시 요청한 후 최종 보고서를 확정해 주세요.');
    if(state.scope)window.AstraPractice.setReportLock({...state.scope,locked:state.busy||Boolean(state.pending)});
  }

  async function work(action) {
    if(!state.scope||state.busy||otherWorkLocked())return;
    const epoch=state.epoch;state.busy=true;if(state.storageOK)notice();render();
    try{await action(()=>epoch===state.epoch);}
    catch(error){
      if(epoch!==state.epoch)return;
      if(error.status===401||error.status===404||error.status===410||error.message==='wrong_run'){
        const previous=state.scope?{...state.scope}:null;if(previous){try{window.sessionStorage.removeItem(storageKey(previous));}catch(_){}window.AstraPractice.invalidateRun(previous);}state.pending=null;state.loaded=false;state.run=null;if(error.status===401||error.message==='wrong_run')window.AstraAuth?.recheck();notice('로그인 또는 회차 상태를 확인할 수 없습니다. 설문 화면에서 저장된 회차를 다시 확인해 주세요.');
      }else{if(!state.loaded)state.loadFailed=true;notice(state.pending?'서버 처리 결과를 확인하지 못했습니다. 같은 요청 다시 시도를 눌러 저장 결과를 확인해 주세요.':'보고서를 불러오지 못했습니다. 서버 연결을 확인하고 다시 불러와 주세요.');}
    }finally{if(epoch===state.epoch){state.busy=false;render();}}
  }
  async function loadCurrent(allow) {
    const capabilities=await api('/interview-analysis-capabilities');if(!allow())return;
    const run=await api(runPath());if(!allow())return;
    state.capabilities=capabilities;state.loadFailed=false;applyRun(run);
  }
  function request(mode) {
    if(requestBlocked(mode))return;
    state.pending={action:'interview-analysis',body:{expected_revision:state.run.revision,idempotency_key:crypto.randomUUID(),mode}};
    if(!persist()){state.pending=null;render();return;}
    return work(allow=>sendPending(allow,false));
  }
  function requestGame(mode) {
    if(requestBlocked(mode)||state.run?.flow_version!=='five-game-v2'||!state.run?.interview_report?.five_games||state.run?.interview_report_stale)return;
    state.pending={action:'game-analysis',body:{expected_revision:state.run.revision,idempotency_key:crypto.randomUUID(),mode}};
    if(!persist()){state.pending=null;render();return;}
    return work(allow=>sendPending(allow,false));
  }
  function requestSynthesis(mode) {
    if(requestBlocked(mode)||state.context?.interviewDrafts||!state.run?.interview_report?.five_games||state.run?.interview_report_stale)return;
    state.pending={action:'synthesis-analysis',body:{expected_revision:state.run.revision,idempotency_key:crypto.randomUUID(),mode}};
    if(!persist()){state.pending=null;render();return;}
    return work(allow=>sendPending(allow,false));
  }
  function requestCompletion(action) {
    if(action==='evidence-linkage'?linkageBlocked():finalizeBlocked())return;
    state.pending={action,body:{expected_revision:state.run.revision,idempotency_key:crypto.randomUUID()}};
    if(!persist()){state.pending=null;render();return;}
    return work(allow=>sendPending(allow,false));
  }
  async function sendPending(allow,retrying) {
    const pending=structuredClone(state.pending);
    try{
      const run=await api(`${runPath()}/${pending.action||'interview-analysis'}`,{method:'POST',body:pending.body});if(!allow())return;
      scopedRun(run);state.pending=null;persist();applyRun(run);if(retrying){const current=await api(runPath());if(allow())applyRun(current);}
    }catch(error){
      if(!allow())return;
      if(error.status===409&&error.code==='analysis_request_running'){notice('서버에서 같은 분석 요청을 처리 중입니다. 잠시 뒤 같은 요청 다시 시도로 저장 결과를 확인해 주세요.');render();return;}
      const definitive=error.status>=400&&error.status<500&&!([401,404,410].includes(error.status));
      if(definitive){state.pending=null;persist();try{const current=await api(runPath());if(allow())applyRun(current);}catch(_){}const serviceCode=/^gemini_http_(5\d\d)$/.exec(error.code||'');notice(serviceCode?`Gemini 서버가 HTTP ${serviceCode[1]} 오류를 반환했습니다. 반복 요청을 멈추고 상태를 확인해 주세요.`:analysisErrors[error.code] || '서버가 이 요청을 거절했습니다. 현재 회차와 AI 설정을 확인해 주세요.');render();return;}
      throw error;
    }
  }
  function contextChanged(context) {
    const scope=context.user&&context.run?{user_id:context.user.user_id,run_id:context.run.run_id}:null;
    const same=scope&&state.scope&&scope.user_id===state.scope.user_id&&scope.run_id===state.scope.run_id;
    const changed=same&&(context.run.revision>(state.run?.revision??-1)||context.busy!==state.context?.busy||context.locked!==state.context?.locked||context.gameLocked!==state.context?.gameLocked||context.interviewLocked!==state.context?.interviewLocked||context.interviewDrafts!==state.context?.interviewDrafts||context.run.status!==state.run?.status);
    if(!same||context.run?.revision!==state.run?.revision)state.synthesisPrompt=null;
    state.context=context;
    if(same){if(context.run.revision>=(state.run?.revision??-1))state.run=context.run;if(changed)render();if(!state.loaded&&!state.busy&&!otherWorkLocked())work(loadCurrent);return;}
    const previous=state.scope;state.epoch++;state.scope=scope;state.run=context.run;state.capabilities=null;state.loaded=false;state.loadFailed=false;state.busy=false;state.pending=null;state.storageOK=true;if(previous)state.lastScope=previous;
    if(context.authStatus==='guest'&&state.lastScope){clearUserJournals(state.lastScope.user_id,state.lastScope);state.lastScope=null;}
    notice();render();if(!scope)return;readPending();render();work(loadCurrent);
  }

  window.AstraReport={};
  document.addEventListener('DOMContentLoaded',()=>{
    const bridge=window.AstraPractice;
    $('report-synthesis-prompt')?.addEventListener('click',()=>work(async allow=>{
      if(resultsLocked())return;
      const prompt=await api(runPath()+'/synthesis-prompt');if(allow())state.synthesisPrompt=prompt;
    }));
    $('report-synthesis-mock')?.addEventListener('click',()=>requestSynthesis('mock'));
    $('report-synthesis-ai')?.addEventListener('click',()=>requestSynthesis('live'));
    if(!['subscribe','updateRun','invalidateRun','setReportLock'].every(name=>typeof bridge?.[name]==='function')||!['createApi','verifyQuote'].every(name=>typeof window.AstraClient?.[name]==='function')){
      $('report-status').textContent='근거 보고서 화면을 불러오지 못했습니다.';$('report-refresh').disabled=true;$('report-mock').disabled=true;$('report-analyze').disabled=true;notice('화면 파일 일부가 이전 버전이거나 불러오지 못했습니다. Ctrl + F5로 화면을 새로고침해 주세요. 저장된 기록은 유지됩니다.');return;
    }
    api=window.AstraClient.createApi();$('report-refresh').addEventListener('click',()=>work(loadCurrent));$('report-mock').addEventListener('click',()=>request('mock'));$('report-analyze').addEventListener('click',()=>request('live'));$('report-game-mock')?.addEventListener('click',()=>requestGame('mock'));$('report-game-ai')?.addEventListener('click',()=>requestGame('live'));$('report-retry').addEventListener('click',()=>work(allow=>sendPending(allow,true)));
    $('report-linkage')?.addEventListener('click',()=>requestCompletion('evidence-linkage'));$('report-finalize')?.addEventListener('click',()=>requestCompletion('interview-finalize'));$('report-followups')?.addEventListener('click',()=>{if(!state.busy&&!state.pending&&state.run?.status!=='completed')navigateTab('interview');});window.AstraPractice.subscribe(contextChanged);
  });
})();
