# Codex 설정과 적용 절차

확인 기준일: 2026-09-16. 제공된 설정은 **템플릿**이며, 사용자의 실제 Codex 설치에 적용하거나 실행해 검증한 설정은 아니다. 설치 버전·계정·관리 정책에 맞는지 먼저 확인한다.

## 1. 파일의 역할

| 이 패키지의 원본 | 프로젝트에 적용할 위치 | 의미 |
|---|---|---|
| `templates/AGENTS.md` | 프로젝트 루트 `AGENTS.md`에 필요한 부분 병합 | Codex가 읽는 프로젝트 지침 |
| `templates/config.toml` | `.codex/config.toml`에 키 단위 병합 | 서브에이전트 기본 실행 설정 |
| `templates/agents/*.toml` | `.codex/agents/*.toml` | 역할별 사용자 정의 에이전트 |
| `MASTER_PROMPT.md`, 나머지 설계 문서 | `ai_interview_codex/`에 보관 | 명시적으로 읽도록 지시하는 작업 명세 |

`toml.md`는 Markdown이다. 그것을 `.codex/config.toml` 대신 두지 않는다. `ORCHESTRATOR.md`도 Codex가 자동 인식하는 특별 설정명이 아니다. 메인 지시문에서 읽고 따를 역할 설명이다. `HARNESS.md`는 검증 명세이며 파일명 자체로 테스트가 실행되지 않는다.

프로젝트별 사용자 정의 에이전트는 `.codex/agents` 아래 TOML 파일에 정의한다. 각 역할의 `name`, `description`, `developer_instructions`와 선택적인 모델·추론·sandbox 설정을 사용한다. 프로젝트 지침은 `AGENTS.md`로 제공한다. [공식 서브에이전트 문서](https://learn.chatgpt.com/docs/agent-configuration/subagents), [공식 AGENTS.md 문서](https://learn.chatgpt.com/docs/agent-configuration/agents-md)

## 2. 템플릿 설정

```toml
[agents]
enabled = true
max_concurrent_threads_per_session = 3
default_subagent_model = "gpt-5.6-sol"
default_subagent_reasoning_effort = "medium"
```

동시 개수 3은 메인을 제외한 서브에이전트 한도다. 기존 `[agents]`가 있으면 두 번째 테이블을 만들지 말고 필요한 키만 병합한다. 기존 `enabled=false` 또는 더 낮은 동시성 한도가 있으면 이를 유지하고 그 범위에서 순차/병렬 작업을 진행한다. 프로젝트 소유자가 그 제한 변경을 이미 명시적으로 허용한 경우에만 그 승인 범위를 적용한다. 오래된 `max_threads` 같은 별칭과 충돌하는 설정을 함께 남기지 않는다. 버전에 맞는 형식은 [공식 설정 참조](https://learn.chatgpt.com/docs/config-file/config-reference)에서 확인한다.

역할 템플릿은 도메인 검토에 `gpt-6-astra`, 구현·QA에 `gpt-5.6-sol`을 지정한다. 메인 모델은 이 설정 파일이 강제로 바꾸지 않는다. 계정에서 사용할 수 있는 모델을 선택하고 명시된 역할 모델을 쓸 수 없으면 현재 지원되는 모델로 조정한 사실을 기록한다. [공식 모델 선택 문서](https://learn.chatgpt.com/docs/models)

읽기 전용 검토 역할은 `sandbox_mode = "read-only"`를 제안한다. 실제 실행 환경의 상위 정책과 세션 설정도 확인해야 하며, 이 템플릿이 보안 경계를 새로 보장한다고 가정하지 않는다. 구현 역할에는 권한 확대 설정을 넣지 않았고 부모 실행 환경의 적용 가능한 권한을 따른다.

## 3. 기존 프로젝트에 적용할 순서

1. 프로젝트 루트인지 확인하고 현재 지침·설정과 사용자 변경을 읽는다. 전역 홈 설정을 변경하지 않는다.
2. 필요한 diff를 만든다. 루트 지침은 짧게 유지하고 상세 문서는 `ai_interview_codex`를 참조한다.
3. 이름이 겹치는 역할 파일이 있으면 내용과 목적을 확인한다. 기존 것을 덮어쓰지 말고 병합하거나 고유한 이름으로 조정한다. 실제 역할 이름과 배정 문서가 일치하도록 한다.
4. TOML 구문을 검증하고, 설치된 Codex의 지원 형식과 실제 역할 인식을 확인한다. 구문 파싱 성공과 Codex 로딩 성공을 구분한다.
5. 프로젝트 신뢰나 설정 제한이 있으면 정상적인 제품 절차를 따른다. 신뢰 DB를 몰래 수정하거나 권한 제한을 해제하지 않는다.
6. 변경이 현재 세션에 반영되지 않으면 새 세션에서 확인한다. 지금 사용 가능한 도구로 진행할 수 있는 구현은 계속한다. 다음 세션에는 `RESUME_PROMPT.md`를 사용한다.

Windows CLI를 이미 설치한 경우 다음은 확인·시작 예다. 명령이 존재하는지부터 확인하고 출력의 비밀 값을 공유하지 않는다.

```powershell
codex.cmd --version
codex.cmd -m gpt-6-astra
```

Sol로 메인 작업을 실행하려면 두 번째 줄을 `codex.cmd -m gpt-5.6-sol`로 바꿀 수 있다. VS Code 확장이나 다른 클라이언트에서는 해당 클라이언트의 모델 선택·설정 지원을 확인한다. `.cmd` 호출은 PowerShell의 스크립트 실행 정책을 전역으로 낮추는 명령이 아니다.

## 4. 지원되지 않을 때

오류 메시지·현재 버전·확인한 공식 문서를 기록하고 지원되는 구성을 사용한다. 기능 토글 이름을 추측하거나 ‘설정 파일을 만들었으므로 실행됐다’고 보고하지 않는다. 사용자 정의 역할이 없더라도 일반 서브에이전트가 가능하면 좁은 역할 지시문을 전달할 수 있다. 둘 다 없으면 메인이 같은 역할을 순차 수행한다.

이 패키지는 Codex 개발 세션의 역할 설정이다. **완성될 웹앱이 운영 중 사용하는 AI 공급자·모델·키 설정과는 별개**다. 앱의 질문·추출·피드백 모델은 서버 어댑터·환경변수·비용 설정으로 관리하고 Codex 모델명을 앱 API에 자동 복사하지 않는다.
