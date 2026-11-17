# 2026-10-13 제출 연결 구현 계획

사용자는 기존 미완료 연결을 오늘 22:00 KST까지 진행하도록 요청했다. 기존 승인 설계는 EVIDENCE_LINKAGE_EXPLANATION.md 및 PIPELINE_HANDOFF.md다. Git 저장소가 없어 worktree/commit 대신 변경 전 사본과 검사 산출물을 보존한다. 기존 사용자 DB와 별도 팀원 AI 코드는 변경하지 않는다.

## 계약과 범위

- 설문/게임/중립 면접 원본 및 기존 resource 경로 보존. 새 B01~B03 게임 매핑 활성화 없음.
- POST /api/runs/{id}/evidence-linkage: expected_revision, idempotency_key. 현재 interview_report의 검증된 기본 추출 뒤에 설문/게임 관찰을 연결하고 조건부 질문을 저장한다. 오래된 기본 보고서는 거절한다.
- 기존 POST /answers로 조건부 답변을 저장한다. 질문 mode=adaptive_followup, conditioned_on_prior_evidence=true, disclosed_prior_information 및 generated_from_evidence_refs를 서버 질문에서 보존한다.
- POST /api/runs/{id}/interview-finalize: expected_revision, idempotency_key. 설문6/게임별3/기본면접3 처리 및 최신 근거 연결을 확인한다. 후속 답변은 선택이며 미응답을 표시한다. 불변 최종 보고서와 완료 상태를 저장한다. 기존 /finalize와 구분한다.
- UI는 위 순서를 제공하고 기록 탭을 서버 소유 회차 조회/재개/삭제로 연결한다. 키/개인 DB는 전달본에서 제외한다.
- 팀원 AI는 별도 컴퓨터에 있으므로 현재 어댑터 계약과 합성 transport로 통합 검사한다. 실제 코드 확보 없이 live 통합 성공을 주장하지 않는다.

## 파일 소유권

1. root: app/evidence_linkage.py, app/interview_analysis.py, tests/test_evidence_linkage.py, tests/test_live_interview_analysis.py, 인계 문서/전달본/전체 검증.
2. backend: app/main.py, 필요한 app/store.py, tests/test_completion_pipeline.py. 원자성·소유권·멱등성·삭제·최종확정 검증.
3. frontend: html/ 아래 파일(client.js는 필요시 명시 보고), tests/frontend_*.test.cjs. 후속 질문·연결/확정·서버 기록과 오류 복구 검증.
4. reviewer: 읽기 전용 도메인/API/최종 변경 검토; artifacts/completion-20261013/REVIEW.md에 결과 작성.

## 실행과 완료 기준

- 각 담당자는 변경 전 사본, 의미 있는 실패 재현 후 구현/회귀 검사를 남긴다. 다른 담당자의 파일을 되돌리지 않는다.
- 안전 실행기: .venv/Scripts/python.exe -B -X utf8 -m tools.run_checks --output-root artifacts/completion-20261013/checks tests -q
- 화면 검사: node --test tests/frontend_*.test.cjs
- 실제 API/새 SQLite에서 설문→두 게임→기본면접→mock/주입 대역→연결→후속답변→확정→재조회→삭제 검사.
- 최종 근거는 CURRENT_STATE.md/VERIFICATION.md와 전달본 안내에 기록. 실제 브라우저/live/사람 평가는 실행 여부 별도 표시.

## 사전 충돌 검토

| 작업 | 공유 인터페이스 | 결정 |
|---|---|---|
| root/backend | build_linkage(run, definitions), finalize_report(run, definitions) | root의 순수 함수 결과를 backend가 store.mutate 안에서 저장 |
| backend/frontend | 새 두 POST와 기존 answers/list/delete | 전체 run snapshot 반환, 기존 revision/key 규칙 유지 |
| root/frontend | evidence_linkage에 observations/links/questions, final interview_report | 구조 명세를 담당자 메시지로 고정 |
| 각 작업 자체 | 기존 계약과 신규 흐름 | 원래 게임 경로/보고서 유지, 새 경로 분리 |

Ruling: 기존 설계와 사용자의 재개 승인을 적용해 추가 승인 대기 없이 구현한다. 병렬 작업은 ORCHESTRATOR.md의 명시 지침을 따르며 최대 3개, 소유 파일은 겹치지 않는다.

## 실행 원장

- Task1 root 근거 연결/기본격리: complete, 22경계 검사 포함 전체315통과.
- Task2 completion_backend API/보존: complete, 집중15통과, 전체315에 포함. 불변 기존분석 및 조건부 답변 분리.
- Task3 completion_frontend UI/기록: complete, 전체100통과. 미저장 초안확정 차단 포함.
- Task4 completion_review 독립검토: complete, 지적R1~R6 수정후 확인. 현재 검토범위 차단없음.
- Task5 root 전체 검증/로컬반영: complete, Python315/Node100, HTTP/기존회차 보존 확인. 실제 브라우저 및 팀원AI는 blocked/skipped로 분리.
- Task6 전달본 준비: complete. 소스/합성보고서/설명서 ZIP 생성·117파일 해시 검사. 압축해제본 Python62/Node100 재현통과. 최신 ZIP 해시/무결성은 인접 산출물 참조.
