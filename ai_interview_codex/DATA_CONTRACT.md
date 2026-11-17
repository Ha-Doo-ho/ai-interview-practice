# 데이터 계약과 근거 연결

이 문서는 논리 계약이다. 아래 개념을 반드시 각각의 SQL 테이블로 만들 필요는 없다. 기존 구조에 맞춰 정규화·JSON 컬럼을 선택하되 검증·조회·삭제·재현 요구를 충족해야 한다. 실제 스키마·마이그레이션·API 타입은 저장소를 확인한 뒤 구현한다.

## 1. 식별자와 공통 원본

`run_id`는 한 사용자의 한 번의 전체 연습 회차다. 로그인 세션과 구분한다. `attempt_id`는 그 회차 안에서 설문 블록·게임·면접을 시도한 단위다. 다른 회차/재시도 기록은 자동 합산하지 않는다.

| 구분 | 필수 필드 또는 동등한 정보 | 용도 |
|---|---|---|
| 소유권 | `user_id`, `run_id`, `attempt_id`, `record_id` | 모든 조회·변경·비동기 작업의 범위 |
| 원본 종류 | `source_type`, `source_id`, `source_version` | 설문/게임 이벤트/면접 자기보고 구분 |
| 제시 정의 | `item_id`, `item_version`, `instructions_version`, `presentation_id` | 당시 문항·설명 복원 |
| 실제 제시 | `prompt_snapshot` 또는 불변 정의 참조, `option_ids`, `display_order`, `presentation_order` | 무작위 순서·동적 질문 포함 실제 화면 복원 |
| 맥락 | `context`, `time_limit_ms`, `practice_or_main`, `language` | 다른 조건의 관찰을 섞지 않기 |
| 시간 | `presented_at`, `started_at`, `completed_at`, 선택적으로 `first_action_elapsed_ms`, `submitted_elapsed_ms` | 제시부터 행동까지의 순서·조건 |
| 상태 | `status`, `missing_reason`, `finalized_at`, `record_version` | 무응답·시간 초과·확정·정정 구분 |
| 품질 | `quality_flags`, 기록 누락·연결 끊김·백그라운드 전환 등 실제 확인된 사실 | 자료 사용 가능성 설명 |

시스템 시각은 UTC, 화면 반응 시간은 단조 증가 시계의 경과값을 사용한다. 클라이언트 시각만으로 이벤트 순서를 신뢰하지 말고 서버 수신 시각·순번도 보존한다. 네트워크 지연을 사용자의 숙고 시간으로 간주하지 않는다. 반응 시간·수정 횟수는 맥락 정보이며 신뢰도/거짓말 점수 입력이 아니다. 마우스 전체 궤적·모든 키 입력 같은 불필요한 감시는 수집하지 않는다.

고정 문항은 버전이 불변인 정의를 참조할 수 있어 매 응답마다 전체 문구를 중복 저장할 필요가 없다. 생성 질문·변경된 선택지처럼 정의에서 재구성할 수 없는 제시 내용은 실제 원문을 저장한다. 해당하지 않는 필드는 `null`과 이유를 사용하며 의미 없는 ID를 만들어 넣지 않는다.

응답의 원문 수정은 새 버전으로 남긴다. ‘불변’은 **몰래 덮어쓰지 않는다**는 뜻이지 사용자 삭제를 막는다는 뜻이 아니다. 삭제 정책은 원문과 파생 결과에 모두 적용한다.

## 2. 형식별 응답

### 2.1 `ordinal_6`

문항 정의에 `scale_id`, `scale_version`, `ordered_options[{option_id,label,position}]`, 선택 강도의 의미를 저장한다. `position`과 `selected_position`은 **1부터 6까지**다. UI 배열의 0 기반 인덱스를 저장 위치와 섞지 않는다. 응답은 `selected_option_id`, `selected_label_snapshot` 또는 불변 참조, `selected_position`을 갖는다. 서버가 옵션 ID·라벨·위치의 일치를 검사한다.

원시 코드 4/5/6을 긍정이라는 하나의 값으로만 저장하지 않는다. ‘4점 대 6점’보다 ‘그런 편이다 대 매우 그렇다’로 피드백한다. 평균이 필요하다는 이유로 임의의 성향 종합 점수를 먼저 만들지 않는다. 다른 문항·척도·언어 버전의 코드를 직접 비교하지 않는다.

### 2.2 `paired_perspective`

`pair_id`, `respondent_user_id`, `perspective=self|imagined_others`, `paired_item_version`, 각 응답의 전체 ordinal 정보, `perspective_presentation_order`, `prior_response_visible`을 저장한다. 각 관점은 별도 제한 시간·제출 상태를 가질 수 있다. 한쪽만 응답한 경우 다른 쪽을 복사하거나 평균으로 채우지 않는다.

두 값의 위치 차이를 저장해도 그것은 이 응답 쌍의 차이일 뿐 ‘실제 주변 평가와의 오차’가 아니다. 같은 응답자에서 나온 두 값을 독립 표본 두 개로 세지 않는다.

### 2.3 `bipolar_slider`

`left_anchor_id/label`, `right_anchor_id/label`, `min`, `max`, `step`, `initial_value`, `final_value`, `interaction_occurred`, `explicit_confirmation`, `submit_status`, `change_count`를 저장한다. 단계의 유효성은 서버에서도 검증한다.

예시로 자체 문항을 -6~+6, 간격 1로 설계할 수 있다. 이 수치는 화면을 보고 추정한 상용 검사 규칙이 아니라 자체 UI 설정이다. 부호는 해당 문항에서 선택한 끝의 방향이다. 절댓값을 협업·확신·성실성 강도로 바꾸지 않는다. 연속 슬라이더도 UI 좌표와 잠재 성향의 등간성을 동일시하지 않는다.

중앙값 유지 후 명시적 제출은 답변일 수 있다. 초기 중앙값에 손대지 않고 시간 초과한 것은 미응답이다. `interaction_occurred=false`만으로 미응답으로 판정하지 않고 제출 방식까지 확인한다.

### 2.4 `top_k_rank`

`candidate_set_id/version`, `all_candidate_ids`, 각 후보의 원문/버전, `display_order`, `requested_k`, `ranked_selection[{option_id,rank}]`, `submitted_count`, `selection_events` 또는 선택·변경 요약, `status`를 저장한다.

정상 제출은 후보에 존재하는 고유 ID k개와 중복 없는 1~k 순위여야 한다. 시간 초과로 k개 미만인 부분 응답은 초안/부분 기록으로 보존하되 정상 완료로 처리하지 않는다. 사용자가 순위를 수정하면 최종 순위와 초기 클릭 순서를 구분한다. 미선택 집합은 전체 후보에서 계산할 수 있지만 미선택 후보끼리의 순서는 알 수 없다.

## 3. 행동 및 매핑 등록부

행동 정의에는 `behavior_id`, `behavior_version`, `name`, `operational_definition`, `inclusions`, `exclusions`, `context_requirements`를 둔다. MVP 식별자는 B01/B02/B03이다.

| 매핑 필드 | 의미 |
|---|---|
| `mapping_id`, `version` | 변경 시 새 버전 생성 |
| `source_definition_id/version`, `source_kind` | 문항·게임 이벤트 규칙·면접 루브릭 중 어떤 정의를 연결하는가 |
| `behavior_id/version`, `reason` | 어떤 좁은 행동과 왜 관련되는가 |
| `observable_proxy` | 직접 관찰인지 대리 지표인지, 원자료가 자기보고인지 |
| `preconditions`, `eligible_opportunity_rule` | 비교·관찰이 성립하는 조건 |
| `limitations`, `permitted_uses` | 알 수 없는 것, 질문 생성/관찰 보고 등에 허용된 용도 |
| `practice_review_status` | `draft`, `approved_for_practice`, `retired` |
| `reviewer_type`, `reviewer_id`, `review_mode`, `reviewed_at`, `review_note` | 실제 검토 출처; 기본 `independent_reviewer`, 불가 시 `same_agent_separate_pass`와 한계 기록; 작성 단계 자기 자동 승인 금지 |
| `validity_status` | MVP 기본 `provisional_unvalidated`; 연습 검토와 분리 |

같은 행동 ID만 붙였다고 비교가 성립하지 않는다. 코드에서 활성 매핑, 버전 호환, 관찰 기회, 단위·맥락, source_kind, 허용 용도를 모두 검사한다. 연결 이유를 설명할 수 없는 문항은 `unmapped`로 두고 성향/게임 비교에서 제외한다. 강제로 B01~B03 중 하나에 배정하지 않는다.

## 4. 게임 기록과 집계

| 레코드 | 필수 정보 |
|---|---|
| 게임 정의 | `game_id/version`, `rules_version`, 보상표, 라운드 구성, 제한 시간, 난이도, 난수 사용 시 seed |
| 라운드 | `round_id`, 순서, 연습/본 과제, 시작/종료 조건, 초기 자원·과제 상태, 실제 정보 노출 |
| 행동 기회 | `opportunity_id`, 대상 행동/매핑, 가능 시작/종료, 실제 합법적 선택, 비용·장애, `eligible`와 사유 |
| 이벤트 | `event_id`, `sequence_no`, 종류, 서버 시각·경과값, `state_before_ref`, 사용자가 택한 값, `state_after_ref` |
| 결정 | `decision_id`, 확정 선택, 당시 제약·가능 행동, 개인/팀 자원 배분, 계산된 게임 결과 |
| 새 정보 | `information_id/version`, 내용·노출 시점·접근 이벤트, 이전 결정 참조, 수정 기회·수정 결정 참조 |
| 이유 | `reason_self_report_id`, 사용자 설명 원문·버전, 묻는 시점 | 

로그 또는 상태 스냅샷으로 결정 당시 상태를 재현할 수 있어야 한다. seed만 저장하고 실제 행동을 잃지 않는다. 서버는 현재 상태에서 허용된 행동·자원 한도·확정 여부·이벤트 순서를 검사한다. 클라이언트가 보낸 보상값이나 선택 가능 여부를 검증 없이 사실로 저장하지 않는다. 정보가 제시되기 전에 나온 행동을 그 정보를 이용한 수정으로 판정하지 않는다.

집계는 `{metric_id, behavior_id, mapping_version, numerator, denominator, unit, included_opportunity_ids, excluded_opportunities_with_reasons, algorithm_version}` 형태를 가진다. 기회 3회 중 1회 정보 창 열기는 비율 1/3로 계산 가능하다. 기회 0회는 값 `null`과 `no_eligible_opportunity`이며 0/0을 0점으로 만들지 않는다.

응답하지 않은 기회, 접근할 수 없던 기회, 일부러 행동하지 않은 기회를 구분한다. 행동 순서·과제 점수와 사용자 설명은 각각 별도 증거다. 단순 선호를 실제 행동과 같은 source_kind로 합치지 않는다.

## 5. 면접 원본과 추출

질문에는 `question_id/version`, `question_text`, `question_mode=baseline|adaptive_followup`, `target_behavior_ids`, `asked_criteria`, `question_prompt_version`, `generated_from_evidence_refs`, `disclosed_prior_information`, `conditioned_on_prior_evidence`, `selection_reason`, `trigger_rule_id/version`, 제시 순서·시간·제한을 저장한다. `selection_reason`은 검증된 근거·규칙에 따른 질문 선택 이유이며 사용자 동기를 추정한 문장이 아니다.

기본 질문은 prior evidence가 없는 중립 질문이다. 후속 질문에 강도나 게임 관찰이 들어가면 `conditioned_on_prior_evidence=true`다. 실제 질문에서 이 부분을 삭제한 뒤 ‘독립적으로 물었다’고 기록하지 않는다. 기본/후속 추출은 별도 레코드·입력 계보·캐시 공간을 사용한다.

답변에는 `answer_id/version`, 원문, `source_kind=typed_self_report`, 생성·제출·정정 시각, `question_ref`, `status`, 이전 버전 참조를 저장한다. 미래 전사 확장은 `media_id/version`, `asr_raw_transcript_id/version`, `corrected_transcript_id/version`, 정정자·정정 시각을 분리한다. 전사 정정 시 인용은 해당 버전으로 다시 계산하거나 무효화한다.

추출 결과의 각 요소는 다음을 가진다.

```text
extraction_id / version
answer_id / answer_version / question_id / question_version
mode: baseline | conditioned_followup
behavior_id / mapping_id / mapping_version / rubric_id / rubric_version
criterion: situation | role | other_information | action | reasoning | result | learning
status: explicit | partial | not_mentioned | not_asked | unassessable
evidence_spans: [{source_id, source_version, start, end, quote}]
limitations / missing_reason
model_id / prompt_version / schema_version / runtime_mode / created_at
```

`explicit`은 해당 내용이 명시되었다는 의미다. 내용의 진실성이나 높은 역량을 인증하지 않는다. `not_mentioned`에 가짜 인용을 넣지 않는다. 질문하지 않은 기준을 설명 부족이라는 자동 감점으로 처리하지 않는다. 후속으로 물을 연습 방향은 제안할 수 있다. 질문 제시 여부, 답변 제출 여부, 각 기준의 언급 여부는 별개 상태 필드다. 하네스의 `asked_answered`, `asked_no_text`, `asked_no_mention`은 이 조합을 구별하는 예이며 제출 상태와 내용 평가를 하나의 필드로 덮어쓰라는 뜻이 아니다.

인용 인덱스는 **불변 원문에 대한 Unicode code point 기준의 반개구간 `[start,end)`**로 통일한다. Python 문자열 슬라이스와 JavaScript의 코드 포인트 배열을 대조할 수 있다. 저장 뒤 자동 정규화/공백 정리로 원문을 바꾸지 않는다. 정규화가 필요하면 별도의 텍스트 버전으로 저장한다. `quote == source_text[start:end]`를 코드 포인트 기준으로 확인한다. 미래 미디어 시간은 원본 미디어 버전의 밀리초 구간으로 별도 저장한다.

## 6. 근거 적격성과 비교 결과

기본 비교 범위는 같은 `user_id`·`run_id`, 선택된 확정 attempt, 활성·삭제되지 않은 원본의 버전 고정 스냅샷이다. 다른 회차 비교는 MVP에서 자동으로 하지 않는다. 향후 명시적인 종단 비교 기능이 생겨도 회차/버전/조건 차이를 노출하고 현재 결과와 섞지 않는다.

자료 사용 순서: 소유권/삭제 상태 → 원본 존재·버전 → 매핑 검토·허용 용도 → 행동·조건·기회 적격성 → 독립/조건부 구분 → 비교. 소유권 실패는 `not_comparable`로 감춰서 내용과 함께 반환하지 말고 접근 자체를 거부한다.

| 비교 상태 | 최소 조건 | 허용하지 않는 결론 |
|---|---|---|
| `supports_statement` | 같은 좁은 행동에 관련되는 적격 근거가 진술을 뒷받침하는 방향으로 존재함 | 성향이 검증됨/거짓말이 아님 |
| `contextual_difference` | 관련 행동의 관찰이 다르고, 조건 차이를 실제 기록으로 기술할 수 있음 | 그 조건이 차이를 일으켰다는 인과 단정 |
| `needs_clarification` | 관련 근거가 있지만 이유·맥락·해석을 확인해야 함 | 앞뒤가 다르므로 거짓말 |
| `insufficient_evidence` | 관련 근거·관찰 기회·원문 품질이 부족함 | 0점/부정적인 성향 |
| `not_comparable` | 행동 정의·척도·버전·조건의 호환성이 성립하지 않음 | 넓은 태그가 같으므로 모순 |

판정 우선순위를 명시한다. 접근 권한이 없으면 상태 분류 전에 거부한다. 그다음 순서는 (1) 행동/매핑/단위/버전 비호환이면 `not_comparable`, (2) 호환되지만 근거·적격 기회·판독 품질이 부족하면 `insufficient_evidence`, (3) 관련 관찰 차이와 기록된 조건 차이를 기술할 수 있으면 `contextual_difference`, (4) 나머지 해석에 추가 확인이 필요하면 `needs_clarification`, (5) 호환 맥락에서 진술을 뒷받침하는 명시적 근거가 있고 미해결 해석 문제가 없으면 `supports_statement`다. 기록된 조건 차이만 있고 관찰 차이는 없다면 자동으로 contextual_difference를 주지 않는다. 맥락 차이가 비교 자체를 무효화하는 수준이면 (1)이 우선이다.

서버가 가능한 상태 범위를 제한하고 AI가 제안한 결과를 검증한다. 문장의 의미적 적절성까지 스키마 검증만으로 보장할 수는 없으므로 별도 평가가 필요하다. 모호하면 `needs_clarification`/`insufficient_evidence`로 남기고 억지로 긍정/부정으로 나누지 않는다.

비교 레코드에는 `comparison_id/version`, 행동·매핑 버전, 모든 `evidence_refs`, `baseline_extraction_refs`, `conditioned_followup_refs`, 비교 가능성 판정과 이유, 상태, 제한, `comparison_rule_version`, 모델/프롬프트/스키마 버전, 생성 모드를 둔다.

## 7. 보고서의 문장별 추적

각 결과 카드는 `report_id/version`, `claim_id`, `claim_type`, 문장, `source_refs`, 원문 인용/로그 범위, 파생 metric 참조, 비교 상태, `limitations`, 연습 제안과 그 근거, `model_id`, `prompt_version`, `rubric_id/version`, `schema_version`, `runtime_mode`, 생성 시각을 가진다. 해당 생성 정보를 담은 불변 derivation 레코드를 참조해도 된다. 모델을 사용하지 않은 계산은 그 사실과 `algorithm_version`을 남긴다. 하나의 문장이 서로 다른 출처 사실을 섞으면 각각 참조를 붙이거나 문장을 나눈다.

서버 검증은 최소한 다음을 포함한다.

- 참조 존재, 버전·사용자·회차·삭제 여부 일치.
- 인용이 실제 원문 구간과 정확히 일치.
- 숫자·기회 횟수·응답 라벨이 저장값/검증된 계산값과 일치.
- 사용되지 않은 자료를 ‘확인했다’고 표시하지 않음.
- 금지된 점수·확률·성격 판정 필드가 스키마에 없음.

‘다음에는 상대에게 확인한 내용을 설명해 보세요’라는 연습 제안은 과거 행동의 사실 주장이 아니다. 제안과 관찰 사실을 필드와 문구에서 구분한다. 출처 검증 실패는 보고서 성공으로 덮지 말고 재시도/오류 상태로 남긴다.

## 8. 확정·재시도·무효화

회차 상태 예시는 `in_progress → completed` 또는 `abandoned/deleting/deleted`다. AI 작업 상태는 별도 `pending/running/succeeded/failed/cancelled`로 둔다. 응답 상태와 AI 처리 상태를 같은 필드에 섞지 않는다.

멱등 키는 사용자·회차·작업 종류 범위에서 고유해야 한다. 같은 키·같은 요청은 같은 논리 결과를 반환하고, 같은 키·다른 내용은 충돌로 거부한다. 낙관적 잠금 또는 트랜잭션으로 확정 경쟁을 처리한다. 확정 후 수정이 필요하면 명시적 새 버전/새 attempt로 만들고 이전 파생 결과의 사용 여부를 갱신한다.

삭제 요청은 원본과 의존 그래프상의 추출·비교·보고서·캐시·작업 입력/출력을 제거하거나 비가역적으로 내용 제거한다. 삭제 차단용 최소 식별 메타데이터를 남기는 경우 원문을 보관하지 말고 목적·수명을 문서화한다. 작업 시작 시뿐 아니라 완료 결과 저장 직전에도 소유권·삭제/세대 번호를 확인해 늦은 작업이 내용을 복원하지 못하게 한다. 백업 보관·삭제 주기는 실제 배포 전에 별도로 문서화한다.

정의 새 버전이 생겼다고 기존 보고서를 조용히 바꾸지 않는다. 과거 보고서는 당시 스냅샷임을 유지하고, 재분석을 요청하면 새 버전 결과를 만든다. 삭제되거나 철회된 원본은 재분석에 사용하지 않는다.

## 9. AI 인터페이스

앱 런타임 모드는 `mock|live`다. 네트워크 없는 provider 테스트 더블은 `runtime_mode=mock`, `provider_execution=test_double`로 기록한다. 이를 실제 공급자 응답으로 저장하지 않는다. 개발·CI 기본은 mock이며 `allowed_model_ids`, `max_input_tokens`, `max_output_tokens`, `timeout_ms`, `max_retries`, `max_calls_per_run`, `max_cost_per_run`을 서버 설정으로 제한한다. 한도 산정에 필요한 값이 불명확하면 유료 요청을 보내지 않는다. 실제 과금이 있는 테스트는 승인된 모델·예산 내에서만 별도로 실행한다. 키가 없으면 live 미설정 상태를 표시한다. 이 제한은 웹앱의 외부 AI 호출에 관한 것이며 현재 사용자가 요청한 Codex 개발 작업 자체를 금지하는 뜻이 아니다.

역할별 입력을 최소화한다. 게임 집계의 분석 입력 allowlist는 게임 규칙·기회·상태·이벤트와 소유권/버전 검증 정보다. 기본 면접 추출의 내용 입력 allowlist는 중립 기본 질문, 답변, 대상 행동·매핑·루브릭이다. 설문 응답/강도와 게임 프로필/집계를 기본 면접 추출에 넣지 않는다. 질문이 prior evidence를 공개했다면 기본 경로에서 거부하고 조건부 경로로 처리한다. 적응형 질문 생성에는 검증된 사실 요약과 필요한 원문만 넣는다. 문장 생성에는 이미 확정한 상태와 검증된 근거를 넣어 새 판정을 임의로 추가하지 못하게 한다.

입력 분리는 시스템이 설문·게임 결과를 별도 프로필로 주입하지 않는다는 뜻이다. 사용자가 답변 원문에서 이전 과제를 스스로 언급했다면 그 원문을 지우거나 금지 문자열로 처리하지 않는다. 이를 자기보고 내용으로 보존하고 해당 맥락·제한을 기록한다. 파이프라인 격리가 통계적인 독립성이나 경험의 진실성을 보장하지 않는다.

캐시는 사용자·회차·attempt·원본 버전·처리 모드·프롬프트/루브릭/알고리즘 버전을 구분한다. 기본 추출 캐시에 조건부 후속 답변을 재사용하지 않는다. 캐시 키만으로 권한을 대신하지 않으며 조회/저장 시 적격성과 삭제 세대도 다시 확인한다.

사용자 답변·문항·외부 텍스트에 포함된 명령은 입력 데이터다. 이 내용이 프롬프트 역할·도구 사용·모델 출력 스키마·참조 범위를 바꾸지 못하게 한다. 모델 출력에서 허용된 키·열거형·ID만 수용하고, 소유권과 인용을 다시 검증한다. 내부 모델 confidence 숫자를 객관적인 성향 신뢰도로 노출하지 않는다.
