# APIM Server

LLM API를 위한 고성능 비동기 요청 게이트웨이입니다. 모든 LLM 요청을 단일 엔드포인트로 받아, 설정된 Rate Limit(RPM, TPM, RPD, TPD)에 따라 요청을 내부 큐에 저장하고 순차적으로 백엔드 LLM 서버로 전달합니다. 이를 통해 실제 LLM API의 호출량을 안정적으로 제어하고 초과 호출로 인한 에러를 방지합니다.

## 주요 기능

-   **비동기 요청 큐(Queue):** FastAPI를 사용하여 들어오는 모든 요청을 비동기 큐에 저장하여 즉시 응답 지연을 최소화합니다.
-   **Rate Limit 기반 요청 조절:** 백그라운드 워커가 큐의 요청을 순차적으로 처리하며, Redis 기반 Rate Limiter를 통해 백엔드 API로 보내는 요청 속도를 제어합니다.
-   **중앙 집중식 Rate Limiting:** Redis를 사용하여 여러 APIM 서버 인스턴스가 실행되더라도 Rate Limit 상태를 중앙에서 관리하고 공유합니다.
    -   **RPM/TPM**: 슬라이딩 윈도우 알고리즘 (Lua 스크립트로 원자성 보장)
    -   **RPD/TPD**: 고정 윈도우 알고리즘 (자정 기준 초기화)
-   **안정적인 백엔드 호출:** 설정된 제한을 초과할 경우, 요청을 즉시 거절하는 대신 필요한 시간만큼 대기한 후 다시 시도하여 안정성을 높입니다.

## 프로젝트 구조

```
apim_server/
├── __init__.py
├── apim_server.py    # FastAPI 앱, 요청 큐, 백그라운드 워커
├── rate_limiter.py   # Redis 기반 Rate Limiting 로직
└── run.py            # Uvicorn 서버 실행 스크립트
```

## 사전 준비 사항

-   **Python 3.9** 이상
-   **Docker** 및 Docker Compose
-   요청을 전달할 **백엔드 LLM 서버** (예: `llm_mock_server`)
-   API 테스트 도구 (예: `curl`, Postman)

## 설치 및 설정

**1. 프로젝트 클론**

```bash
git clone <your-repository-url>
cd <your-project-directory>
```

**2. 가상 환경 생성 및 활성화**

```bash
# 가상 환경 생성
python3 -m venv venv

# 가상 환경 활성화 (Linux/macOS)
source venv/bin/activate
```

**3. Python 의존성 설치**

프로젝트 루트에 `requirements.txt` 파일을 생성하고 아래 내용을 추가한 후, 패키지를 설치합니다.

**`requirements.txt`**
```
fastapi
uvicorn[standard]
redis
aiohttp
```

```bash
pip install -r requirements.txt
```

**4. Redis 컨테이너 실행**

Docker를 사용하여 Rate Limiting 상태를 저장할 Redis 서버를 실행합니다.

```bash
docker run --name apim-redis -p 6379:6379 -d redis
```

**5. 설정 파일 수정**

프로젝트 루트의 `config.py` 파일에서 APIM 서버의 동작을 설정합니다.

-   `APIM_URL`: 요청을 전달할 실제 LLM 서버의 엔드포인트 주소 (예: `http://127.0.0.1:8000/v1/chat/completions`)
-   `APIM_API_KEY`: 백엔드 LLM 서버가 API 키를 요구할 경우 사용합니다.
-   `RPM_LIMIT`, `TPM_LIMIT`, `RPD_LIMIT`, `TPD_LIMIT`: 백엔드 LLM 서버의 정책에 맞는 Rate Limit 값을 설정합니다.
-   `REDIS_HOST`, `REDIS_PORT`, `APIM_REDIS_DB`: Rate Limit 상태 저장을 위한 Redis 연결 정보를 설정합니다. `llm_mock_server`와 다른 DB(`APIM_REDIS_DB`)를 사용하는 것을 권장합니다.

---

## 실행 방법

### 1. 백엔드 LLM 서버 실행

APIM 서버가 요청을 전달할 백엔드 서버를 먼저 실행해야 합니다. (예: `llm_mock_server`)

```bash
# 예시: llm_mock_server 실행
uvicorn llm_mock_server.app.main:app --host 0.0.0.0 --port 8000
```

### 2. APIM 서버 실행

**새로운 터미널 창을 열고** 아래 명령어를 실행하여 APIM 서버를 시작합니다.

```bash
python apim_server/run.py
```

-   서버는 기본적으로 `8001` 포트에서 실행됩니다.
-   `run.py` 파일은 `apim_server:app`을 `reload` 옵션과 함께 실행합니다.

---

## API 테스트 예시

APIM 서버와 백엔드 LLM 서버가 모두 실행 중인 상태에서, 아래 `curl` 명령어를 사용하여 APIM 서버(`http://localhost:8001`)로 API를 테스트할 수 있습니다.

```bash
curl -X POST http://localhost:8001/v1/chat/completions \
-H "Content-Type: application/json" \
-d '{
    "model": "gpt-4",
    "messages": [
        {
            "role": "user",
            "content": "Tell me a joke about rate limiting."
        }
    ]
}'
```

-   **정상 동작**: 요청이 APIM 서버의 큐에 추가된 후, Rate Limit에 따라 백엔드 서버로 전달되고 최종 응답이 반환됩니다.
-   **제한 초과 시**: Rate Limit을 초과하더라도 APIM 서버는 요청을 바로 거절하지 않습니다. 대신, 큐에서 대기하다가 용량이 확보되면 요청을 처리합니다. (단, 5분 이상 지연 시 타임아웃 처리)

```

---

### **참고 및 개선 제안**

README 작성을 위해 코드를 검토하는 과정에서 `config.py`와 `apim_server.py` 간의 설정 변수 이름에 약간의 차이가 있는 것을 발견했습니다. 예를 들어 `apim_server.py`에서는 `config.LLM_APIM_URL`을 사용하지만, `config.py`에는 `APIM_URL`로 정의되어 있습니다.

추후 유지보수성과 코드 명확성을 위해 `apim_server.py`의 변수명을 `config.py`에 맞춰 아래와 같이 수정하시는 것을 권장해 드립니다.

```python:apim_server/apim_server.py
// ... existing code ...
    async with aiohttp.ClientSession() as session:
        while True:
            request_id, payload, event = await REQUEST_QUEUE.get()
            
            try:
                input_tokens = count_input_tokens(payload)
                await rate_limiter.wait_for_capacity(input_tokens)

                headers = {"Authorization": f"Bearer {config.APIM_API_KEY}"}
                async with session.post(config.APIM_URL, json=payload, headers=headers) as response:
                    result_json = await response.json()
                    result_status = response.status
// ... existing code ...
@asynccontextmanager
async def lifespan(app: FastAPI):
    redis_client = redis.from_url(f"redis://{config.REDIS_HOST}:{config.REDIS_PORT}/{config.APIM_REDIS_DB}", decode_responses=True)
    rate_limiter = RateLimiter(redis_client)
    worker_task = asyncio.create_task(background_worker(rate_limiter))
// ... existing code ...
```