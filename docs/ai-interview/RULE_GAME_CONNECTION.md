# 현재 두 규칙 게임의 실제 회차 저장 연결 — 2026-10-10

사용자 요청: 기존 HTML의 게임 결과와 행동 기록을 로그인한 사용자의 실제 연습 회차에 저장하고 다시 조회한다. 현재 가위바위보·카드 화면을 보존한다. 사용자가 확인한 6문항 저장·복원은 반복 구현하지 않는다. 2026-10-11 구현·자동 검증·로컬 서버 반영을 완료했으며 실제 화면 수동 확인은 대기다.

## 범위와 해석

- 가위바위보(rsp), 카드(card) 각각 본 라운드 3회, 라운드당 20초, 10초 경과 후 규칙 변경. 기존 UI를 연결한다.
- 라운드별 0점 시작, 정답 +10, 오답 -5, 하한 0. 서버가 제시 자극·규칙과 선택을 대조해 계산한다. 같은 카드의 같은 제시 단계는 한 번만 선택할 수 있다.
- 원본 시작/문제 제시/규칙 공개/선택/종료 이벤트, 정오답·실제 점수 변경·제시 내용·버전·서버 수신 시각·순번을 보존한다. UI 응답 지연이나 브라우저 전환을 능력/성향으로 해석하지 않는다.
- B01/B02/B03에 새 매핑을 활성화하지 않는다. `mapping_status=unmapped`; 기존 resource-bridge의 `run.game`, records, 집계, 완료 판정을 바꾸지 않는다. 추가 데이터는 `run.rule_games`에 둔다. 설문 강도는 이 게임 채점에 넣지 않는다.
- 게임 점수는 해당 게임 규칙의 결과다. 면접·근거 보고서 연결은 이 작업의 완료 조건이 아니다.

## 서버 계약

기존 cookie/CSRF/소유권/revision/idempotency를 그대로 사용한다. 저장소 스키마 변경 없이 Store.mutate를 통한다.

- `GET /api/rule-game-definitions` → 정의 객체: `version`, `rounds_per_game=3`, `duration_ms=20000`, `reveal_after_ms=10000`, `correct_points=10`, `incorrect_points=-5`, `score_floor=0`, `games` (`rsp`/`card`의 title/rules).
- `GET /api/runs/{id}/rule-games` → `{run, server_time}`. 소유 회차 전체의 최신 snapshot과 UTC 서버 시각. 읽기만으로 게임을 시작하거나 완료하지 않는다.
- `POST /api/runs/{id}/rule-games` → 업데이트된 전체 run. 입력: 공통 `expected_revision`, `idempotency_key`, `game_type:'rsp'|'card'`, `action:'start'|'answer'|'reveal'|'finish'|'visibility'`. start 외에는 `round_id` 필수. answer는 `stimulus_id`, `choice`(rsp는 hand, card는 card_id). visibility는 `hidden:boolean`.
- 클라이언트가 점수·정답·새 자극을 제출하지 못한다. 추가 필드 및 잘못된 타입을 거부한다. 서버에서 원본 6문항의 제출/시간초과/건너뜀 저장 여부를 검사한 뒤 게임을 시작한다.
- 두 게임 중 한 라운드만 동시에 진행할 수 있다. 완료한 라운드는 수정하지 않는다. 20초 이전 finish 및 10초 이전 reveal은 거부한다. 서버 마감 이후 answer/reveal은 거부하고 finish로 저장을 마친다. 늦게 도착한 선택을 소급 채점하지 않는다.
- initial 단계라도 reveal_due_at 이후 answer는 `409 rule_game_reveal_required`로 거부한다. 채점은 해당 라운드 scoring_snapshot만 사용한다. 공개 없이 종료되면 `quality_flags: ['rule_reveal_not_recorded']`를 남기고 revealed_at은 null로 유지한다. 화면에도 공개 기록 누락을 표시하며 가상의 공개 이벤트를 만들지 않는다.
- 모든 변경은 단일 atomic mutate. 같은 키·동일 요청은 동일 run snapshot을 반환한다. 최신 시각은 GET으로 얻는다. 삭제·다른 소유자·완료된 회차는 기존 정책으로 차단한다.

`run.rule_games` shape:

```text
{version:'1.0.0', mapping_status:'unmapped', games:{
  rsp:{game_type:'rsp', game_id:'rule-rsp', game_version:'1.0.0', rounds:[]},
  card:{game_type:'card', game_id:'rule-card', game_version:'1.0.0', rounds:[]}
}}
round = {round_id, index:1..3, practice_or_main:'main', status:'in_progress'|'completed',
  phase:'initial'|'changed'|'completed', started_at, deadline_at, reveal_due_at, revealed_at:null|ISO,
  completed_at:null|ISO, duration_ms:20000, score, correct_count, incorrect_count,
  rule:{rule_id,label}, stimulus:{stimulus_id,opponent_hand}|{stimulus_id,cards:[{card_id,value}],selected_card_ids:[]},
  events:[{event_id,sequence_no,type,server_at,elapsed_ms,...actual event facts}], quality_flags:[]}
```

게임 정의·규칙·채점 규칙의 스냅샷과 user/run/attempt 출처 필드는 서버에서 추가한다. UI는 위의 최소 필드를 사용한다.

## 화면 계약

- `AstraPractice.subscribe(listener)`는 `{user,run,ready,busy,locked}`를 전달한다. `updateRun(run)`은 현재 소유자/회차 및 최신 revision만 반영한다. `setGameLock({user_id,run_id,locked})`는 같은 회차에서 게임 진행/제출 대기 중 회차 변경을 막는다.
- 별도 `html/games.js`가 실제 게임을 담당한다. 기존 script.js의 게임용 가짜 전역은 실제 UI에서 호출하지 않는다. client.js는 유지한다.
- 시작/선택/공개/종료마다 서버가 반환한 상태를 표시한다. 전송 중 중복 입력을 잠근다. 불확실한 전송은 계정·회차별 sessionStorage에 동일 요청을 보존하며 재시도한다. 재연결 시 GET으로 최신 상태와 시각을 다시 맞춘다.
- 새로고침 시 같은 라운드·제시 내용·점수 복원. 마감 이후에는 서버 종료 저장을 수행하고, 시간을 되돌려 다시 시작하지 않는다. 계정 변경/로그아웃은 이전 화면과 늦게 도착한 응답을 차단한다.
- 게임 중 다른 화면/백그라운드로 전환한 사실은 client reported visibility로 기록한다. 사용자가 내용을 보거나 이해했다는 사실로 해석하지 않는다.
- 숨김 상태는 게임 탭 이탈 또는 document hidden의 결합이다. 상태가 실제로 바뀐 경우만 회차별 순서 대기에 보관하고 동일 요청 재시도와 함께 복원한다. 서버 이벤트 시각은 수신 시각이며 지연 중 실제 화면 전환 시각이나 반응 속도를 증명하지 않는다. 카드 정오답 색/접근성 라벨은 같은 자극·카드의 서버 선택 이벤트를 사용한다.
- 선택/완료 기록 보기에서는 실제 자극, 규칙, 선택, 정오답, 점수 변화, 서버 시각을 표시한다. 게임별 3라운드 완료 상태를 따로 표시한다.

## 파일 소유권·검증

- root: html/games.js, html/practice.js, html/script.js, html/index.html, html/style.css, tests/frontend_games.test.cjs, tests/frontend_practice.test.cjs, 통합 문서.
- backend worker: app/rule_games.py, app/main.py의 관련 import/routes/error mapping, tests/test_rule_games.py. 기존 game.py/analysis.py/store.py와 사용자 DB는 수정하지 않는다.
- explorer/reviewer: 읽기 전용. 다른 작업자의 파일을 되돌리지 않는다. 최대 동시 하위 에이전트 3개.
- TDD: UI/서버 실제 경계의 실패 재현 → 구현 → 관련 검사 → 서버 변경에 따른 전체 Python 회귀 → 독립 리뷰 → 필요한 수정·재검사.
- 합성 데이터/mock만 사용. `tools.run_checks`로 임시 SQLite/외부 호출 차단. 실제 브라우저가 없으면 blocked로 기록하며 UI 테스트를 실제 브라우저 검사로 표현하지 않는다.
- 최신 테스트 DB를 유지해 로컬 서버 반영하고 CURRENT_STATE/VERIFICATION에 실제 결과를 기록한다. live AI/운영 배포는 실행하지 않는다.
