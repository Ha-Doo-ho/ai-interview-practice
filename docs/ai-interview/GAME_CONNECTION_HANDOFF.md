# 게임 저장 연결 재개 기록 — 2026-10-10

> 2026-10-11 갱신: 아래 중단 기록의 미해결 코드 문제는 수정·검증했고 같은 로컬 DB로 서버에 반영했다. 현재 상태는 CURRENT_STATE.md/VERIFICATION.md의 2026-10-11 항목을 따른다. 남은 것은 사용자의 실제 게임 화면 확인과 별도 후속 범위인 면접·보고서 연결이다. 아래 내용은 전날의 역사적 인계 기록이다.

사용자가 늦은 시간으로 오늘 작업 종료를 요청했다. 추가 구현·검사·서버 재시작 없이 중단했다. 다음 요청에서 이 기록을 읽고 이어서 진행한다.

## 범위와 구현 현황

- 현재 가위바위보·카드 게임을 유지하고 로그인한 사용자의 실제 서버 연습 회차에 결과와 행동 기록을 저장한다. 추가 게임 선택 질문은 필요 없다.
- 서버: `app/rule_games.py`, `app/main.py`, `tests/test_rule_games.py`. `/api/rule-game-definitions`, `/api/runs/{run_id}/rule-games` GET/POST. 서버가 자극·정답·점수·시각을 관리하고 소유권·revision·멱등성 검사를 적용한다.
- 결과는 `run.rule_games`에 별도로 저장하며 `mapping_status: unmapped`이다. 기존 resource-bridge의 `run.game`, B01/B02/B03 분석과 완료 조건을 충족한 것으로 간주하지 않는다.
- 화면: 새 `html/games.js`, `practice.js`의 회차 공유·잠금·무효화, `index.html` 버튼/기록 표시, `script.js` 이동 알림, `style.css`. `html/client.js`는 변경하지 않았다.
- 테스트: `tests/frontend_games.test.cjs` 10개, `tests/frontend_practice.test.cjs` 14개가 마지막 묶음 실행에서 통과했다. 서버 집중 테스트 24개 통과 근거는 `artifacts/offline-checks/run-90f67vco/`이다. 전체 회귀 테스트는 아직 실행하지 않았다.
- 기존 사용자 확인: 로그인과 설문 6/6 저장, 새로고침 후 동일 회차·응답 복원은 정상이다. 이를 다시 요청하지 않는다.

## 먼저 수정할 리뷰 사항

1. `app/rule_games.py`의 `_answer`: initial 단계에서 `now >= reveal_due_at`인데 reveal 요청이 도착하지 않았으면 이전 규칙 응답을 수락하고 있다. 서버에서 이 경계를 강제하고 오래된 응답을 거부하거나 전환 후 stale 자극으로 거부해야 한다. 10초 이후 reveal 없이 answer 요청 시 점수·이벤트가 잘못 추가되지 않는 회귀 검사를 추가한다. 20초 종료까지 reveal이 없었던 경우의 기록 의미도 명시한다.
2. 같은 파일의 `_answer` 채점은 `RULE_GAME_DEFINITIONS` 대신 해당 라운드의 `scoring_snapshot`을 사용해야 한다. 라운드 시작 후 전역 점수 정의를 바꿔도 시작 시점 점수가 적용되는 회귀 검사를 추가한다. 리뷰어가 snapshot=10인데 실제 score_after=99가 되는 재현을 보고했다.
3. `html/games.js`의 단일 `state.visibility`는 busy/pending 중 hidden→visible 변화를 덮어쓴다. 순서 있는 전환 대기로 보존하고 지연 요청 중 숨김·복귀가 둘 다 기록되는 검사를 추가한다.

읽기 전용 리뷰 에이전트 `/root/rule_game_review`는 사용자 종료 요청으로 중단했다. 최종 승인 리뷰가 아니다. 백엔드 작업 에이전트 `/root/rule_game_backend`는 집중 테스트 완료 상태였다. 다음 턴에서 에이전트 사용 시 당시 지침과 가용 상태를 다시 따른다.

## 수정 이후 남은 검증과 반영

- `tests/test_frontend_integration.py` 정적 자산/스크립트 순서 검사에 games.js를 포함한다.
- 필요하면 practice-refresh의 게임 진행 잠금과 응답 유실 mock의 실제 서버 커밋 후 유실 조건을 보강한다.
- 관련 Node 묶음(auth/client/survey/practice/games)을 실행하고 정확한 결과를 저장한다. 미실행 예상 통과 수를 결과로 쓰지 않는다.
- Python은 안전 실행기 `.\.venv\Scripts\python.exe -B -X utf8 -m tools.run_checks tests -q`를 사용한다. 직접 pytest로 사용자 DB를 건드리지 않는다.
- 독립 리뷰의 미해결 사항을 다시 확인하고 CURRENT_STATE.md, VERIFICATION.md, RULE_GAME_CONNECTION.md 및 관련 구현 계획/근거를 갱신한다.
- 브라우저 도구는 이전 확인에서 목록이 빈 배열이었다. 사용 가능 여부를 확인하고 불가능하면 직접 UI 검증을 했다고 주장하지 않는다.
- 그 뒤 같은 로컬 테스트 DB를 sqlite3.backup으로 백업하고 서버를 재시작한다. 이번 중단 시에는 서버 재시작을 하지 않았다. 정적 파일 변경만 기존 서버에서 노출될 수 있다.

## 로컬 실행 정보

- URL: `http://127.0.0.1:8000/frontend/index.html`.
- 마지막 확인 서버: launcher PID 34072 / server PID 34116. 종료 전 실제 명령행과 포트를 다시 확인한다.
- DB: `E:/SchoolContest/artifacts/manual-browser/preview-20261009-95ca0574/interview.db`. 기존 계정과 설문 응답을 보존한다.
- 서버 환경: `AI_LIVE_ENABLED=false`, `PAID_AI_ENABLED=false`, `COOKIE_SECURE=false`; uvicorn app.main:app, host 127.0.0.1, port 8000, no-access-log. 백그라운드 Start-Process는 `-WindowStyle Hidden`을 사용한다.
- 이전 시작 근거: `artifacts/practice-connect-20261010/STARTUP.json`. 이번 UI 백업 및 중간 증거: `artifacts/game-connect-20261010/`.
- 이번 세션의 기본 shell 호출은 helper_unknown_error로 실패했고 승인된 실행으로 읽기/검사를 수행했다. Windows 파일 읽기는 UTF-8을 명시한다.

## 사용자에게 안내할 다음 테스트

구현·검증·서버 반영을 마친 다음에만 요청한다. 기존 6/6 설문 회차를 그대로 열고 게임 탭에서 20초 라운드 실행 → 서버 저장 횟수와 실제 행동 기록 확인 → 새로고침 후 같은 기록 유지 → 나머지 라운드/카드 게임 확인 순서다. 면접·최종 보고서 연결은 아직 별도 후속 범위다.
