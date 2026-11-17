# 현재 회차의 실제 AI·통합 근거 보고서 연결

## 목적과 확정 범위

사용자는 기존 설문·두 규칙 게임·기본 면접 답변 저장/복원을 확인하고 실제 AI 분석·근거 보고서 연결을 요청했다. 설문·게임·면접을 같은 회차에서 연결하는 기존 목적을 유지한다. 기존 비교 로직은 resource-bridge 게임용이며 현재 RPS/card에 행동 매핑을 임의로 붙이지 않는다. 합격/성격/거짓말/임의 일관성 점수는 만들지 않는다.

기존 `/analyze`, `/finalize`, `run.analysis/report_draft/report`, 원본 `runtime_mode`와 모든 원본은 보존한다. 별도 면접 분석 파생물 `run.interview_analysis`, `run.interview_report`를 추가한다. 보고서는 저장된 초안이며 회차를 completed로 바꾸지 않는다. 현재 회차를 다시 만들거나 게임을 재실행할 필요가 없어야 한다.

## API와 모듈 계약

- 인증된 GET `/api/interview-analysis-capabilities`: `{live_available, reason, model_id, max_calls_per_run, max_cost_microusd}`. 비밀 값은 절대로 응답하지 않는다.
- POST `/api/runs/{run_id}/interview-analysis`: strict `{expected_revision, idempotency_key, mode}`. `mode`는 명시적인 `live` 또는 `mock`. mock 화면 문구는 `AI 미사용 · 저장 근거`이며 의미 분석을 했다고 표시하지 않는다. 미설정 live를 자동 mock으로 바꾸지 않는다.
- 소유권/삭제/완료/버전/멱등성을 확인한다. 현재 baseline 질문 모두에 latest leaf 답변 상태가 있어야 한다. live는 nonblank asked_answered가 적어도 1개 있어야 한다. 빈 답변과 건너뜀은 AI에 보내지 않는다. 설문/게임 완료를 새 선행조건으로 두지 않는다.
- `app/interview_analysis.py`: `analysis_capabilities() -> dict`, `prepare_analysis(run, definitions, mode) -> dict`, `execute_analysis(prepared, *, before_call=None) -> dict`, `input_snapshot(run, definitions) -> dict`.
- prepared에는 서버가 계산한 `calls_required`, `cost_microusd`, `max_calls_per_run`, `max_cost_microusd`와 실행에 필요한 스냅샷/설정이 있다. 비밀키는 prepared/DB/응답에 포함하지 않는다. 반환 결과는 `{runtime_mode, requested_mode, provider_execution, model_id, input_snapshot, report}`. 생산 live는 provider_completed, 명시적 mock은 not_called, 주입된 오프라인 transport는 test_double/mock으로 표시한다.
- input_snapshot은 generation/definitions_version, 현재 질문·답변의 ID/버전, 원본 survey record refs, 원본 resource game 및 rule_games 상태 버전을 포함한다. analysis 저장 자체의 revision 증가는 결과를 stale로 만들지 않는다. API는 생성 시 입력 revision을 별도로 기록한다.

## 인용·표시 계약

- 모델에 주입하는 입력은 각 질문 원문/버전/asked_criteria/rubric/behavior와 해당 답변 원문/버전뿐이다. 설문·게임·기존 파생물·계정 정보는 주입하지 않는다.
- 모델은 7개 criterion의 status와 짧은 원문 인용 구간만 반환한다. source/question/answer/behavior 결속과 provenance는 서버가 붙인다. strict JSON schema 후 서버에서도 필수 키·상태·정수 code-point `[start,end)`·원문 일치·현재 답변 결속을 검증한다. explicit/partial에만 인용을 허용한다. 묻지 않은 criterion은 not_asked, 무응답/건너뜀은 unassessable이며 행동 부재가 아니다.
- report 기본 필드: report_id, report_version, created_at, runtime_mode, requested_mode, provider_execution, model_id, input_snapshot, limitations, cards, surveys, rule_games.
- cards는 질문 순서의 목록. card는 behavior_id, behavior_name, question_id, question_version, question_text, answer_id, answer_version, answer_status, criteria(criterion 키별 객체), comparison, practice_suggestions. criterion 객체는 criterion/status/evidence_spans/limitations/missing_reason. 인용은 source_id/source_version/start/end/quote/offset_unit.
- comparison은 기존 비교 상태/우선순위 함수를 재사용한다. 실제 매핑/관찰 기회가 없으면 insufficient_evidence; RPS/card는 별도로 mapping_status=unmapped 및 not_comparable. 게임 점수를 B01/B02/B03이나 설문 강도의 검증으로 바꾸지 않는다.
- practice_suggestions는 criterion, text, template_version, basis_refs를 갖는 고정 rubric 보완 안내이며 모델이 생성한 사실 주장과 구분한다.
- surveys는 같은 회차의 원본 survey records를 표시용으로 보존한 목록. 순서형 라벨/방향/순위/두 관점/결측 상태를 유지한다. S-B02와 R-UNMAPPED의 비교 제외를 명시한다.
- rule_games는 게임별 안전한 요약 목록이며 game_id/game_version/state_version/mapping_status/comparison_status 및 rounds를 갖는다. round는 round_id/round_index/status/score/correct_count/incorrect_count/quality_flags/event_refs 등 실제 저장 사실만 포함한다. 미공개 자극/정답을 새 보고서로 노출하지 않는다. 라운드 점수는 합격/성향 점수가 아니다.
- 기존 HTML의 88/85점, 근거 없는 강점 문구, 가짜 로컬 finalize를 실제 보고서 화면에서 제거한다. stale 보고서는 이전 입력 기준임을 알리고 새 분석을 명시적으로 요청하게 한다. 인용은 현재 기록의 해당 immutable 답변 버전으로 다시 대조한다.

## 호출·저장·실패 경계

- 기존 Responses API 어댑터와 서버 전용 키를 사용한다. API 키/허용 모델/유료 실행 flag/유한한 비용 상한/토큰별 가격 설정이 없으면 네트워크 전에 차단한다. 토큰 예산은 실제 전송할 입력+schema+instructions의 보수적 상한을 계산하며 답변을 잘라내지 않는다. 출력/timeout/retry 한도를 강제하고 자동 재시도는 0으로 둔다.
- 같은 키 동시 요청은 DB 원자적 예약으로 한 작업만 호출한다. 예약 시 회차별 호출 수·비용 상한을 영속 차감한다. 실패/timeout도 예약을 환급해 호출 예산을 우회하지 않는다. 동일 failed/running 키는 공급자를 다시 호출하지 않는다. 이미 성공한 키는 정확한 저장 응답을 재전달한다.
- 완료 시 현재 generation/revision/소유권/삭제/완료를 다시 확인한다. 실패한 결과는 보고서에 쓰지 않는다. 요청 중 삭제는 원본·파생·작업 결과의 부활을 막는다. 필요한 DB 테이블은 add-only로 만들며 기존 사용자 DB를 초기화하지 않는다.
- UI는 요청 동안 같은 회차의 답변·게임·회차 변경을 잠근다. pending request를 user/run별 sessionStorage에 보존하고 재시도는 동일 body/key이다. stale 응답/계정 변경/삭제 후 결과를 표시하지 않는다. 자동 호출/자동 재분석 없음.

## 실행 계획과 파일 소유권

Goal: 기존 회차의 설문·게임·면접 원본과 검증된 AI 인용을 같은 보고서에서 조회/복원한다.

Architecture: 기존 스택 FastAPI/SQLAlchemy/SQLite/vanilla JS 유지. 별도 AI 파생 namespace로 원본과 기존 resource 분석 계약을 보존한다. 다음 작업은 병렬로 진행하되 계약은 이 문서를 따른다.

- [x] AI worker: app/interview_analysis.py, 필요한 app/ai_provider.py 보완, tests/test_live_interview_analysis.py. 실패 검사→입력격리/정확인용/live설정/예산/출력검증→집중 통과. 기존 app/analysis.py는 수정하지 않고 pure validator/comparison을 재사용했다.
- [x] Backend worker: app/main.py, app/store.py, tests/test_interview_analysis_api.py. 원자적 호출 예약/재전달/예산 지속/새API/삭제·수정경합 검증. 원래 analyze/finalize 경계 보존.
- [x] UI worker: html/report.js, tests/frontend_report.test.cjs. Root: html/index.html/script.js/style.css/practice.js/games.js/interview.js, 결합검사/정적검사/실제 API 여정, .env.example 및 로컬 실행 안내. client.js 보존.
- [x] 독립 리뷰: 입력격리/인용-행동 결속/숫자·상태 의미/예산·중복/삭제/문구 검토 후 지적 사항 수정. 상세 실행 이력은 VERIFICATION.md.
- [x] 최종 실행: 관련 Node 87 passed, 안전 실행기 전체 Python 274 passed, 합성 같은 회차 통합 API 여정, backup 후 동일 DB 서버 재시작 및 HTTP/기존 snapshot 대조. 사용자 DB에 테스트 답변이나 mock/live 분석을 임의 제출하지 않았다.
- [ ] 별도 확인: 사용자 실제 보고서 화면, 서버 키/모델/가격/예산 설정 후 실제 AI 호출·인용 사람 검토. 현재 하네스 66 passed/2 pending_manual, 전체 완료 아님.

## 검토 초점과 현재 실행 상태

- 수정된 답변의 오래된 인용을 새 분석으로 표시하지 않기: UI/API stale 검사.
- 같은 요청의 응답 유실·동시 탭 요청: DB 예약과 exact replay, UI journal 검사.
- 유효한 다른 행동/답변의 인용 혼입: AI 출력 서버 결속 검사.
- 비어 있는 답변과 B02 not_asked: AI 호출 수/criterion 검사.
- 삭제·회차 변경 중 느린 provider 응답: API generation와 UI epoch 검사.

Ruling: 사용자가 요청한 연결 구현과 기존 프로젝트 계획 범위에서 작업을 계속한다. 새로 기능별 승인을 반복 요청하지 않는다. 실제 유료 호출은 구체적인 키·모델·비용 설정 확인과 기존 승인 범위가 충족돼야 한다. 현재는 Process/User의 key/model 환경변수와 프로젝트 .env가 확인되지 않았고, 확인한 이전 문서에 키 연결 기록도 없었다. 기존 키가 없다고 단정하지 않는다. 외부 AI 호출은 아직 실행하지 않았다.

Ruling: 프로젝트는 Git 저장소가 아닌 기존 공유 작업 폴더다. 사용자 수정/서버 회차를 보존하며 비중복 파일 소유권과 artifacts 백업으로 진행하고 커밋/가상의 worktree를 주장하지 않는다.

공식 API 확인: https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=responses (strict text.format, 추가 서버 검증 필요). 실제 호출 결과와 합성 transport 실행은 VERIFICATION.md에 구분한다.
