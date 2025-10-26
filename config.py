LATENCY: float = 1  # 실제 제한의 90% 수준에서 동작하도록 설정

# gpt5 tier 5 기준
RPM_LIMIT: int = 10000 / 100 # 분당 요청 수 제한
TPM_LIMIT: int = 10000000 / 100 # 분당 토큰 수 제한 (간단한 계산을 위해 글자 수로 대체)
RPD_LIMIT: int = 500000 / 100 # 일일 요청 수 제한
TPD_LIMIT: int = 500000000 / 100 # 일일 토큰 수 제한

# --- Redis 연결 정보 ---
REDIS_HOST: str = "localhost"
REDIS_PORT: int = 6379
LLM_REDIS_DB: int = 0
APIM_REDIS_DB: int = 1  # APIM 서버와 다른 DB를 사용하여 상태를 격리할 수 있습니다 (예: 1)

# --- 호출할 대상 서버 정보 ---
# 이 브로커가 최종적으로 요청을 보낼 LLM APIM 서버의 주소입니다.
APIM_URL = "http://127.0.0.1:8000/v1/chat/completions" # 이 부분을 확인 및 수정해주세요.
LLM_APIM_API_KEY: str = "DUMMY_API_KEY" # APIM 서버가 키를 요구할 경우 사용

LLM_RATE_LIMIT_PREFIX: str = "llm_usage"
APIM_USAGE_PREFIX: str = "apim_usage"