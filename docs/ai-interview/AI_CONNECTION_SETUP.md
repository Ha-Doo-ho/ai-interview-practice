# 실제 AI 연결 설정과 로컬 시연

기존 OpenAI Responses API 호출 어댑터를 현재 HTML의 면접 분석 경로에 연결한다. API 키를 새로 발급해야 한다는 뜻은 아니다. 기존 서버용 키가 있다면 그 설정을 사용한다. 현재 확인한 Process/User 환경과 프로젝트 `.env`에서는 키 설정을 찾지 못했으며, 다른 환경에 키가 존재하지 않는다고 단정하지 않는다.

## 실행 전 구분

- `저장 근거 보기 · AI 미사용`: 저장된 설문·게임·면접 원본과 결측 상태를 보고서로 정리한다. 외부 AI 호출이나 의미 판정은 하지 않는다.
- `AI 분석 요청`: 중립 기본 질문과 답변을 서버에서 외부 AI로 전송한다. 실제 provider 결과를 검증한 경우에만 실제 AI 결과로 표시한다. 설정이 없거나 출력 검증이 실패하면 성공으로 바꾸지 않는다.
- 두 모드 모두 같은 회차의 원본을 읽는다. 설문·게임 결과는 기본 면접 추출 입력에 주입하지 않고 보고서 조립 단계에서 원본으로 함께 표시한다. 현재 RPS/card는 행동 비교용 매핑이 없어 직접 성향 비교에 사용하지 않는다.

## 키 보관

키 값은 채팅, HTML, JavaScript, Git/문서, 테스트 fixture에 넣지 않는다. 앱은 서버 프로세스의 `AI_PROVIDER_KEY`만 읽는다. `.env.example`은 비밀 없는 설정 예시이며 앱이 자동으로 읽는 파일은 아니다.

PowerShell에서 필요한 경우 다음처럼 화면에 키를 표시하지 않고 서버 프로세스 환경에 설정할 수 있다. 이 명령은 사용자가 직접 자신의 터미널에서 실행한다.

```powershell
$interviewApiSecret = Read-Host '기존 OpenAI API 키' -AsSecureString
$env:AI_PROVIDER_KEY = [System.Net.NetworkCredential]::new('', $interviewApiSecret).Password
Remove-Variable interviewApiSecret
```

키를 입력한 동일 PowerShell에서 서버를 실행해야 그 서버가 값을 상속한다. 다른 터미널에 입력한 Process 환경변수는 기존 실행 서버에 자동 반영되지 않는다. 사용자/서비스 환경에 기존 설정이 있다면 해당 실행 방식에 맞게 이어서 사용한다.

## 모델·호출 상한

`.env.example`의 다음 값을 서버 환경으로 설정한다. 실제 사용할 모델과 현재 가격은 [공식 모델 목록](https://developers.openai.com/api/docs/models) 및 [공식 가격표](https://developers.openai.com/api/docs/pricing)에서 확인한다. 특정 모델의 사용 권한이나 가격을 추정하지 않는다.

| 환경변수 | 의미 |
|---|---|
| AI_MODEL_ID | 사용할 정확한 모델 ID |
| AI_ALLOWED_MODEL_IDS | 서버에서 허용할 모델 ID 목록 |
| AI_LIVE_ENABLED / PAID_AI_ENABLED | 실제 호출과 유료 호출을 허용할 때만 true |
| AI_MAX_INPUT_TOKENS | 요청당 입력 상한. 예시 12000 |
| AI_MAX_OUTPUT_TOKENS | 요청당 출력 상한. 예시 2000 |
| AI_TIMEOUT_MS | 요청당 제한 시간. 예시 30000 |
| AI_MAX_RETRIES | 0. 자동 유료 재시도 없음 |
| AI_MAX_CALLS_PER_RUN | 회차 전체 호출 예약 한도. 예시 9 |
| AI_MAX_COST_MICROUSD | 회차 전체 비용 예약 상한. 정수 micro-USD |
| AI_INPUT_RATE_MICROUSD_PER_MILLION_TOKENS | 선택 모델의 입력 100만 토큰 가격을 micro-USD로 환산 |
| AI_OUTPUT_RATE_MICROUSD_PER_MILLION_TOKENS | 선택 모델의 출력 100만 토큰 가격을 micro-USD로 환산 |

1 USD는 1,000,000 micro-USD다. 예를 들어 사용자가 정한 회차 예산이 0.10 USD라면 상한 값은 100000이다. 이는 승인된 예산이나 모델 가격의 제안이 아니라 단위 환산 예시다. 기존 `AI_MAX_COST_PER_RUN`은 구 어댑터의 USD 단위 설정이므로 새 경로에서는 정수 상한과 충돌하지 않도록 설정한다.

기본 답변 3개가 모두 비어 있지 않으면 한 번의 분석에 최대 3개 공급자 호출이 필요하다. 빈 답변/건너뜀은 호출하지 않는다. 입력은 원문을 잘라내지 않고 상한 초과 시 거부한다. 실패와 timeout도 실제 호출 여부가 불확실하므로 예약을 자동 환급하지 않는다. 같은 요청 재확인은 새로운 공급자 호출을 만들지 않는다.

## 로컬 서버와 기록 보존

현재 확인된 시연 DB는 `artifacts/manual-browser/preview-20261009-95ca0574/interview.db`다. 재개할 때 새 DB를 만들지 않는다. 아래 명령은 필요한 환경을 설정한 PowerShell에서, 기존 서버를 확인해 정상 종료한 뒤 사용한다. 실제 재시작 결과와 PID/백업 위치는 CURRENT_STATE.md의 최신 항목을 따른다.

```powershell
Set-Location E:\SchoolContest
$env:DATABASE_URL = 'sqlite:///E:/SchoolContest/artifacts/manual-browser/preview-20261009-95ca0574/interview.db'
$env:COOKIE_SECURE = 'false'
.\.venv\Scripts\python.exe -B -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-access-log
```

기존 DB에 필요한 추가 테이블만 생성하며 설문·게임·답변 원본을 초기화하지 않는다. 시작 자체로 AI를 호출하지 않는다. 브라우저에서 기존 회차를 선택하고 `4. AI 리포트`에서 모드/설정 상태를 확인한 뒤 명시적으로 요청한다.

## 검증과 한계

로컬 자동 검사는 합성 데이터와 주입 transport만 사용한다. 실제 유료 API 실행·사람에 의한 인용 정확성 확인·실제 브라우저 접근성 확인은 각각 별도로 기록한다. UI에 저장 근거가 표시되는 것만으로 실제 AI 연결이 성공했다고 보지 않는다.

Responses API 출력은 [공식 Structured Outputs 문서](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=responses)의 strict schema를 사용하고, 서버에서 실제 답변 원문의 인용 구간/버전/행동 결속을 추가로 확인한다.
