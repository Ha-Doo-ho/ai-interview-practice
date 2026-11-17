# 기본 면접 질문·답변의 실제 회차 연결 — 2026-10-11

사용자는 두 규칙 게임의 같은 회차 저장을 확인한 뒤 기본 면접 질문·답변 연결을 승인했다. 기존 질문/답변 API를 재사용하는 제한된 화면 연결이다. 기존 계정·설문·게임 결과와 client.js를 보존한다.

## 표시와 저장 계약

- 소유 회차의 `run.questions`에서 중립 baseline 질문만 배열 순서대로 표시한다. 현재 B01/B02/B03 질문 3개다. 임의 자기소개/지원동기 예시를 서버 질문으로 저장하지 않는다.
- 같은 회차 `GET /api/runs/{run_id}`와 `POST /api/runs/{run_id}/answers`를 사용한다. 질문별 저장/건너뜀/답변 없이 기록을 제공한다. 작성된 글을 건너뜀으로 조용히 버리지 않는다.
- 요청은 `expected_revision`, `idempotency_key`, `question_id`, `status`, `text` 및 수정 시 `replaces_answer_id`, `expected_answer_version`이다. 답변의 공백·줄바꿈·Unicode를 보존한다. HTML textarea의 브라우저 줄바꿈 정규화 이후 실제 입력 값을 전달한다. 임의 elapsed_ms를 보내지 않는다.
- `asked_answered`, `asked_no_text`, `skipped`를 구분한다. 내용의 미언급 여부나 실제 행동 부재를 이 상태로 판정하지 않는다. 수정은 새 버전으로 추가하며 이전 질문·답변 스냅샷과 연결을 그대로 둔다.
- 서버 응답을 확인한 기록만 저장 수에 포함한다. 최신 답변과 과거 수정 이력을 소유자에게 표시한다. 확정된 회차는 읽기 전용이다. 이 작업에서 분석/finalize 요청이나 AI 호출은 하지 않는다.

## 회복과 연결 경계

- `html/interview.js`는 AstraPractice의 user/run/auth/busy/locked/gameLocked 상태를 구독한다. 독립 `setInterviewLock`으로 면접 요청/재시도 중 회차 변경과 게임 쓰기를 막는다. 자기 잠금을 자기 입력 금지 조건에 다시 넣지 않는다.
- 새 모듈의 초안·원래 수정 기준·미확정 요청은 user/run별 sessionStorage에 둔다. 인증 토큰은 넣지 않는다. 새로고침 때 서버 최신 기록과 임시 입력을 구분한다.
- 불확실한 실패는 원래 payload/revision/key를 그대로 재시도한다. 과거 멱등 응답 이후 GET으로 최신 상태를 확인한다. 다른 화면의 수정과 충돌하면 최신 서버 답변과 보관된 입력을 함께 확인하고 명시적으로 이어가게 한다. 몰래 최신 버전을 덮어쓰지 않는다.
- 소유자/회차/epoch를 확인해 늦은 응답의 화면 오염을 막는다. 삭제·인증 실패 시 이전 원문 화면을 지운다. 일시적인 인증 확인 상태와 확정 로그아웃을 구분하고, 로그아웃하면 해당 사용자의 이 모듈 임시 자료를 정리한다.
- 서버에 추가 게임 선행조건을 만들지 않는다. 두 규칙 게임의 unmapped 상태나 기존 resource-bridge 완료 조건을 바꾸지 않는다. 면접 답변을 저장했다고 근거 보고서까지 완성된 것으로 표시하지 않는다.

## 파일 소유권과 검증

- root: index.html/style.css/script.js/practice.js/games.js, 실제 모듈 결합 테스트, 정적 통합 검사, 문서·로컬 서버 확인.
- interview_ui: 새 html/interview.js와 tests/frontend_interview.test.cjs.
- rule_game_backend: 새 tests/test_interview_connection.py. 서버 제품 코드는 원칙적으로 변경하지 않는다.
- game_contracts: 기존 답변 경계 읽기 전용 탐색. 후속 독립 리뷰는 읽기 전용. 동시 하위 작업자 최대 3개, 재귀 위임 없음.
- 검증은 실제 스크립트의 합성 DOM/transport, 실제 ASGI+임시 SQLite로 수행한다. 안전 Python 실행기는 `.\.venv\Scripts\python.exe -B -X utf8 -m tools.run_checks`다. 질문별 API/버전/Unicode/멱등성/소유권·삭제·확정 경계 및 같은 회차 게임 보존을 검사한다.
- 실제 브라우저 검사 가능 여부와 자동 검사/사용자 수동 확인을 구분한다. 실행 결과는 VERIFICATION.md와 CURRENT_STATE.md에 남긴다.

## 진행 체크

- [x] 기존 API·질문·수정 버전 계약 확인.
- [x] 기존 HTML 예시를 실제 질문 영역으로 교체, 모듈별 회차 잠금 연결 및 회귀 검사.
- [x] 면접 모듈의 저장·초안·복원·오류 처리와 집중 검사.
- [x] 실제 모듈 결합/ASGI 검사, 독립 리뷰, 필요한 수정.
- [x] 실행 서버 파일 대조와 사용자 테스트 안내 및 상태 기록.

최종 자동 검사: 관련 Node 73 passed, 전체 Python 236 passed(격리 SQLite/mock, 외부 호출 0). 실행 서버의 10개 정상 경로와 미인증 조회 401을 확인했다. 근거는 `artifacts/interview-connect-20261011/` 및 `artifacts/offline-checks/run-b4h4bwxa/`다. 실제 브라우저 제어 목록이 비어 직접 시각/접근성 검사는 blocked이며 사용자 면접 저장·수정·복원 확인은 pending_manual이다. 기존 서버·사용자 DB는 재시작/초기화하지 않았다.
