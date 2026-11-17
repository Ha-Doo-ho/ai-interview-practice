"""Factual linkage, conditional provenance and frozen neutral evidence."""
from copy import deepcopy
import pytest

from app.content import DEFINITIONS
from app.interview_analysis import prepare_analysis, execute_analysis
from app.survey import build_survey_record
from test_live_interview_analysis import sample_run


def prepared_run():
    run = sample_run()
    run['records'] = [r for r in run['records'] if r['source_type'] != 'survey']
    definition = next(x for x in DEFINITIONS['surveys'] if x['item_id'] == 'O-B03')
    run['records'].append(build_survey_record(definition=definition, user_id=run['user_id'], run_id=run['run_id'], attempt_id=run['attempt_id'], presentation_order=1, response={'selected_position': 5}, status='submitted', elapsed_ms=1000))
    initial = {'rule_id':'card-even', 'label':'짝수'}
    changed = {'rule_id':'card-multiple-3','label':'3의 배수'}
    board = {'stimulus_id':'board-1', 'cards':[{'card_id':str(v),'value':v} for v in [6,2,3,1]]}
    events = [{'event_id':'reveal', 'sequence_no':1,'type':'rule_revealed','rule':changed}]
    for index, value in enumerate([6,2,3,1], 2):
        events.append({'event_id':f'choice-{value}','sequence_no':index,'type':'response_selected','rule':changed,'stimulus':board,'choice':str(value),'correct':value in (6,3)})
    run['rule_games']['games']['card']['rounds'] = [{'round_id':'card-1','index':1,'status':'completed','revealed_at':'synthetic-time','rule_snapshot':{'initial':initial,'changed':changed},'events':events,'quality_flags':[]}]
    result = execute_analysis(prepare_analysis(run, DEFINITIONS, 'mock'))
    run['interview_analysis'] = result
    run['interview_report'] = deepcopy(result['report'])
    return run


def test_game_facts_keep_overlap_and_do_not_change_baseline_or_originals():
    from app.evidence_linkage import build_linkage
    run = prepared_run(); before = deepcopy(run)
    result = build_linkage(run, DEFINITIONS)
    card = next(x for x in result['observations'] if x['game_type'] == 'card')
    assert card['after']['accepted_count'] == 4 and card['after']['correct_count'] == 2
    assert card['overlap'] == {'new_only':1,'old_only':1,'both':1,'neither':1}
    assert card['mapping_status'] == 'unmapped'
    assert run == before
    link = next(x for x in result['links'] if x['behavior_id'] == 'B03')
    assert link['survey_refs'][0]['response_text'] == '그렇다'
    assert link['comparison_status'] == 'insufficient_evidence'
    question = next(q for q in result['questions'] if q['behavior_id']=='B03')
    assert question['conditioned_on_prior_evidence'] is True
    assert question['generated_from_evidence_refs'] and question['disclosed_prior_information']
    assert '그렇다' in question['question_text']


@pytest.mark.parametrize('revealed', [True, False])
def test_missing_disclosure_and_zero_accepted_responses_are_distinct(revealed):
    from app.evidence_linkage import game_observations
    run = prepared_run(); item = run['rule_games']['games']['card']['rounds'][0]
    item['events'] = item['events'][:1] if revealed else []
    item['revealed_at'] = 'synthetic-time' if revealed else None
    result = next(x for x in game_observations(run) if x['game_type']=='card')
    assert result['missing_reason'] == ('no_accepted_response_after_disclosure' if revealed else 'rule_reveal_not_recorded')
    assert result['after']['accepted_count']==0
    assert 'accuracy' not in result['after']


def test_linkage_detects_source_change_but_not_conditioned_answer_and_final_preserves_cards():
    from app.evidence_linkage import build_linkage, linkage_is_current, finalize_report
    run = prepared_run(); run['evidence_linkage'] = build_linkage(run,DEFINITIONS)
    run['questions'].extend(deepcopy(run['evidence_linkage']['questions']))
    q = run['evidence_linkage']['questions'][0]
    run['records'].append({'record_id':'conditional','source_type':'typed_answer','source_version':'1.0.0','data':{'answer_id':'conditional','answer_version':'1.0.0','question_id':q['question_id'],'question_version':q['question_version'],'question_mode':'adaptive_followup','conditioned_on_prior_evidence':True,'disclosed_prior_information':deepcopy(q['disclosed_prior_information']),'generated_from_evidence_refs':deepcopy(q['generated_from_evidence_refs']),'text':'🙂 질문에 공개된 선택의 이유입니다.','status':'asked_answered'}})
    assert linkage_is_current(run,DEFINITIONS)
    final = finalize_report(run,DEFINITIONS)
    assert final['cards']==run['interview_analysis']['report']['cards']
    assert final['followup_answers'][0]['text']=='🙂 질문에 공개된 선택의 이유입니다.'
    assert final['followup_answers'][0]['conditioned_on_prior_evidence'] is True
    assert any(a['status']=='not_answered' for a in final['followup_answers'])
    assert final['source_report_id']==run['interview_analysis']['report']['report_id']
    assert final['report_id']!=final['source_report_id']
    run['records'][-2]['record_version']='2.0.0'
    assert not linkage_is_current(run,DEFINITIONS)


def test_question_identity_is_stable_and_source_version_mismatch_is_not_mapped():
    from app.evidence_linkage import build_linkage
    run=prepared_run()
    first=build_linkage(run,DEFINITIONS); second=build_linkage(run,DEFINITIONS)
    assert first['questions']==second['questions']
    run['records'][-1]['item_version']='unreviewed'
    result=execute_analysis(prepare_analysis(run,DEFINITIONS,'mock'))
    run['interview_analysis']=result; run['interview_report']=deepcopy(result['report'])
    links=build_linkage(run,DEFINITIONS)['links']
    assert all(not x['survey_refs'] for x in links)


def test_changed_game_event_invalidates_report_and_existing_linkage():
    from app.evidence_linkage import build_linkage, linkage_is_current
    from app.store import Conflict
    run=prepared_run(); run['evidence_linkage']=build_linkage(run,DEFINITIONS)
    run['rule_games']['games']['card']['rounds'][0]['events'].append({'event_id':'later','type':'visibility_reported','sequence_no':7,'hidden':True})
    assert not linkage_is_current(run,DEFINITIONS)
    with pytest.raises(Conflict,match='interview_report_stale'):
        build_linkage(run,DEFINITIONS)


def test_mismatched_event_truth_and_source_quote_fail_closed():
    from app.evidence_linkage import build_linkage, game_observations
    from app.store import Validation
    run=prepared_run()
    run['rule_games']['games']['card']['rounds'][0]['events'][1]['correct']=False
    with pytest.raises(Validation,match='evidence_linkage_invalid'): game_observations(run)
    run=prepared_run(); card=run['interview_analysis']['report']['cards'][0]
    card['criteria']['action']['evidence_spans']=[{'source_id':card['answer_id'],'source_version':card['answer_version'],'start':0,'end':1,'quote':'X','offset_unit':'unicode_code_point'}]
    with pytest.raises(Validation,match='evidence_linkage_invalid'): build_linkage(run,DEFINITIONS)


@pytest.mark.parametrize('mutation',['context_only','incomplete','source_kind','behavior_version'])
def test_only_eligible_comparison_survey_can_trigger_clarification(mutation):
    from app.evidence_linkage import build_linkage
    run=prepared_run(); definitions=deepcopy(DEFINITIONS)
    card=run['interview_analysis']['report']['cards'][2]
    answer=next(r['data'] for r in run['records'] if r.get('data',{}).get('answer_id')==card['answer_id'])
    # Rebuild a genuine baseline report after editing the synthetic response.
    answer['text']='처음 계획을 유지했습니다.'; answer['status']='asked_answered'
    mapping=next(m for m in definitions['mappings'] if m['mapping_id']=='map-survey-o-b03')
    if mutation=='context_only': mapping['permitted_uses'].remove('evidence_comparison')
    elif mutation=='incomplete': run['records'][-1]['status']='timed_out'
    elif mutation=='source_kind': mapping['source_kind']='game_metric'
    else: mapping['behavior_version']='999'
    result=execute_analysis(prepare_analysis(run,definitions,'mock'))
    run['interview_analysis']=result; run['interview_report']=deepcopy(result['report'])
    card=result['report']['cards'][2]
    card['criteria']['action']['evidence_spans']=[{'source_id':answer['answer_id'],'source_version':answer['answer_version'],'start':0,'end':len(answer['text']),'quote':answer['text'],'offset_unit':'unicode_code_point'}]
    link=next(x for x in build_linkage(run,definitions)['links'] if x['behavior_id']=='B03')
    assert link['comparison_status']==('not_comparable' if mutation in {'source_kind','behavior_version'} else 'insufficient_evidence')
    assert not any(x.get('comparison_eligible') for x in link['survey_refs'])


@pytest.mark.parametrize('mutation',['card_binding','foreign_record'])
def test_explicit_wrong_source_identity_is_rejected(mutation):
    from app.evidence_linkage import build_linkage
    from app.store import Validation
    run=prepared_run()
    if mutation=='card_binding': run['interview_analysis']['report']['cards'][0]['question_id']='baseline-b02'
    else: run['records'][-1]['user_id']='someone-else'
    with pytest.raises(Validation, match='evidence_linkage_invalid'): build_linkage(run,DEFINITIONS)


def test_retired_interview_mapping_cannot_drive_a_new_comparison():
    from app.evidence_linkage import build_linkage
    run=prepared_run(); definitions=deepcopy(DEFINITIONS)
    next(m for m in definitions['mappings'] if m['mapping_id']=='map-interview-b01')['practice_review_status']='retired'
    link=next(x for x in build_linkage(run,definitions)['links'] if x['behavior_id']=='B01')
    assert link['comparison_status']=='not_comparable'
    assert any(x.get('mapping_id')=='map-interview-b01' for x in link['exclusions'])


@pytest.mark.parametrize('field,value', [('conditioned_on_prior_evidence',True),('disclosed_prior_information',[{'text':'prior'}]),('generated_from_evidence_refs',['survey-1']),('question_mode','adaptive_followup')])
@pytest.mark.parametrize('target',['question','answer'])
def test_contaminated_baseline_is_rejected_before_extraction(target,field,value):
    import app.interview_analysis as subject
    run=sample_run()
    if target=='question': run['questions'][0][field]=value
    else:
        next(r for r in run['records'] if r.get('data',{}).get('answer_id')=='answer-current')['data'][field]=value
    with pytest.raises(ValueError, match='question_definition_mismatch|baseline_conditioning_mismatch'):
        subject.prepare_analysis(run,DEFINITIONS,'mock')
