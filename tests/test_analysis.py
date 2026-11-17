import copy
import json
import pytest


def test_quote_codepoint_and_version():
    from app.analysis import validate_quote, AnalysisError
    text = '동료에게 먼저 물었어요🙂 그리고 수정했어요.'
    span = dict(source_id='a', source_version=1, start=8, end=13, quote='물었어요🙂')
    assert validate_quote(text, span, 'a', 1) == span
    for change in ({'end':99}, {'source_version':2}, {'quote':'없던 말'}):
        with pytest.raises(AnalysisError):
            validate_quote(text, {**span, **change}, 'a', 1)


def test_extraction_isolation_and_missingness():
    from app.analysis import extract_answer, AnalysisError
    question = dict(question_id='Q-B01', question_version=1, question_text='누구에게 무엇을 물었나요?', behavior_id='B01', question_mode='baseline', conditioned_on_prior_evidence=False, asked_criteria=['other_information'])
    answer = dict(answer_id='a', answer_version=1, text='동료에게 먼저 물었어요🙂', status='submitted')
    inp = dict(question=question, answer=answer, behavior_id='B01', rubric_version='1')
    result = extract_answer(inp)
    assert result['runtime_mode'] == 'mock'
    assert result['criteria']['learning']['status'] == 'not_asked'
    assert result['criteria']['other_information']['status'] == 'unassessable'
    assert result['criteria']['other_information']['evidence_spans'] == []
    assert result['answer_evidence_spans'][0]['quote'] == answer['text']
    with pytest.raises(AnalysisError, match='allowlist'):
        extract_answer({**inp, 'survey_strength':6, 'game_profile_id':'g'})
    conditioned = copy.deepcopy(inp)
    conditioned['question']['conditioned_on_prior_evidence'] = True
    with pytest.raises(AnalysisError, match='conditioned'):
        extract_answer(conditioned)


def test_budget_blocks_before_provider():
    from app.analysis import Provider, AnalysisError
    spy = []
    p = Provider(transport=lambda *a, **k: spy.append(1))
    for key,value in [('input_tokens',4001),('output_tokens',801),('timeout_ms',15001),('retries',3)]:
        with pytest.raises(AnalysisError, match='budget_exceeded'):
            p.check_budget(**{key:value})
    assert spy == []


def test_comparison_precedence():
    from app.analysis import compare_evidence
    base = dict(compatible=True, denominator=3, numerator=3, explicit_support=True, observation_difference=False, documented_context_difference=False, unresolved=False)
    assert compare_evidence(**base)['status'] == 'supports_statement'
    assert compare_evidence(**{**base,'compatible':False,'denominator':0})['status'] == 'not_comparable'
    assert compare_evidence(**{**base,'denominator':0})['status'] == 'insufficient_evidence'
    assert compare_evidence(**{**base,'observation_difference':True,'documented_context_difference':True})['status'] == 'contextual_difference'
    assert compare_evidence(**{**base,'explicit_support':False,'unresolved':True})['status'] == 'needs_clarification'


def test_lineage_allowlists_and_cache_namespaces_are_separate():
    from app.analysis import AnalysisError, build_cache_key, validate_lineage_inputs

    validate_lineage_inputs('baseline_game', {'game_events': ['e-1'], 'mapping_version': '1'})
    with pytest.raises(AnalysisError, match='interview_profile_id'):
        validate_lineage_inputs(
            'baseline_game',
            {'game_events': ['e-1'], 'mapping_version': '1', 'interview_profile_id': 'ip-56'},
        )

    common = dict(
        user_id='u-1', run_id='r-1', attempt_id='a-1', source_id='answer-1',
        source_version='1.0.0', question_version='1.0.0', rubric_version='1.0.0',
        mapping_version='1.0.0', prompt_version='extract-v1',
    )
    baseline = build_cache_key(mode='baseline', **common)
    conditioned = build_cache_key(mode='conditioned_followup', **common)
    assert baseline != conditioned
    assert baseline[0] == 'baseline'
    assert conditioned[0] == 'conditioned_followup'


def test_conditioned_extraction_is_separate_and_never_independent_confirmation():
    from app.analysis import extract_conditioned_answer

    question = dict(
        question_id='F-B03', question_version='2', question_text='앞선 근거를 보고 설명해 주세요.',
        behavior_id='B03', question_mode='adaptive_followup', conditioned_on_prior_evidence=True,
        asked_criteria=['reasoning'], generated_from_evidence_refs=['survey:s-1'],
        disclosed_prior_information=['survey label: 매우 그렇다'],
    )
    answer = dict(answer_id='fa-1', answer_version='1', text='새 정보를 보고 계획을 유지했습니다.', status='asked_answered')
    result = extract_conditioned_answer(dict(question=question, answer=answer, behavior_id='B03', rubric_version='1'))
    assert result['mode'] == 'conditioned_followup'
    assert result['conditioned_on_prior_evidence'] is True
    assert result['independent_confirmation'] is False
    assert result['lineage']['cache_namespace'] == 'conditioned_followup'
    assert result['criteria']['reasoning']['status'] == 'unassessable'
    assert result['answer_evidence_spans'][0]['quote'] == answer['text']


def test_snapshot_validation_rejects_foreign_withdrawn_and_stale_records():
    from app.analysis import AnalysisError, validate_snapshot

    run = dict(user_id='u-1', run_id='r-1', attempt_id='a-1', generation=3, status='in_progress')
    base = dict(
        record_id='rec-1', source_type='typed_answer', source_version='1', user_id='u-1',
        run_id='r-1', attempt_id='a-1', status='submitted', generation=3,
        data={'answer_id': 'ans-1', 'answer_version': '1', 'text': '원문'},
    )
    validate_snapshot(run, [base])
    for change, code in [
        ({'user_id': 'u-2'}, 'ownership_mismatch'),
        ({'run_id': 'r-2'}, 'cross_run_evidence'),
        ({'status': 'withdrawn'}, 'withdrawn_evidence'),
        ({'generation': 2}, 'stale_generation'),
    ]:
        with pytest.raises(AnalysisError, match=code):
            validate_snapshot(run, [{**base, **change}])


def test_mock_and_live_provenance_cannot_mix():
    from app.analysis import AnalysisError, validate_runtime_modes

    assert validate_runtime_modes([{'runtime_mode': 'mock'}, {'runtime_mode': 'mock'}]) == 'mock'
    with pytest.raises(AnalysisError, match='mixed_provenance'):
        validate_runtime_modes([{'runtime_mode': 'mock'}, {'runtime_mode': 'live'}])


def _definitions():
    behaviors = {
        'B01': {'behavior_id': 'B01', 'behavior_version': '1', 'name': '결정 전 정보 확인', 'operational_definition': '결정 전에 다른 사람의 정보를 확인함'},
        'B02': {'behavior_id': 'B02', 'behavior_version': '1', 'name': '자원 배분', 'operational_definition': '제한된 자원을 개인·팀 과제에 배분함'},
        'B03': {'behavior_id': 'B03', 'behavior_version': '1', 'name': '새 정보 후 재검토', 'operational_definition': '새 정보 이후 선택을 재검토함'},
    }
    mappings = []
    for behavior_id in behaviors:
        mappings.append({
            'mapping_id': f'm-{behavior_id}', 'version': '1', 'behavior_id': behavior_id,
            'behavior_version': '1', 'reason': '연습용 좁은 행동 연결', 'observable_proxy': '관찰된 게임 이벤트와 자기보고',
            'preconditions': ['same_run'], 'limitations': ['과제 밖 행동으로 일반화할 수 없음'],
            'permitted_uses': ['comparison', 'question_generation', 'report'],
            'practice_review_status': 'approved_for_practice', 'validity_status': 'provisional_unvalidated',
            'reviewer_type': 'independent_codex_domain_review', 'reviewer_id': 'domain-review',
            'reviewed_at': '2026-09-16T00:00:00Z',
        })
    questions = [
        {'question_id': f'Q-{bid}', 'question_version': '1', 'question_text': f'{bid} 경험을 설명해 주세요.',
         'behavior_id': bid, 'target_behavior_ids': [bid], 'question_mode': 'baseline',
         'conditioned_on_prior_evidence': False, 'asked_criteria': ['action', 'reasoning']}
        for bid in behaviors
    ]
    return {'version': '1', 'behaviors': behaviors, 'mappings': mappings, 'questions': questions, 'runtime_mode': 'mock'}


def _run(label='매우 그렇다'):
    records = [
        {
            'record_id': 'survey-1', 'source_type': 'survey_response', 'source_version': '1',
            'user_id': 'u-1', 'run_id': 'run-1', 'attempt_id': 'attempt-1', 'status': 'submitted', 'generation': 1,
            'item_id': 'O-B01', 'item_version': '1',
            'data': {'behavior_id': 'B01', 'selected_position': 6, 'selected_label_snapshot': label},
        },
        {
            'record_id': 'answer-1', 'source_type': 'typed_answer', 'source_version': '1',
            'user_id': 'u-1', 'run_id': 'run-1', 'attempt_id': 'attempt-1', 'status': 'submitted', 'generation': 1,
            'data': {'answer_id': 'answer-1', 'answer_version': '1', 'question_id': 'Q-B01', 'question_version': '1',
                     'question_text_snapshot': 'B01 경험을 설명해 주세요.', 'behavior_id': 'B01', 'question_mode': 'baseline',
                     'conditioned_on_prior_evidence': False, 'text': '동료에게 먼저 물었어요🙂', 'status': 'asked_answered'},
        },
    ]
    return {
        'run_id': 'run-1', 'user_id': 'u-1', 'attempt_id': 'attempt-1', 'generation': 1,
        'status': 'in_progress', 'revision': 4, 'runtime_mode': 'mock', 'records': records,
        'questions': _definitions()['questions'],
        'game': {'metrics': [{'metric_id': 'metric-B01', 'behavior_id': 'B01', 'mapping_version': '1',
                              'numerator': 2, 'denominator': 2, 'unit': 'eligible_opportunity',
                              'included_opportunity_ids': ['o-1', 'o-2'], 'excluded_opportunities_with_reasons': [],
                              'algorithm_version': 'game-metric-v1'}]},
    }


def test_analyze_run_preserves_baseline_when_survey_strength_changes():
    from app.analysis import analyze_run

    weak = analyze_run(_run('그런 편이다'), _definitions())
    strong = analyze_run(_run('매우 그렇다'), _definitions())
    weak_baseline = [x for x in weak['extractions'] if x['mode'] == 'baseline']
    strong_baseline = [x for x in strong['extractions'] if x['mode'] == 'baseline']
    assert weak_baseline == strong_baseline
    assert weak['metrics'] == strong['metrics']
    assert weak['questions'][0]['question_text'] != strong['questions'][0]['question_text']
    assert strong['questions'][0]['conditioned_on_prior_evidence'] is True
    assert strong['questions'][0]['disclosed_prior_information'] == ['survey label: 매우 그렇다', 'game observation: 2/2 eligible opportunities']
    assert strong['comparisons'][0]['conditioned_followup_refs'] == []


def test_analyze_run_report_is_grounded_and_does_not_invent_scores_or_causes():
    from app.analysis import analyze_run, validate_report

    result = analyze_run(_run(), _definitions())
    assert result['runtime_mode'] == 'mock'
    assert set(result) == {'extractions', 'metrics', 'comparisons', 'questions', 'report', 'runtime_mode'}
    card = next(c for c in result['report']['cards'] if c['behavior_id'] == 'B01')
    quote = card['interview_evidence'][0]
    assert quote['quote'] == '동료에게 먼저 물었어요🙂'
    assert quote['quote'] == quote['answer_text'][quote['start']:quote['end']]
    assert card['game_evidence']['numerator'] == 2
    assert card['game_evidence']['denominator'] == 2
    assert card['comparison_status'] == 'needs_clarification'
    forbidden_keys = {'score', 'confidence', 'accuracy', 'pass_probability', 'personality_score', 'hiring_recommendation'}
    assert not forbidden_keys.intersection(card)
    assert '때문에' not in str(result['report'])
    validate_report(result['report'], _run(), result['metrics'], result['extractions'])


def test_report_validation_rejects_fabricated_quote_and_numbers():
    from app.analysis import AnalysisError, analyze_run, validate_report

    run = _run()
    result = analyze_run(run, _definitions())
    fabricated_quote = copy.deepcopy(result['report'])
    fabricated_quote['cards'][0]['interview_evidence'][0]['quote'] = '없던 말'
    with pytest.raises(AnalysisError, match='quote_mismatch'):
        validate_report(fabricated_quote, run, result['metrics'], result['extractions'])
    fabricated_number = copy.deepcopy(result['report'])
    fabricated_number['cards'][0]['game_evidence']['numerator'] = 5
    with pytest.raises(AnalysisError, match='metric_mismatch'):
        validate_report(fabricated_number, run, result['metrics'], result['extractions'])


def test_report_validation_rejects_fabricated_survey_label_and_reference_id():
    from app.analysis import AnalysisError, analyze_run, validate_report

    run = _run()
    result = analyze_run(run, _definitions())
    fabricated_label = copy.deepcopy(result['report'])
    fabricated_label['cards'][0]['survey_evidence']['responses'][0]['selected_label_snapshot'] = '원본에 없는 라벨'
    with pytest.raises(AnalysisError, match='survey_mismatch'):
        validate_report(fabricated_label, run, result['metrics'], result['extractions'])
    fabricated_ref = copy.deepcopy(result['report'])
    fabricated_ref['cards'][0]['source_refs'].append('survey:missing@1')
    with pytest.raises(AnalysisError, match='evidence_ref_missing'):
        validate_report(fabricated_ref, run, result['metrics'], result['extractions'])


def test_unreviewed_mapping_is_not_eligible_for_comparison():
    from app.analysis import analyze_run

    definitions = _definitions()
    definitions['mappings'][0]['practice_review_status'] = 'draft'
    result = analyze_run(_run(), definitions)
    comparison = next(c for c in result['comparisons'] if c['behavior_id'] == 'B01')
    assert comparison['status'] == 'not_comparable'
    assert comparison['reason'] == 'mapping_not_approved_for_practice'


def test_live_provider_is_blocked_before_transport_without_explicit_opt_in(monkeypatch):
    from app.ai_provider import LiveProvider, ProviderError

    monkeypatch.delenv('AI_LIVE_ENABLED', raising=False)
    monkeypatch.delenv('PAID_AI_ENABLED', raising=False)
    calls = []
    provider = LiveProvider(transport=lambda *args, **kwargs: calls.append((args, kwargs)))
    with pytest.raises(ProviderError, match='live_disabled'):
        provider.generate({'input': 'synthetic'}, input_tokens=10, output_tokens=20)
    assert calls == []


def test_analyze_resolves_survey_behavior_from_definition_item_id():
    from app.analysis import analyze_run

    run = _run()
    run['records'][0]['data'].pop('behavior_id')
    definitions = _definitions()
    definitions['surveys'] = [{'item_id': 'O-B01', 'item_version': '1', 'behavior_id': 'B01'}]
    result = analyze_run(run, definitions)
    card = next(item for item in result['report']['cards'] if item['behavior_id'] == 'B01')
    assert card['survey_evidence']['selected_label_snapshot'] == '매우 그렇다'


def test_live_structured_output_must_use_exact_source_spans():
    from app.analysis import AnalysisError, validate_model_extraction_output

    criteria = []
    for criterion in ('situation', 'role', 'other_information', 'action', 'reasoning', 'result', 'learning'):
        criteria.append({'criterion': criterion, 'status': 'not_asked', 'evidence_spans': [], 'limitations': [], 'missing_reason': 'criterion_not_asked'})
    criteria[3] = {
        'criterion': 'action', 'status': 'explicit',
        'evidence_spans': [{'source_id': 'a', 'source_version': '1', 'start': 0, 'end': 2, 'quote': '행동'}],
        'limitations': ['자기보고'], 'missing_reason': None,
    }
    assert validate_model_extraction_output({'criteria': criteria}, '행동 원문', 'a', '1')['criteria'][3]['status'] == 'explicit'
    criteria[3]['evidence_spans'][0]['quote'] = '조작'
    with pytest.raises(AnalysisError, match='quote_mismatch'):
        validate_model_extraction_output({'criteria': criteria}, '행동 원문', 'a', '1')


def test_report_preserves_all_survey_response_forms_for_a_behavior():
    from app.analysis import analyze_run

    run = _run()
    run['records'].append({
        'record_id': 'survey-paired', 'source_type': 'survey_response', 'source_version': '1',
        'user_id': 'u-1', 'run_id': 'run-1', 'attempt_id': 'attempt-1', 'status': 'submitted', 'generation': 1,
        'item_id': 'P-B01', 'item_version': '1',
        'data': {'behavior_id': 'B01', 'self': {'selected_label_snapshot': '그렇다'},
                 'imagined_others': {'selected_label_snapshot': '그런 편이다'},
                 'respondent_user_id': 'u-1'},
    })
    definitions = _definitions()
    definitions['surveys'] = [
        {'item_id': 'O-B01', 'item_version': '1', 'behavior_id': 'B01'},
        {'item_id': 'P-B01', 'item_version': '1', 'behavior_id': 'B01'},
    ]
    card = next(item for item in analyze_run(run, definitions)['report']['cards'] if item['behavior_id'] == 'B01')
    assert [item['record_id'] for item in card['survey_evidence']['responses']] == ['survey-1', 'survey-paired']
    assert card['survey_evidence']['responses'][1]['respondent_user_id'] == 'u-1'


def test_each_used_source_mapping_must_be_review_approved():
    from app.analysis import analyze_run

    definitions = _definitions()
    combined = definitions['mappings'].pop(0)
    game = {**combined, 'mapping_id': 'map-game-b01', 'source_kind': 'game_event_rule',
            'source_definition_id': 'game', 'source_definition_version': '1', 'version': '1'}
    survey = {**combined, 'mapping_id': 'map-survey-b01', 'source_kind': 'survey_self_report',
              'source_definition_id': 'O-B01', 'source_definition_version': '1', 'version': '1'}
    interview = {**combined, 'mapping_id': 'map-interview-b01', 'source_kind': 'interview_rubric',
                 'source_definition_id': 'rubric-b01', 'source_definition_version': '1', 'version': '1', 'practice_review_status': 'draft'}
    definitions['mappings'] = [game, survey, interview, *definitions['mappings']]
    run = _run()
    run['game']['metrics'][0]['mapping_id'] = 'map-game-b01'
    comparison = next(item for item in analyze_run(run, definitions)['comparisons'] if item['behavior_id'] == 'B01')
    assert comparison['status'] == 'not_comparable'
    assert comparison['reason'] == 'interview_mapping_not_approved_for_practice'


def test_survey_mapping_without_comparison_permission_is_excluded_from_comparison_refs():
    from app.analysis import analyze_run

    definitions = _definitions()
    combined = definitions['mappings'].pop(0)
    game = {**combined, 'mapping_id': 'map-game-b01', 'source_kind': 'game_event_rule',
            'source_definition_id': 'game', 'source_definition_version': '1', 'version': '1'}
    survey = {**combined, 'mapping_id': 'map-survey-b01', 'source_kind': 'bipolar_preference_self_report',
              'source_definition_id': 'O-B01', 'source_definition_version': '1', 'version': '1',
              'permitted_uses': ['practice_question_generation', 'original_response_report']}
    interview = {**combined, 'mapping_id': 'map-interview-b01', 'source_kind': 'interview_rubric',
                 'source_definition_id': 'rubric-b01', 'source_definition_version': '1', 'version': '1'}
    definitions['mappings'] = [game, survey, interview, *definitions['mappings']]
    run = _run()
    run['game']['metrics'][0]['mapping_id'] = 'map-game-b01'
    comparison = next(item for item in analyze_run(run, definitions)['comparisons'] if item['behavior_id'] == 'B01')
    assert comparison['status'] == 'needs_clarification'
    assert all(not ref.startswith('survey:') for ref in comparison['evidence_refs'])
    assert comparison['excluded_evidence_with_reasons'][0]['reason'] == 'survey_mapping_use_not_permitted'


def test_adaptive_question_asked_criteria_matches_question_wording():
    from app.analysis import analyze_run

    question = analyze_run(_run(), _definitions())['questions'][0]
    assert question['asked_criteria'] == ['reasoning']
    assert '판단 기준이나 조건' in question['question_text']


def test_timed_out_survey_selection_is_preserved_but_excluded_from_comparison_and_disclosure():
    from app.analysis import analyze_run
    from app.content import DEFINITIONS
    from app.survey import build_survey_record

    survey_definition = next(item for item in DEFINITIONS['surveys'] if item['item_id'] == 'O-B01')
    timed_out = build_survey_record(
        definition=survey_definition,
        user_id='u-1',
        run_id='run-1',
        attempt_id='attempt-1',
        presentation_order=1,
        response={'selected_position': 6},
        status='timed_out',
        elapsed_ms=30_000,
    )
    run = _run()
    run['records'][0] = timed_out
    run['game']['metrics'][0].update(mapping_id='map-game-b01', mapping_version='1.0.0')

    result = analyze_run(run, copy.deepcopy(DEFINITIONS))
    comparison = next(item for item in result['comparisons'] if item['behavior_id'] == 'B01')
    survey_ref = f"survey:{timed_out['record_id']}@{timed_out['source_version']}"
    assert survey_ref not in comparison['evidence_refs']
    assert {'evidence_ref': survey_ref, 'reason': 'survey_precondition_not_met:submitted'} in comparison['excluded_evidence_with_reasons']
    assert all('survey label:' not in disclosure for question in result['questions'] for disclosure in question['disclosed_prior_information'])
    response = next(card for card in result['report']['cards'] if card['behavior_id'] == 'B01')['survey_evidence']['responses'][0]
    assert response['record_status'] == 'timed_out'
    assert response['evidence_eligibility'] == 'partial_not_eligible'
    assert response['selected_position'] == 6


def test_extraction_uses_actual_question_rubric_and_rejects_mapping_version_mismatch():
    from app.analysis import analyze_run
    from app.content import DEFINITIONS

    definitions = copy.deepcopy(DEFINITIONS)
    question = copy.deepcopy(next(item for item in definitions['questions'] if item['behavior_id'] == 'B01'))
    run = _run()
    run['records'] = [run['records'][1]]
    run['questions'] = [question]
    answer = run['records'][0]['data']
    answer.update(
        question_id=question['question_id'],
        question_version=question['question_version'],
        question_text_snapshot=question['question_text'],
    )
    run['game']['metrics'] = []

    valid = analyze_run(copy.deepcopy(run), definitions)
    extraction = valid['extractions'][0]
    assert extraction['rubric_id'] == question['rubric_id']
    assert extraction['rubric_version'] == question['rubric_version']
    assert extraction['lineage']['rubric_ref'] == 'rubric-b01@1.0.0'
    assert extraction['mapping_id'] == 'map-interview-b01'
    assert extraction['mapping_eligible'] is True

    mismatched_definitions = copy.deepcopy(definitions)
    mismatched_question = next(item for item in mismatched_definitions['questions'] if item['question_id'] == question['question_id'])
    mismatched_question['rubric_version'] = '9.0.0'
    mismatched_run = copy.deepcopy(run)
    mismatched_run['questions'][0]['rubric_version'] = '9.0.0'
    mismatched = analyze_run(mismatched_run, mismatched_definitions)
    bad_extraction = mismatched['extractions'][0]
    assert bad_extraction['mapping_eligible'] is False
    assert bad_extraction['mapping_eligibility_error'] == 'rubric_version_incompatible'
    comparison = next(item for item in mismatched['comparisons'] if item['behavior_id'] == 'B01')
    assert comparison['status'] == 'not_comparable'
    assert comparison['reason'] == 'interview_rubric_version_incompatible'


def test_adaptive_questions_name_the_behavior_specific_observation_without_scoring_it():
    from app.analysis import _adaptive_question

    expected = {
        'B01': '결정 전에 정보 창을 연 횟수',
        'B02': '개인·팀 배분을 확정한 횟수',
        'B03': '새 정보 뒤 선택을 바꾼 횟수(유지도 허용)',
    }
    questions = {}
    for behavior_id, phrase in expected.items():
        questions[behavior_id] = _adaptive_question(
            behavior_id,
            {'record_id': f's-{behavior_id}', 'source_version': '1', 'selected_label_snapshot': '그렇다'},
            {'metric_id': f'm-{behavior_id}', 'algorithm_version': '1', 'numerator': 3, 'denominator': 3},
            None,
        )
        assert phrase in questions[behavior_id]['question_text']
        assert '점수' not in questions[behavior_id]['question_text']
    assert len({question['question_text'] for question in questions.values()}) == 3


def test_answer_correction_chain_extracts_only_latest_immutable_leaf():
    from app.analysis import analyze_run

    run = _run()
    original = run['records'][1]
    original['data']['text'] = '오타가 있는 원문'
    corrected = copy.deepcopy(original)
    corrected['record_id'] = 'answer-record-2'
    corrected['source_version'] = '2'
    corrected['data'] = {
        **corrected['data'], 'answer_id': 'answer-2', 'answer_version': '2',
        'previous_answer_version_ref': {'answer_id': 'answer-1', 'answer_version': '1'},
        'text': '정정한 원문🙂',
    }
    original['data']['answer_id'] = 'answer-1'
    original['data']['answer_version'] = '1'
    run['records'].append(corrected)
    result = analyze_run(run, _definitions())
    assert len(result['extractions']) == 1
    assert result['extractions'][0]['answer_id'] == 'answer-2'
    assert result['report']['cards'][0]['interview_evidence'][0]['quote'] == '정정한 원문🙂'


def test_answer_correction_chain_rejects_missing_predecessor():
    from app.analysis import AnalysisError, analyze_run

    run = _run()
    run['records'][1]['data']['previous_answer_version_ref'] = {'answer_id': 'missing', 'answer_version': '0'}
    with pytest.raises(AnalysisError, match='correction_predecessor_missing'):
        analyze_run(run, _definitions())


def test_answer_correction_chain_rejects_cycle():
    from app.analysis import AnalysisError, analyze_run

    run = _run()
    first = run['records'][1]
    first['data']['answer_id'] = 'answer-1'
    first['data']['answer_version'] = '1'
    second = copy.deepcopy(first)
    second['record_id'] = 'answer-record-2'
    second['data']['answer_id'] = 'answer-2'
    second['data']['answer_version'] = '2'
    first['data']['previous_answer_version_ref'] = {'answer_id': 'answer-2', 'answer_version': '2'}
    second['data']['previous_answer_version_ref'] = {'answer_id': 'answer-1', 'answer_version': '1'}
    run['records'].append(second)
    with pytest.raises(AnalysisError, match='correction_cycle'):
        analyze_run(run, _definitions())


def test_baseline_derivation_is_stable_across_json_storage_roundtrip():
    from app.analysis import analyze_run

    run = _run()
    first = analyze_run(run, _definitions())
    stored = json.loads(json.dumps(first, ensure_ascii=False))
    second = analyze_run(run, _definitions())
    old_baseline = [item for item in stored['extractions'] if item['mode'] == 'baseline']
    new_baseline = [item for item in second['extractions'] if item['mode'] == 'baseline']
    assert old_baseline == new_baseline
