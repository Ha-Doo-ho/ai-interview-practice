# AI 면접 연습 서비스 — Codex 실행 패키지

작성 기준: 2026-09-16. 이 패키지는 **Codex에 맡길 구현 지시문·설계 기준·설정 템플릿·수용 시나리오**다. 완성된 앱이나 실행을 마친 테스트 프로그램이 아니다.

목표는 **성향 응답의 강도를 원형대로 보존하고, 비교 가능한 게임·면접 근거를 연결해 추가 연습 방향을 제공하는 서비스**다. 실제 채용검사의 점수·성격·거짓말 여부를 판정하지 않는다.

## 사용 방법

1. ZIP을 풀어 기존 프로젝트 루트에 `ai_interview_codex` 폴더를 둔다. 기존 소스와 `.codex`, `AGENTS.md`를 덮어쓰지 않는다.
2. 그 프로젝트 폴더에서 Codex를 실행한다. Windows에서 `codex`가 PowerShell 실행 정책 때문에 실패하면, 설치되어 있는 `codex.cmd`를 사용한다. 계정에서 지원되는 모델을 선택한다.
3. 아래 지시문을 붙여 넣는다. 상세 명령 전체를 직접 붙여 넣으려면 [MASTER_PROMPT.md](MASTER_PROMPT.md)를 사용한다.

```text
ai_interview_codex/MASTER_PROMPT.md를 읽고 실행하세요.
참조된 REQUIREMENTS.md, DATA_CONTRACT.md, ORCHESTRATOR.md,
DELIVERY_PHASES.md, HARNESS.md, CODEX_SETUP.md와 harness/scenarios.json도 읽으세요.
먼저 기존 저장소와 현재 Codex의 설정·서브에이전트 지원을 확인하세요.
기존 파일과 사용자 변경을 보존하고, 이 명세의 텍스트 MVP를 구현·검증하세요.
계획만 제시하고 멈추지 말고 승인된 로컬 작업을 진행하세요.
실제 실행 결과와 미실행 항목을 구분하고 docs/ai-interview/CURRENT_STATE.md에 남기세요.
```

모델을 명시하려면 해당 모델이 사용 가능한 환경에서 `codex.cmd -m gpt-6-astra` 또는 `codex.cmd -m gpt-5.6-sol`로 시작할 수 있다. 모델 접근 권한이나 설치 버전이 다르면 사용 가능한 모델로 진행하고 차이를 기록한다. 다른 이름을 이 두 모델의 별칭이라고 가정하지 않는다.

## 파일 안내

| 파일 | 용도 |
|---|---|
| [MASTER_PROMPT.md](MASTER_PROMPT.md) | Codex에 주는 전체 실행 명령 |
| [REQUIREMENTS.md](REQUIREMENTS.md) | 기능 범위, 강도 해석, 금지된 추론, 완료 기준 |
| [DATA_CONTRACT.md](DATA_CONTRACT.md) | 저장 필드, 버전, 상태, 비교 조건, 근거 계보 |
| [ORCHESTRATOR.md](ORCHESTRATOR.md) | 역할 분담, 병렬 작업, 파일 소유권, 통합 규칙 |
| [DELIVERY_PHASES.md](DELIVERY_PHASES.md) | 구현 순서와 단계별 검증 |
| [HARNESS.md](HARNESS.md) | 실제 앱 테스트로 구현해야 할 검증 명세 |
| [harness/scenarios.json](harness/scenarios.json) | 합성 입력·기대 결과·금지 결과를 담은 수용 사례 |
| [CODEX_SETUP.md](CODEX_SETUP.md) | 현재 설정 형식, 기존 설정에 병합하는 절차 |
| [templates/AGENTS.md](templates/AGENTS.md) | 프로젝트 상시 지침 초안 |
| [templates/config.toml](templates/config.toml) | `.codex/config.toml`에 병합할 설정 초안 |
| `templates/agents/*.toml` | `.codex/agents/`에 넣을 역할별 에이전트 설정 |
| [RESUME_PROMPT.md](RESUME_PROMPT.md) | 다음 Codex 세션에서 이어서 작업할 명령 |
| [SOURCES.md](SOURCES.md) | 첨부 자료 반영 범위와 공식 설정 문서 |
| [PACKAGE_VALIDATION.md](PACKAGE_VALIDATION.md) | 패키지에 실제로 수행한 검사와 수행하지 않은 작업 |

`toml.md`는 설명용 Markdown 파일명일 뿐 Codex 설정 파일 형식이 아니다. **실제 설정은 `.toml`, 작업 지침은 `.md`**로 분리했다. 역할 TOML은 지원되는 Codex에서 명시적으로 선택·호출되어야 하며, 파일이 있다는 이유만으로 모든 역할이 자동 실행되지 않는다.

첨부 계획서는 텍스트 면접을 우선 구현하는 방향을 제안한다. 이번 패키지는 후속 대화에서 요청한 네 가지 성향 입력·게임·근거 통합까지 텍스트 MVP 범위로 정리했다. 영상 처리는 다음 단계다. 원본 계획서와 참고 화면은 패키지에 재배포하지 않았다.

패키지 자체의 형식 검사는 앱의 정확도나 심리측정 타당성을 증명하지 않는다. `HARNESS.md`의 시나리오를 실제 서비스에 연결한 테스트와 사람 검토가 별도로 필요하다.
