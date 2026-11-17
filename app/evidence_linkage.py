"""Deterministic source linkage after neutral extraction, without ability scores.

This module never calls a provider and never changes source evidence. Rule-game
observations remain unmapped task facts; followups are conditioned self-report.
"""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from uuid import uuid4

from . import interview_analysis
from .rule_games import _correct
from .store import Conflict, Validation

VERSION = 'evidence-linkage-1.0.0'
COMPLETION_POLICY_VERSION = 'rule-games-text-1.0.0'
LIMITATIONS = [
    '설문과 면접은 같은 사용자의 자기보고이며 독립된 진실 검증이 아닙니다.',
    '규칙 게임은 해당 과제의 선택 기록이며 B01/B02/B03의 직접 측정이 아닙니다.',
    '후속 답변은 공개된 근거를 참고한 조건부 자기보고입니다.',
]


def _digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')).hexdigest()


def _baseline_report(run, definitions):
    analysis = run.get('interview_analysis') or {}
    report = analysis.get('report')
    if not isinstance(report, dict) or not report.get('report_id') or not isinstance(run.get('interview_report'), dict):
        raise Conflict('interview_analysis_required')
    try:
        current = interview_analysis.input_snapshot(run, definitions)
    except (ValueError, KeyError, TypeError):
        raise Validation('evidence_linkage_invalid') from None
    if analysis.get('input_snapshot') != current or report.get('input_snapshot') != current:
        raise Conflict('interview_report_stale')
    return report


def _source_snapshot(run, definitions):
    report = _baseline_report(run, definitions)
    baseline_ids = {q['question_id'] for q in definitions['questions'] if q.get('question_mode') == 'baseline'}
    records = [r for r in run.get('records', []) if r.get('source_type') == 'survey' or
               (r.get('source_type') == 'typed_answer' and r.get('data', {}).get('question_id') in baseline_ids)]
    lineages = list(records) + [r.get('lineage', {}) for game in (run.get('rule_games') or {}).get('games', {}).values() for r in game.get('rounds', [])]
    for lineage in lineages:
        if any(key in lineage and lineage[key] != run.get(key) for key in ('user_id','run_id','attempt_id')):
            raise Validation('evidence_linkage_invalid')
    return {
        'run_id': run.get('run_id'), 'user_id': run.get('user_id'), 'attempt_id': run.get('attempt_id'),
        'baseline_input': interview_analysis.input_snapshot(run, definitions),
        'source_report_id': report['report_id'],
        'source_digest': _digest({'records': records, 'rule_games': run.get('rule_games'),
                                 **({'appointment_games': run.get('appointment_games')} if run.get('flow_version') == 'five-game-v2' else {}),
                                 'cards': report.get('cards'), 'mappings': definitions.get('mappings')}),
    }


def linkage_is_current(run, definitions):
    linkage = run.get('evidence_linkage')
    if not isinstance(linkage, dict) or linkage.get('version') != VERSION:
        return False
    try:
        return linkage.get('input_snapshot') == _source_snapshot(run, definitions)
    except (ValueError, KeyError, TypeError, Conflict, Validation):
        return False


def game_observations(run):
    result = []
    for game_type, game in ((run.get('rule_games') or {}).get('games') or {}).items():
        if game_type not in {'rsp', 'card'}:
            continue
        for round_state in game.get('rounds', []):
            events = round_state.get('events', [])
            reveals = [e for e in events if e.get('type') == 'rule_revealed']
            reveal = reveals[0] if len(reveals) == 1 and round_state.get('revealed_at') else None
            before = {'accepted_count': 0, 'correct_count': 0, 'event_refs': []}
            after = deepcopy(before)
            overlap = {'new_only': 0, 'old_only': 0, 'both': 0, 'neither': 0}
            details = []
            initial = (round_state.get('rule_snapshot') or {}).get('initial') or {}
            changed = (round_state.get('rule_snapshot') or {}).get('changed') or {}
            valid_rules = {'rsp': {'rsp-win','rsp-lose','rsp-draw'}, 'card': {'card-even','card-multiple-3','card-at-least-7'}}[game_type]
            for event in events:
                if event.get('type') != 'response_selected':
                    continue
                post = reveal is not None and event.get('sequence_no', -1) > reveal.get('sequence_no', -1)
                expected = changed if post else initial
                rule = event.get('rule') or {}
                try:
                    if rule.get('rule_id') not in valid_rules or rule != expected or not isinstance(event.get('correct'), bool):
                        raise ValueError('invalid rule')
                    correct = _correct(game_type, rule['rule_id'], event['stimulus'], event['choice'])
                    if correct != event['correct'] or not event.get('event_id'):
                        raise ValueError('invalid observation')
                    group = after if post else before
                    group['accepted_count'] += 1
                    group['correct_count'] += int(correct)
                    group['event_refs'].append(event['event_id'])
                    detail = {'event_id':event['event_id'], 'sequence_no':event['sequence_no'],
                              'stimulus':deepcopy(event['stimulus']), 'choice':event['choice'],
                              'rule':deepcopy(rule), 'correct':correct, 'phase':'after' if post else 'before'}
                    if post:
                        if initial.get('rule_id') not in valid_rules:
                            raise ValueError('invalid initial rule')
                        old = _correct(game_type, initial['rule_id'], event['stimulus'], event['choice'])
                        category = 'both' if correct and old else 'new_only' if correct else 'old_only' if old else 'neither'
                        overlap[category] += 1
                        detail['old_rule_correct'] = old
                        detail['rule_overlap'] = category
                    details.append(detail)
                except (KeyError, ValueError, TypeError, StopIteration):
                    raise Validation('evidence_linkage_invalid') from None
            missing = 'rule_reveal_not_recorded' if reveal is None else 'no_accepted_response_after_disclosure' if not after['accepted_count'] else None
            result.append({
                'game_type':game_type, 'game_id':game.get('game_id'), 'game_version':game.get('game_version'),
                'round_id':round_state.get('round_id'), 'round_index':round_state.get('index'),
                'status':round_state.get('status'), 'mapping_status':'unmapped', 'comparison_status':'not_comparable',
                'before':before, 'after':after, 'overlap':overlap, 'response_details':details,
                'disclosure_status':'recorded' if reveal else 'rule_reveal_not_recorded', 'missing_reason':missing,
                'rule_snapshot':deepcopy(round_state.get('rule_snapshot')),
                'event_refs': ([reveal['event_id']] if reveal else []) + before['event_refs'] + after['event_refs'],
                'limitations':['분모는 서버가 수락한 응답 수입니다. 고정된 관찰 기회 수가 아닙니다.',
                               '서버 공개 기록은 실제 읽기·이해를 보증하지 않습니다.',
                               '두 규칙에 모두 맞는 선택은 변경 규칙 사용을 구분하지 못합니다.',
                               '정오답이나 전후 차이로 적응력·동기·고집을 판단하지 않습니다.'],
            })
    return result


def _survey_refs(run, definitions, behavior_id, exclusions):
    refs = []
    behavior = next((b for b in definitions['behaviors'] if b['behavior_id']==behavior_id), {})
    for record in run.get('records', []):
        if record.get('source_type') != 'survey':
            continue
        definition = next((d for d in definitions['surveys'] if d['item_id'] == record.get('item_id')), None)
        if definition is None or definition.get('behavior_id') != behavior_id:
            continue
        excluded = {k:record.get(k) for k in ('record_id','record_version','item_id','item_version')}
        if record.get('item_version') != definition['item_version']:
            exclusions.append({**excluded,'reason':'source_version_incompatible'})
            continue
        candidates = [m for m in definitions['mappings'] if m.get('source_definition_id') == record.get('item_id') and m.get('behavior_id') == behavior_id]
        mapping = candidates[0] if len(candidates)==1 else None
        expected_kind = {'ordinal_6':'survey_self_report','paired_perspective':'paired_perspective_self_report','bipolar_slider':'bipolar_preference_self_report'}.get(definition['type'])
        if (not mapping or mapping.get('practice_review_status') != 'approved_for_practice'
                or mapping.get('validity_status') != 'provisional_unvalidated'
                or mapping.get('source_kind') != expected_kind
                or mapping.get('behavior_version') != behavior.get('behavior_version')
                or mapping.get('source_definition_version') != record.get('item_version')
                or 'practice_question_generation' not in mapping.get('permitted_uses', [])):
            exclusions.append({**excluded,'mapping_id':(mapping or {}).get('mapping_id'),'reason':'mapping_incompatible_or_unapproved'})
            continue
        data = record.get('data') or {}
        if data.get('definition_snapshot') != definition or data.get('prompt_snapshot') != definition.get('prompt'):
            exclusions.append({**excluded,'mapping_id':mapping['mapping_id'],'reason':'definition_snapshot_incompatible'})
            continue
        common = {'record_id':record['record_id'], 'record_version':record.get('record_version'),
                  'item_id':record['item_id'], 'item_version':record['item_version'], 'prompt':data.get('prompt_snapshot'),
                  'mapping_id':mapping['mapping_id'], 'mapping_version':mapping['version'],
                  'use':'comparison_allowed' if 'evidence_comparison' in mapping.get('permitted_uses', []) else 'context_only',
                  'response_snapshot':deepcopy(data)}
        branches = [('self', data.get('self', {})), ('imagined_others', data.get('imagined_others', {}))] if definition['type']=='paired_perspective' else [('self', data)]
        for perspective, branch in branches:
            status = branch.get('status', record.get('status'))
            response_text = branch.get('selected_label_snapshot')
            if definition['type']=='bipolar_slider':
                response_text = f"{data.get('left_anchor_label')} ↔ {data.get('right_anchor_label')}; 위치 {data.get('final_value')} (범위 {data.get('min')}~{data.get('max')})" if data.get('final_value') is not None else None
            refs.append({**deepcopy(common), 'status':status, 'perspective':perspective,
                         'response_text':response_text, 'missing_reason':branch.get('missing_reason'),
                         'comparison_eligible': (common['use']=='comparison_allowed' and record.get('status')=='submitted'
                            and status=='submitted' and response_text is not None
                            and (definition['type']!='paired_perspective' or all(data.get(p,{}).get('status')=='submitted' for p in ('self','imagined_others'))))})
    return refs


def _interview_refs(run, card, definitions):
    records = {r.get('data', {}).get('answer_id'):r.get('data', {}) for r in run.get('records', []) if r.get('source_type')=='typed_answer'}
    answer = records.get(card.get('answer_id'))
    if not answer or answer.get('answer_version') != card.get('answer_version'):
        raise Validation('evidence_linkage_invalid')
    question = next((q for q in definitions['questions'] if q['question_id']==card.get('question_id')), None)
    if (not question or any(card.get(key)!=question.get(key) for key in ('question_id','question_version','behavior_id'))
            or any(answer.get(key)!=card.get(key) for key in ('question_id','question_version','behavior_id'))
            or answer.get('question_mode','baseline')!='baseline'
            or answer.get('conditioned_on_prior_evidence',False) is not False
            or answer.get('disclosed_prior_information',[])!=[] or answer.get('generated_from_evidence_refs',[])!=[]):
        raise Validation('evidence_linkage_invalid')
    result = []
    for criterion, value in (card.get('criteria') or {}).items():
        spans = deepcopy(value.get('evidence_spans') or [])
        for span in spans:
            start, end = span.get('start'), span.get('end')
            if (span.get('source_id') != answer['answer_id'] or span.get('source_version') != answer['answer_version']
                    or span.get('offset_unit') != 'unicode_code_point' or type(start) is not int or type(end) is not int
                    or not (0 <= start < end <= len(answer.get('text', ''))) or answer['text'][start:end] != span.get('quote')):
                raise Validation('evidence_linkage_invalid')
        result.append({'answer_id':answer['answer_id'], 'answer_version':answer['answer_version'],
                       'question_id':card['question_id'], 'question_version':card['question_version'],
                       'criterion':criterion, 'status':value.get('status'), 'evidence_spans':spans})
    return result


def build_linkage(run, definitions):
    report = _baseline_report(run, definitions)
    snapshot = _source_snapshot(run, definitions)
    linkage_id = 'link-' + _digest(snapshot)[:24]
    observations = game_observations(run)
    links, questions = [], []
    prompts = {
        'B01':'그 응답과 관련하여 누구에게 어떤 정보를 확인했고 결정에 어떻게 반영했는지, 구체적인 경험과 이유를 설명해 주세요.',
        'B02':'그 응답과 관련하여 개인·팀 과제의 제약과 선택 가능한 대안, 실제 배분 기준과 결과를 설명해 주세요.',
        'B03':'새 정보나 규칙을 확인했을 때 무엇을 유지하거나 바꾸었는지, 기억나는 선택의 이유와 경험을 설명해 주세요.',
    }
    for card in report.get('cards', []):
        behavior = card['behavior_id']
        exclusions = []
        surveys = _survey_refs(run, definitions, behavior, exclusions)
        interview_refs = _interview_refs(run, card, definitions)
        canonical_question = next(q for q in definitions['questions'] if q['question_id']==card['question_id'])
        interview_mapping, mapping_error = interview_analysis._interview_mapping(definitions, canonical_question, use='comparison')
        provenance = card.get('extraction_provenance') or {}
        if not mapping_error and (provenance.get('mapping_id') != (interview_mapping or {}).get('mapping_id')
                or provenance.get('mapping_version') != (interview_mapping or {}).get('version')
                or provenance.get('rubric_id') != canonical_question.get('rubric_id')
                or provenance.get('rubric_version') != canonical_question.get('rubric_version')):
            mapping_error = 'extraction_mapping_version_incompatible'
        if mapping_error:
            exclusions.append({'question_id':card['question_id'], 'answer_id':card['answer_id'],
                               'mapping_id':provenance.get('mapping_id'), 'reason':mapping_error})
        disclosed, evidence_refs, parts = [], [], []
        for item in surveys:
            ref = {k:item[k] for k in ('record_id','record_version','item_id','item_version','mapping_id','mapping_version','perspective')}
            evidence_refs.append({'source_type':'survey', **ref})
            viewpoint = '내가 상상한 타인의 관점' if item['perspective']=='imagined_others' else '본인 관점'
            if item['response_text'] is not None and item['status']=='submitted':
                text = f"설문 ‘{item['prompt']}’에 {viewpoint}에서 ‘{item['response_text']}’라고 응답했습니다."
            elif item['response_text'] is not None:
                text = f"설문 ‘{item['prompt']}’의 {viewpoint} 선택 ‘{item['response_text']}’이 미완료 상태({item['status']})로 저장되어 있습니다."
            else:
                text = f"설문 ‘{item['prompt']}’은 응답 내용이 없으며 저장 상태는 {item['status']}입니다."
            parts.append(text); disclosed.append({'source_type':'survey', **ref, 'text':text})
        quoted = next((span for item in interview_refs for span in item['evidence_spans']), None)
        if mapping_error:
            quoted = None
        evidence_refs.append({'source_type':'typed_answer', 'answer_id':card['answer_id'], 'answer_version':card['answer_version'], 'question_id':card['question_id'], 'question_version':card['question_version']})
        if quoted:
            text = f"기본 답변에는 ‘{quoted['quote']}’라는 설명이 있습니다."
            parts.append(text); disclosed.append({'source_type':'typed_answer', 'span':deepcopy(quoted), 'text':text})
        if behavior == 'B03' and observations:
            for observation in observations:
                ref = {k:observation[k] for k in ('game_id','game_version','round_id','event_refs')}
                evidence_refs.append({'source_type':'rule_game', **ref})
                title = '카드' if observation['game_type']=='card' else '가위바위보'
                if observation['missing_reason']=='rule_reveal_not_recorded':
                    text = f"{title} {observation['round_index']}라운드는 변경 규칙 공개 기록이 없어 공개 후 선택을 확인할 수 없습니다."
                elif observation['missing_reason']:
                    text = f"{title} {observation['round_index']}라운드는 변경 규칙 공개 후 수락된 응답이 없습니다."
                else:
                    count=observation['after']
                    text = f"{title} {observation['round_index']}라운드는 변경 규칙 공개 후 수락 응답 {count['accepted_count']}개 중 {count['correct_count']}개가 당시 규칙에 맞았습니다."
                parts.append(text); disclosed.append({'source_type':'rule_game', **ref, 'text':text})
            parts.append('이 게임 관찰은 현실의 계획 재검토 능력을 직접 측정한 것이 아닙니다.')
        if not parts:
            parts.append('현재 저장된 기본 답변에서 선택 이유를 더 확인하는 연습입니다.')
        qid = f"followup-{linkage_id}-{behavior.lower()}"
        question = {'question_id':qid, 'question_version':'1.0.0', 'question_text':' '.join(parts+[prompts[behavior]]),
                    'behavior_id':behavior,'target_behavior_ids':[behavior], 'question_mode':'adaptive_followup',
                    'conditioned_on_prior_evidence':True,'generated_from_evidence_refs':evidence_refs,
                    'disclosed_prior_information':disclosed,'question_prompt_version':VERSION,
                    'rubric_id':card.get('rubric_id'),'rubric_version':card.get('rubric_version'),
                    'asked_criteria':['action','reasoning','result'], 'selection_reason':'저장된 자기보고와 과제 관찰의 맥락·이유 확인',
                    'trigger_rule_id':'source-linked-practice', 'trigger_rule_version':VERSION,
                    'linkage_id':linkage_id, 'source_report_id':report['report_id']}
        questions.append(question)
        eligible = any(s['comparison_eligible'] for s in surveys)
        comparison_status = 'not_comparable' if mapping_error or (exclusions and not eligible) else 'needs_clarification' if quoted and eligible else 'insufficient_evidence'
        links.append({'behavior_id':behavior,'behavior_name':card.get('behavior_name'), 'survey_refs':surveys,
                      'interview_refs':interview_refs,'comparison_status':comparison_status, 'exclusions':exclusions,
                      'summary':'원본 응답과 경험 설명을 연결해 맥락과 이유를 추가 확인합니다. 일치·모순·능력 수준을 판정하지 않습니다.',
                      'limitations':deepcopy(LIMITATIONS), 'question_id':qid})
    return {'linkage_id':linkage_id,'version':VERSION,'source_report_id':report['report_id'], 'input_snapshot':snapshot,
            'links':links,'observations':observations,'questions':questions,'limitations':deepcopy(LIMITATIONS)}


def finalize_report(run, definitions):
    if not run.get('evidence_linkage'):
        raise Conflict('evidence_linkage_required')
    if not linkage_is_current(run, definitions):
        raise Conflict('evidence_linkage_stale')
    report = deepcopy(_baseline_report(run, definitions))
    game_analysis = run.get('game_analysis')
    if game_analysis:
        from .five_game_reporting import build_five_game_report
        current = build_five_game_report(run)
        game_report = game_analysis.get('report') or {}
        if (game_report.get('source_digest') == current['source_digest'] and
                game_report.get('baseline_report_id') == report.get('report_id') and
                game_report.get('baseline_report_version') == report.get('report_version')):
            report['game_analysis'] = deepcopy(game_report)
            report['game_analysis_provenance'] = {k:game_analysis.get(k) for k in ('runtime_mode','requested_mode','provider_execution','model_id')}
    linkage = run['evidence_linkage']
    answers = [r.get('data', {}) for r in run.get('records', []) if r.get('source_type')=='typed_answer']
    superseded = {(a.get('previous_answer_version_ref') or {}).get('answer_id') for a in answers}
    followups = []
    stored_questions = {q['question_id']:q for q in run.get('questions', [])}
    for question in linkage['questions']:
        if stored_questions.get(question['question_id']) != question:
            raise Validation('evidence_linkage_invalid')
        matches = [a for a in answers if a.get('question_id')==question['question_id'] and a.get('answer_id') not in superseded]
        if len(matches)>1:
            raise Validation('evidence_linkage_invalid')
        answer = matches[0] if matches else None
        item = {key:deepcopy(question[key]) for key in ('question_id','question_version','question_text','question_mode','conditioned_on_prior_evidence','disclosed_prior_information','generated_from_evidence_refs')}
        item.update({'answer_id':None,'answer_version':None,'text':'','status':'not_answered','source_kind':'conditioned_self_report'})
        if answer:
            for field in ('question_version','question_mode','conditioned_on_prior_evidence','disclosed_prior_information','generated_from_evidence_refs'):
                if answer.get(field) != question[field]:
                    raise Validation('evidence_linkage_invalid')
            item.update({key:deepcopy(answer.get(key)) for key in ('answer_id','answer_version','text','status')})
        followups.append(item)
    report.update({'source_report_id':report['report_id'],'report_id':str(uuid4()),'status':'finalized',
                   'finalized_at':datetime.now(timezone.utc).isoformat(),'completion_policy_version':COMPLETION_POLICY_VERSION,
                   'evidence_linkage':deepcopy(linkage),'followup_answers':followups})
    report['limitations'] = list(report.get('limitations', [])) + deepcopy(LIMITATIONS)
    return report
