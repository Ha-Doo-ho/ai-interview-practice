"""Export a clearly synthetic completed report from the actual API journey."""
from copy import deepcopy
import json
from test_completion_pipeline import api, journey, ok


def test_export_completed_synthetic_example(api, tmp_path):
    client, _app, _owner, _run, _clock = api
    run=journey(api)
    baseline=deepcopy(run['interview_analysis'])
    run=ok(client,run,'evidence-linkage')
    for question in run['evidence_linkage']['questions']:
        run=ok(client,run,'answers',question_id=question['question_id'],status='asked_answered',text='합성 예시입니다. 공개된 선택을 참고해 당시 규칙과 선택 이유를 다시 설명합니다. 실제 사용자 경험이 아닙니다.')
    run=ok(client,run,'interview-finalize')
    assert run['status']=='completed' and run['interview_analysis']==baseline
    assert len(run['interview_report']['followup_answers'])==3
    assert client.get(f"/api/runs/{run['run_id']}").json()['interview_report']==run['interview_report']
    artifact={'artifact_kind':'synthetic_api_completion_example','real_user_data':False,'external_ai_calls':0,
              'description':'실제 FastAPI/격리 SQLite 경로로 생성한 합성 mock 보고서. 생략한 원본 응답 상태도 그대로 보존.',
              'report':run['interview_report']}
    output=tmp_path/'completion-example.json'
    output.write_text(json.dumps(artifact,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('SYNTHETIC_EXAMPLE='+str(output))
