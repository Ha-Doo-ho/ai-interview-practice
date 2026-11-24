/* Shared by browser and Node tests. No storage or DOM side effects. */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.AstraClient = factory();
})(typeof globalThis === 'object' ? globalThis : this, function () {
  'use strict';
  const failure = (code, extra = {}) => Object.assign(new Error(code), {code, ...extra});
  function createApi(transport = globalThis.fetch.bind(globalThis)) {
    return async (path, {method = 'GET', body} = {}) => {
      const headers = {Accept: 'application/json'};
      if (method !== 'GET') headers['X-Requested-With'] = 'interview-app';
      if (body !== undefined) headers['Content-Type'] = 'application/json';
      let response;
      try { response = await transport('/api' + path, {method, headers, credentials: 'same-origin', body: body === undefined ? undefined : JSON.stringify(body)}); }
      catch (_) { throw failure('network_error'); }
      let data = null;
      if (response.status !== 204) {
        try { data = await response.json(); }
        catch (_) { throw failure('unreadable_response', {status: response.status >= 400 ? response.status : undefined}); }
      }
      if (!response.ok) throw failure(data?.error || 'request_failed', {status: response.status});
      return data;
    };
  }
  function createMutation(api, newKey = () => crypto.randomUUID()) {
    let pending = null, active = false;
    async function execute() {
      if (active) throw failure('request_in_progress');
      if (!pending) throw failure('no_pending_request');
      active = true;
      try { const result = await api(pending.path, {method: 'POST', body: JSON.parse(pending.json)}); pending = null; return result; }
      catch (error) { if (error.status >= 400 && error.status < 500) pending = null; throw error; }
      finally { active = false; }
    }
    return {
      get pending() { return pending ? {path: pending.path, body: JSON.parse(pending.json)} : null; },
      async send(run, action, payload = {}) {
        if (pending) throw failure('pending_request');
        pending = {path: `/runs/${encodeURIComponent(run.run_id)}/${action}`, json: JSON.stringify({...payload, expected_revision: run.revision, idempotency_key: newKey()})};
        return execute();
      },
      retry: execute,
    };
  }
  function buildSurveyResponse(item, status, values) {
    const required = status === 'submitted';
    const position = value => {
      if (value === undefined || value === null || value === '') {
        if (required) throw failure('selection_required');
        return null;
      }
      return {selected_position: Number(value)};
    };
    if (item.type === 'ordinal_6') return position(values.selected_position);
    if (item.type === 'paired_perspective') {
      const branch = value => {const selected = position(value);return {...selected, status: selected ? 'submitted' : status};};
      return {self: branch(values.self), imagined_others: branch(values.imagined_others)};
    }
    if (item.type === 'bipolar_slider') return {
      final_value: required || values.touched ? Number(values.value) : null,
      interaction_occurred: Boolean(values.touched), explicit_confirmation: required, change_count: values.changes || 0,
    };
    if (item.type === 'top_k_rank') {
      const selected = values.selected_ids || [];
      if (required && selected.length !== item.requested_k) throw failure('rank_count');
      return {selected_ids: [...selected], selection_events: structuredClone(values.selection_events || [])};
    }
    throw failure('unknown_survey');
  }
  function latestAnswer(run, questionId) {
    const records = (run.records || []).filter(r => r.source_type === 'typed_answer' && r.data.question_id === questionId);
    const replaced = new Set(records.map(r => r.data.previous_answer_version_ref?.answer_id));
    return records.find(r => !replaced.has(r.data.answer_id));
  }
  function answerPayload(run, questionId, text, status) {
    if (status === 'asked_answered' && !text.trim()) throw failure('answer_required');
    const previous = latestAnswer(run, questionId)?.data;
    return {question_id: questionId, text: status === 'asked_answered' ? text : '', status,
      ...(previous ? {replaces_answer_id: previous.answer_id, expected_answer_version: previous.answer_version} : {})};
  }
  function requiredSurveyIds(run, definitions) {
    if (run?.survey_set_version && !run.survey_definition_snapshot) return [];
    const items = run?.survey_definition_snapshot || definitions?.surveys;
    if (!items) return ['O-B01','O-B02','O-B03','P-B01','S-B02','R-UNMAPPED'];
    if (!Array.isArray(items) || !items.length || items.some(i=>!i||typeof i.item_id!=='string'||!i.item_id)) return [];
    const ids = items.map(i=>i.item_id);
    if (run?.survey_set_version && (run.survey_set_version!=='work-behavior-v2' ||
        ids.join(',')!=='O-B01,O-B02,O-B03,O-PLAN-COMPARE,O-RESULT-LEARNING' ||
        items.some(i=>i.type!=='ordinal_6'||i.ordered_options?.length!==6))) return [];
    return new Set(ids).size===ids.length ? ids : [];
  }
  function progress(run, definitions) {
    const records = run.records || [], rounds = run.game?.rounds || [];
    const surveyIds = new Set(records.filter(r => r.source_type === 'survey' && ['submitted','timed_out','skipped'].includes(r.status)).map(r => r.item_id));
    const answerIds = new Set(records.filter(r => r.source_type === 'typed_answer' && ['asked_answered','asked_no_text','skipped'].includes(r.data.status)).map(r => r.data.question_id));
    const base = (run.questions || []).filter(q => q.question_mode === 'baseline');
    const mainDone = rounds.filter(r => r.practice_or_main === 'main' && r.status === 'completed').length;
    const required = requiredSurveyIds(run, definitions);
    const surveysDone = required.filter(id => surveyIds.has(id)).length;
    const answersDone = base.filter(q => answerIds.has(q.question_id)).length;
    const gameDone = rounds.length > 0 && run.game.phase === 'complete' && rounds.every(r => r.status === 'completed');
    const editable = run.status !== 'completed';
    return {mainDone, surveysDone, answersDone, gameDone, canAnalyze: editable && mainDone > 0,
      canFinalize: editable && gameDone && required.length>0 && surveysDone === required.length && answersDone === base.length && Boolean(run.analysis && run.report_draft)};
  }
  function analysisStale(run, definitions) {
    const saved = run.analysis?.input_snapshot;
    if (!saved) return true;
    const refs = (run.records || []).filter(r=>!(r.source_type==='typed_answer'&&r.data?.question_mode==='supplemental')).map(r => ({record_id:r.record_id,record_version:r.record_version,source_type:r.source_type,source_version:r.source_version,status:r.status}));
    return saved.generation !== run.generation || saved.game_state_version !== run.game.state_version || saved.definitions_version !== definitions.version ||
      saved.record_refs.length !== refs.length || refs.some((r,i) => Object.keys(r).some(k => r[k] !== saved.record_refs[i][k]));
  }
  function verifyQuote(span, records) {
    const source = records.find(r => r.source_type === 'typed_answer' && r.data.answer_id === span.source_id && r.data.answer_version === span.source_version)?.data;
    if (!source || !Number.isInteger(span.start) || !Number.isInteger(span.end)) return {valid:false};
    const points = Array.from(source.text);
    if (span.start < 0 || span.end < span.start || span.end > points.length) return {valid:false};
    const quote = points.slice(span.start,span.end).join('');
    return {valid:quote === span.quote,quote,source};
  }
  return {createApi, createMutation, buildSurveyResponse, latestAnswer, answerPayload, progress, analysisStale, verifyQuote, requiredSurveyIds};
});
