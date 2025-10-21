llm_mock_server/
├── app/
    ├── __init__.py
    ├── main.py             # FastAPI 앱 생성, 미들웨어/라우터 설정
    ├── api/
    │   ├── __init__.py
    │   └── v1/
    │       ├── __init__.py
    │       ├── router.py       # v1 API 라우터 통합
    │       └── endpoints/
    │           ├── __init__.py
    │           └── chat.py     # '/chat/completions' 엔드포인트 로직
    ├── core/
    │   ├── __init__.py
    │   └── config.py         # 설정 (Rate Limit 값 등)
    ├── models/
    │   ├── __init__.py
    │   └── chat.py           # Pydantic 모델 (Request/Response)
    ├── services/
    │   ├── __init__.py
    │   └── chat_service.py   # 비즈니스 로직 (응답 생성)
    └── middleware/
        ├── __init__.py
        └── rate_limiting.py  # Rate Limiting 미들웨어

# LLM Mock Server

비동기 방식으로 LLM 호출을 처리하는 FastAPI 기반의 Mock 서버입니다. Redis를 사용하여 확장 가능한 실시간 Rate Limiting(RPM, TPM, RPD, TPD) 기능을 구현합니다.

## 주요 기능

-   FastAPI를 사용한 비동기 API 엔드포인트 (`/v1/chat/completions`)
-   Redis 기반의 중앙 집중식 Rate Limiting
    -   **RPM/TPM**: 슬라이딩 윈도우 알고리즘 (Lua 스크립트로 원자성 보장)
    -   **RPD/TPD**: 고정 윈도우 알고리즘 (자정 기준 초기화)
-   실시간 사용량 모니터링 스크립트 제공

## 사전 준비 사항

-   **Python 3.12** 이상
-   **Docker** 및 Docker Compose
-   API 테스트 도구 (예: `curl`, Postman)

## 설치 및 설정

**1. 프로젝트 클론**

```bash
git clone <your-repository-url>
cd <your-project-directory>
```

**2. 가상 환경 생성 및 활성화**

프로젝트 의존성을 시스템과 격리하기 위해 가상 환경 사용을 강력히 권장합니다.

```bash
# 가상 환경 생성
python3 -m venv venv

# 가상 환경 활성화 (Linux/macOS)
source venv/bin/activate

# 가상 환경 활성화 (Windows)
# venv\Scripts\activate
```

**3. Python 의존성 설치**

```bash
pip install -r requirements.txt
```

**4. Redis 컨테이너 실행**

Docker를 사용하여 Rate Limiting 상태를 저장할 Redis 서버를 실행합니다.

```bash
docker run --name apim-redis -p 6379:6379 -d redis
```

아래 명령어로 컨테이너가 정상적으로 실행 중인지 확인할 수 있습니다.

```bash
docker ps
```

**5. Rate Limit 설정 (선택 사항)**

API의 분당/일일 요청 및 토큰 제한은 설정 파일에서 관리합니다. 필요에 따라 값을 수정할 수 있습니다.

-   **파일 위치**: `llm_mock_server/app/core/config.py`
-   **설정 변수**: `RPM_LIMIT`, `TPM_LIMIT`, `RPD_LIMIT`, `TPD_LIMIT`

---

## 실행 방법

### 1. LLM Mock Server 실행

아래 명령어를 실행하여 FastAPI 애플리케이션 서버를 시작합니다.

```bash
uvicorn llm_mock_server.app.main:app --host 0.0.0.0 --port 8000 --reload
```

-   `--reload`: 개발 중에 코드가 변경될 때마다 서버를 자동으로 재시작해주는 편리한 옵션입니다.
-   서버가 정상적으로 시작되면 터미널에 `Application startup complete.` 로그가 출력됩니다.

### 2. 실시간 상태 모니터링 실행

서버의 현재 Rate Limit 사용량을 실시간으로 확인하려면, **새로운 터미널 창을 열고** 아래 명령어를 실행하세요.

```bash
python -m llm_mock_server.monitor
```

-   **주의**: `-m` 옵션을 사용하여 모듈 형태로 실행해야 프로젝트 내부의 `config` 파일을 정상적으로 import 할 수 있습니다.

이제 모니터링 터미널에는 1초마다 갱신되는 상태 대시보드가 표시됩니다.

```
==================== LLM SERVER STATUS (Live) ====================
RPD :     0 / 10000 (  0.0%)
TPD :     0 / 2000000 (  0.0%)
RPM :     0 / 60    (  0.0%)
TPM :     0 / 60000 (  0.0%)
=================================================================
(Config file is reloaded every second. Press Ctrl+C to exit)
```

---

## API 테스트 예시

서버와 모니터링이 모두 실행 중인 상태에서, 아래 `curl` 명령어를 사용하여 API를 테스트할 수 있습니다.

```bash
curl -X POST http://localhost:8000/v1/chat/completions \
-H "Content-Type: application/json" \
-d '{
    "model": "gpt-4",
    "messages": [
        {
            "role": "user",
            "content": "Hello, world!"
        }
    ]
}'
```

-   **성공 응답**: API가 정상적으로 호출되면 Mock 응답이 반환됩니다.
-   **제한 초과 응답**: 설정된 Rate Limit을 초과하면 `429 Too Many Requests` 상태 코드와 함께 에러 메시지가 반환됩니다.