# 결, 면접 연습

나 알아보기 설문, 게임 기록, 텍스트 면접을 저장하고 출처별 근거와 다음 연습을 보여주는 로컬 웹앱입니다. 합격 확률·성격 점수·진실성 판정을 제공하지 않습니다.

2026-11-25: 새 연습의 나 알아보기를 **업무 행동 5문항·문구가 모두 표시되는 6단계 동의형**으로 변경했습니다. 전혀 그렇지 않다 / 그렇지 않다 / 그렇지 않은 편이다 / 그런 편이다 / 그렇다 / 매우 그렇다 중 선택하며, 초기 선택은 비어 있습니다. `해당 경험 없음`과 `판단하기 어려움`은 별도 결측으로 저장합니다. 기존 회차는 당시의 6문항과 응답 형식을 보존합니다. 대안별 예상 결과 비교와 반복 결과 활용의 두 새 문항은 자체 업무 행동 자기보고이며 공식 능력 점수가 아닙니다. [설계와 해석 범위](docs/superpowers/specs/2026-11-24-work-survey-design.md)를 확인하세요.

동료가 기존 설치를 갱신할 때는 자신의 변경 내용을 확인한 뒤 `git pull --ff-only origin main`으로 내려받고 서버를 다시 시작하세요. 브라우저를 새로고침한 뒤 **새 연습을 생성**하면 5문항을 확인할 수 있습니다. 이전 회차를 이어 하면 기존 문항 구성이 유지됩니다.

2026-11-25 게시 전 재검증: 전체 Python **519개**, frontend **141개** 통과. 격리한 합성 SQLite와 mock만 사용했으며 실제 외부 AI 호출은 하지 않았습니다. 사람 평가 시나리오 2개와 브라우저 육안 검증은 별도로 남아 있습니다.

2026-11-19: 요청 변경 처리·공간 배치·반복 업무 경험을 묻는 선택 면접 13문항과 **세 활동 종합 피드백**을 추가했습니다. 설문 원척도, 8종 게임 기록, 최신 면접 답변을 함께 담은 프롬프트를 확인하고 별도 AI 평가를 요청할 수 있습니다. 기존 기본 면접 분석은 유지하며, 종합 결과는 잘한 점·보완점과 비교 제한·개선계획·확인 질문으로 구분합니다. 기존 진행 회차에서는 빠진 업무 경험 문항을 추가할 수 있습니다. [종합 기능과 한계](docs/ai-interview/THREE_SOURCE_SYNTHESIS_20261119.md)를 확인하세요.

이번 변경의 전체 자동 검사: Python 511개, frontend 134개 통과. 최종 보완 후 종합 기능 집중 검사 10개도 통과했습니다. 실제 외부 AI 응답 품질과 브라우저 육안 검증은 다음 검증 항목입니다. 종합 입력 한도는 `AI_SYNTHESIS_MAX_INPUT_TOKENS`로 설정하며 기존 비용·호출수 한도는 공유합니다.

2026-11-17: 도형 회전·길 만들기·마법약 만들기를 게임 탭의 **추가 역량 게임 · 선택 연습**에 구현했습니다. 기존 다섯 게임은 유지합니다. 새 게임의 연습/본게임, 서버 채점, 문항별 기록, 재시작 및 보고서 결과 표시는 연결되어 있습니다. 새 세 게임에 대한 AI 해석은 아직 포함하지 않습니다. 상세 내용은 [게임 구현 결과](docs/ai-interview/GAME_IMPLEMENTATION_RESULT.md)를 참고하세요.

2026-10-29: 새 연습 회차는 가위바위보 → 숫자 카드 → 약속 요일 → 약속 장소 → 버스 번호 순서입니다. 마지막 세 게임은 공통 난이도와 각 10문항을 사용합니다. 각 문항과 게임별 결과는 서버에 기록하며, 보고서의 게임 연습 제안은 면접 분석 후 별도로 요청합니다. 기존 회차는 당시의 두 게임 완료 정책을 유지합니다. 실제 브라우저 전체 여정 및 실제 외부 AI 검증 현황은 [현재 상태](docs/ai-interview/CURRENT_STATE.md)와 [검증 기록](docs/ai-interview/VERIFICATION.md)을 확인하세요.

2026-10-13: 현재 가위바위보/카드 게임을 유지한 근거 연결, 조건부 후속 질문·답변, 최종 보고서 확정, 서버 기록 조회·이어하기·삭제를 연결했습니다. 로컬 합성 데이터로 검증했으며 팀원 컴퓨터의 실제 AI 코드 통합과 실제 브라우저 수동 검증은 별도입니다. [전달본 실행·AI 연결 안내](docs/ai-interview/DELIVERY_20261013.md)를 먼저 읽어 주세요.

Python/FastAPI, SQLAlchemy, HTML/CSS/JavaScript를 사용합니다. 로컬 기본 DB는 SQLite이며 MySQL 연결 설정도 지원합니다. **SQLite 검증과 MySQL 검증은 별개**입니다. 실제 검증 현황은 [VERIFICATION.md](docs/ai-interview/VERIFICATION.md)를 확인하세요.

## Windows PowerShell 실행

아래 명령을 한 줄씩 실행합니다. 시스템 관리자 권한은 일반 앱 실행에 필요하지 않습니다.

```powershell
git clone https://github.com/Ha-Doo-ho/ai-interview-practice.git
Set-Location -LiteralPath .\ai-interview-practice
```

처음 설치할 때만:

```powershell
py -3 -m venv .venv
```

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

서버 시작:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-access-log
```

브라우저에서 <http://127.0.0.1:8000>을 엽니다. 새 계정을 만들고 ‘새 연습 시작’을 선택하세요. 중지는 서버 창의 `Ctrl+C`입니다. 기본 DB는 프로젝트의 `interview.db`이며 버전 관리에서 제외합니다.

## 분석 모드와 데이터

현재 HTML은 `저장 근거 보기 · AI 미사용`과 명시적인 `AI 분석 요청`을 구분합니다. `/interview-analysis`는 서버 키·허용 모델·비용 한도·출력 인용을 검사합니다. 그 뒤 `/evidence-linkage`로 근거를 연결하고 `/interview-finalize`로 현재 게임용 보고서를 확정합니다. OpenAI 및 Gemini 서버 연결 코드가 포함되어 있습니다. 게임과 AI 미사용 보고서는 API 키 없이 실행할 수 있으며 실제 AI 분석에는 별도 서버 설정이 필요합니다. 기존 resource-bridge용 `/analyze`·`/finalize`는 별도 경로로 보존했습니다. [AI 연결 설정](docs/ai-interview/AI_CONNECTION_SETUP.md), [Gemini 설정](docs/ai-interview/GEMINI_SETUP.md), [현재 상태](docs/ai-interview/CURRENT_STATE.md)를 함께 확인하세요.

서버는 프로세스 환경변수를 읽으며 `.env` 또는 `.env.example`을 자동으로 불러오지 않습니다. `.env.example`은 키가 없는 설정 예시입니다. `tools/start_gemini_local.ps1`은 키를 숨김 입력으로 받아 서버를 시작하지만, 기존 로컬 설정의 모델·단가·비용 한도를 포함하므로 사용 전 본인 환경에 맞게 확인해야 합니다. 이 스크립트는 기존 `interview.db`를 요구하므로 처음 설치할 때는 위 일반 서버 시작 명령으로 DB를 먼저 생성합니다. 이번 공개 소스 업로드에서 실제 AI 호출은 실행하지 않았습니다.

공개 저장소에는 API 키, 실제 사용자 DB, 캡처 화면 및 로컬 테스트 산출물을 포함하지 않습니다. 테스트 fixture와 보고서 JSON 예시는 합성 데이터입니다. 검증 문서의 `artifacts/` 경로는 작성자의 로컬 실행 증거 위치이며 저장소에 함께 올라오지 않습니다.

슬라이더 중앙 확정과 무조작 시간 초과는 다른 상태로 저장합니다. 상상한 타인 관점도 응답자는 본인이며, 순위에 없는 항목은 싫어함을 뜻하지 않습니다. 정보 창 열기는 이해 여부를 뜻하지 않습니다. 새 정보 뒤 선택 유지는 변경과 구분되는 유효 관찰입니다.

현재 HTML의 ‘응시 기록’ 탭과 성향 설문 영역에서 본인 서버 회차를 조회·재개할 수 있습니다. 기록 탭의 삭제는 실제 서버 삭제 API를 호출합니다. 서버는 원본·보고서·캐시·작업 내용을 제거하고 늦게 끝나는 작업의 저장을 막습니다. 기술적인 삭제 차단 메타데이터와 백업 정책은 [운영 문서](docs/ai-interview/OPERATIONS.md)를 참고하세요.

## 검증

```powershell
.\.venv\Scripts\python.exe -B -X utf8 -m tools.run_checks
```

한 파일만 검사하려면:

```powershell
.\.venv\Scripts\python.exe -B -X utf8 -m tools.run_checks tests/test_backend.py
```

실행기는 **앱을 import하기 전**부터 새 임시 SQLite DB와 mock 환경을 적용하고 외부 네트워크·실제 모델 전송을 차단합니다. 실제 TestClient 요청에 필요한 Python 내부 로컬 소켓만 허용합니다. 매 실행의 새 `artifacts/offline-checks/run-*/` 폴더에 소스 해시, 실제 테스트 결과, 시나리오 결과와 로그를 기록하므로 기존 DB와 보고서를 덮지 않습니다. 콘솔의 `Evidence:` 경로를 확인하세요. 직접 pytest를 실행하면 전역 app이 먼저 기본 DB를 열 수 있으므로 검증에는 위 실행기를 사용하세요.

자동 테스트는 합성 데이터와 임시 SQLite DB를 사용합니다. 원본 수용 시나리오는 `ai_interview_codex/harness/scenarios.json`, 테스트 연결은 `@pytest.mark.scenario`입니다. 일부 테스트만 실행했을 때 미실행 시나리오는 통과로 세지 않습니다. 사람 평가 SCN-051/053은 `pending_manual`로 분리합니다. 유료 API 호출·운영 배포·효과성 검증은 이 로컬 실행에 포함되지 않습니다.

2026-11-17 검증 기록: 전체 Python 495개·frontend 128개 통과. 이후 최종 확정 경로 보호 수정 및 회귀 테스트 추가 후 관련 Python 11개를 별도로 통과했습니다. 수용 시나리오 66개 통과·사람 평가 2개 대기입니다. [현재 상태](docs/ai-interview/CURRENT_STATE.md), [실행 근거](docs/ai-interview/VERIFICATION.md), [현재 게임용 합성 최종 보고서](docs/ai-interview/completion-example-20261013.json)를 참고하세요. 아래 명령은 기존 resource-bridge 경로의 별도 합성 예시를 생성합니다.

```powershell
.\.venv\Scripts\python.exe -B -X utf8 -m tools.run_checks --sample
```

새 합성 예시는 해당 실행 폴더의 `sample/`에 저장합니다. 기존 `docs/ai-interview/sample-report.json`은 보존합니다.
