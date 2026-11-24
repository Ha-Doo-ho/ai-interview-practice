"""Versioned practice questionnaires, pinned at run creation.

Legacy runs intentionally keep the original six questions and response types.
New questions are self-reports, not validated ability measurements.
"""
from copy import deepcopy

WORK_VERSION = 'work-behavior-v2'
PLAN_ID = 'O-PLAN-COMPARE'
LEARNING_ID = 'O-RESULT-LEARNING'
NONRESPONSE_OPTIONS = [
    {'id':'no_experience','label':'해당 경험 없음'},
    {'id':'unsure','label':'판단하기 어려움'},
]
NCS_REFERENCE = 'https://www.ncs.go.kr/web/job/contents/3.%20직업공통능력-문제해결능력.pdf'
JOBDA_REFERENCE = 'https://www.jobda.im/info/406'

def create_snapshot(version):
    if version != WORK_VERSION:
        raise ValueError('unsupported_survey_set')
    from .content import SURVEYS, _ordinal
    items = deepcopy(SURVEYS[:3])
    for ident, prompt, topic, component, page, game in (
        (PLAN_ID, '처리 방법을 선택해야 하는 업무에서는, 방법별로 예상되는 결과를 비교한다.',
         'planning','대안 비교 및 평가',38,'path'),
        (LEARNING_ID, '비슷한 업무를 반복할 때, 여러 차례의 결과를 비교해 다음 처리 방법을 선택한다.',
         'learning','성찰 및 피드백',41,'potion'),
    ):
        item = _ordinal(ident, None, prompt)
        item['design_basis'] = {
            'topic_id':topic,'validity_status':'unvalidated_practice_item',
            'ncs':{'url':NCS_REFERENCE,'edition':'2025.12','component':component,'printed_page':page},
            'jobda':{'url':JOBDA_REFERENCE,'related_game_type':game},
            'scope':'업무 행동 자기보고; 공식 검사 문항이나 게임 수행능력 점수가 아님',
        }
        items.append(item)
    for item in items:
        item['nonresponse_options'] = deepcopy(NONRESPONSE_OPTIONS)
        item['instructions_version'] = WORK_VERSION
    return items

def survey_items(run):
    """Use the immutable questionnaire of this run, or the legacy contract."""
    snapshot = run.get('survey_definition_snapshot')
    version = run.get('survey_set_version')
    if version is not None or snapshot is not None:
        from .content import ORDERED_OPTIONS
        if (version != WORK_VERSION or not isinstance(snapshot,list) or len(snapshot)!=5
                or any(not isinstance(i,dict) for i in snapshot)
                or [i.get('item_id') for i in snapshot] != ['O-B01','O-B02','O-B03',PLAN_ID,LEARNING_ID]
                or any(i.get('type')!='ordinal_6' or i.get('ordered_options')!=ORDERED_OPTIONS
                       or i.get('nonresponse_options')!=NONRESPONSE_OPTIONS for i in snapshot)):
            raise ValueError('invalid_survey_snapshot')
        return deepcopy(snapshot)
    from .content import SURVEYS
    return deepcopy(SURVEYS)

def definitions_for_run(run, definitions):
    result = deepcopy(definitions)
    result['surveys'] = survey_items(run)
    return result
