# 팀원 인계 전 파이프라인 점검 — 2026-10-12

> **2026-10-13 후속 구현:** 아래는 당시 점검 이력이다. 현재 소스에는 근거 연결·조건부 후속 답변·현재 게임용 최종 확정·서버 기록 화면을 구현했다. 최신 실행법/인터페이스/검증 한계는 [DELIVERY_20261013.md](DELIVERY_20261013.md)와 CURRENT_STATE.md 첫 항목을 따른다. 사용자 확인으로 AI 코드는 팀원 컴퓨터에 별도 보관 중이며 실제 통합은 아직 미실행이다. 게임의 B01~B03 직접 매핑은 여전히 활성화하지 않았다.

> 같은 날짜 후속 결정: 사용자는 현재 가위바위보·카드 유지 및 별도 규칙 선택 관찰을 선택했다. 정보 확인·자원 배분은 설문/면접 근거로 설명한다. 아래 작업 1의 게임 선택은 확정됐으며 다시 선택을 요구하지 않는다. 문항별 논리·과제 한계·교수 질의 답변과 미활성 RG01 제안은 `EVIDENCE_LINKAGE_EXPLANATION.md`를 따른다. 아래 파이프라인 미연결 항목은 아직 완료되지 않았다.

## 판단

현재 `E:\SchoolContest` 파일은 **같은 회차의 원본 저장·기본 면접 분석·자료를 모아 보여주는 보고서**까지 연결된 개발본이다. **현재 가위바위보·카드 게임과 성향 응답을 비교해 조건부 후속 면접과 최종 보고서로 이어지는 전체 파이프라인 완성본은 아니다.**

AI 담당 팀원에게 통합 작업을 위한 소스로 인계하는 것은 타당하다. 전달 시 아래 미연결 부분을 명시해야 한다. 팀원이 구현한 AI 코드가 현재 폴더에 반영됐는지, 별도 보관 중인지는 아직 확인되지 않았다. 팀원의 외부 AI 실행 성공/인터페이스 호환성을 이번 점검으로 확인했다고 기록하지 않는다.

## 현재 연결 상태

| 구간 | 현재 코드에서 확인한 상태 |
|---|---|
| 로그인 → 회차 → 성향 6문항 | 서버 저장·원본 의미/버전·재조회 연결 |
| 가위바위보/카드 각 3라운드 | 서버 정오답·점수·행동 이벤트 저장 연결 |
| 중립 기본 텍스트 면접 3개 | 답변 저장·수정 버전·초안/재조회 연결 |
| 기본 면접 → AI 어댑터 → 검증된 인용 | 신규 `/interview-analysis` 경로 구현, 합성 transport 검증. 실제 팀원 AI는 미확인 |
| 설문·규칙 게임·기본 면접 → 같은 보고서 | 신규 `interview_report`에서 함께 표시 |
| 현재 규칙 게임 → B01/B02/B03 근거 | **미연결**. `unmapped/not_comparable`; 기존 매핑은 resource-bridge용 |
| 설문 응답 + 게임 관찰 + 면접 인용 → 비교 | **현재 새 보고서에서 미완성**. 설문은 별도 원본 목록이며 새 비교 함수의 입력으로 사용되지 않음 |
| 비교 → 조건부 후속 질문 → 후속 답변 | **현재 HTML 흐름에 미연결**. 기존 분석기에는 기능이 있으나 새 흐름과 이어지지 않음 |
| 새 보고서 → 회차 최종 완료 | **미연결**. 신규 결과는 초안이고 `in_progress` 유지; 기존 finalize는 별도 analysis/resource 게임 완료를 요구 |

## 코드 근거와 두 경로의 차이

현재 HTML 경로:

```text
html/practice.js → /surveys → run.records
html/games.js → /rule-games → run.rule_games
html/interview.js → /answers → 중립 기본 답변 원본/버전
html/report.js → /interview-analysis → app/interview_analysis.py
  → 현재 질문·답변만 AI 입력 → 인용/버전/스키마 검증
  → run.interview_analysis + run.interview_report
  → 기본 면접 카드 + 설문 원본 목록 + 규칙 게임 결과 목록
```

- `html/interview.js:11`은 `question_mode=baseline` 및 `conditioned_on_prior_evidence=false`만 표시한다. 현재 화면에서는 적응형 후속 질문을 작성할 수 없다.
- `html/report.js`는 `/interview-analysis`를 호출하며 기존 `/analyze` 및 `/finalize`를 호출하지 않는다.
- `app/interview_analysis.py::_comparison`은 적격 resource 게임 metric과 면접 요소 상태를 사용한다. 설문 선택 라벨/강도를 읽지 않으며 검증된 방향 규칙이 없어 자동 지지 판정도 하지 않는다.
- 같은 모듈의 `_survey_report`는 원본 표시 목록을 만들고 `_rule_games_report`는 현재 두 규칙 게임을 `unmapped/not_comparable`로 표시한다. `_suggestions`는 빠진 면접 설명 요소에 대응하는 고정 연습 안내다. 맞춤 후속 질문 생성과 다르다.

원래 설계 경로:

```text
app/game.py의 resource-bridge → run.game.metrics
기본 답변 + 설문 원본 → /analyze → app/analysis.py::analyze_run
  → 기본 mock 추출/비교/조건부 후속 질문
  → run.analysis + run.report_draft + run.questions
후속 답변 → /finalize → 원래 완료 조건 재검사 → run.report
```

- `app/analysis.py::_adaptive_question`에는 실제 설문 라벨·게임 기회를 인용하는 후속 질문 생성 코드가 있다. 그러나 이 분석기는 신규 `interview_analysis`의 live 추출 결과를 소비하지 않고 자체 mock 추출 경로를 사용한다.
- `app/main.py`의 `/analyze`는 `snapshot.game.rounds`에 완료한 본 라운드를 요구한다. `run.rule_games`에 저장된 가위바위보/카드 완료만으로 통과하지 않는다.
- `/finalize`는 기존 `analysis/report_draft`와 resource 게임 전체 완료를 요구한다. 신규 `interview_report`를 만든 것을 최종 완료로 대체하지 않는다.

## ‘점수에 반영’의 의미

원래 설계는 면접 답변으로 저장된 게임 점수나 설문 선택을 소급 수정하는 방식이 아니다. 게임 점수는 정오답 규칙의 결과이고, 설문 1~6은 당시 선택한 응답 위치다. 둘을 합쳐 성격 점수로 만들지 않는다.

의도한 연결은 **각 원본을 보존한 뒤 같은 행동에 관한 근거를 비교하고, 차이나 부족한 설명을 후속 면접에서 확인하는 것**이다. 기본 면접 AI에 설문 강도·게임 점수를 먼저 넣지 않는 입력 격리는 유지해야 한다. 현재 빠진 것은 이 기본 추출 이후의 연결이다.

현재 게임에는 B01의 결정 전 타인 정보 확인과 B02의 개인·팀 자원 배분 기회가 없다. 규칙 전환을 곧바로 B03으로 이름만 바꿔 연결해서도 안 된다. 새 정보 노출·초기 선택·재검토 기회의 정의와 검토된 매핑이 필요하다.

## 팀원과 마무리할 작업

1. **최종 시연 게임과 관찰 행동 확정.** 원래 B01/B02/B03 설계를 유지하면 기존 resource-bridge 게임 연결을 활용할 수 있다. 현재 RPS/card를 유지한다면 실제 관찰 가능한 행동에 맞는 별도 정의·관련 설문/질문·검토된 매핑이 필요하다. 없는 관찰 기회를 가짜 데이터로 채우지 않는다.
2. **기본 AI 추출 결과와 비교 단계 연결.** 팀원 어댑터가 현재 neutral 질문/답변 입력과 엄격한 인용 출력 계약을 만족하는지 확인하고, 그 검증된 추출물을 설문·적격 게임 비교 단계에 전달한다. 기존 mock 추출로 다시 덮어쓰지 않는다.
3. **조건부 후속 면접 연결.** 근거 참조·질문 원문·버전·공개된 설문/게임 정보를 저장하고, UI에서 후속 질문/답변을 지원한다. 후속 답변은 `conditioned_on_prior_evidence=true`로 분리하며 중립 기본 근거를 변경하지 않는다.
4. **최종 보고서/완료 조건 정합화.** 선택한 게임과 필요한 면접 단계의 실제 완료 조건에 맞춰 버전 고정 보고서를 저장한다. 현재 `/finalize`의 조건을 무조건 우회하지 않는다.
5. **하나의 합성 회차에서 전체 통합 확인.** 설문 → 최종 게임 → 기본 면접 → 팀원 AI → 비교 → 후속 질문/답변 → 최종 보고서 → 재조회. 인용/숫자/버전과 오류·재시도·삭제도 함께 확인하고 live/mock을 구분한다.

추가 화면 인계 사항: 현재 HTML의 `응시 기록` 탭은 `html/script.js`의 예전 localStorage 표를 사용한다. 서버 회차 목록/재개는 설문 영역의 `practice-runs`에 연결되어 있다. 서버 삭제 API는 존재하지만 이 기록 탭의 삭제 버튼은 서버 삭제 기능이 아니다. 전체 제품 인계 시 해당 화면도 서버 기록과 연결해야 한다.

## 전달할 파일과 실행

HTML 폴더만으로는 서버 저장·비교·AI 계약이 전달되지 않는다. 최소한 다음을 함께 전달한다.

- `app/`, `html/`, `migrations/`, `tests/`, `tools/`, `ai_interview_codex/`
- `requirements.txt`, `pytest.ini`, `conftest.py`, `AGENTS.md`, `.env.example`, `README.md`
- `docs/ai-interview/`의 현재 상태·검증·AI 연결·파이프라인 인계 문서

`.venv`, 실제 `.env`/키, `interview.db` 및 DB 백업, 사용자 답변이 있는 artifacts, 캐시/브라우저 프로필은 소스 전달 묶음에서 제외한다. 같은 프로젝트 폴더 안에 있으므로 ‘폴더 전체를 그대로 압축’하면 소스 외 자료도 함께 전달될 수 있다. 원본 파일을 삭제하라는 의미는 아니다.

팀원은 별도 폴더에 받아 기존 AI 구현과 대조·병합하고, 자신의 새 개발 DB로 시작한다. Python 의존성은 `requirements.txt`로 재설치하고 키는 서버 환경에만 둔다. `AI_CONNECTION_SETUP.md`는 어댑터 계약/환경 안내이며 팀원의 구현을 덮어쓰라는 지시가 아니다.

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
$env:DATABASE_URL = 'sqlite:///./team-development.db'
.\.venv\Scripts\python.exe -B -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-access-log
```

검증은 사용자 DB를 여는 직접 pytest 대신 안전 실행기를 사용한다.

```powershell
.\.venv\Scripts\python.exe -B -X utf8 -m tools.run_checks tests -q
node --test tests/frontend_*.test.cjs
```

## 이번 점검의 한계

읽기 전용 제품 코드 감사와 합성 데이터 자동 검사다. 현재 보고서의 저장/복원 검사는 전체 맞춤 면접 연결 완료의 증거가 아니다. 팀원 AI 코드/실제 유료 호출/직접 브라우저/사람 평가/운영 배포는 이번 확인 범위에 포함하지 않았다. 실제 실행 결과는 `VERIFICATION.md`의 2026-10-12 항목을 따른다.
