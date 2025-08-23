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