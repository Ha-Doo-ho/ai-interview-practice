# Verification

## 2026-11-25 — 게임 순서 및 면접 진입 결함 교차 검증

- RED / root 및 독립 테스터: 가위바위보·카드 종료 직후 약속 게임과 함께 선택 게임 입구가 활성화됐다. root는 실제 브라우저에서 도형 회전 연습 시작 → `.aptitude-playing`으로 약속 영역 가림 → 면접 입력 비활성화를 재현했다. 같은 회차의 기록으로 상태를 대조했으며 실제 제보 기기의 자동 건너뛰기 여부는 미확인이다.
- RED / 자동: `tests/frontend_five_game_handoff.test.cjs`가 전체 페이지 스크립트와 실제 appointment/town ES 모듈을 결합해 조기 선택 게임 진입을 검출했다. `tests/test_aptitude_sequence.py`는 조기 start가 409 대신 200을 반환해 실패했다. 수정 전 실패를 확인한 뒤 구현했다.
- GREEN / 관련 API / passed: 순서·소유권·멱등성·약속 30문항·면접 저장 및 과거 활성 선택 게임 중단 검사 **15 passed**, exit 0. 경로 `E:/Scoolcontest2/game-flow-fix-20261125/artifacts/green-api/run-e6e679ad799b48329c1bfc0cb297b93b/RESULTS.json`. 원래의 offline guard와 격리 합성 SQLite를 사용했다.
- GREEN / 독립 Astra 6.2 high / passed: 수정 사본 전체 frontend **146 passed / 0 failed**. 예전 활성 시도 중단, 미확인 요청 재시도, 선택 게임 완료 기록이 있는 회차의 약속 순서, 다섯 게임 완료 후 선택 3종 이용을 확인했다. 근거는 원본 프로젝트의 `artifacts/game-flow-20261125/tester-review.md`, `tester-checkout-handoff.txt`, `tester-checkout-suite.txt`다. 테스터 검사는 합성 DOM·transport이며 root의 실제 브라우저 검증과 구분한다.
- GREEN / 실제 브라우저 / passed: 키·사용자 DB를 상속하지 않는 임시 서버에서 필수 카드 종료 경계의 약속 게임 표시/선택 입구 숨김, 요일·장소·버스 각 10문항, 면접 이동과 비어 있지 않은 답변 1건의 서버 저장, 필수 완료 후 추가 3종 표시를 확인했다. 테스트 시계로 제시 대기를 가속했고 실제 UI 이벤트와 실제 API를 사용했다. 예상되는 로그인 전 `/api/me` 401과 favicon 404 외에 게임 스크립트 오류는 관찰하지 않았다.
- GREEN / root 전체 재검증 / passed: 수정 사본에서 offline guard로 전체 Python **521 passed**, exit 0, ASGI **5,421**건, guard 위반·공급자 전송·검사 시작 후 소스 변경 모두 **0**. 전체 frontend **146 passed / 0 failed**. 하네스 **66 passed / 2 pending_manual**. 근거는 `E:/Scoolcontest2/game-flow-fix-20261125/artifacts/verification-summary.json`, `artifacts/full-checks/run-0e56b7fcd239434684afc8d44c5adce2/RESULTS.json`과 `artifacts/frontend-full.txt`다.
- 환경 구분: 원본 선택 게임 JS의 OS 쓰기 거절 때문에 공개 소스만 짧은 격리 사본 `E:/Scoolcontest2/game-flow-fix-20261125`에 복사해 수정했다. 최초 중첩 경로 검사에서 SQLite unable-to-open 오류가 났고 짧은 경로의 동일 소스·동일 guard 검사로 재실행했다. 키·사용자 DB·실제 AI·운영 서버를 사용하지 않았다.

## 2026-11-25 — GitHub 기록 전 전체 재검증

- 범위: 승인한 새 5문항 업무 설문·6단계 동의형·별도 결측·기존 6문항 회차 호환·종합 입력과 화면. 실제 키가 있는 로컬 설정, 사용자 DB, 캡처, 로컬 산출물과 Word/PDF는 게시 대상에서 제외한다. 원격 기준 `main`은 `bd0d13e0f23a431c4905f3c7c3361b4ee5cbd28b`이며 그 위에 변경을 추가한다.
- 자동 / 전체 Python / passed: `.venv/Scripts/python.exe -u -B -X utf8 artifacts/work-survey-20261124/guarded_checks.py --output-root artifacts/github-publish-20261125/checks tests -q` → **519 passed**, exit 0. ASGI 요청 5,235건, guard 위반 0, 공급자 전송 시도 0, 자격증명 상속 없음, 검사 시작 이후 소스 해시 변경 없음. 기존 UUID 부모 디렉터리 wrapper와 수정하지 않은 offline guard를 사용했다.
- 자동 / 전체 frontend / passed: `node --test tests/frontend_*.test.cjs` → **141 passed / 0 failed**. 합성 DOM·transport 기반이며 실제 브라우저 육안 검사는 아니다.
- 하네스 / 미완료: **66 passed / 2 pending_manual**. 사람 평가를 자동 통과로 간주하지 않는다.
- 근거: 로컬 `artifacts/github-publish-20261125/verification-summary.json`, `checks/run-1607753f386e4e869df0b88ba6149201/RESULTS.json`, `SOURCE_HASHES.json`, `EXECUTION.json`, `harness-results.json` 및 `frontend-tests.txt`. 게시 후보는 텍스트 파일 허용 목록과 키 패턴 검사로 확인하고 변경 전후 내용을 비교했다. 로컬 `.env.example`을 읽거나 전송하지 않는다.
- 미실행: 실제 Gemini 호출·응답 품질 평가, 사용자 서버 재시작·실제 브라우저 검증, NCS/JOBDA 출처 재감사와 보고서 편집. GitHub 코드 기록은 운영 서비스 배포나 심리측정 타당성 검증과 별개다.

## 2026-11-19 — 세 활동 종합 평가 입력 및 별도 AI 요청

- 최종 인용 계보 보완 후 / **passed**: 조건부 공개 인용의 span source_id/version/start/end/offset_unit을 중복 원문 없이 보존했다. 집중 10 passed, exit 0, 13.39초. `artifacts/synthesis-20261119/targeted-final.txt`. 독립 Astra 재실행은 8게임+보충13문항 각각148~155자에서 Gemini 보수입력59,227/64,000 및 완료/권한/금지출력 검사를 확인했다(인용계보 필드 보완 전 측정).

- 자동 / 합성 자료·격리 SQLite·mock 공급자 / **passed**: `.venv/Scripts/python.exe -B -X utf8 -m pytest tests -q -p no:cacheprovider` → **511 passed**, exit 0, 212.80초. DATABASE_URL=artifacts/synthesis-20261119/full-import.db, AI_LIVE_ENABLED=false, PAID_AI_ENABLED=false. 공급자 테스트는 자체 transport 주입. 로그 `artifacts/synthesis-20261119/python-full.txt`. 기존 anyio 경고 1개.
- 자동 / 합성 DOM·mock transport / **passed**: `node --test tests/frontend*.test.cjs` → **134 passed**, exit 0. 로그 `artifacts/synthesis-20261119/frontend-full.txt`.
- 마지막 입력 압축/두 활동 비교 제한/영문 금지표현 보완 이후 자동 / **passed**: `pytest tests/test_synthesis.py tests/test_synthesis_flow.py -q -p no:cacheprovider` → **10 passed**, exit 0, 15.68초. 8종 전체 게임 완료와 보충13답변 각 한국어 100자 이상을 기본64k 종합 한도에서 Gemini 대역으로 전달했다. 실제 시도는 테스트 전용 DB/메모리에서만 생성했다.
- 포함 범위: 원척도/질문 원문/최신 답변 버전/현재 유효 후속만 수집, 8종 결측 구분, practice 분리, 실제 추가 게임 엔진, active 숨김 정보 보호, 주제별 출처 및 관찰상태 검증, 미사용 GET, 소유권·CSRF·완료회차 보호, 동일 요청 재생, 변경 후 stale, 최종 원문 고정. UI는 프롬프트 원문, 명시 요청, 자료 인용과 stale 숨김.
- 독립 / GPT-6.2 Astra high / 지적 후 수정: 12k/64k 입력 크기 문제를 종합기본한도 및 중복 제거로 보완; 과거 조건부 원문 재전송 차단; 라운드별 노출 누락/약속 실제 시간 보존; 숫자카드-WM 과잉 연결 제거; 단일활동 차이 주장 및 명시적 당락/백분위 출력 거부.
- 한계: 자유문장 전체의 의미를 자동 검증하는 것은 아니다. 실제 외부 AI 응답의 품질 및 브라우저 육안 검증은 **not run**. 새 실제 유료 호출·배포·사용자 운영 DB 직접 변경은 없다.

## 2026-11-19 — 공간 배치·반복 업무 면접 추가

- 자동 / 합성 데이터·임시 SQLite·mock / **passed**: `.venv/Scripts/python.exe -B -X utf8 -m pytest tests/test_supplemental_interview.py tests/test_frontend_integration.py tests/test_interview_analysis_api.py tests/test_evidence_linkage.py tests/test_completion_policy.py -q -p no:cacheprovider` → **53 passed**, exit 0, 9.71초. 기존 anyio DeprecationWarning 1개. DATABASE_URL을 artifacts/work-interview-20261119/test-import.db로 분리하고 AI_LIVE_ENABLED=false, PAID_AI_ENABLED=false. 로그 python-tests.txt.
- 자동 / 합성 DOM·mock transport / **passed**: `node --test tests/frontend*.test.cjs` → **133 passed**, exit 0. 로그 artifacts/work-interview-20261119/frontend-tests.txt.
- TDD / **confirmed**: 수정 전 신규 그룹 추가·내보내기 부족으로 Python 4 failed / 1 passed, 기존 WM 회차 추가 버튼/신규 그룹 표시 대상 frontend 2 failed. 수정 후 통과. 최초 시스템 Python은 fastapi 미설치로 collection 실패했고 프로젝트 .venv로 재실행했다.
- 독립 적대적 검토 / GPT-6.2 Astra high / **passed**: 기존 기본·WM 질문과 답변 보존, 반복 추가 멱등성, 새 8문항의 질문·그룹·보고서 원문 연결을 별도 메모리 실행과 코드 검토로 확인. 수정 필요한 결함 없음.
- 실제 브라우저 / **not run**: 이번 검증은 API와 합성 DOM에 한정한다. 전체 Python 500개 재실행이나 실제 화면 확인을 이번 결과로 주장하지 않는다.

## 2026-11-19 — 작업기억 선택 면접 추가

- 자동 / synthetic SQLite + mock / **passed**: 전체 `python -B -X utf8 -m pytest -q -p no:cacheprovider --harness-report artifacts/wm-interview-20261119/harness-results.json` → **500 passed**, exit 0, 85.87초. 앱 import 전에 DATABASE_URL을 별도 `artifacts/wm-interview-20261119/test-import.db`로 지정하고 AI_LIVE_ENABLED=false / PAID_AI_ENABLED=false를 적용했다. 각 API 테스트는 pytest 임시 DB를 사용한다. 기존 Starlette/anyio DeprecationWarning 1건.
- 자동 / 합성 DOM + mock transport / **passed**: `node --test tests/frontend*.test.cjs`에 해당하는 전체 파일 목록 실행 → **132 passed**, exit 0. 독립 답변 저장·복원, 기존3 진도 보존, 게임 조건부 근거가 stale이어도 선택 면접은 작성 가능, 완료 후 잠금, 보고서 확정 원문 및 HTML 이스케이프를 확인했다.
- 자동 / 네트워크·외부DB 쓰기 가드 포함 / **passed**: `python -m tools.run_checks --output-root artifacts/wm-interview-20261119/guarded tests/test_supplemental_interview.py` 경로 실행 → **4 passed**, API 요청 56, 공급자 전송 0, 가드 위반 0. 실제 실행은 runpy로 같은 모듈/인자를 실행하고 5초 진단 타이머를 걸었으며 정상 종료했다. 근거: `artifacts/wm-interview-20261119/guarded/run-l8j6xqi5/RESULTS.json`, `EXECUTION.json`, `SOURCE_HASHES.json`.
- TDD / **confirmed**: 새 문항 부재·추가 endpoint 부재, 합성 DOM의 문항 미표시·저장 버튼 부재, 보고서 미표시, 구 snapshot 오염을 수정 전 실패로 확인한 뒤 수정 후 통과했다.
- 초기 전체 검사 / **failed then fixed**: 499 passed, 캐시 버전 통일 검사 1 failed. html/index.html의 모든 로컬 asset 버전을 20261119로 통일한 뒤 전체 500 passed를 재확인했다.
- 실행기 시도 / **aborted, not counted**: 기본 output-root의 run_checks 두 실행이 무출력 장기 실행되어 해당 실행 프로세스만 중단했다. 명시 output-root의 가드 검증과 별도 DB를 지정한 전체 검사를 사용했다.
- 독립 적대적 검토 / GPT-6.2 Astra high / **resolved**: 구 분석기의 supplemental 답변 오인과 구 정적 화면의 비baseline 전체를 필수 후속으로 간주하는 문제를 발견했다. 수정 후 메모리 내 실제 분석/화면 진행 함수에서 재현되지 않으며 API 회귀 테스트도 통과했다.
- 실제 브라우저 / **blocked**: Playwright는 브라우저 세션 사용 중 오류, CUA IAB는 browser access host unavailable. 실제 화면·모바일 육안 검증을 했다고 주장하지 않는다. 전용 임시 DB를 사용하는 검증 서버는 종료했다.
- 수용 시나리오: **66 passed / 2 pending_manual**, manifest 전체 상태는 incomplete. 외부 AI 실호출, 운영 배포, 측정 타당도 검증은 미실행.

## 2026-11-17 — GitHub 공개 소스 점검

- 자동 / offline synthetic + mock / **passed**: `python -B -X utf8 -m tools.run_checks --output-root artifacts/github-publish-20261117/checks tests/test_aptitude_api.py tests/test_frontend_integration.py tests/test_baseline_configuration_guard.py -q` → **8 passed**, exit 0. 실행 근거 `artifacts/github-publish-20261117/checks/run-t13b_r_6/`. 전체 회귀를 다시 실행한 결과로 표시하지 않는다.
- 자동 + 소스 검토 / **passed**: 허용 목록의 159개 소스·테스트·문서에서 알려진 API 키/개인키 패턴 미검출. 비밀번호 대입 후보는 합성 fixture 또는 HTML 속성으로 확인했다. 공개 `.env.example`은 빈 키로 구성했다. 실제 사용자 DB, `.env`, 캡처, 로그, 가상환경, `artifacts/`는 공개 파일 목록에서 제외했다.
- **skipped**: 이번 업로드에서 실제 외부 AI 호출, 서버 재시작, 운영 배포 및 사용자 DB 변경은 실행하지 않았다. 원격 업로드 검증 결과와 파일 해시는 로컬 `artifacts/github-publish-20261117/`에 별도 보관한다.

## 2026-11-17 — 추가 게임 3종 실행 검증

- 자동 / offline synthetic + mock / **passed**: `.\.venv\Scripts\python.exe -B -X utf8 -m tools.run_checks --output-root artifacts/aptitude-20261117/final tests -q` → **495 passed**, exit 0. `artifacts/aptitude-20261117/final/run-kvjatojl/RESULTS.json` 및 `EXECUTION.json`. 공급자 호출 0, 가드 위반 0. Starlette/anyio 기존 DeprecationWarning 1건.
- 자동 / 구형 `/finalize` 활성 게임 보호 최종 수정 / **passed**: `python -B -X utf8 -m tools.run_checks --output-root artifacts/aptitude-20261117/legacy-guard tests/test_aptitude_api.py tests/test_aptitude_journey.py -q` → **11 passed**, exit 0. `.../legacy-guard/run-vx6b_7mk`. 전체 495건 실행 후 이 보호 로직과 신규 회귀 테스트 1개를 추가했으므로 전체 실행과 최종 변경 후 실행을 구분한다. 해당 신규 테스트의 수정 전 실패도 `.../legacy-guard/run-u6nlfne_`에 남아 있다.
- 자동 / frontend mock DOM / **passed**: `node --test tests/frontend_*.test.cjs` → **128 passed, 0 failed**, `artifacts/aptitude-20261117/frontend-final.txt`. 새 게임 8건 포함. 이후 문서만 변경했다.
- 자동 / real SQLite + FastAPI 전체 진행 / **passed**: `tests/test_aptitude_journey.py` 8건에서 **1,471 HTTP 요청**, 도형/길 각 10문항, 마법약 20/100문항, 연습 제외, 정오답 순서·0점 하한, 개별 문항 재조회, 동일키 재시도/새키 중복 거절, 중단→재시작, 정확한 만료 시각, 소유자 삭제와 tombstone, 실제 최종 보고서 확정/결과 저장/수정 차단을 확인했다. 별도 근거 `artifacts/aptitude-20261117/journeys/run-nzsp2m82`.
- 자동 / 공식 수용 시나리오에 연결된 실제 테스트 / **passed 66, pending_manual 2**: 전체 실행의 `harness-results.json`에 SCN-001~068 결과 기록. 사람 검토 SCN-051/053을 자동 통과로 취급하지 않는다. 새 테스트만 실행한 기록에서 기존 66건은 미선택으로 blocked이며 전체 실행 결과와 혼동하지 않는다.
- 브라우저 자동 조작 + 에이전트 화면 검토 / local AI disabled / **passed**: 별도 포트 8001·합성 SQLite `artifacts/aptitude-20261117/browser-preview.db` 사용. 실제 로그인/회차 선택, 연습과 도형/길 10문항 완료, 마법약 20문항 완료, 15초 timeout, Enter 입력, 명령 후 새로고침 복원, 중단/재시작, 보고서 추가 기록 8개, 모바일390px 가로 넘침 없음 확인. `rotation-browser.png`, `path-browser.png`, `potion-mobile-browser.png`, `results-browser.png`. 마법약 첫 브라우저 스크립트의 예상 화면 assertion 실패 이후 실제 상태를 재조회하고, 별도 새 시도로 시간 초과와 결과 흐름을 재검증했다. 실제 사용자의 테스트 완료나 심리검사 정확도 검증으로 확대하지 않는다.
- 독립 코드 검토 / AI agent / **passed after fixes**: SVG 화면 좌표 방향·회전 후 동일 크기, 한글 재료명, 마법약 피드백 사이 timeout 억제, 예측률 분모, 취소된 회전까지 누적 집계를 수정하고 회귀 검사했다. 거절 오류가 이후 정상 timeout을 막지 않도록 일반 오류 조건도 제거했다.
- 미실행: 유료 Gemini/OpenAI live 호출, 운영 배포, 사람 대상 UX/심리측정 타당성, MySQL 실제 배포 검증. 실제 사용자 DB와 키를 사용하지 않았다. 기존 외부 아이콘/폰트 CDN 로드 문제는 새 게임 기능의 의존성이 아니다.

## 2026-10-29 — Gemini 503 사용자 확인

- 사용자 보고: Google 오류 `503 ServiceUnavailable`, 트래픽 과부하. Google 공식 오류 안내와 대조했다. 오류 원문·키를 수집하지 않았고 별도 실제 재시도는 하지 않았다.

## 2026-10-29 — 반복 Gemini 5xx 원인 조사

- 관련 합성 Python 검사 53 passed (`artifacts/gemini-root-20261029/verified/run-sgmo5d8n/`), 보고서 합성 DOM 23 passed. 5xx 숫자 코드만 저장, 민감한 오류 본문 미저장, Gemini 요청 `store=false` 확인.
- 과거 5xx 정확한 번호·근본 원인 및 수정 이후 실제 Google 호출은 미확인. 사용자 회차에 추가 호출이나 한도 변경은 하지 않았다.

## 2026-10-29 — Gemini 재분석 서버 오류

- 사용자 보고 오류와 저장 상태를 읽기 전용으로 확인: 새 live 요청 실패, 이전 live/provider_completed 보고서 및 면접 3개·게임 5개 유지. 서버 정적 HTML HTTP 200. Google 개별 요청의 5xx 상세 번호·원인은 미확인, 실제 재시도 없음.

## 2026-10-29 — 회차별 AI 호출 한도 조정

- 서버 시작 PowerShell 파서 확인 및 한도 설정 15회·500000 micro-USD 확인. 면접 API/비용 경계 합성 검사 39 passed (`artifacts/ai-budget-20261029/run-xfset2za/`). 서버 재시작 및 실제 유료 재요청은 미실행이다.

## 2026-10-29 — 면접 답변 연습 안내

- 합성 DOM 전체 화면 검사 119 passed. 검증된 인용만 잘 드러난 항목에 사용, 변조·누락 인용 배제, 모든 요소 명시 시 중립 연습 표시 및 자동 AI 재요청 없음 검사 포함. 정적 자산 서버 검사 3 passed (`artifacts/report-practice-20261029/run-4goix_g5/`).
- 실제 사용자 브라우저 화면 검사는 미실행. 별도의 새로운 AI 서술형 피드백은 생성·검증하지 않았다.

## 2026-10-29 — 사용자 실제 Gemini 면접 분석

- 사용자 제공 캡처 8·9와 현재 회차의 저장 메타데이터를 읽기 전용 확인: live / provider_completed / `gemini-3.6-flash`, 성공 예약 1건. 같은 보고서의 저장 원문 대조 인용 19건 일치, 불일치 0건. 다섯 게임 항목 존재. 답변 원문은 로그로 출력하지 않았다.
- 사람 평가에 의한 인용 의미·피드백 적절성은 미실행이며 별도 게임 AI 제안 요청도 미실행이다. AI 생성 출력이 합격·성향·직무 적합도를 증명하지 않는다.

## 2026-10-29 — Gemini 사이트와 진단 설정 정렬

- Gemini 3에만 low 설정을 적용하고 Gemini 2.5 및 OpenAI 설정을 보존, 합성 인용 원인 분류, 기타 면접·게임과 정적 파일 검사: 76 passed (`artifacts/gemini-diagnosis-final-20261029/run-vvrkr2yy/`). 현재 실행 서버 재시작·실제 API 재호출은 미실행이다.

## 2026-10-29 — Gemini 인용 검증 보완

- 사용자가 합성 진단의 인용 불일치를 보고했다. 모의 검사에서 정확히 한 번 나타나는 원문 위치 복구, 잘못된 문구 거부, 모호한 문구 보존, 기존 OpenAI 검증을 확인했다. `tools.run_checks` 관련 71 passed (`artifacts/gemini-citation-20261029/final/run-0r3sz9k3/`). 실제 수정 후 재진단은 미실행.

## 2026-10-29 — Gemini 합성 응답 미완료

- 실제 사용자 보고: 3.6 모델 메타데이터 조회 성공, 합성 생성 미완료. 실제 종료 이유는 미확인.
- 변경된 독립 진단의 low 설정과 종료 사유 분리 모의 검사 포함 23 passed (`artifacts/gemini-incomplete-20261029/run-ergae6vr/`). 실제 재호출 없음. 합성 입력에 대한 보수적 추정은 34985 micro-USD이며 실제 청구와 동일하다고 보장하지 않는다.

## 2026-10-29 — 사용자 Gemini 키 확인

- 사용자 보고: 메타데이터 전용 진단이 `MODEL_HTTP_400`, `API_KEY_INVALID` 반환. 키 값이나 실제 Google 오류 본문은 수집하지 않았다. 진단 도구 실행 결과는 사용자 진술이며 별도 재호출하지 않았다.

## 2026-10-29 — Gemini 모델 조회 오류 분류

- 메타데이터 전용 모드에서 생성 요청이 발생하지 않음과 정해진 키 오류 분류만 노출함을 합성 검사. 진단·제공자 검사 21 passed (`artifacts/gemini-metadata-20261029/run-kw97xzbg/`). 실제 HTTP 400의 상세 원인은 미확인이다.

## 2026-10-29 — Gemini 직접 모델 진단 준비

- 사용자 보고: 모델 정보 조회 성공, 3.5 별칭으로 합성 생성 시 Google 5xx. 실제 원문과 정확한 상태는 수집하지 않았음.
- 진단 도구에서 3.6 직접 요청 및 상태 번호만 출력하도록 수정. 합성 테스트 19 passed (`artifacts/gemini-direct-check-20261029/run-fwagw4d0/`). 3.6 직접 실제 호출은 아직 미실행.

## 2026-10-29 — Gemini 독립 진단 준비

- 진단 합성 transport 및 Gemini/면접 서버 검사 50 passed (`artifacts/gemini-diagnose-tool-20261029/final/run-l0evru9_/`); PowerShell 구문 확인. 실제 Google 메타데이터 조회·합성 생성은 미실행이다.

## 2026-10-29 — Gemini 400 진단 정정

- Gemini API 키 오류 코드의 안전한 분류, 다른 400 원인에 대한 과도한 단정 방지: 합성 Python 검사 61 passed (`artifacts/gemini-diagnostic-20261029/run-nwrr3qxk/`), 보고서 합성 DOM 19 passed. 실제 API 재호출 없음.

## 2026-10-29 — Gemini 스키마 호환성 보완

- `tools.run_checks ... tests/test_gemini_provider.py tests/test_live_interview_analysis.py tests/test_five_game_ai.py -q`: 60 passed (`artifacts/gemini-schema-20261029/run-dsdwsnhu/`), 합성 transport. Gemini 전송 스키마에서 비지원 `maxLength`만 제거하고 원본 스키마와 서버 인용 검증은 유지하는 회귀 검사 포함.
- 실제 API 400의 구체적 원인은 미확정이며 수정 후 live 재검증은 미실행. Gemini 제공자 측 구조화 출력 필드 목록을 Google 공식 문서와 대조했다.

## 2026-10-29 — Gemini 요청 실패 진단

- Gemini HTTP 400/401/403/404/429/503 합성 오류 분류 및 민감한 오류 내용 미노출, 기존 면접 분석과 정적 자산: 48 passed (`artifacts/gemini-failure-20261029/run-73of2d40/`). 화면 코드 검사 115 passed.
- 캡처의 과거 실패 원인은 저장되지 않아 미확인. 실제 Google 재호출 및 수정된 실행 서버의 수동 검사는 미실행이다. 실패 예약의 호출/비용 한도는 보수적으로 유지된다.

## 2026-10-29 — Gemini 로컬 실행 준비

- `tools/start_gemini_local.ps1` PowerShell 파서 구문 검사 통과. 기존 서버가 8000 포트를 사용 중일 때 키 입력 전 안전하게 중단되는 것을 확인했다. 이후 자체 서버를 종료했고 포트가 비어 있는 것을 확인했다.
- `pytest tests/test_gemini_provider.py tests/test_five_game_ai.py -q`: 21 passed (합성 transport). 실제 키 입력·서버 재시작·Gemini 호출은 사용자 직접 실행 전으로 미검증이다.

## 2026-10-29 — Gemini 연결 준비

- `python -B -X utf8 -m tools.run_checks --output-root artifacts/gemini-20261029/final tests -q`: 379 passed, failed 0, guard violation 0. 합성 데이터·mock transport; Gemini 형식, 서버 검증, 설정 변경 차단 및 기존 OpenAI 경로 포함. 결과 `artifacts/gemini-20261029/final/run-ynk5hfnb/`.
- harness 66 passed, 2 pending_manual, 전체 incomplete. 프런트엔드 합성 DOM 검사 114 passed. 실제 Gemini 호출, 실제 모델과 스키마 호환성, 실제 청구 및 사람 검사는 미실행.

## 2026-10-29 — 보고서 화면 초기화 오류

- 수정 전 `node --check html/report.js`가 문법 오류를 보고했고, 보고서 UI 합성 DOM 검사 17건이 스크립트 구문 오류로 실패했다. 오류 및 통합 기능 복구 후 `node --test tests/frontend*.test.cjs`: 114 passed, failed 0. 서버 HTML은 HTTP 200 및 갱신 스크립트 참조 확인.
- 사용자 브라우저의 화면 확인 및 실제 AI 호출은 미실행. 현재 키/AI 설정과 Gemini 연결을 이 작업에서 변경하지 않았다.

## 2026-10-29 — 보고서 중복 표시 수정

- `node --test tests/frontend_report.test.cjs`: 17 passed, failed 0. 여러 제안의 문구와 서로 다른 출처를 보존하고 동일 출처는 한 번 표시하는 합성 DOM 회귀 검사 포함.
- HTTP 200 및 최신 report.js 참조 확인. 실제 브라우저에서 수정된 보고서 표시와 live AI 실행은 미검증이다.

## 2026-10-29 — 약속 게임 글자 크기

- 서버에서 갱신된 HTML과 스타일시트 HTTP 200 및 새 스타일 참조 확인. `node --test tests/frontend_appointment_games.test.cjs`: 7 passed. 실제 화면의 시각적 크기 확인은 미실행이다.

## 2026-10-29 — 게임 카드 및 진행 화면

- `node --test tests/frontend*.test.cjs`: **113 passed, failed 0**, 합성 DOM. 요일 카드 표시와 선택 전달, 선행 게임 완료 전 약속 게임 숨김, 완료된 앞 게임 영역 숨김 및 다음 게임 표시를 검사했다.
- 브라우저 연결 호스트가 사용 불가하여 실제 브라우저에서 새 요일 카드의 시각적 표시와 전체 플레이는 **미실행**이다. 서버 점수·시간·문항 기록 코드는 이 화면 변경에서 수정하지 않았다.

## 2026-10-29 — 다섯 게임 통합 검증

- 자동 서버 검사: `python -B -X utf8 -m tools.run_checks --output-root artifacts/five-game-20261029/final-verified tests -q` — **371 passed**, failed 0. 합성 입력, FastAPI와 격리 SQLite, mock/test double 사용. 외부 AI 호출 없음, guard violation 0. 결과: `artifacts/five-game-20261029/final-verified/run-fnwldbxy/`.
- harness 실제 연결 실행: **66 passed, 2 pending_manual**, failed 0. 수동 2건 때문에 overall incomplete다. `harness-results.json` 참고.
- 브라우저 화면 코드 자동 검사: `node --test tests/frontend*.test.cjs` — **110 passed**, failed 0. 가상 DOM 검사이며 실제 사람이 브라우저를 조작한 검사는 아니다.
- 합성 API 종단 검사에서 현재 회차의 두 기존 게임과 새 게임 30문항, 저장·보고서 원본 대조, 게임 분석 mock 및 test double, 최종 확정, 재조회, 다른 사용자 접근 차단과 삭제를 확인했다. 실제 외부 공급자 호출은 검증하지 않았다.
- 실행 서버 `127.0.0.1:8000`에서 HTML 및 새 게임·보고서 스크립트 HTTP 200 확인. 실제 로그인부터 종료까지의 화면 수동 검사와 live AI 검사는 **미실행**이다. 게임 AI는 검증된 조건·집계 기반의 제한된 제안이며 문항별 원본의 AI 해석은 미구현이다.

## 2026-10-29 — 다섯 게임 통합 계약 초안

| 대상 | 결과 | 범위 |
|---|---|---|
| 구현·연결 검사 | skipped | 이번 단계에서 계약 초안과 코드 조사만 수행. 새 통합 기능은 아직 구현하지 않음 |
| 실제 AI/운영 배포 | skipped | 실행하지 않음 |

## 2026-10-29 — 약속 게임 10문항 조건 확인

- 자동 / 독립 JS core / passed: `node --test appointment-memory-game/tests/core.test.mjs` 10 passed. 정답 +10, 오답·시간 초과 -5, 최저 0과 난이도별 시간 규칙 검증. 현재 테스트만으로 10문항 고정이나 5게임 통합을 검증했다고 보지 않는다.
- 자동 / 10문항 고정, 세 게임 공통 난이도, 5게임 보고서 및 AI 입력 / skipped: 사용자 요구사항 확인만 했으며 아직 미구현·미실행.
- 실제 AI 호출, 실제 브라우저 전체 여정, 사람 평가 / skipped: 실행하지 않음.

## 2026-10-29 — 약속 기억 게임 연결 가능성 점검

| 대상 | 결과 | 범위 |
|---|---|---|
| 독립 게임 core | 자동 10 passed | `node --test appointment-memory-game/tests/core.test.mjs`, `artifacts/appointment-assessment-20261029/core-tests.log`; 무작위 문제·정답·시간·점수 검증. 브라우저/서버 통합 검증 아님 |
| 전달 원본 | 6개 해시 일치 | `SOURCE_INFO.json`의 dist 5개 및 테스트 1개 SHA-256과 현재 파일 대조 |
| 5단계 연결·서버 저장·보고서 | 미구현 / 미실행 | 코드 검토 결과 기존 완료 조건은 rsp/card만 처리하고 별도 게임 결과는 브라우저 메모리에만 존재. 사용자 요청 순서로 실행하지 않음 |
| 실제 브라우저·사람 평가·AI | skipped | 실행하지 않음. 제품 코드 및 기존 사용자 DB 변경 없음 |

## 2026-10-29 — 선택형 자원 게임 추가 롤백

| 대상 | 실제 결과 | 근거와 범위 |
|---|---|---|
| 소스 원복 | passed | 백업 manifest와 기존 8개 파일 SHA-256 일치, 추가한 5개 제품/테스트/도구 파일은 제품 경로에서 제거해 artifact에 보관. DB 미수정 |
| 기존 설문·게임 UI 연결 | passed | `node --test --test-name-pattern='actual practice and game scripts share' tests/frontend_practice.test.cjs`: 합성 DOM 1 passed |
| 기존 페이지·규칙 게임 | passed | 안전 실행기 `tests/test_frontend_integration.py tests/test_rule_games.py -q`: 31 passed, 임시 DB/mock. `rollback-check/run-eikjm_tq` |
| 실제 서버·브라우저 | blocked / skipped | 8000 포트 접속 불가; 서버 시작·종료 및 실제 사용자 브라우저 재시험은 하지 않음 |
| 기존 보고서 오류·실제 AI | 미수정 / 미실행 | 종전의 보고서 표시 4건, 실제 AI 연결 검증은 별도 |

## 2026-10-28 — 자원 게임 선택형 시험 연결

| 대상 | 실제 결과 | 범위 |
|---|---|---|
| 전체 Python | 321 passed | `artifacts/resource-preview-20261028/full/run-2cefjk9_/RESULTS.json`; 임시 SQLite/합성 데이터, HTTP3416, provider0, guard위반0 |
| 수용 하네스 | 66 passed / 2 pending_manual | 같은 폴더 harness-results.json, overall incomplete |
| 전체 frontend | 109 passed / 4 failed | `artifacts/resource-preview-20261028/frontend-final.log`: 기존 보고서 문구·표시 4건 실패 유지. 신규 자원 게임 합성 DOM 13건 통과 |
| 플래그 및 API | passed | `tests/test_resource_game_preview.py`: OFF 불변, ON 4라운드, 재시도, 소유권/버전, OFF 이후 기존 확정, ON 진행 중 확정 차단 |
| 되돌리기 | passed | `tests/test_resource_preview_restore.py`: 임시 폴더 dry-run, 사용자 편집 감지 후 무변경, 새 파일 보관, DB 불변. 실제 프로젝트 원복 미실행 |
| UI 간 잠금 | passed | practice/game 실제 스크립트의 추가 게임 잠금 회귀 및 신규 UI 합성 DOM 검사. 실제 브라우저의 전체 시험 대기 |
| 라운드 사이 잠금 | 수정 전 failed → 수정 후 passed | 선택형 연습 종료 후 잠금이 남는 사례를 합성 DOM으로 재현하고 수정. `round-lock-red.log` / `round-lock-green.log`. 수정 후 관련 Python 9개 `final-check/run-m44fzs7g/` 통과 |
| 8000 서버 반영 | 미적용 | 실행 중 서버 `/api/features` 404. 프로세스 명령행 권한 거부로 임의 종료하지 않음. 새 설정으로 재시작 후 사용자가 실제 브라우저 시험 필요 |
| 실제 AI·사람 타당성 | skipped / pending_manual | 외부 호출 또는 역량 효과성 검증 없음 |

## 2026-10-28 — 자원 배분 게임 결과 미표시 진단

실행: `.venv/Scripts/python.exe -B -X utf8 -m tools.run_checks --output-root artifacts/resource-review-20261028/checks artifacts/resource-review-20261028/test_resource_review.py tests/test_disclosure_policy.py tests/test_completion_policy.py -q`.

| 대상 | 실제 결과 | 근거와 범위 |
|---|---|---|
| 기존 resource API 전체 여정 | passed | 합성 설문·연습1+본3·면접·후속답변·기존 최종화 후 `report` 카드3개 생성/GET 대조. `interview_report` 없음 확인 |
| 현재 화면에 기존 최종보고서 투입 | 미표시 재현 | `report-display-check.cjs`에 위 실제 합성 API JSON 전달. 실제 report.js + 기존 합성 DOM/transport에서 결과 공백·‘보고서 없음’·재분석 비활성 확인. Node exit0, `artifacts/resource-review-20261028/display.log`. 브라우저 실조작 아님 |
| 자원 게임 완료 후 신규 최종화 | 미통합 재현 | 신규 기본 보고서의 비교에는 resource metric 참조 존재. 게임 상세 목록에는 resource 게임 없음. `/interview-finalize`는 rsp/card 미완료로 409 `game_completion_required` |
| 고정 개인5/팀5 전략 | 재현 | 정보 창을 열지 않고 모든 라운드에서 배분 유지 시 최종 개인/팀 조건 모두 충족. 게임 정의에 대한 관찰이며 역량 타당성 검증 아님 |
| Python 진단+공개정책+완료정책 | 28 passed | `checks/run-k8vzn3rm/RESULTS.json`, HTTP578·provider전송0·guard위반0. 진단 통과를 제품 결함 수정으로 계산하지 않음 |
| 전체 수용 하네스 | blocked / 미충족 | 같은 실행의 harness-results: 0 passed / 66 blocked / 2 pending_manual. 선택 실행에 전체 수용 검사들이 포함되지 않아 전체 통과 아님 |
| 최초 진단 실행 | 27 passed / 1 failed | `checks/run-mke4oq7z/`: 합성 결과를 실행 폴더 밖에 쓰려던 진단 코드가 `write_outside_attempt` guard에 차단. 진단 출력 경로를 해당 실행의 tmp_path로 수정 후 재실행; 제품 결함으로 세지 않음 |
| 실제 브라우저·외부 AI·동료 당시 코드 | skipped | 이번에는 현재 저장소와 합성 실행만 확인. 사용자 실제 기록 수정 없음 |

## 2026-10-28 — 사용자 제공 최종 보고서 캡처 검토

| 대상 | 실제 결과 | 근거와 범위 |
|---|---|---|
| 최종 보고서 화면 도달 | passed (제공 화면 확인) | `캡처화면/1.png`에서 각 단계 완료 수와 ‘최종 보고서 · 확정됨’ 확인. 전체 조작 과정을 직접 관찰한 검사가 아님 |
| 실제 AI 분석 | blocked | ‘서버에 AI 분석 설정이 준비되지 않았습니다.’ 표시. `html/report.js`와 `app/interview_analysis.py`의 `live_not_configured` 경로 대조. 빠진 개별 설정은 미확인 |
| AI 사용 여부의 화면 표현 | failed (화면 검토) | 기본 보고서에도 AI 평가/AI 멘토 제목이 표시됨. 기존 자동 표시 검사 4건은 해결되지 않음 |
| 외부 모델 재호출·전체 자동 검사 재실행 | skipped | 이번에는 캡처와 해당 코드만 읽음. 설정/모델 호출/원본 수정 없음 |

## 2026-10-28 — 문제 1: 게임 시작 연결 복구

| 대상 | 실제 결과 | 근거와 범위 |
|---|---|---|
| 수정 전 문법/회차 검사 | failed | `node --check html/practice.js`: Unexpected token '-'. `node --test tests/frontend_practice.test.cjs`: 0 passed / 22 failed. `artifacts/issue-1-20261028/before.log` |
| 수정 후 문법 검사 | passed | `node --check html/practice.js`, exit 0 |
| 설문 저장→게임 시작→종료 저장 | passed | `node --test --test-name-pattern='actual practice and game scripts share' tests/frontend_practice.test.cjs`: 1 passed. 실제 스크립트와 합성 DOM/HTTP transport; `artifacts/issue-1-20261028/game-integration.log` |
| 전체 frontend | failed | `node --test tests/frontend_*.test.cjs`: 96 passed / 4 failed / 0 skipped. `artifacts/issue-1-20261028/after.log` |
| 전체 Python | passed | `.venv/Scripts/python.exe -B -X utf8 -m tools.run_checks --output-root artifacts/issue-1-20261028/backend tests -q`: 315 passed, exit 0. 합성 입력·임시 SQLite·외부 전송 차단. `artifacts/issue-1-20261028/backend/run-g4wdm9vm/RESULTS.json`. anyio 별칭 deprecation 경고 1건 |
| 수용 하네스 | 자동 66 passed / 사람 평가 2 pending_manual | 같은 실행 폴더의 `harness-results.json`, overall incomplete. 실제 HTTP 요청 3,239건, provider 전송/guard 위반 0건 |
| 사용자 브라우저 재시험 | skipped | 수정 후 사용자 PC 화면에서 직접 재시험한 결과는 아직 없음 |
| 실제 AI 호출/운영 배포 | skipped | 실행하지 않음 |

전체 frontend의 미해결 4건은 이번에 변경하지 않은 보고서 표시와 관련한다. 테스트를 완화하거나 전체 통과로 표시하지 않았다.

- `tests/frontend_practice.test.cjs:366` — `four actual modules save a report for the same run, guard writes and restore it without a new analysis`: 상태 문구에 `AI 미사용` 없음.
- `tests/frontend_report.test.cjs:126` — `renders grounded cards, original survey semantics and unmapped game facts while discarding invalid citations`: 기대하는 상황/역할/다른 정보/행동/이유/결과/배움 표시 불일치.
- `tests/frontend_report.test.cjs:182` — `stale and execution modes are labeled conservatively and completed runs stay read-only`: `AI 분석 완료` 대신 `AI 전문 평가 완료` 표시.
- `tests/frontend_report.test.cjs:198` — `late private responses and older cached runs cannot replace current scope or newer report`: 상태 문구에 `AI 미사용` 없음.

## 2026-10-28 — 수동 테스트 접속 준비

| 대상 | 실제 결과 | 근거와 범위 |
|---|---|---|
| 로컬 가상환경 생성 | passed | `python -m venv .venv`, exit 0. 의존성 설치 완료를 뜻하지 않음 |
| 의존성 설치 | blocked | `.venv/Scripts/python.exe -m pip install -r requirements.txt`, exit 1. 패키지 인덱스 연결 시 WinError 10013 발생 |
| 로컬 페이지 접속 | blocked | `Invoke-WebRequest http://127.0.0.1:8000/frontend/index.html`, 연결 불가. 실행 중인 서버 확인 안 됨 |
| 로그인부터 최종 보고서까지 사람 평가 | skipped | 사용자가 수행할 예정이며 이번 실행 결과는 없음 |
| 자동 회귀·수용 하네스 | skipped | 이번 요청은 접속 준비이며 테스트를 실행하지 않음. 기존 결과와 구분 |
| 실제 AI / mock 분석 | skipped | 두 분석 모드 모두 이번에 실행하지 않음. 외부 AI 호출 없음 |

## 2026-10-13 — 현재 게임의 근거 연결·후속 면접·최종 확정·서버 기록

| 대상 | 실제 결과 | 근거와 범위 |
|---|---|---|
| 전체 Python 회귀 | **315 passed**, exit0 | `artifacts/completion-20261013/final-checks/run-xde15lqp/RESULTS.json`; 실제 FastAPI/새 SQLite/합성 입력, HTTP 3,239건, 외부 transport0, guard 위반0 |
| 전체 frontend | **100 passed, 0 failed, 0 skipped** | root `node --test tests/frontend_*.test.cjs`, exec196f9b; `artifacts/completion-20261013/frontend/node-tests.log`; 합성 DOM/history/transport, 실제 브라우저 아님 |
| 새 API 전체 흐름 | passed, 전체315에 포함 | `tests/test_completion_pipeline.py`15개; mock 및 requested-live+주입 test_double, 설문→게임→기본→연결→후속→확정→재조회→삭제, 소유권/409/404/멱등키/오래된 근거 검사 |
| 근거·격리 경계 | passed, 전체315에 포함 | `tests/test_evidence_linkage.py`22개; 카드 양쪽 규칙 겹침, 미공개/공개후무응답, 원본불변, 중립 오염 거부, 자료/매핑/인용 버전과 소유권, not_comparable 제외 사유 |
| 합성 최종 보고서 | passed, 전체315에 포함 | `tests/test_completion_example.py`; 실제 API 경로의 mock 최종 보고서를 `docs/ai-interview/completion-example-20261013.json`으로 복사. 실제 사람 자료 없음 |
| 하네스 | 66 passed / 2 pending_manual, overall incomplete | 같은 실행의 harness-results.json. 기존 68시나리오와 실제 검사 등록/실행 집계. 사람평가를 자동통과로 합산하지 않음 |
| 독립 코드/도메인 검토 | 완료, 차단 지적 없음 | `artifacts/completion-20261013/REVIEW.md`; 독립 AI 검토, R1~R6 수정 확인. 전문가 타당화 아님 |
| 실행 서버·기존 DB 보존 | passed | `artifacts/completion-20261013/local/HTTP.json`, PRESERVATION.json. 페이지와9자산200·바이트일치, 미인증2경로401, 새API2개, 기존회차1 snapshot hash 일치·SQLite integrity ok |
| 실제 브라우저 | blocked | fresh cua inventory apps=[], browsers=[]; createBrowserTab('iab',...) → Browser is not available. 다른 UI 조작 경로로 우회하지 않음 |
| 실제 팀원 AI/외부 모델 | skipped | 사용자가 팀원 코드는 이 컴퓨터에 없다고 확인. 합성 transport 계약만 검사. 실제 모델 호출0이며 live/paid false로 로컬 서버 실행 |
| 전달 ZIP | passed | 117파일 해시/무결성/DB·키 제외 확인. 별도 압축 해제본에서 실제 API·필수 fixture·정적파일 Python62개 및 frontend100개 재현 통과. 기존 .venv는 인터프리터/설치 의존성만 사용 |
| MySQL/운영 배포/사람 효과성 | 미실행 | SQLite/합성 결과로 대체하지 않음 |

실제 전체 명령: `.venv/Scripts/python.exe -B -X utf8 -m tools.run_checks --output-root artifacts/completion-20261013/final-checks tests -q` 및 `node --test tests/frontend_*.test.cjs`.

실패/수정 이력: root `run-nszo6hui`13실패(신규 모듈 부재 및 중립 조건부표지 미거부), `run-t9iok8qe`6실패(매핑 적격성과 출처 바인딩), `run-d0axiorp`폐기 면접매핑1실패 후 각각 수정/통과. 기존 루브릭 오류코드 회귀는 호환 코드를 유지해 수정. 최초 전체 `run-r7o1hbvu`313통과/1실패는 stylesheet cache version 불일치였고 소스 자산 버전 통일 후 위 최종315개 통과. 실패 증거를 지우거나 합산하지 않았다.

기본면접 결과는 그대로 두고 검증 후 설문·게임 자료를 연결한다. 후속 답변은 서버가 보존한 질문/공개근거/생성참조와 대조하며, 미응답은 not_answered다. skipped/timed_out 응답을 내용이 제출된 것으로 바꾸지 않는다. 게임은 B01~B03 직접 매핑 없음과 한계를 계속 표시한다.

로컬 서버는 기존 listener 없음 확인 후 PID19040으로 새로 시작했다. 기존 DB는 앱 import 전 readonly 연결로 backup, 실행 후 무결성/회차 해시 대조. 무단 외부 전달/운영 배포/기존자료 삭제 없음. ZIP 검증 및 전달 내용은 DELIVERY_20261013.md와 PACKAGE_REPORT.md를 따른다.

전달 직전 화면의 과거 ‘근거 보고서는 아직 연결되지 않았습니다’ 안내 한 문장을 현재 흐름에 맞게 정정했다. 제품 로직 변경 없이 정적 통합3개 통과(`artifacts/completion-20261013/static-final/run-jm3qr5ea/`) 및 실행 HTTP 페이지/9자산 일치를 다시 확인했다. 압축 해제62개 재현 증거는 `artifacts/delivery-20261013/unpacked-verification/artifacts/package-checks/run-9ku_xmer/`다. 최종 ZIP 옆 해시와 패키지 검사 JSON을 기준으로 파일을 대조한다.

## 2026-10-12 — 연결 설명의 근거 검증 및 보고서 제외 사유 정정

| 검사 | 실제 결과 | 증거/범위 |
|---|---|---|
| S-B02/R-UNMAPPED 제외 사유 재현 | 2 failed, 1 passed | `artifacts/linkage-review-20261012/attempts/run-3ougmgff`; 수정 전 예상한 오류 재현, O-B02 대조 통과 |
| 같은 3개 사례 수정 후 실행 | 3 passed | `run-d_heed_8`; 실제 builder 응답·원본 불변·mock 미호출 포함 |
| 전체 Python 회귀 | 277 passed | `run-hvddkt_v`; 위 새 3개 포함. in-process FastAPI/새 SQLite/합성 transport |
| 설명 근거 합성 검사 | 4 passed | `run-bt7oftfp`; 정의 용도 목록, 카드 6/2/3/1의 양쪽 규칙 대조와 새 자극, 규칙 미공개, 공개 후 무응답 |
| 독립 도메인 검토 | 완료, 한계/미검증 사항 기록 | `artifacts/linkage-review-20261012/DOMAIN_REVIEW.md`; AI 읽기 전용 검토, 사람 타당화 아님 |
| 실제 브라우저 | blocked | Chrome 발견 후 도구가 현재 URL을 확인하지 못해 자동 조작 중단. 실제 화면 통과 증거 없음 |
| 실제 AI/팀원 어댑터·새 전체 파이프라인 | 미실행 | 코드 변경 또는 합성 통과로 해당 실행을 대신하지 않음 |
| frontend 회귀 | 이번 미실행 | HTML/JS 미변경. 이전 91개 통과는 과거 기록으로 유지 |

모든 이번 Python 실행은 `tools.run_checks --output-root artifacts/linkage-review-20261012/attempts ...`로 앱 import 전에 새 DB를 지정했다. 기존 자격 증명을 상속하지 않았고 외부 모델 transport 시도/guard 위반은 각 RESULTS에서 0이다. 금지 DB/네트워크 canary 차단은 정상 안전 장치 검사이며 위반 건수와 구분한다. 기존 사용자 DB 조회·서버 기동/재시작·실제 모델 호출은 하지 않았다. 기본 셸 격리기의 시작 오류는 승인 실행 경로와 프로젝트 자체의 안전 검사로 분리했다.

문서·해시·변경 diff·합성 예시는 위 새 증거 폴더에 보존했다. 능력 예측 정확도, 새로운 매핑 활성화, 현재 게임과 조건부 면접의 전체 제품 완료를 입증하는 검사가 아니다. `EVIDENCE_LINKAGE_EXPLANATION.md`의 현재/목표 구분을 따른다.

## 최신 검증 범위 — 2026-10-08: 10월 19일 PC 웹 시연

사용자가 완료 기준 A(게임·실제 AI·보고서를 포함한 PC 웹 시연)를 선택했다. 게임의 10/15 연결 가능일은 사용자 전달에 따른 잠정 일정이며 확정 또는 검증 결과가 아니다. 작업 목표와 지연 대안은 CURRENT_STATE.md의 최신 범위를 따른다.

| 항목 | 상태 및 근거 |
|---|---|
| 기존 PC 기본 8개 및 추가 접근 통제·건너뜀/시간 초과·통신 재시도 | 수동 / 사용자 보고 / passed 이력 유지. 이번에 재실행하지 않았으며 Codex 직접 브라우저 관찰로 바꾸지 않는다. |
| 실제 모바일 기기 점검 | skipped / 사용자 명시적 범위 제외. 기존 '모바일 1건 미완료'를 PC 시연 완료의 차단 조건에서 제외한다. 통과로 기록하지 않는다. |
| 외부 공개 배포·MySQL 운영 환경 검증 | 이번 PC 시연 범위에서 skipped. 실행 또는 통과를 주장하지 않는다. |
| 별도 게임 화면 연결·실제 AI·최종 PC 통합 여정 | 미실행 / 대기. 10/15 게임 연결일도 미확정이다. 기존 mock·옛 화면 검증을 새 통합 결과로 재사용하지 않는다. |
| SCN-051 전체 사람 평가·SCN-053 효과성 연구 | pending_manual 이력 유지, 이번 시연 마감의 완료 조건에서는 후속으로 둔다. 인용·수치·과장 여부의 최소 사람 검토는 실제 보고서로 수행해야 한다. |

이번에는 위 범위·일정 기록을 갱신하고 문서 저장 내용을 확인했다. 제품 코드 수정, DB 변경, 자동 회귀 재실행, 실제 AI 호출, 게임 통합 실행, 운영 배포는 하지 않았다. 기존 자동 검사와 읽기 전용 자료 대조 결과는 아래 이력을 보존한다. 전체 제품 또는 실제 AI 검증 완료 선언이 아니다.

이하 이전 기록의 모바일 미완료 조건은 위 사용자 결정으로 대체한다.

## 최신 상태 — 2026-10-08 PC 수동 점검 종료 및 저장 자료 대조 정리

- 사용자 보고 기준으로 PC 수동 점검을 마쳤다. 기본 8개 항목 외에 다른 계정의 기존 회차 URL 조회 거절, 5개 설문 건너뜀+마지막 문항 시간 초과 후 6/6, 통신 실패 시 답변 입력 유지와 연결 복구 후 원래 요청 재시도·저장 표시를 확인했다. Codex 직접 브라우저 관찰 결과와 구분한다.
- 자동 / 읽기 전용 SQLite 저장 자료 대조: 설문 6개, 기본 질문 3개의 답변 버전 10개, 과거 저장 응답 스냅샷 16개를 검사했다. 과거 스냅샷과 현재 원본 레코드의 136개 비교가 일치했고 정의·라벨·관점·방향·순위 및 답변 이전 버전 연결 검사도 통과했다.
- 최초 assertion 174 passed / 1 failed의 원인은 검사기 가정 오류다. 숫자 order를 최종 선택 목록으로 오해했다. UI의 select/move/remove 의미로 이력을 재생해 최종 순위를 대조하도록 정정했다. 합성 정상 예와 잘못된 순서·순번·rank 거절 확인을 포함한 재실행은 assertion 179 passed / 0 failed다. pytest 테스트 개수나 하네스 통과 수가 아니다.
- 증거: `artifacts/manual-browser/run-20261007-212826-f2c9a079/record-audit-corrected-20261008-222111/RESULTS.json`, `CORRECTION.json`, `verify_saved_records.py`, stdout/stderr. 최초 실패 artifact는 그대로 보존했다. 정정 실행기의 첫 시도는 PowerShell의 -c 인용 전달 때문에 Python 구문 분석에서 실패했으며 UTF-8 코드 전달로 재시도했다. 앱 소스·기존 DB는 수정하지 않았다.
- 대조 범위는 저장 당시 서버 응답과 현재 저장본 사이의 원본 보존 및 정의·버전 일치다. 독립적으로 녹화한 최초 브라우저 입력 대조나 AI 정확도 검증은 아니다. 전체 자동 회귀·live AI·게임 화면·운영 배포는 이번 미실행이다.
- 현재 합의한 1단계 화면 점검 범위에서 남은 사용자 확인은 **실제 모바일 기기의 화면·조작 확인 1건**이다. 연결 준비와 실제 확인 전까지 1단계 전체 완료로 표시하지 않는다. 현재 서버는 127.0.0.1 바인딩이므로 휴대폰에서 같은 주소만 입력하면 접속되지 않는다. 게임 연결과 전체 보고서 여정은 다음 단계의 별도 범위다.
- 기존 테스트 DB와 10월 7일 회차를 보존한다. 재개 DB·명령 및 이전 결과는 아래 이력을 참고한다.


## 2026-10-07 — 사용자 수동 점검 마감 및 저장 상태 확인

- **수동 / 사용자 보고 / passed:** 회원가입·로그인·새 회차 진입, 설문 6개 저장 표시 및 6/6, 기본 면접 3개 저장·수정 표시 및 3/3, 새로고침 후 첫 설문 저장 상태, 재로그인·기록 재개 후 진행률과 수정 내용 유지, 미저장 답변 이동 확인·취소 후 내용 유지. 마지막 보고로 좁힌 데스크톱 창에서 겹침·잘림 없음과 원활한 키보드 조작을 추가했다.
- 이 결과는 사용자의 채팅 보고이며 Codex 직접 브라우저 관찰이 아니다. 실제 모바일, 전체 접근성, 저장 원문 정확성 또는 이전 버전 내용 일치의 검증으로 확대하지 않는다.
- **자동 / 로컬 SQLite 읽기 전용 / passed:** 테스트 DB에 삭제되지 않은 in_progress 회차 1개, 설문 레코드 6개, 기본 질문 3개의 답변 기록, 기본 답변 버전 레코드 10개 확인. `PRAGMA quick_check`는 `ok`. 답변 원문·비밀번호·세션 토큰은 출력하지 않았다.
- 대상: `artifacts/manual-browser/run-20261007-212826-f2c9a079/interview.db`. 앱을 import하지 않고 Python sqlite3의 `mode=ro`로 접속해 스냅샷의 기록 종류·질문 수·버전 레코드 수만 집계했다. [메타데이터 결과](../../artifacts/manual-browser/run-20261007-212826-f2c9a079/SESSION_END_CHECK.json). DB 자체와 WAL/SHM을 보존하며, 서버 재시작 후 재조회 검사는 이번에 수행하지 않았다.
- **미실행 / 대기:** 회차 삭제·삭제 후 접근, 추가 계정의 화면 접근 통제, 원본 선택값 및 이전 버전 원문 대조, 추가 오류·재시도·타이머, 게임 화면·전체 보고서 흐름·live AI·MySQL·운영·SCN-051/053. 전체 자동 회귀를 재실행하지 않았다.
- 사용자 요청으로 오늘 테스트를 종료한다. 같은 DB로 재개하는 명령과 서버 상태는 CURRENT_STATE.md 최신 인계에 기록했다.

## 2026-10-04 새 Astra HTML 연결 검사

- 실제 실행: 격리 실행기 `tools.run_checks ... tests` → **202 passed**, in-process HTTP 2,125개. [실행 결과](frontend-integration/20261004-214259-KST/attempts/run-lt75uro3/RESULTS.json).
- JavaScript: **13 passed** — 요청·설문·답변·단계·인용 10개, DOM 대역 화면 이동 3개. [개별 결과](frontend-integration/20261004-214259-KST/JS_RESULTS.tap).
- 신규 실제 API 여정: JS helper가 만든 합성 payload 저장, 이전/수정 답변 보존, 본게임 이전 분석 거절, 본게임1 이후 중간 분석, 미완료 확정 거절, 전체 완료 확정, 재로그인 재개, 다른 계정 접근/삭제 차단, 본인 삭제.
- 앱 import 전 새 임시 DB 적용, 자격 증명 상속 없음, 실제 모델 전송 시도 0, 보호 위반 0. [실행 환경](frontend-integration/20261004-214259-KST/attempts/run-lt75uro3/EXECUTION.json).
- 시나리오: 자동 66 passed, 사람 평가 SCN-051/053 2 pending_manual. 전체 효과성 검증 완료가 아니다.
- **미실행:** 새 HTML의 실제 브라우저/시각/키보드 검사(연결 가능한 브라우저 없음), 새 게임 프론트 통합, 실제 AI/MySQL/배포. 과거 화면 통과를 새 화면에 귀속하지 않는다.
- [검증 상세 및 RED→GREEN](frontend-integration/20261004-214259-KST/VALIDATION.md), [독립 검토 및 수정](frontend-integration/20261004-214259-KST/REVIEW.md), [전후 보존 SHA](frontend-integration/20261004-214259-KST/PRESERVATION_AFTER.json).

아래 항목은 당시 버전의 검증 이력이다.

---

## 2026-09-17 current verification

The executable application is a local **mock** text MVP. Automated success is not human validation, live-provider validation, or a deployment approval.

| Check | Mode / environment | Actual result |
| --- | --- | --- |
| Full pytest suite | Automatic, synthetic data, mock, temporary SQLite databases | **passed: 78 tests in 7.52 s** |
| Acceptance harness | Actual pytest executions mapped to original 68 cases | **66 passed, 0 failed, 0 blocked, 0 skipped; 2 pending_manual** |
| JavaScript syntax | `node --check app/static/app.js` | **passed**, exit 0 |
| Python compilation | `python -m compileall -q app tests tools` | **passed**, exit 0 |
| Human report review SCN-051 | Independent human evaluation | **pending_manual** |
| Effectiveness study SCN-053 | Independent human study | **pending_manual** |
| MySQL migration and concurrency | Dedicated MySQL server | **not run**; no verified test server |
| Paid/live provider | External AI | **not run**; app remains mock |
| Operational deployment | External service | **not run** |

Command: `.venv/Scripts/python.exe -X utf8 -m pytest -q --tb=short --harness-report docs/ai-interview/harness-results.json`.
The [machine-readable result](harness-results.json) deliberately retains `overall_status: incomplete` because human evaluations remain pending. Passing tests count executed checks, not proven psychological accuracy or exhaustive production safety.

### Browser evidence

On 2026-09-16 the actual local UI completed all six survey items (four input formats), one practice and three main game rounds, three baseline answers, three conditioned followups and a saved report. The report contained three baseline and three conditioned lineage references. Confirmed untouched slider submission remained `0` with explicit confirmation; top-k reordering was saved as growth/autonomy/stability. Korean/emoji code-point slicing returned the exact emoji. Original-record disclosure opened using the keyboard.

Desktop 1440 px and mobile 390 px screenshots were inspected; document width did not exceed the viewport. Evidence: [desktop](browser-report-desktop.png), [mobile](browser-report-mobile.png). Final report page console check showed zero errors/warnings at that checkpoint. Initial unauthenticated 401 and deliberate deleted-record 404 requests are expected and must not be mistaken for application crashes.

The first browser development attempt used an obsolete synthetic game snapshot and encountered `KeyError: state_version`. A fresh synthetic DB was used for the successful full journey. No migration of that obsolete test snapshot is claimed. A fast information request/input sequence exposed an input-reset risk; input controls were subsequently locked during the request. The focused resumption regression checks that final fix separately.

On 2026-09-17, a dedicated `artifacts/browser/resume-0917.db` was used. The deleted synthetic run `e6a8f4fe-08fa-447f-a908-b0b0b2db2c80` was reopened through its old UI address: the page displayed the unavailable-record message, its API returned **404**, and the cached game controls were absent. This closes the deletion check interrupted during the preceding session. Browser modal handling returned before the original function's final result, so a separate explicit assertion verified the post-deletion state.

The first resumed setup script waited for a survey heading to change even though consecutive ordinal items share that heading. That automation timeout was corrected to wait for the actual item sequence. The subsequent synthetic setup completed. It was a test synchronization issue, not an app change.

The focused game regression **passed** after deliberately holding the information request: both the allocation input and submit button were disabled while pending; after release, initial personal allocation **4**, final allocation **5**, and `changed_after_evidence` were all persisted. The run was `ca618337-81f9-4f2d-956f-e648397342ad`. [Resumption results](browser-resume-results.json) records the actual returned values and the separate deletion assertions. The application implementation was preserved in this resumption; additions were browser regression scripts, verification artifacts and documentation.

### Independent code review and regressions

Read-only domain reviewer `/root/domain_review_resume` approved 11 source-specific mappings for practice use on 2026-09-16; all remain `provisional_unvalidated`. This is an AI review, not SCN-051 human evaluation. Its final review at 14:25:34 UTC independently ran 73 relevant tests successfully.

Reproduced and fixed: deletion racing cache insertion/job completion; stale analysis finalized after new baseline answers; missing refreshed baseline caches; server-side game deadlines; attempt ownership; opportunities counted before they existed; incomplete survey evidence entering comparisons; actual rubric version mismatch; UI retaining a deleted run in memory. Regression tests include actual SQLite SQLAlchemy statement interleavings; MySQL concurrency was not exercised.

### Reproducible artifacts

- [Synthetic report with original records and lineage](sample-report.json), generated through the tested API journey. Contains synthetic data only.
- [Scenario JSON schema](scenario-schema.json), generated from the validated harness models.
- `python -m tools.generate_sample` regenerates both artifacts locally with mock data and no external AI calls. The first Windows attempt failed on an open SQLite handle; explicit engine disposal fixed it and the subsequent generation succeeded.
- Focused game browser automation: `tools/browser_resume_setup.js`, then `tools/browser_resume_regression.js`, using the Playwright MCP function runner against the dedicated test server. These are browser-tool function bodies, not Node CLI entry points. Use the synthetic test database only: setup creates an account when logged out or a new practice run when already logged in. Deletion is verified separately through the visible list/delete confirmation and a repeated lookup of the old URL.

---

## 2026-09-16 resume baseline

- Automatic / local SQLite planned / mock: `.venv/Scripts/python.exe -X utf8 -m pytest -q` — **failed**, collection error `ModuleNotFoundError: app.content`, 1 error in 0.73 s. Existing backend implementation was not present after interruption.
- Sandbox shell execution — **passed** for current file queries and test launch. User supplied Doctor output has 0 fail; this is environment evidence, not application validation.
- Git — no repository; `git rev-parse --show-toplevel` returned not a Git repository.
- Browser journey — **not run** at this checkpoint.
- MySQL — **blocked**, no verified local server/test database yet; SQLite tests will not be represented as MySQL tests.
- Paid live AI — **blocked**, no paid app call authorized or performed. Deployment — **skipped**, outside current local implementation scope.
- SCN-051 human review and SCN-053 effectiveness study — **pending_manual**, never counted as automated passes.

The section above is the historical resume baseline, not the present application status. The collection error was resolved by the implementation now verified above.


## 명령 1 근거 대조 — 20260918-183707-KST

이번 범위는 문서 준비·기존 증거 대조다. [실행 폴더](traceability-followup/20260918-183707-KST/README.md), [입력 manifest](traceability-followup/20260918-183707-KST/SOURCE_MANIFEST.json), [H-01/H-03 개별 판정](traceability-followup/20260918-183707-KST/TASK_RESULTS/01_EVIDENCE.json)을 참조한다. 명령 2~6은 미시작이다.

- H-01: JSON 6개·Python 4개 모두 존재하며 SHA를 기록하고 원본 사본을 보존했다. 과거 스크립트는 미실행이다.
- H-03: 저장된 과거 79개 시작/종료 SHA와 출력 14개 SHA가 일치한다. 작업용 CSV 3개는 보고서 §9와 일치한다. 현재 파일 중 과거 79개 기준과 다른 것은 검토 로그 1개이며 버전 4 후보로 분리했다.
- 보류: 정확한 당시 입력 검토 로그 원본 바이트 대조, CODEX_FOLLOWUP_COMMANDS_20260918.md 원본 확인. 해당 자료 미발견을 이유로 독립 CSV 작업을 차단하지 않는다.
- 자동 검사: 파일 역할·존재·SHA·복사·포인터·이번 전후 보존 검사만 실행했다. 실제 passed/failed 수는 [PREPARATION_VERIFICATION.json](traceability-followup/20260918-183707-KST/evidence/current/PREPARATION_VERIFICATION.json)에 기록한다. 과거 30/103개 검사는 이번에 재실행하지 않았다.
- 실행 환경: 로컬 파일 검사, mock/live 모델 실행 없음. 전체 앱 테스트·서버·DB 조회·실제 모델 호출·배포는 이번 범위에서 skipped(미실행)다. 사람 평가는 skipped(미실행)이며 정확도·효과성 주장은 없다. AI 미연동은 현재 단계이며 실패가 아니다.
- 제품 구현 상태: 이번 미변경. 앱·설정·기존 DB·과거 결과 폴더는 변경하지 않았다. Git 저장소가 없어 commit 상태 대신 파일별 SHA와 코드 집합 SHA를 기록했다.

이 기록은 위 과거 검증 결과를 이번 실행 결과로 승격하지 않는다.


## 2026-09-20 — AI 미연동 백엔드 명령 1/4

[기준선과 남은 조건](backend-readiness/20260920-003025-KST/BASELINE.md), [1-A/B/C 개별 판정](backend-readiness/20260920-003025-KST/TASK_RESULTS/01.json), [실제 검사 결과](backend-readiness/20260920-003025-KST/VALIDATION_RESULTS.json).

- 범위: 현재 API·호출 경로·기존 검사 식별 및 앱 import 전 DB 격리 확인. 1-A/B/C는 이 범위에서 충족이다. 명령 2는 미시작이며 백엔드 전체 준비 완료 판정은 아니다.
- 자동/로컬 SQLite/mock: 격리 검사 8개 통과. 실제 새 DB 2개 연결·스키마 확인, API 등록 15개 대조, 테스트 78개 수집. 테스트 본문 실행 0개이며 78개 기능 통과로 집계하지 않는다.
- 실행기 초기 실패 4회는 결과 폴더에 보존했다. NUL 로그 장치 및 Windows OS 정보 조회 차단을 보완한 실행이 통과했다. 앱 결함 수정은 없다.
- 기존 앱·프런트·테스트·설정 및 기존 DB 파일 40개의 전후 SHA가 일치한다. 기존 DB는 SQL로 열지 않았다. 새 결과 폴더와 이 상태/검증 문서의 추기만 작성했다.
- 서버/브라우저/MySQL/실제 AI/사람 평가는 이번 미실행이다. AI 미연동은 전제이며 실패가 아니다. 프런트는 별도 담당자가 개발 중이고 API/origin 합의는 아직 확인되지 않았다.
- 기존 PKG-01/02는 최신 후속 기록상 충족. H-03/C-05의 역사적 원본 확인은 국소 보류로 유지한다. 입력 명령 파일은 최신 보완 기록에 존재하므로 과거의 파일 미발견 상태를 현재로 확대하지 않는다.


## 2026-09-20 — AI 제외 프런트 연동 전 추가 검토

[검토 결과와 잔여 작업](preintegration-review/20260920-201656-KST/REVIEW.md), [개별 항목](preintegration-review/20260920-201656-KST/FINDINGS.json), [합성 함수 검사](preintegration-review/20260920-201656-KST/PROBE_RESULTS.json).

- 프로젝트 파일 627개 목록/해시 및 595개 텍스트 형식 확인. 설치 의존성·캐시 제외; DB 관련 22개는 바이트 해시만 검사. 전수 형식 검사가 모든 동작의 무결함을 증명하지 않는다.
- 현재 소스/설정 28개와 명령 1의 고정 해시 일치. 기존 산출물 64개도 영수증 해시 일치. 최신 검토자 입력은 review/AI_INTERVIEW_REVIEW_LOG.md 버전 16/26절이다.
- 자동/합성/함수 검사: 정상 대조 1개 passed, 기대 검증과 다른 사례 7개 failed(잘못된 자료형 6종+오류 코드 전달 1종), 기존 현상 관찰 2개. 프로세스 정상 종료를 이 실패들의 통과로 세지 않는다. 타입 오류와 deadline 오류 전달 보완 필요.
- 실제 HTTP/Store/DB/전체 pytest/서버/브라우저/MySQL/live AI/사람 평가 미실행. API 경로 함수 일부는 AST로 추출하고 인증·본문 helper를 대체했으므로 라우터·인증·DB 검사로 집계하지 않는다.
- API 계약, 안전한 검증 안내, 실제 API/저장 회귀, 정책/origin 합의, 인계가 남았다. AI 미연동은 결함 아님. 프런트는 별도 담당이며 새 UI는 이 저장소에서 식별되지 않았다.
- 앱/프런트/설정/기존 테스트/기존 DB/과거 결과는 미변경. 검토 파일과 CURRENT_STATE/VERIFICATION 추기만 작성. 기존 명령 2~4는 시작하지 않았다.


## 2026-09-20 — 첫 필수 보완: PRV-01/03

[변경·실행 근거](backend-readiness/20260920-204132-KST-fixes/README.md), [개별 결과](backend-readiness/20260920-204132-KST-fixes/TASK_RESULTS.json).

- 사용자 마감 범위: 2026-09-24까지 AI/실제 새 프런트 연결을 제외한 백엔드 준비·검증·인계. 새 UI 전달 자체를 이번 완료 조건으로 두지 않는다.
- PRV-01: 잘못된 JSON 자료형을 먼저 검사하도록 main/game/survey 최소 수정. 실제 API 13개 사례가 수정 전 500에서 수정 후 422/validation_error로 바뀌었고, 새 DB 세션으로 전체 테이블 무변경을 확인했다.
- PRV-03: tools.run_checks로 app import 전 DB/mock 격리 및 외부 통신 차단. README/실행 안내와 샘플 출력 경로 보완. 직접 샘플 진입은 app import 전에 거절한다.
- 자동/실제 in-process FastAPI·Store·임시 SQLite/mock: 전체 회귀 **91 passed**, HTTP 179건 계측. 하네스 **66 passed / 2 pending_manual**. 별도 샘플 생성 HTTP 40건 성공. 외부 모델 transport 시도/가드 위반 없음. 서버·브라우저·MySQL·live AI·사람 평가는 미실행.
- 기존 DB/프런트/과거 결과는 보존. 현재 소스가 과거 명령1 SHA와 달라졌으므로 과거 입력 목록을 갱신하지 않는다.
- API 계약, deadline 오류 코드 정리, 추가 부작용/경계 검사, 정책/목표 DB 범위와 최종 인계가 남았다. 91개 통과를 전체 준비 완료나 사람 평가 완료로 확대하지 않는다.


## 2026-09-24 — AI 미연동 백엔드 명령 2/4

[현재 API 계약](backend-readiness/20260920-003025-KST/API_CONTRACT.md), [미실행 시나리오](backend-readiness/20260920-003025-KST/API_SCENARIOS.json), [2-A/B/C 개별 결과](backend-readiness/20260920-003025-KST/TASK_RESULTS/02.json), [추가 입력·변경 근거 안내](backend-readiness/20260920-003025-KST/command02-20260924/README.md).

- 명령2 문서 산출물 작성: API15개의 인증·요청/응답·오류·버전·멱등 규칙, 정상/예외 흐름, 현재 정책과 미결 선택, 81개 선언형 검증 시나리오. 새로운 API 시나리오는 전부 미실행이며 actual=null이다. 명령3은 시작하지 않았다.
- 최신 검토자 입력은 review/AI_INTERVIEW_REVIEW_LOG.md 버전17·27절이다. 정확한 경로·SHA·사본을 command02-20260924/SOURCE_MANIFEST.json에 추가했다. 명령1 BASELINE/SOURCE_MANIFEST/inputs/01.json은 당시 기준으로 보존한다.
- 이미 수정한 입력 오류는 main/game/survey 3파일의 전후 SHA·diff·13개 문제 입력을 별도로 기록했다. 과거 red13실패→green13통과·전체91통과의 원본 결과와 소스 SHA를 연결했으며, 전체 회귀 당시 기록된 소스는 현재와 일치한다. 이번에 91개를 재실행하거나 새81개 시나리오 통과로 집계하지 않았다.
- deadline_not_reached의 현행 정적 경로는 GameValidation 발생→domain_error에서 validation_error로 변환→HTTP422다. 내부409 매핑을 목표 계약의 독립 근거로 사용하지 않는다. 마감 전 거절 시 snapshot/revision/이벤트/기록/멱등 등 업무 상태 유지와 마감 도달·초과의 timeout 저장 처리를 구분했다.
- 이번 자동 실행은 문서·JSON·AST·파일 해시 검사뿐이다. 결과는 command02-20260924/DOCUMENT_VALIDATION_RESULTS.json. 기존 고정 보호파일223개의 전후 해시가 일치했다. 기존 DB는 SQL로 열지 않았으며 바이트 해시만 대조했다. 앱·프론트·설정·과거 결과 변경은 없다.
- 남은 조건: 명령3의 실제 HTTP/새 DB 세션 검증, timeout 목표 HTTP/code 선택과 필요한 최소 변경·회귀, 분석 실패/긴key의 job 쓰기 확인, 완료·중간 분석·정보 공개·입력 범위 및 프론트 origin 합의, 이후 명령4 인계. 실제 AI·새 UI 통합·MySQL·배포·사람 평가는 이번 미실행/별도 범위다.
- 프론트는 별도 담당이 개발하며 실제 AI는 미연동이다. H-03/C-05의 역사적 원본 확인 보류는 유지한다. 문서 산출물 충족을 제품 또는 백엔드 준비 전체 완료로 확대하지 않는다.


## 2026-09-24 — 명령2 시나리오 보완 및 명령3 우선 항목 부분 실행

[변경·검증·잔여 조건](backend-readiness/20260920-003025-KST/priority-fixes/20260924-233409-KST/README.md), [명령3 부분 결과](backend-readiness/20260920-003025-KST/TASK_RESULTS/03.json).

- 먼저 질문 생성 뒤 적격 기회가0→1로 달라지고 같은ID의 새 질문 문구가 실제 달라지는 시나리오를 작성했다. 기존 원문·버전·공개정보·답변 연결 및 기본 추출 보존을 검사했다.
- 실제 HTTP/Store/새 SQLite: 수정 전8개 중6실패/2통과, 최소 수정 후8통과. 기존 검사를 포함한 전체99통과. 하네스66통과/사람평가2대기이며 후자를 완료로 바꾸지 않았다.
- main.py는 기존128자 키 한도를 DB 접근 전에 검사하고 analyze에서도 제시 질문 보존을 적용한다. main/store는 분석 예외의 running job을 failed/result null/종료시각으로 정리하며 삭제·취소·성공 결과를 덮어쓰지 않는다. 원본이나 예외 원문을 실패 job에 추가 저장하지 않는다.
- 기존81개 계약 시나리오 중 이번에 개별 연결한4개 통과,77개 미실행.8개 집중 검사는 finalize 변형과 잘못된 결과/삭제취소 확인을 포함한다.99개 회귀 성공을 계약81개 완료로 계산하지 않는다. 명령3 전체는 부분 수행, 명령4는 미시작이다.
- 새 DB는 앱 import 전에 지정하고 기존 runner의 네트워크/model transport 차단을 사용했다. 실제 외부 모델 호출/transport 시도 및 가드 위반0. 프론트/기존DB/설정/과거 결과를 보존했다. API_CONTRACT/API_SCENARIOS의 변경 전 사본과 해시를 별도 보관했다.
- 정보 공개·완료 정책·프론트 origin·timeout 코드 선택은 미변경이다. 명령3 이후 결정 가능하지만 명령4에서 미결을 숨긴 채 무조건 준비완료로 닫을 수 없다. 조건부 인계 문서에는 영향과 재검증 조건을 남긴다. 실제 AI 미연동은 실패가 아니다.


## 2026-09-25 — 진행안 3 오류 계약 / 4 정책 구분

입력·인증·소유권·충돌·완료/삭제 후 오류 및 timeout 단계 경계를 실제 in-process HTTP/새 SQLite로 확인했다. 미사용 deadline_not_reached 내부409 매핑을 제거했으며 공개422/validation_error는 유지했다. 새33개·전체132개 통과, 외부 모델 시도0/격리 위반0. harness66 통과·사람평가2 대기.

정책 관찰: 게임 도중 분석 가능, 기본 무응답/스킵 접수+분석 후 설문/게임 미시작이어도 완료 가능, 후반 게임 정보가 공개 전에도 응답에 포함됨. 정책 동작은 변경하지 않았다. 원래 명령3 전체는 부분 수행, 명령4 인계는 미실행. 프론트 별도 개발·AI 미연동 유지. [결과](backend-readiness/20260920-003025-KST/error-policy/20260924-235044-KST/README.md)의 저장소 경로는 `docs/ai-interview/backend-readiness/20260920-003025-KST/error-policy/20260924-235044-KST/README.md`이다.


## 2026-09-25 — 명령3 필수 API·DB 검증 마무리

새 합성 SQLite/mock에서 기존·추가 검사 전체 175개 통과, API 시나리오81개 개별 연결(정책 관찰3개는 승인과 구분). 새 앱/DB 재조회, 사용자 분리·삭제, 실제 HTTP 분석중 삭제, 버전/재시도/timeout/기본·조건부 모드 저장 확인. 앱 코드 이번 미변경; 기존 DB 보존 대조는 새 실행 증거 참조. 외부 모델 호출0/격리 위반0. 사람평가2건은 별도 대기.

정책 결정과 명령4 인계는 아직 남음. 프론트 별도 개발·실제 AI 미연동 유지. [실행 결과](backend-readiness/20260920-003025-KST/command03-completion/20260925-001303-KST/README.md).


## 2026-09-25 — 승인된 보고서 확정 정책 적용

설문6개 접수(건너뜀/시간초과 인정), 게임4라운드 정상/시간초과 종료, 기본면접3개 접수(무응답/스킵 인정) 후 확정하도록 서버 gate 추가. 후속 답변 필수화 없음. 새409 survey_responses_required/game_completion_required; 거절시6개 DB 업무 테이블 보존. 기존 확정 기록/동일요청 재시도 유지. 새14개·전체189개 통과, 실제모델 시도0/격리 위반0.

[결과](backend-readiness/20260920-003025-KST/completion-policy/20260925-003553-KST/README.md). 중간 분석·정보 공개 정책과 명령4 인계는 별도 남음. 프론트/AI/기존DB/과거 결과 미변경.


## 2026-09-25 — 요청한 합성 회차 실행 및 mock 보고서 확정

설문6 → 게임4(연습1+본게임3) → 기본면접3 → mock 분석 → 보고서 확정(completed)을 새 SQLite/in-process HTTP로 실행했습니다. 시나리오1개 통과, HTTP40건, 실제 모델 transport 시도0/격리 위반0. 저장·동일 확정 재시도·새 앱 인스턴스 재조회 일치. 후속 질문3개 생성, 후속 답변0개. 소스 및 기존 DB 등 캡처한736개 파일 해시 동일. 합성 사례이며 사람의 성향/진실성 또는 AI 의미 분석 정확도 검증은 아닙니다. 앱 코드·프론트 변경 없음. 중간 분석/정보 공개 정책·명령4 인계는 별도 잔여 작업입니다. [보고서와 실행 근거](backend-readiness/20260920-003025-KST/mock-demonstration/20260925-005420-KST/README.md).


## 2026-09-25 — 승인된 중간 분석·서버 정보 공개 및 명령4 인계

본게임1개 정상/timeout 종료 후 analyze 허용(연습제외), 이전요청409 main_round_completion_required와DB보존. reveal 전 새정보·변경조건4개경로를 모든Run/definitions응답·재시도에서 제외, 서버원본유지. 새정책11개 포함 전체회귀200개+현재소스합성회차1개 통과, 모델transport0/격리위반0. 명령4 4-A/B/C 작성, 개발SQLite/mock 백엔드 준비완료. 프론트개발·배포origin/담당자합의·브라우저연결·MySQL/운영·실제AI·사람평가는 별도. [인계와증거](backend-readiness/20260920-003025-KST/command04-handoff/20260925-010843-KST/README.md).


## 2026-10-07 — 수동 확인용 서버 시작 점검

- 실행: 별도 합성 SQLite DB와 AI 비활성 환경에서 `.venv/Scripts/python.exe -B -X utf8 -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-access-log`. 시작 로그의 application startup complete 확인.
- 로컬 HTTP 점검 passed: GET / → 200; Astra 제목, /frontend/script.js 참조, mock 표시 확인. 대상 DB: artifacts/manual-browser/run-20261007-212826-f2c9a079/interview.db.
- 사람/실제 브라우저 회원가입·로그인·새 회차 생성은 pending_manual. 이번에 전체 자동 검사, 게임 UI, live AI, MySQL, 운영 배포는 실행하지 않았다. HTTP 응답 확인을 화면 조작 통과로 집계하지 않는다.


## 2026-10-07 — 사용자 보고에 따른 수동 화면 확인

- 사용자 보고로 확인: 회원가입 뒤 아이디·로그아웃·새 연습 시작 표시, 이어서 새 회차의 1. 나 알아보기 / 2. 상황 게임 / 3. 면접 연습 / 4. 근거 확인 모의 분석 표시.
- 근거 유형: 사용자의 채팅 보고. Codex가 실제 브라우저 화면을 직접 관찰하거나 조작한 결과가 아니다. 로그아웃 후 재로그인은 별도 명시 보고가 없어 독립 통과로 추가하지 않는다.
- 다음: 설문 첫 문항 표시·입력·저장 수동 확인. 설문/답변 저장, 게임, 분석, 보고서 확정, 삭제 검증은 이번 사용자 보고로 통과 처리하지 않는다. 계정 비밀번호는 기록하지 않는다.


## 2026-10-07 — 첫 설문 저장 표시 사용자 확인

- 사용자 보고: 나 알아보기 첫 문항에서 응답하기 → 선택 → 응답 저장을 진행했고, 해당 문항에 응답 저장 표시가 나타남.
- 이 조작 후 저장 표시 확인은 수동/사용자 보고 기준 passed. Codex의 직접 브라우저 관찰이나 DB 원본 대조 결과가 아니다.
- 다음 확인: 브라우저 새로고침 후 같은 회차에서 첫 문항의 저장 상태 유지. 선택값 원본 일치와 나머지 설문은 아직 확인 대기.


## 2026-10-07 — 새로고침 후 첫 설문 저장 상태 사용자 확인

- 사용자 보고: F5 새로고침 후 같은 회차 화면이 다시 열리고, 첫 문항의 응답 저장 표시가 유지됨.
- 수동/사용자 보고 기준으로 회차 화면 복귀와 저장 상태 표시 유지 passed. Codex의 직접 브라우저 관찰, 선택값 원본 대조 또는 전체 DB 영속성 검증으로 확대하지 않는다.
- 다음 확인: 나머지 설문 5개의 입력·저장 및 설문 처리 진행 표시. 면접 답변·게임·분석·삭제는 이번 확인에 포함하지 않는다.


## 2026-10-07 — 설문 6개 저장 표시 및 진행률 사용자 확인

- 사용자 보고: 나 알아보기 문항 6개 모두 응답 저장으로 표시되고, 근거 확인에 설문 6/6이 표시됨.
- 수동/사용자 보고 기준으로 설문 6개 저장 상태 표시와 진행률 표시 passed. 선택 라벨·강도·관점·순위의 저장 원본 대조, 시간 초과·건너뜀 분기 또는 Codex 직접 브라우저 검증 완료를 뜻하지 않는다.
- 다음 확인: 기본 면접 질문 3개의 답변 작성·저장. 게임 종료 기록이 없어 분석·보고서 확정은 계속 대기한다.


## 2026-10-07 — 기본 면접 3개 저장 표시 및 진행률 사용자 확인

- 사용자 보고: 기본 면접 질문 3개 각각에 답변 저장이 표시되고, 근거 확인에 기본 면접 3/3이 표시됨.
- 수동/사용자 보고 기준으로 기본 면접 3개 저장 상태 표시와 진행률 표시 passed. 답변 원문 대조, 수정 버전 보존, 새로고침 후 답변 유지 또는 Codex 직접 브라우저 검증을 수행한 것으로 집계하지 않는다.
- 다음 확인: 첫 기본 답변 수정·저장 후 새로고침과 재열기, 수정 내용·버전 및 기본 면접 3/3 유지 확인. 게임·분석·최종 확정은 이번 확인에 포함하지 않는다.


## 2026-10-07 — 기본 면접 답변 3개의 수정 및 재열기 사용자 보고

- 사용자 보고: 기본 면접 질문 3개 모두 수정 가능하며, 답변 보기 / 수정을 열면 수정된 내용이 저장된 상태로 보임.
- 수동/사용자 보고 기준으로 수정 기능과 재열기 시 수정 내용 표시를 확인했다. 수정 답변 저장 버튼의 실제 클릭 순서, F5 이후 유지, 표시된 답변 버전 번호 및 이전 원문 보존은 별도 명시 확인이 없어 통과로 추가하지 않는다.
- 다음 확인: 같은 테스트 계정으로 로그아웃·재로그인 후 연습 기록에서 기존 회차를 열고 설문 6/6, 기본 면접 3/3, 수정 답변 내용이 유지되는지 확인. 비밀번호는 기록하지 않는다.


## 2026-10-07 — 재로그인 후 기존 회차 및 수정 답변 유지 사용자 확인

- 사용자 보고: 로그아웃 → 같은 테스트 계정으로 로그인 → 연습 기록에서 기존 회차 열기를 순서대로 수행했고, 설문 6/6·기본 면접 3/3·수정 답변 내용이 모두 유지됨.
- 수동/사용자 보고 기준으로 재로그인, 기록 목록에서 기존 회차 재개, 진행률 및 수정 답변 내용 유지 passed. Codex의 직접 브라우저 관찰·DB 원본 대조 또는 이전 답변 버전 보존 검증으로 확대하지 않는다.
- 다음 확인: 면접 답변에 미저장 내용을 입력한 뒤 화면 이동 시 확인 대화상자가 나타나고, 이동을 취소하면 작성 내용이 유지되는지 확인. 회차 삭제는 아직 수행하지 않았다.


## 2026-10-07 — 미저장 답변 이동 취소 및 내용 유지 사용자 확인

- 사용자 보고: 면접 답변에 저장하지 않은 문장을 추가한 뒤 브라우저 뒤로 가기를 누르자 저장하지 않은 입력이 있다는 이동 확인창이 표시됨. 취소를 누르면 답변 화면과 추가한 문장이 유지됨.
- 수동/사용자 보고 기준으로 뒤로 가기 확인창 표시와 취소 후 미저장 내용 유지 passed. 이동 승인·탭 종료·새로고침 경계까지 검증한 것으로 확대하지 않는다.
- 다음 확인: 좁은 데스크톱 브라우저 창에서 글·입력칸·버튼 표시, Tab 이동 시 초점 표시 및 면접 답변 열기. 실제 모바일 기기 검증과 구분한다. 회차 삭제는 아직 수행하지 않았다.


## 2026-10-08 — 10월 7일 수동 점검 재개 준비

- 사용자 요청으로 점검을 재개한다. 10월 7일 회차를 보존하고, 삭제 확인은 별도 새 테스트 회차로 진행한다. 삭제는 아직 수행하지 않았다.
- 샌드박스 초기화 오류(helper_unknown_error: setup refresh had errors)로 기본 명령 2개가 프로세스 생성 전에 실패했다. 샌드박스 밖 확인에서 기존 테스트 DB·Python 존재, 포트 8000 미기동 및 HTTP 연결 불가를 확인했다. 앱 테스트 실패와 구분한다.
- 기존 DB artifacts/manual-browser/run-20261007-212826-f2c9a079/interview.db를 명시해 mock 전용 로컬 서버를 재시작했다. 새 DB는 만들지 않았다. AI_LIVE_ENABLED=false, PAID_AI_ENABLED=false, COOKIE_SECURE=false, --no-access-log 적용.
- 서버 PID 13360, GET http://127.0.0.1:8000/ → HTTP 200 및 Astra 페이지 표시 문자열 확인. 시작 근거: artifacts\manual-browser\run-20261007-212826-f2c9a079\resume-20261008-211759-06559595/STARTUP_CHECK.json.
- 실제 사용자 브라우저 재로그인·새 회차 생성·삭제·삭제 후 접근 확인은 대기다. HTTP 확인을 브라우저 조작 통과로 집계하지 않는다. 전체 자동 회귀·live AI·운영 배포는 이번 미실행이다.


## 2026-10-08 — 별도 테스트 회차 삭제 및 삭제 후 접근 사용자 확인

- 사용자 보고: 삭제 확인용 새 회차에 답변을 저장한 뒤 해당 회차를 삭제했다. 연습 기록에는 10월 7일 기존 회차가 남아 있고, 삭제한 회차 주소로 재접속하면 불러오지 못했습니다 / 회차가 삭제되었거나 접근할 수 없습니다 안내가 표시됨.
- 수동 / 사용자 보고 / passed: 별도 회차 삭제 뒤 기존 회차 보존 표시, 삭제한 회차 URL 재접속 차단 안내. Codex의 직접 브라우저 관찰, 실제 HTTP 상태 코드 확인 또는 DB 원본·파생 자료 전체 삭제 검증으로 확대하지 않는다.
- 처음 안내한 사용자 기본 점검 8개 항목을 사용자 보고 기준으로 모두 확인했다: 회원가입·로그인·회차 생성, 설문 저장 표시, 기본 면접 저장 표시, 답변 수정·재열기, 새로고침·재로그인 후 기록 유지, 미저장 답변 이동 취소, 좁은 창·키보드 조작, 별도 회차 삭제·삭제 후 접근.
- 1단계 전체 완료 판정과는 구분한다. 남은 확인은 5개 묶음: 다른 계정의 접근 차단, 원본 선택값·이전 답변 버전 대조, 통신 오류·지연·재시도, 시간 초과·건너뜀, 실제 모바일 기기 화면·조작. 기존 자동 검사 이력과 새 화면의 추가 확인을 구분한다.
- 10월 7일 기존 회차는 계속 보존한다. 재개 DB는 artifacts/manual-browser/run-20261007-212826-f2c9a079/interview.db이며, 이번에는 전체 자동 회귀·live AI·게임 통합·운영 배포를 실행하지 않았다.


## 2026-10-08 — 다른 계정 조회 차단 및 설문 건너뜀·시간 초과 사용자 확인

- 다른 계정 조회 차단: 사용자가 tester01의 10월 7일 기존 회차를 열어 주소 복사 → 로그아웃 → 별도 계정 가입/로그인 → 복사한 주소 접속 순서로 진행했다고 명시 확인했다. 불러오지 못했습니다 / 회차가 삭제되었거나 접근할 수 없습니다 안내가 표시됨. 해당 수동 조회 차단 검사는 사용자 보고 기준 passed이며 반복 확인하지 않는다. Codex의 직접 브라우저 관찰이나 다른 계정의 수정/삭제 API 검사는 아니다.
- 최초 건너뜀: 사용자 보고로 첫 설문의 건너뜀 표시와 설문 1/6을 확인했다.
- 실제 후속 진행: 사용자가 같은 테스트 흐름에서 설문 5개를 건너뛰고 마지막 질문을 시간 초과시킨 뒤 설문 6/6 표시를 확인했다. 수동 / 사용자 보고 기준으로 건너뜀·시간 초과를 포함한 처리 진행률 확인 passed. 안내했던 두 번째 문항 시간 초과 및 2/6을 실행한 것으로 기록하지 않는다. 모든 입력 형식의 시간 초과 의미를 검증한 것으로 확대하지 않는다.
- 중간의 불명확한 입력과 안되는데 메시지는 사용자가 채팅 줄바꿈 확인이었다고 정정했다. 앱 오류나 수용 검사 실패로 집계하지 않는다.
- 별도 저장 자료 검사: artifacts/manual-browser/run-20261007-212826-f2c9a079/record-audit-20261008-215425/RESULTS.json에 검사 assertion 174 passed / 1 failed가 있다. 실패명은 survey_6_selection_events_final_order다. 당시 자료는 읽기 전용으로 대조했으며 앱 결함인지 검사 가정 문제인지 아직 미판정이다. 전체 pytest·하네스 결과가 아니며 원본 대조 전체 통과로 집계하지 않는다. 사용자 요청에 따라 추가 조사보다 수동 화면 점검을 우선한다.
- 다음: 별도 테스트 회차의 기본 면접 답변을 이용해 통신 실패 표시·미저장 텍스트 보존·동일 요청 재시도 후 저장을 수동 확인한다. 실제 모바일 확인과 저장 자료 검사의 미판정 항목도 남아 있다. 10월 7일 기존 회차는 보존한다.


## 2026-10-08 — 통신 실패·재시도 사용자 확인 및 PC 수동 점검 종료

- 사용자 보고: 별도 테스트 회차의 면접 답변에 대해 안내한 Offline 전환 → 저장 시 연결 오류와 입력 유지 확인 → No throttling 복원 → 원래 요청 다시 시도 → 저장 표시 확인 절차가 모두 정상 동작함.
- 수동 / 사용자 보고 / passed: 통신 실패 안내, 답변 입력 보존, 통신 복원 뒤 저장 재시도. Codex의 직접 화면 관찰, 실제 전송 body/key 비교 또는 서버 저장 뒤 응답만 유실되는 모든 경로의 재현으로 확대하지 않는다.
- 사용자와 진행하는 PC 기본 수동 점검은 여기서 마친다. 같은 동작을 다시 요구하지 않는다. 남은 것은 실제 모바일 기기 확인 및 record-audit-20261008-215425의 미판정 assertion 한 건을 포함한 저장 자료 대조 정리다. 새 검증 범위를 임의로 추가하지 않는다.

## 2026-10-09 — 사용자 변경 html 화면 미리보기 HTTP 확인

- 범위: 변경된 페이지를 로컬 서버로 제공하고 브라우저 열기를 요청했다. 제품 파일은 수정하지 않았으며 서버 연동 복구 완료를 주장하지 않는다.
- 환경: 별도 SQLite DB artifacts/manual-browser/preview-20261009-95ca0574/interview.db, AI_LIVE_ENABLED=false, PAID_AI_ENABLED=false, COOKIE_SECURE=false, 127.0.0.1:8000, --no-access-log. 기존 테스트 DB는 보존했다.
- 자동 / mock 설정 / passed: GET /, /frontend/index.html, /frontend/style.css, /frontend/script.js, /frontend/client.js → 각각 HTTP 200. HTTP 응답 확인이며 UI 기능·분석 결과 검증은 아니다.
- 자동 / mock 설정 / failed: 첫 화면(/)에서 참조하는 상대 경로 GET /style.css, /script.js → 각각 HTTP 404. 경로 수정은 아직 하지 않았다. /frontend/index.html 주소에서는 해당 상대 리소스 경로가 /frontend/ 아래로 해석된다.
- 직접 UI 검사 / blocked: Browser 런타임 선택 시 No browser is available, browsers.list() 결과 []. 기본 브라우저에서 http://127.0.0.1:8000/frontend/index.html 열기 명령은 성공했으나 실제 화면을 관찰하지 못했다. 수동 사용자 화면 확인은 pending_manual.
- 근거: artifacts/manual-browser/preview-20261009-95ca0574/STARTUP.json, HTTP_CHECKS.json, server.stderr.log. 전체 pytest·하네스·live AI·운영 배포는 skipped. 과거 수용 시나리오 통과 이력을 이번 화면의 통과로 재사용하지 않는다.

## 2026-10-09 — 새 화면의 성향 설문 6문항 복원 검증

- 범위: html 세 파일의 설문 표시·입력 복원과 같은 출처 리소스 경로 수정. 원문은 app/content.py 및 GET /api/definitions. client.js는 SHA-256 3A6566BEF6B57823ABDF917EF526B9351E9F1C1D1D8A94BBDB942002016C9040로 변경 전후 동일하다. 테스트 fixture와 서버의 version/surveys가 일치하는지 실제 TestClient 응답으로 대조했다.
- RED / 자동 / mock: 새 Node 테스트에서 여섯 원본 문항을 렌더링하지 않는 실패를 확인했다(0 != 6; 기존 두 정적 문항은 테스트 DOM에 주입하지 않음). 최초 테스트 도구에 appendChild가 없어 발생한 오류는 도구 보완 후 별도로 재실행했고, 수정 전 누락 실패는 artifacts/survey-restore-20261009/red-survey-tests.txt에 기록했다.
- passed / 자동 / mock DOM 경계: node --test tests/frontend_survey.test.cjs tests/frontend_client.test.cjs → 17 passed, 0 failed. 실제 script.js 이벤트·렌더링과 client.js를 실행한다. 여섯 문항/네 형식, 순서형 라벨, 기본 선택 없음, 두 관점 분리, 중앙값 명시 확정, 슬라이더 변경 후 재확정, 중복 순위 차단/순위 수정, 미응답 이동 차단, 문항 조회 실패/재시도, 아이콘 라이브러리 부재를 검사했다. 실제 브라우저 또는 시각·접근성 평가를 의미하지 않는다.
- passed / 자동 / 임시 SQLite·mock: .venv/Scripts/python.exe -B -X utf8 -m tools.run_checks tests/test_frontend_integration.py tests/test_backend.py -q → 27 passed, exit 0. 실제 서버 리소스, 문항 fixture 일치, 소유권·입력·출처 계약을 확인했다. 결과: artifacts/offline-checks/run-b4um7b_g/RESULTS.json 및 harness-results.json.
- 시나리오 연결: 새 Node 검사명에 SCN-001/004/006/007/009의 해당 화면 불변식을 표시했다. 기존 tests/test_backend.py의 실제 pytest.mark.scenario 검사로 SCN-001/004/006/007/008/009 관련 서버 계약도 실행했다. Node 부분 검사만으로 각 수용 시나리오 전체 통과를 주장하지 않으며 전체 시나리오 집계는 위 harness-results.json의 실행/미실행 구분을 따른다.
- passed / 자동 HTTP: /, /frontend/index.html, /frontend/style.css, /frontend/client.js, /frontend/script.js, /api/definitions → 각각 200. 서버의 여섯 원문과 fixture를 UTF-8로 대조했다. 근거: artifacts/survey-restore-20261009/http-checks.json 및 RESULTS.json. PowerShell 기본 .Content 해석에서 한글이 잘못 표시되어 RawContentStream을 UTF-8로 재해석했으며 앱의 문자 깨짐으로 판정하지 않았다.
- failed / 변경 전 회귀 기준: tests/frontend_navigation.test.cjs의 browser Back cannot silently discard an unsaved answer, navigation immediately removes old interactive run while fetch is delayed, Back during answer write stays in initiating run until response is handled 세 검사. 이전 화면을 대체한 사용자 변경본에서 이미 실패했으며 이번 범위에서 복구하지 않았다. 근거: artifacts/survey-restore-20261009/baseline-navigation-tests.txt.
- pending_manual: 수정 후 실제 화면 표시·키보드·모바일 확인. 앞선 사용자 보고는 수정 전 페이지가 보인다는 확인이며 이번 여섯 문항 복원의 시각 검증으로 확대하지 않는다. 브라우저 자동 제어는 앞서 연결 불가였고 이번에는 재실행하지 않았다.
- skipped: 전체 자동 회귀, 시간 제한/시간 초과 UI, 인증 및 실제 설문 저장 경로의 새 화면 연결, 게임/근거 보고서 복구, live AI, 운영 배포. 현재 응답은 untimed_screen_preview 메모리 자료이며 서버 저장 완료로 표시하지 않는다.

## 2026-10-10 — 회원가입·로그인·세션 복원·로그아웃

- 범위: 새 html/auth.js 및 index.html/style.css의 인증 UI 연결. 기존 backend/client.js/script.js를 보존했다. 변경 전 파일과 해시는 artifacts/auth-connect-20261010/before/ 및 RESULTS.json에 있다.
- RED / 자동 / mock DOM: 연결 전 로그인 상태 표시가 없는 실패를 확인했다. 근거: artifacts/auth-connect-20261010/red-auth-tests.txt.
- passed / 자동 / mock DOM 경계: node --test tests/frontend_auth.test.cjs tests/frontend_survey.test.cjs tests/frontend_client.test.cjs → 30 passed, 0 failed. 실제 auth.js와 client.js의 호출/화면 상태를 검사한다. 회원가입 자동 로그인, 세션 복원, 잘못된 입력, 가입 중복, 잘못된 비밀번호, 중복 제출, 응답 유실 후 세션 대조, 연결 불가/재시도, 확정된 로그아웃, 로그아웃 실패, 사용자명 마크업의 텍스트 표시를 포함한다. DOM fixture는 브라우저/시각/접근성 검증이 아니다.
- passed / 자동 / 임시 SQLite·mock: .venv/Scripts/python.exe -B -X utf8 -m tools.run_checks tests/test_frontend_integration.py tests/test_backend.py -q → 28 passed, exit 0. 신규 실제 HTTP 테스트는 회원가입 201, 로그인 200, /me 복원, 중복 아이디 409, 잘못된 로그인 401, CSRF 없는 로그아웃 403, 정상 로그아웃 204, 폐기된 쿠키 재사용 401 및 재로그인 시 새 세션을 검사한다. 공개 응답에 user_id/username만 있고 HttpOnly/SameSite=strict 쿠키인 것을 확인했다. 합성 계정만 사용하며 사용자 운영 DB를 수정하지 않는다.
- 시나리오: test_auth_session_register_restore_logout_login_and_revocation은 SCN-012 인증 경계의 보완 검사다. 기존 SCN-012 다른 사용자 회차 조회 거부 검사도 함께 실행했다. 전체 사례 집계는 artifacts/offline-checks/run-337z746u/harness-results.json을 따르며 인증 보완 검사 하나를 전체 접근 통제 검증으로 확대하지 않는다.
- passed / 자동 HTTP 제공: 실행 중인 127.0.0.1:8000에서 /, /frontend/index.html, /frontend/auth.js, /frontend/client.js, /frontend/script.js, /frontend/style.css 각각 200. 근거: artifacts/auth-connect-20261010/http-checks.json. 이 GET 확인은 실제 브라우저 가입/로그인 성공 판정이 아니다.
- blocked / 직접 브라우저 자동 제어: Browser 런타임이 No browser is available을 반환했다. pending_manual / 사용자 확인: 새로고침 후 상단 회원가입·로그인 표시, 테스트 계정 가입, 로그인 상태 표시, 새로고침 유지, 로그아웃 후 재로그인, 잘못된 비밀번호 안내, 좁은 화면·키보드 조작.
- 별도 읽기 전용 AI 코드 검토 완료: 차단 코드 결함 없음, 제한된 로컬 수동 브라우저 테스트 준비 판정. 실제 브라우저 통합 검증은 Important 공백으로 남겼다. persisted pageshow 이벤트와 logout 및 후속 /me 모두 통신 실패하는 분기의 직접 자동 검사는 minor 공백으로 기록했다. 근거: artifacts/auth-connect-20261010/REVIEW.json.
- skipped: 전체 회귀/구형 내비게이션 3개 실패 재검사, 설문 서버 저장/조회 연결, 게임/보고서 연결, 실제 AI 호출, 운영 배포. 현재 단계의 자동 검사 통과를 앱 전체 완성 또는 운영 배포 준비로 표시하지 않는다.

## 2026-10-10 — 인증 기본 흐름 수동 확인 결과

- 수동 / 사용자 보고 / passed: 사용자가 안내한 다섯 단계 모두 정상 동작했다고 보고했다. 범위는 강력 새로고침 후 인증 화면 표시, 회원가입 입력, 가입 직후 아이디와 로그인됨 표시, 새로고침 후 로그인 유지, 로그아웃 후 동일 계정 재로그인이다.
- 이전 자동 검사 58개 및 코드 검토 결과와 구분한 추가 사용자 확인이다. Codex가 직접 화면이나 네트워크 요청을 관찰한 결과로 기록하지 않는다.
- 이번 보고로 잘못된 비밀번호, 중복 아이디, 통신 오류, 다른 계정 접근 통제, BFCache, 실제 모바일·키보드 조작까지 수동 통과했다고 판단하지 않는다. 새로운 자동 검사를 실행하지 않았다.
- 설문 서버 저장·재조회는 아직 미구현이며 이 인증 확인에 포함되지 않는다. 이미 확인된 기본 인증 절차는 반복 요청하지 않는다.

## 2026-10-10 — 설문 입력에서 게임 화면으로 이동 수동 확인

- 수동 / 사용자 보고 / passed: 여섯 성향 설문 입력 → 응답 확인 후 게임 화면으로 클릭 → 가위바위보·카드 게임 화면 표시. 버튼 클릭 보고와 실제 전환 확인을 후속 사용자 답변으로 구분해 확인했다.
- 이 결과는 화면 체험 흐름에 한정한다. 게임 실행/점수/라운드 진행, 서버 회차 생성, 설문 응답 저장·복원, 보고서 근거 정확성은 이번 확인에 포함하지 않는다.
- 추가 자동 검사나 Codex 직접 브라우저 검증은 실행하지 않았다. 사용자 확인으로 기존 자동 검사 수를 늘리지 않는다. 제품 코드 변경 없음.

## 2026-10-10 — 실제 회차·설문 저장 연결 검증

- 후속 수동 / 사용자 보고 / passed: 사용자가 `서버 저장 6 / 6문항`까지 전부 실행했다고 보고했다. 실제 사용자 화면에서 여섯 문항 진행과 서버 저장 완료 표시를 확인한 결과로 한정한다. 새로고침 후 회차·응답 복원, 개별 선택값의 DB 원본 대조, 게임·보고서 검증은 이 보고에 포함하지 않는다. 이번 확인 기록을 위해 제품 코드를 변경하거나 추가 자동 검사를 실행하지 않았다.

- 자동 / 합성 DOM·mock transport / passed: `node --test tests/frontend_practice.test.cjs tests/frontend_auth.test.cjs tests/frontend_survey.test.cjs tests/frontend_client.test.cjs` 최종 42 passed. 새 버튼, 6문항 실제 UI payload, 문항별 revision, 명시적 중앙, 별도 관점, 순위 변경 이벤트, 시간 초과 부분 순위, 새로고침 시 선택/기한 복원, 응답 유실 후 동일 요청 재시도, 늦은 입력 차단, 로그인 변경 후 늦은 응답 무시 및 임시자료 정리를 검사했다. 추가로 422 버전 변경 후 명시적 복구와 오프라인 초기 로드 후 재연결을 검사했다. 실제 브라우저 렌더링 검사는 아니다.
- 자동 / 실제 FastAPI·임시 SQLite·mock AI / passed: `.\.venv\Scripts\python.exe -B -X utf8 -m tools.run_checks tests -q` 207 passed, 0 failed, 0 skipped. `run-xgkz4ztt/RESULTS.json`: exit 0, 실제 ASGI 요청 2,185회, guard 위반 0, provider transport 0. 외부 네트워크와 기존 DB를 차단한 실행이다.
- 신규 서버 검사는 UI 핸들러가 생성한 `tests/fixtures/practice_ui_payloads.json`과 원문 데이터를 대조하고, 저장/재조회/멱등 재시도/다른 계정 접근 거부/동시 회차 생성/삭제 후 재시도/부분 rank 검증을 실행한다. SCN-001/004/007/009/012의 해당 저장·소유권 수용 조건과 연결하며 fixture 파일 존재 자체를 실행 성공으로 세지 않는다.
- 실패 후 수정 기록: 초기 버튼 미구현 및 생성 재시도 중복 실패(`red-node.txt`, `run-mpsdv1uk`); 부분 순위 2위가 1위로 저장되던 실패(`run-4argu6s0`); 전체 Python 첫 실행의 성격 판정 방지 안내 누락 1건(`run-o79kk6m8`, 206 passed/1 failed). 각각 수정 후 최종 검사로 확인했다. 중간 관련 Python 32 passed는 `run-azib1voq`에 있다.
- 자동 / 로컬 실행 서버 read-only HTTP / passed: `/`, `/frontend/index.html`, `practice.js`, `auth.js`, `script.js`, `style.css`, `/api/definitions` 모두 200. `artifacts/practice-connect-20261010/http-checks.json`. 실제 테스트 DB를 백업하고 같은 DB로 서버 재시작했으며 사용자 계정/기록을 초기화하지 않았다.
- 보존 확인: `html/client.js` SHA256은 작업 전후 `3A6566BEF6B57823ABDF917EF526B9351E9F1C1D1D8A94BBDB942002016C9040`으로 동일하다.
- blocked: in-app Browser가 `[]`를 반환하여 Codex 직접 브라우저 동작/시각 검증을 실행하지 못했다. pending_manual: 새 저장 기능에 대한 실제 사용자 새로고침/이어하기 확인, 브라우저 쿠키·BFCache·모바일/키보드. 이전의 미저장 화면 체험 수동 확인을 이번 기능 통과로 간주하지 않는다.
- skipped: 기존 구형 내비게이션 Node 3개 실패 재검사, 게임·면접·보고서 연결, live AI, MySQL, 운영 배포. 전체 Python 통과는 이 미구현 범위의 완성이나 운영 준비를 뜻하지 않는다.
- 독립 AI 코드 리뷰 / 수정 후 확인: 검증 거부 후 pending 고착 Important 1건을 발견해 red→green 테스트와 명시적 복구 경로로 수정했다. 리뷰어의 후속 검토에서 해당 경로에 남은 Important 없음. minor였던 생성 전 예외 mock은 서버 커밋 후 응답 유실을 모델링하도록 보완했다. v2 복구 테스트도 새 버전 제출 이후 저장 상태까지 검사한다. 코드 검토는 사람 평가·실제 브라우저 검사를 대신하지 않는다. `REVIEW.json` 참조.
- 최종 오류 복구 HTML/JS 보완 후 관련 실제 API/리소스 검사는 `run-gihuhcn3`에서 7 passed. 207 전체 검사와 중복되는 7개이며 총 고유 통과 수에 더하지 않는다. 최종 정적 리소스도 실행 서버에서 다시 HTTP 200 확인했다.

## 2026-10-10 — 저장된 설문 새로고침 복원 수동 확인

- 수동 / 사용자 보고 / passed: 새로고침 후 같은 회차 번호 표시, `서버 저장 6 / 6문항` 유지, 저장 문항을 펼쳤을 때 본인이 선택한 응답 유지. 사용자가 안내한 세 항목 모두 정상 동작한다고 명시 확인했다.
- 앞선 여섯 문항 저장 완료 표시 확인과 함께 실제 사용자 화면의 기본 저장·복원 흐름을 확인 완료로 기록한다. 해당 pending_manual 상태를 갱신하며 같은 절차를 반복 요청하지 않는다.
- 추가 자동 검사 및 제품 코드 변경 없음. 자동 통과 수에 사용자 확인을 더하지 않는다. 직접 브라우저 관찰·DB 원본 대조·오류 상황·다른 계정 접근·BFCache·모바일/키보드·게임/보고서 검증은 이 확인 범위에 포함하지 않는다.
## 2026-10-10 — 게임 저장 연결 검증 중단 기록 (최신)

- 상태: 사용자 요청으로 일시 중단. 일부 테스트 통과가 전체 기능 완료를 의미하지 않는다.
- 자동 / 합성 DOM·mock transport / passed: 마지막 `node --test tests/frontend_practice.test.cjs tests/frontend_games.test.cjs` 실행 24 passed. 실제 브라우저 검사가 아니다.
- 자동 / FastAPI·임시 SQLite / passed: 담당 에이전트의 `tests/test_rule_games.py` 집중 검사 24 passed. 근거: `artifacts/offline-checks/run-90f67vco/`. 전체 Python 회귀 검사는 이번 게임 변경 후 미실행이다.
- AI 코드 리뷰 / 미해결: 서버가 10초 규칙 전환 시점을 지난 이전 규칙 응답을 수락할 수 있음; 라운드의 채점 스냅샷 대신 전역 정의로 채점함; 요청 처리 중 화면 숨김→복귀가 하나의 값으로 합쳐져 이탈 기록이 누락될 수 있음. 리뷰는 중단했으며 승인 완료가 아니다.
- skipped / 사용자 종료 요청: 위 문제 수정·회귀 검사·최종 리뷰·새 API를 반영한 로컬 서버 재시작·실행 서버 HTTP 검사. 실제 브라우저·사용자 게임 테스트도 미실행이다. live AI와 운영 배포는 미실행이다.
- 상세 인계: [GAME_CONNECTION_HANDOFF.md](GAME_CONNECTION_HANDOFF.md).

## 2026-10-11 — 게임 저장 연결 최종 구현 검증

- 자동 / 실제 FastAPI·임시 SQLite·mock / passed: `.\.venv\Scripts\python.exe -B -X utf8 -m tools.run_checks tests -q` → **235 passed**, exit 0, guard 위반 0, provider transport 0. 근거 `artifacts/offline-checks/run-wir3o9tc/RESULTS.json`. 사용자 DB와 외부 네트워크를 차단한 전체 검사다. 이후 수정은 프런트엔드에 한정되어 아래 최종 검사와 HTTP 파일 대조로 확인했다.
- 자동 / 합성 DOM·mock transport / passed: `node --test tests/frontend_auth.test.cjs tests/frontend_client.test.cjs tests/frontend_survey.test.cjs tests/frontend_practice.test.cjs tests/frontend_games.test.cjs` → **59 passed**, exit 0. 근거 `artifacts/game-connect-20261011/node-tests-final.txt`. 실제 practice/game 스크립트를 함께 실행해 6문항 회차 공유, revision, 회차 잠금, 종료 저장을 검사한다. 서버 커밋 후 응답 유실·동일 키 재시도, 새로고침, 계정 변경/삭제, 카드 ID·중복 선택, 순서 있는 이탈/복귀 대기, 혼합 화면 상태, 정오답 서버 결과 표시를 포함한다. 실제 브라우저 렌더링 검사가 아니다.
- 자동 / 회귀 재현 후 수정 / passed: 서버 집중 검사 red 24 passed/4 failed(`run-p3xnt5ag`) → green 28 passed(`run-65rpp5aq`). 10초 경계의 응답 거부, 불변 채점 기준, 공개 기록 없이 종료된 경우의 누락 표시에 대한 검사다. 화면 대기 기록 red 10 passed/2 failed → green; 중복/혼합 상태 red 12 passed/2 failed → green; 카드 오답 표시 red 14 passed/1 failed → 최종 green. 중간 숫자를 고유 통과 수에 더하지 않는다.
- 수용 하네스 연계: 기존 `ai_interview_codex/harness/scenarios.json`을 사용하는 전체 테스트가 실제 실행됐다. 새 규칙 게임의 저장·소유권·삭제·재시도는 해당 API 경계로 검사했다. 이는 원래 resource-bridge의 행동 관찰 기회나 B01/B02/B03 타당성 검증을 대신하지 않는다. 두 게임의 행동 매핑은 unmapped이며 게임만 완료해 분석·최종화를 우회하지 못한다.
- 독립 AI 코드 리뷰 / 수정 후 확인: `/root/rule_game_review`가 서버 경계/채점 스냅샷 수정과 두 프런트엔드 수정의 해결을 확인했다. 최종 focused Node 29/29(위 59개와 중복) 통과. 사람 평가나 브라우저 접근성 평가로 취급하지 않는다. 근거 `artifacts/game-connect-20261011/REVIEW.json`.
- 자동 / 실행 로컬 서버 읽기 전용 HTTP / passed: 페이지·정적 파일·게임 정의 9개 경로 200, 정적 파일 바이트 일치, 인증 없는 게임 기록 경로 401. 근거 `http-checks.json`. 같은 DB로 실행했고 `BACKUP.json`의 backup integrity_check=ok. 테스트 요청으로 실제 사용자 회차에 게임 행동을 추가하지 않았다.
- blocked: 직접 브라우저 제어(`cua.getState()` → apps=[], browsers=[]). pending_manual: 실제 사용자 게임 플레이·새로고침 후 복원, 색/레이아웃/키보드/스크린리더. 기존 설문 6/6 복원은 이미 사용자 확인 완료이며 새 게임의 수동 통과로 전용하지 않는다.
- skipped: 기존 별도 구형 navigation Node 검사 3건의 실패 재검증/수정, HTML 면접·최종 보고서 연결, MySQL, live AI, 운영 배포. 새 게임 연결의 검증을 전체 제품 완성으로 표시하지 않는다.

## 2026-10-11 — 게임 결과 유지 수동 확인

- 수동 / 사용자 보고 / passed: 새로고침 후에도 같은 게임 결과가 유지됨. 사용자가 이전 화면으로 돌아가는 현상과 함께 명시적으로 보고했다. 앞선 pending_manual 중 기본 게임 결과 복원 흐름을 확인 완료로 갱신한다.
- 화면/탭 위치 복원은 별도 미해결 사용성 항목이다. 사용자가 실제로 확인한 게임 종류·라운드 수는 명시하지 않았으므로 두 게임 3라운드 전체나 모든 행동 기록의 정확성까지 수동 통과로 간주하지 않는다.
- 이번에는 제품 코드 변경이나 추가 검사를 실행하지 않았다. 사용자 확인을 자동 검사 통과 수에 더하지 않는다. Codex 직접 브라우저 관찰/원본 DB 대조, 오류 상황·다른 계정 접근·시각/접근성 확인은 이 보고에 포함되지 않는다.

## 2026-10-11 — 가위바위보 전체 라운드 저장 표시 확인

- 수동 / 사용자 제공 화면 문구 / passed: `라운드 저장됨`, `서버 기록 연결됨`, `라운드 종료 서버 저장: 가위바위보 3 / 3 · 카드 0 / 3`. 가위바위보 3라운드 종료 저장 표시를 사용자 확인 완료로 갱신한다.
- pending_manual: 카드 게임 3라운드 완료. 사용자가 제공한 문구는 카드 0/3이므로 카드 완료를 추정하지 않는다. 개별 채점·행동 로그 원본 대조나 Codex 직접 브라우저 관찰 결과가 아니다.
- 추가 자동 검사·제품 변경 없음. 이전 자동 통과 수는 그대로다.

## 2026-10-11 — 두 게임 전체 라운드 저장 표시 수동 확인

- 수동 / 사용자 제공 화면 문구 / passed: `서버 기록 연결됨`, `라운드 종료 서버 저장: 가위바위보 3 / 3 · 카드 3 / 3`. 같은 회차에서 가위바위보와 카드 각각 3라운드 종료 저장 표시가 확인됐다. 카드 완료의 pending_manual 항목을 사용자 확인 완료로 갱신한다.
- 앞서 사용자 확인한 새로고침 후 결과 유지와 구분해 기록한다. 이번 최종 3/3·3/3 상태에서 새로고침을 재검증했다고 주장하지 않는다. Codex 직접 브라우저 관찰/DB 원본 대조/모든 채점 및 행동 이벤트 정확성/오류·접근성 평가를 뜻하지 않는다.
- 추가 자동 검사와 제품 변경 없음. 자동 통과 수에 사용자 확인을 더하지 않는다. 기본 게임 저장 테스트는 반복 요청하지 않는다.

## 2026-10-11 — 기본 면접 실제 회차 연결 검증

- 자동 / 실제 FastAPI·격리 SQLite·mock / passed: `.\.venv\Scripts\python.exe -B -X utf8 -m tools.run_checks tests -q` → **236 passed**, exit 0, guard 위반 0, provider transport 0. 근거 `artifacts/offline-checks/run-b4h4bwxa/RESULTS.json`. 사용자 DB와 외부 호출을 차단한 전체 검사다.
- 자동 / 실제 API 결합 여정 / passed: 새 `tests/test_interview_connection.py`가 기존 생성 설문 fixture 6개, rsp/card 각각 3라운드 후 같은 회차의 기본 질문 순서·버전, CRLF/Unicode 원문 저장, 명시적 미응답/건너뜀 구분, 수정 버전 계보, 원본 불변, 동일 키 재시도, 앱 재생성 후 조회, 다른 소유자·확정·삭제 거부를 검사했다. 면접 저장 전후 resource-bridge와 rule_games 스냅샷 일치를 대조한다. 집중 검사 `run-wh2dbuuz`의 1 passed는 위 236개에 포함된다. 브라우저 textarea 값은 플랫폼의 줄바꿈 정규화 이후 값이므로 실제 DOM의 CRLF 유지까지 주장하지 않는다.
- 자동 / 실제 브라우저 스크립트·합성 DOM·mock transport / passed: `node --test tests/frontend_auth.test.cjs tests/frontend_client.test.cjs tests/frontend_survey.test.cjs tests/frontend_games.test.cjs tests/frontend_practice.test.cjs tests/frontend_interview.test.cjs` → **73 passed**, exit 0. 근거 `artifacts/interview-connect-20261011/NODE_RESULT.json`. 소유 회차의 질문 사용, 정확한 답변 payload와 수정 참조, 저장 전 성공 표시 금지, 커밋 후 응답 유실 재시도, 충돌 시 입력 보존·명시적 재개, 422 후 수정 재제출, 초기 오프라인 복구, 삭제/로그아웃 후 원문 화면 제거와 늦은 응답 차단, 저장소 오류, 세 모듈의 회차·revision·잠금·복원을 검사한다.
- 실패·보완 기록: 새 면접 잠금 검사는 최초 14 passed/1 failed(`setInterviewLock` 부재) 후 구현으로 통과했다. 구현 검토에서 발견한 definitive 4xx의 무한 pending, 충돌 복구 버튼의 즉시 제출, 저장소 오류 안내 소실, 완료 수/질문 스냅샷 표시를 수정하고 해당 검사를 추가했다. 독립 리뷰의 집중 면접 12/12 및 game/practice/interview 43/43은 위 73개와 중복이며 별도로 합산하지 않는다.
- 수용 하네스: 기존 `ai_interview_codex/harness/scenarios.json` 연계 검사를 포함한 전체 Python이 실행됐다. 새 UI 연결 검사는 면접의 원문·버전·상태·소유권 경계를 실제 모듈과 API로 검증한다. fixture 존재만으로 실행 성공을 판단하지 않으며 새 규칙 게임의 B01/B02/B03 비교 타당성이 검증됐다고 주장하지 않는다.
- 독립 AI 리뷰 / 확인 완료: `REVIEW.json` 참조. 범위 내 남은 Important 코드 문제 없음. 사람 평가/실제 브라우저 접근성 평가와 구분한다.
- 자동 / 실행 중 로컬 서버·읽기 전용 HTTP / passed: 페이지·정적 파일·기본 정의 10개 경로 200(정적 파일 바이트 대조 포함), 미인증 회차 조회 401. 근거 `http-checks.json`. 기존 서버 PID 22964/29268과 같은 DB 유지, 서버 재시작 없음. 테스트를 위해 사용자 회차에 답변을 추가하거나 기존 데이터를 변경하지 않았다. client.js의 보존 SHA256도 확인했다.
- blocked: 직접 브라우저 제어를 다시 확인했으나 `cua.getState()`가 apps=[], browsers=[] 반환. pending_manual: 실제 면접 입력/저장/새로고침 복원/수정 이력, 시각 배치·초점·스크린리더. 기존 게임 저장 사용자 확인을 면접의 수동 통과로 대신하지 않는다.
- skipped: 기존 별도 구형 navigation Node 검사 실패의 재검증/수정, 화면 위치 복원, 실제 AI 호출, HTML 근거 보고서 연결, MySQL, 운영 배포. 모든 자동 검사가 이들 범위까지 완료됐다는 뜻은 아니다.

## 2026-10-11 — 이전 면접 버튼 표시 제보 후 제공 파일 재확인

- 수동 / 사용자 보고 / pending_manual: `답변 저장` 대신 이전 `면접 답변 제출 및 분석 요청` 버튼이 표시됨. 실제 브라우저가 새 화면으로 갱신됐다는 확인은 아직 없다.
- 자동 / 실행 로컬 서버 읽기 전용 HTTP / passed: `http://127.0.0.1:8000/`, `/frontend/index.html`, `/frontend/index.html?view=interview-20261011`, `http://localhost:8000/frontend/index.html` 모두 200. 응답에 `interview-items`와 `/frontend/interview.js`가 있고 `submitInterviewAnswers`는 없다. 실행 프로세스는 기존 PID 22964/29268이다. 근거 exec 응답 `1a6483`, `065262`.
- 원인 미확정: 사용자 접속 주소를 확인 요청했다. Cache-Control 응답 헤더가 없고 ETag/Last-Modified는 있으나, 이것만으로 캐시를 원인으로 판단하지 않는다. 제품 코드·DB 변경·서버 재시작·추가 자동 테스트 실행 없음.

## 2026-10-11 — 면접 입력칸 미표시 제보 후 초기화·조회 실패 보완

- 읽기 전용 / 로컬 기존 DB·HTTP / passed: 지정 회차의 질문 메타데이터를 조회해 중립 baseline 3개, in_progress/revision 72, 원본 records 6개를 확인했다. 원문 답변·계정 정보는 읽기 출력 대상에서 제외했다. HTML과 연결 JS 5개 경로가 실행 서버에서 파일과 일치했다. 근거 `artifacts/interview-load-20261011/read-only-check.json`. 원본 records 수는 rule_games 라운드 수가 아니다.
- 자동 / 합성 DOM·mock / 재현 후 passed: 처음 11 passed/2 failed(exec 70e179). 구버전 practice처럼 setInterviewLock이 없는 bridge에서 실제 interview.js가 `TypeError: window.AstraPractice.setInterviewLock is not a function`으로 중단됐다. 오프라인 최초 조회에서는 안내가 계속 ‘불러오는 중’이며 노출되지 않은 제출 재시도를 가리켰다. 필수 bridge 확인/명시적 화면 갱신 안내와 조회 실패 상태·실제 새로 불러오기 버튼 안내로 보완했다.
- 자동 / 격리 SQLite·mock / 재현 후 passed: 정적 파일 URL 캐시 분리 검사는 버전 없는 주소로 최초 실패(run-cpmtvfes). `html/index.html`의 로컬 CSS/JS 7개 URL에 공통 새 버전을 부여했다. `client.js` 파일 내용은 변경하지 않았다.
- 자동 / 관련 Node / passed: auth/client/survey/games/practice/interview 6개 파일의 **74 passed**, exit 0(exec eb264d). 기존 초안/불확실 제출 재시도/수정 버전/소유권/게임·회차 결합 검사 포함. 실제 브라우저 렌더링 검사가 아니다.
- 자동 / 집중 Python / passed: 안전 실행기로 `tests/test_frontend_integration.py tests/test_interview_connection.py -q` → **4 passed**, exit 0, provider transport 0. 근거 `artifacts/offline-checks/run-6ob0sqg1/RESULTS.json`. 관련 API 여정과 새 버전 URL 응답 바이트 대조가 포함되며 전체 Python 236개를 이번에 재실행했다고 주장하지 않는다.
- 자동 / 실행 로컬 서버 HTTP / passed: 새 페이지 및 그 페이지가 참조하는 버전 URL 7개 HTTP 200/작업 파일 일치. client.js 보존 SHA256 일치. 근거 `artifacts/interview-load-20261011/versioned-assets.json`. 실제 사용자 회차 변경·서버 재시작 없음.
- blocked/pending_manual: cua.getState()의 apps=[], browsers=[]로 직접 브라우저 검사는 blocked. 사용자 브라우저가 실제로 구버전 파일을 사용했는지와 수정 후 입력칸·저장 흐름은 pending_manual. 사용자 주소/오류 문구 응답 없음. 기존 게임·설문 재실행은 요청하지 않는다. 외부 호출·운영 배포 없음.

## 2026-10-11 — 면접 표시 복구 및 이전 제출 버튼 재제보

- 수동 / 사용자 보고: 면접 화면이 제대로 나오나 마지막 버튼은 `면접 답변 제출 및 분석 요청`이라고 보고함. 기본 표시 복구만 확인하며 실제 답변 저장/분석 성공으로 표시하지 않는다.
- 읽기 전용 / 실행 서버 HTTP / passed: `/frontend/index.html?verify=interview-button`은 200, `interview-items`/새 버전 스크립트 존재, 이전 버튼 문구와 `submitInterviewAnswers` 없음. html 및 app/static 검색에서도 해당 이전 버튼 문구/함수는 발견되지 않았다. 근거 exec fb2589.
- unresolved: 사용자가 보는 버튼과 확인 서버 응답의 불일치. 접속 URL과 실제 화면은 미확인이고 캐시로 단정하지 않는다. 코드 수정/추가 자동 테스트/DB 변경 없음. 새 HTML의 실제 AI 분석 연결은 여전히 후속 범위다.

## 2026-10-11 — 답변 저장 버튼 표시 사용자 확인

- 수동 / 사용자 보고 / passed: 사용자가 버튼이 `답변 저장`으로 바뀌었다고 확인했다. 직전의 이전 버튼 표시 불일치 항목을 해소로 갱신한다. 브라우저 직접 관찰이나 원인 확정으로 취급하지 않는다.
- pending_manual: 실제 질문별 답변 저장, 서버 저장 3/3, 새로고침 후 동일 답변 복원과 수정 이력. 버튼 표시 확인을 저장·분석 성공으로 간주하지 않는다.
- 제품 코드/DB 변경·추가 자동 검사 없음. 사용자 확인을 기존 자동 통과 수에 더하지 않는다.

## 2026-10-11 — 면접 답변 저장·새로고침 복원 사용자 확인

- 수동 / 사용자 보고 / passed: 면접 답변이 정상 저장되고 새로고침 후에도 유지됨을 확인했다. 앞선 pending_manual 중 기본 저장·복원 흐름을 확인 완료로 갱신한다.
- 확인 범위 제한: 사용자가 정확한 문항 수나 수정 이력까지 명시하지 않았으므로 3/3 표시·버전 이력·오류/접근성 검증 완료로 확대하지 않는다. 실제 AI 분석·근거 보고서 연결 성공을 뜻하지 않는다.
- 제품 코드/DB 변경·추가 자동 검사 없음. 사용자 확인은 기존 자동 통과 수와 별도로 기록한다. 기본 설문·게임·면접 저장 테스트를 반복 요청하지 않는다.

## 2026-10-11 — 현재 HTML의 AI 경로·통합 근거 보고서 연결

- 구현 범위: 별도 interview-analysis API/파생 보고서, 서버 capability, 원자 예약/동일 키 재전달/영구 예산/삭제·수정 경합, 정확한 인용과 승인 매핑/버전 검사, 현재 HTML 통합 보고서/잠금/재시도/이전 입력 표시. 기존 resource 분석·완료 계약과 사용자 원본은 보존했다.
- 자동 / RED: 새 AI 모듈 부재에 따른 집중 10건 실패, 새 API 부재 6건 실패(`run-jczetju0`), report lock 부재(Node 15 pass/2 fail), 새 정적 report 자산 부재(`run-j765jnu5`). 이후 구현 검사 통과. 단순 fixture 존재를 통과로 처리하지 않았다.
- 자동 / 결합 RED→GREEN: root가 네 실제 화면 스크립트를 한 VM DOM 경계에 실행했을 때 초기 practice 작업 잠금으로 보고서 첫 조회가 시작되지 않아 버튼이 계속 비활성화됨(exec 0f2f3a, 54 pass/1 fail). 같은 회차 잠금 해제 시 지연된 최초 조회를 한 번 시작하도록 수정했다. 최종 관련 Node와 네 모듈 결합 검사가 통과했다. 실제 브라우저 렌더 검사는 아니다.
- 독립 코드 검토 / 수정: explicit 요소를 방향 지지로 오해하는 비교, game/interview 매핑 ID·버전·단위·승인·필수 근거 필드 검사, 빈/공백/과다 인용, prompt/schema/rubric/mapping provenance, 설문 문항 원문·슬라이더 범위·후보 내 부분순위 의미를 보완했다. legacy 비용/estimated_cost NaN·Infinity 거절도 검사했다. 검토자의 좁은 재검토에서 P1 세 가지 수정 확인; 마지막 필수 매핑 필드 P2는 작성자가 수정하고 회귀 검사/최종 전체 검사로 확인했다. 과학적 타당화·독립 사람 평가는 아니다.
- 자동 / 최종 Python / passed: `.\.venv\Scripts\python.exe -B -X utf8 -m tools.run_checks tests -q` → **274 passed**, exit 0, 실제 in-process FastAPI HTTP **2,594**, provider transport **0**, guard 위반 **0**. 근거 `artifacts/offline-checks/run-ooq7dcvg/RESULTS.json`. 이전 중간 전체 실행 255 passed(`run-nu835dby`)와 최종 수를 합산하지 않는다.
- 자동 / 실제 API+격리 SQLite / passed: `tests/test_report_connection.py`의 mock와 요청 모드 live+주입 test_double 두 경우에서 같은 로그인 회차에 설문 6개, RPS/card 각각 3라운드, 답변/답변 없음/건너뜀, 보고서 저장, 정확 재전달, 앱 재생성 후 복원, 수정 후 stale를 검증했다. 원본 불변/비교 제외/원문 인용을 대조했다. 중간 집중 결과 `run-j6fyjeuo`, 최종 전체 결과에도 포함. test_double은 runtime_mode=mock/provider_execution=test_double이며 외부 모델 호출이 아니다.
- 자동 / 하네스 / incomplete: `run-ooq7dcvg/harness-results.json`의 **66 passed, 2 pending_manual**, failed/blocked/skipped 0. Python 테스트 수와 시나리오 수는 다른 집계다. 사람 평가가 남아 전체 완료로 표시하지 않는다.
- 자동 / 최종 관련 Node / passed: `node --test tests/frontend_auth.test.cjs tests/frontend_client.test.cjs tests/frontend_survey.test.cjs tests/frontend_games.test.cjs tests/frontend_practice.test.cjs tests/frontend_interview.test.cjs tests/frontend_report.test.cjs` → **87 passed**, exit 0. 로그 `artifacts/ai-report-connect-20261011/node-final.txt`. 동결 요청 재시도/늦은 응답/소유권/인용 원문 대조/설문 의미/네 모듈 결합 포함.
- 자동 / 기존 전체 frontend glob / failed: UI 담당의 중간 실행 **84 passed/3 failed**. `frontend_navigation.test.cjs`는 이전 앱의 `답변 작성` 및 hashchange 계약을 현재 교체된 script.js에 기대한다. 이 3건은 이번 범위에서 미해결이며 최종 관련 Node 87개에 제외했다. 해당 파일을 삭제하거나 통과로 변경하지 않았다. 실제 사용자 브라우저 뒤로가기/탭 위치 복원 확인을 대신하지 않는다.
- 운영 준비 / 백업 검사기 실패 후 수정: 최초 backup은 생성/무결성 확인됐으나 검증기가 테이블을 `runs`로 잘못 지정해 metadata 저장 전 실패(exec ee89e7). 실제 `practice_runs`로 고쳐 새 backup 생성/무결성/회차 해시 기록 완료(exec d4c2c9). 기존 DB는 두 실행 모두 read-only 연결로 읽었고 앱을 import하지 않았다. 최초 backup 파일은 보존했다.
- 로컬 재시작 / passed: 검증된 기존 uvicorn launcher 22964/child 29268만 종료한 뒤 같은 DB와 live/paid false로 재시작했다. 새 launcher **3192**, child **7688**, 2026-10-11 02:16:24 KST. `BACKUP.json`, `STARTUP.json`, server 로그는 `artifacts/ai-report-connect-20261011/`에 보존. 새로운 분석 요청 테이블만 add-only로 생성됐다.
- 읽기 전용 실행 서버 HTTP/SQLite / passed: 페이지와 같은 버전의 CSS/JS **10개 200/정확 바이트 일치**, 미인증 capability/run **2개 401**, 무결성 ok, 기존 모든 회차 snapshot hash 동일, 새 분석 요청 **0건**. `HTTP_AND_DB.json` 참고. client.js SHA256 `3A6566BEF6B57823ABDF917EF526B9351E9F1C1D1D8A94BBDB942002016C9040` 보존. 실제 사용자 답변·보고서 제출을 자동 검증에 사용하지 않았다.
- blocked / 직접 브라우저: cua.getState() apps=[], browsers=[]로 직접 시각/키보드/접근성 확인 불가. 사용자 보고서 확인은 pending_manual이다. 이전 기본 저장 흐름 사용자 확인을 새 보고서 확인으로 확대하지 않는다.
- skipped / 실제 외부 AI·운영 배포: 실행하지 않았다. 현재 서버에 live/paid false, 확인한 key/model 설정 없음. 기존 키 존재 여부를 전 환경에 대해 단정하지 않는다. 실제 모델·가격·회차 상한 준비 후 명시적 실행과 인용 사람 검토가 필요하다. 상세 안내 `AI_CONNECTION_SETUP.md`. 새로운 유료 호출 승인 요청 때문에 로컬 구현을 중단하지 않았다.

## 2026-10-11 — 미해결 탐색 3건 재현·현재 화면으로 연결 및 탭 복원 수정

- 사용자 질문에 대한 원인 조사: 이전에 범위 밖으로 제외한 3건을 `node --test tests/frontend_navigation.test.cjs`로 그대로 재현했다(exec 96e11e, 0 passed/3 failed). 실패 지점은 없는 `답변 작성` 버튼 2건과 없는 hashchange handler 1건이었다. 옛 `#app`/`#/run/r` 구조의 테스트가 교체된 탭 화면 script.js를 실행했다. app/static/app.js 역시 다른 흐름이므로 파일 경로만 바꾸는 방식은 사용하지 않았다.
- 실제 제품 누락 확인: 현재 navigateTab은 `.active` 클래스만 전환했으며 URL/이력 처리와 최초 fragment 복원이 없었다. 따라서 새로고침 때 마지막 탭이 복원되지 않고 브라우저 뒤로가기를 탭 이동으로 처리하지 않았다. 기존 면접 draft/pending journal은 이미 보존되므로 이 저장 계층은 변경하지 않았다.
- 자동 / 현재 화면 RED: 실제 HTML ID + script.js/interview.js를 사용하는 4개 검사로 변경한 뒤 **4 failed**를 확인했다(`red-current-tests.txt`). 원래 3가지 데이터 보호 목적을 현재 UX에 맞게 검사하고, 잘못된 주소/중복 이력 경계를 추가했다. 옛 검사/제품 파일은 `artifacts/navigation-fix-20261011/before/`에 남겼다.
- 제품 수정: 6개 탭 allowlist, URL fragment, pushState/replaceState, popstate/hashchange 동기화, 최초 탭 복원, 유효하지 않은 주소 복구, 같은 탭 이력/게임 통지 중복 방지. 탭 전환은 면접 DOM과 소유 회차를 재생성하지 않는다. 기존 저장 요청은 같은 회차에 완료되며 완료 후 현재 탭을 강제로 바꾸지 않는다. 임의 구형 라우팅이나 전체화면 앱을 재도입하지 않았다.
- 자동 / 집중 GREEN: 현재 navigation **4 passed**, exec 6bc768. 새로고침 초안·탭 복원, Back/Forward에서 정확 원문 유지, 지연 GET 중 이전 판 숨김과 현재 탭 유지, 저장 중 Back 시 단 한 번 POST/동일 회차/정확 원문, 잘못된 탭/중복 이력을 확인했다.
- 자동 / 전체 frontend / passed: `node --test tests/frontend_*.test.cjs` → **91 passed, 0 failed, 0 skipped**, exec 71febc. 모든 8개 frontend 테스트 파일을 포함하며 navigation 제외 없음. 로그 `artifacts/navigation-fix-20261011/node-all-final.txt`. 이전 87개와 합산하지 않는다.
- 자동 / 집중 Python / passed: `.\.venv\Scripts\python.exe -B -X utf8 -m tools.run_checks tests/test_frontend_integration.py -q` → **3 passed**, exit 0, guard 위반 0/provider transport 0. `artifacts/offline-checks/run-zapo8onu/RESULTS.json`. 서버 제품 코드 변경이 없어 전체 Python은 이번에 다시 실행하지 않았으며 이전 274개를 새 실행으로 표시하지 않는다.
- 읽기 전용 HTTP / passed: 최신 공통 자산 버전 `20261011-navigation1`의 페이지/자산 **10개 200/작업 파일 바이트 일치**, client.js 보존 해시 일치. `artifacts/navigation-fix-20261011/HTTP.json`. 서버 재시작 없음, 사용자 DB 접근 없음, 인증/변경 요청 없음, 외부 AI 호출 없음.
- pending_manual: 실제 브라우저의 Back/Forward/새로고침·키보드·스크린리더 확인은 자동 DOM/history 대역 검사와 구분한다. 이전 cua inventory에 apps/browsers가 없어 직접 브라우저 검증을 완료했다고 주장하지 않는다. 이전 미해결 3건은 코드/자동 검사 관점에서 해소됐으며 실제 AI·사람 평가 대기는 유지한다.

## 2026-10-12 — 팀원 AI 연결 보고 이후 현재 파이프라인 점검

- 사용자 보고: 팀원이 AI 연결을 구현했다고 함. 팀원 구현의 현재 폴더 병합 여부/외부 코드 위치는 미확인이다. 이번 실행이 팀원 AI의 live 검증이라고 주장하지 않는다.
- 읽기 전용 / root API·UI 감사: 현재 HTML은 rule-games/answers/interview-analysis를 호출하며 면접 질문 필터가 baseline만 허용한다. 새 보고서 저장은 기존 analyze/finalize 경로 및 완료 상태를 대체하지 않는다. 기존 analyze는 resource 게임 본 라운드 완료, finalize는 analysis/report_draft 및 resource 전체 완료를 요구한다.
- 읽기 전용 / 독립 도메인 감사: `/root/analysis_review`가 새 분석기에서 설문은 원본 표시용이고 새 비교 함수의 입력이 아니며, 신규 AI 추출 결과가 기존 mock 비교/적응형 질문 흐름으로 전달되지 않음을 확인했다. RPS/card에는 B01/B02 적격 관찰이 없고 B03 연결도 별도 정의·검토가 필요하다. 이는 코드상 연결 범위 확인이며 심리측정 타당화가 아니다.
- 읽기 전용 / 기록 화면: html/script.js의 getRecords/renderRecordsTable/deleteRecord는 localStorage를 사용한다. 서버 목록/재개는 practice.js, 서버 삭제 경계는 별도 API에 있다. 현재 기록 탭을 서버 조회·삭제 UI로 완료했다고 표시하지 않는다. README와 인계 문서를 정정했다.
- 자동 / 전체 Python / passed: `.\.venv\Scripts\python.exe -B -X utf8 -m tools.run_checks tests -q` → **274 passed**, exit 0. 근거 `artifacts/offline-checks/run-mhgbquze/RESULTS.json`. provider transport 0/guard 위반 0. 합성 격리 SQLite와 주입 AI 대역이며 사용자 DB/키를 사용하지 않았다.
- 자동 / 전체 frontend / passed: `node --test tests/frontend_*.test.cjs` → **91 passed, 0 failed, 0 skipped**, exec 201642. navigation 포함 전체 파일 실행. 실제 브라우저 검사와 구분한다.
- 하네스: 66 passed/2 pending_manual, overall incomplete 유지. 원래 게임의 비교/후속 질문 검사가 통과한 것을 현재 규칙 게임에서 해당 흐름을 완료했다는 증거로 바꾸지 않는다.
- 현재 제품의 계약상 제한: tests/test_report_connection.py는 규칙 게임을 unmapped/not_comparable, 면접 카드 비교를 insufficient_evidence, 보고서 저장 후 회차를 in_progress로 확인한다. 해당 통과가 전체 의미 연결이나 최종 완료를 증명하지 않는 이유다.
- 문서 산출물: `docs/ai-interview/PIPELINE_HANDOFF.md`에 현재/기존 경로와 미연결 지점, 점수 수정과 근거 비교의 구분, 인계 대상/제외 파일과 팀원 통합 작업을 정리했다. 제품 코드·실제 데이터·서버 설정 변경 없음, 파일 외부 전달·실제 AI 호출·배포 없음.

## 2026-10-29 Temporary Gemini limits

- Automated / local / passed: PowerShell parser reported no syntax errors in `tools/start_gemini_local.ps1`; inspection confirmed normal limits of 15 calls and 500000 micro USD and conditional temporary limits of 18 calls and 600000 micro USD.
- Manual / live / not run: restarting the user's server and submitting a Gemini request with the temporary limits; no live provider request was made during this change.

## 2026-11-23 나 알아보기 관련성 검토

- 자동 / 정적 정의 대조 / passed: `.venv/Scripts/python.exe -X utf8 artifacts/report-audit-20261123/question-coverage/survey_relevance.py` 실행 성공. 설문 6개, 게임과 면접의 직접 주제 연결이 모두 없는 항목 `R-UNMAPPED` 1개, O-B01/P-B01 원문 동일을 확인했다. 문항별 게임·면접 연결과 원문 및 소스 해시를 `survey-relevance.json`에 저장했다. 실제 사용자 응답·DB·외부 AI 호출은 사용하지 않았다.
- 자료 검토 / 완료: OPM 직무역량 정의와 직무 분석·평가 전략, O*NET 업무 기술 정의 원문을 웹 도구로 확인했다. 문항을 남길 이유는 내용상 업무 관련성과 면접 활용 가능성에 근거한 판단이다. 문항별 신뢰도, 변별도, 예측 타당도, 추가 정보의 통계적 가치를 측정한 것은 아니다.
- 제품 변경 / 미적용: 문항 삭제·교체·선택 응답 전환과 게임 연결 표시는 아직 적용하지 않았다. 관련 기능 회귀 테스트나 실제 설문 응답 시간 측정은 이번에 수행하지 않았다.

## 2026-11-24 대체 문항 적대적 검토

- 독립 내용·코드 검토 / 완료: Astra 6.2 High의 문항별 반례·제안 문안·선호 정보 손실·회차 호환성 검토를 `artifacts/report-audit-20261124/replacement-adversarial-review.md`에 기록했다. 원안 세 문항의 일괄 교체를 타당화한 것은 아니다.
- 합성 반례 / 예상 위험 재현: `.venv/Scripts/python.exe -X utf8 artifacts/report-audit-20261124/replacement_probe.py` exit 0. 메모리에서만 P/S/R의 정의를 새 동의형으로 바꿨을 때 과거 응답 형식과 종합 입력 표지가 세 건 모두 불일치했다. 새 ID만 등록하며 구 ID를 현행 목록에서 뺐을 때 과거 세 기록은 보존됐지만 종합 프롬프트에서 빠졌다. 이 위험은 현행 설문을 무대책으로 교체하는 가정의 결과이며 사용자 DB에서 손상을 재현한 것이 아니다.
- 불변 확인 / passed: `app/content.py`, `app/synthesis.py`, `app/survey.py`의 실행 전후 SHA-256과 합성 응답 원문이 동일했다. 외부 AI·사용자 DB·브라우저·전체 회귀는 실행하지 않았다. 제품 구현은 미변경이다.
- 공식 자료 / 확인: JOBDA 공식 게임 설명과 NCS 2025.12 문제해결능력 분권을 웹 도구로 확인했다. 통합 PDF는 이번 재조회에서 timeout이 발생하여 성공한 분권을 근거로 삼았다. 문항의 심리측정 타당도·실제 시간 절약·도입 효과는 이번 검토로 입증되지 않았다.

## 2026-11-24 6단계 동의형 업무 설문 도입 검증

- 사용자 승인 반영: 새 연습의 핵심 3문항과 승인한 대체 문항 ②③을 합쳐 5문항으로 구성했다. 여섯 문구를 모두 표시하고 초기 선택은 비워 두며, 경험 없음과 판단 어려움을 배타적 결측으로 저장한다. 기존 6문항 회차·구형 요청은 원래 형식과 응답을 유지한다.
- TDD / 확인: 새 문항집 POST가 422를 반환하는 초기 실패 4건, 5문항 게임/확정 경계 실패 2건, 결측 표시·체험·409 충돌 및 형식 오류·공급자 입력 누락의 반례를 수정 전에 확인하고 수정 후 통과시켰다. 실패 로그와 격리 결과는 `artifacts/work-survey-20261124/`에 남겼다.
- 자동 / 전체 Python / passed: `.venv/Scripts/python.exe -u -B -X utf8 artifacts/work-survey-20261124/guarded_checks.py --output-root artifacts/work-survey-20261124/final-checks tests -q` 결과 **519 passed**, exit 0. 실제 ASGI 요청 수, 공급자 전송 시도 0, guard 위반 0, 소스 해시 일치 여부는 `final-summary.json` 및 `final-checks/run-f62ee94655c24fecb8d81cbc81dd4916/RESULTS.json`에 기록했다. 합성 격리 SQLite만 사용했다.
- 실행 환경: 표준 launcher의 `tempfile` 후보 이름 생성이 정체돼 UUID로 부모의 새 attempt 디렉터리만 생성하는 로컬 wrapper를 사용했다. 자식 프로세스의 원래 DB·네트워크·공급자·쓰기 차단 guard와 canary는 변경하지 않았다. 일반 pytest로 확보한 초기 RED/GREEN을 외부 호출 차단 검증으로 잘못 집계하지 않는다.
- 자동 / 전체 frontend / passed: `node --test tests/frontend_*.test.cjs` 결과 **141 passed, 0 failed**. 실제 프런트엔드 스크립트와 합성 DOM/transport에서 라벨·무기본선택·결측·5/6 회차 전환·게임 진입·최종 확정·저장 충돌·기존 화면 안내를 확인했다. 로그 `node-tests-final.txt`.
- 독립 / 적대적 재검토 / 완료: Astra 6.2 High가 최초 6개 문제를 지적했고 수정 후 지원하는 생성·재개·제출·보고서 경로에서 중요/중대 잔여 결함을 발견하지 못했다. 409 후 45초·새로고침·재시도에서도 원래 결측과 결정 시각이 보존되고, 로그아웃 뒤 늦은 성공 응답이 개인 화면을 복원하지 않는 추가 반례를 검사했다. 기존 6형식 설문의 종합 입력 JSON과 digest는 변경 전과 일치했다. `implementation-review.md`.
- 검증 한계: 실제 브라우저의 시각적 화면·키보드 조작, 실제 응답자 인지 면접·시간 절약·신뢰도/변별도·공급자 live 실행은 미실행이다. 서버 재시작, 원격 GitHub 게시, Word/PDF 갱신도 이번에 수행하지 않았다. 자동 검사는 설문 도입의 심리측정 타당도를 증명하지 않는다.

