# Gemini 서버 연결 설정

현재 서버는 환경변수만 읽고 `.env` 및 `.env.example`을 자동으로 읽지 않는다. 아래는 로컬 설정 안내이며 실제 외부 호출 검증은 아직 하지 않았다. API 키는 채팅·예시 파일·브라우저에 적지 않는다. 서버 실행자에게 필요한 권한으로 설정한다.

1. Google AI Studio에서 프로젝트에 허용된 정확한 Gemini 모델 ID, API 결제 상태, 해당 모델의 현재 입력/출력 가격을 확인한다. Gemini GenerateContent와 JSON 스키마 출력 지원이 필요한데, 실제 모델 호환성은 아직 검증하지 않았다.
2. 서버를 실행할 PowerShell에서 `AI_PROVIDER=gemini`, `AI_MODEL_ID` 및 동일한 ID를 포함하는 `AI_ALLOWED_MODEL_IDS`, `AI_LIVE_ENABLED=true`, `PAID_AI_ENABLED=true`를 설정한다. 반드시 실제 비용 지불자와 사용 예산을 먼저 정한다.
3. `AI_MAX_COST_MICROUSD`, `AI_INPUT_RATE_MICROUSD_PER_MILLION_TOKENS`, `AI_OUTPUT_RATE_MICROUSD_PER_MILLION_TOKENS`를 정수로 설정한다. 각각 회차별 예산과 100만 토큰당 달러 가격에 1,000,000을 곱한 값이다. 상한은 이 앱의 추정 예약 한도이며 계정 전체 결제 상한은 아니다.
4. 본인이 동일 PowerShell에서 `Read-Host 'Gemini API 키' -AsSecureString`으로 키를 입력해 `AI_PROVIDER_KEY` 프로세스 환경변수로 전달한다. 설정을 표시하거나 파일에 저장하지 않는다. 키는 해당 실행 프로세스에만 필요하다.
5. 기존 서버와 정확한 데이터베이스 경로를 확인하고, 기존 기록을 보존해 같은 DB를 지정한 후 그 환경에서 서버를 재시작한다. `tools/start_interview.ps1`은 AI를 끄므로 실제 AI 시작용이 아니다. 실제 테스트를 하기 전 개인 답변이 Google에 전송됨을 확인한다.
6. 보고서의 설정 상태와 실제 요청 결과, 공급자 성공 여부, 인용 근거를 확인한다. 실패·모의 응답을 실제 성공으로 표시하지 않는다. 게임 AI는 게임별 조건과 집계를 이용한 제한된 제안이며 문항별 원본 해석이 아니다.

공식 문서: https://ai.google.dev/gemini-api/docs/generate-content/structured-output, https://ai.google.dev/gemini-api/docs/pricing
