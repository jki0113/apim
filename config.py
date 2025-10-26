LATENCY: float = 1  # 실제 제한의 90% 수준에서 동작하도록 설정

# gpt5 tier 5 기준
RPM_LIMIT: int = 10000 / 100 # 분당 요청 수 제한
TPM_LIMIT: int = 10000000 / 100 # 분당 토큰 수 제한 (간단한 계산을 위해 글자 수로 대체)
RPD_LIMIT: int = 500000 / 100 # 일일 요청 수 제한
TPD_LIMIT: int = 500000000 / 100 # 일일 토큰 수 제한

# --- Burst 설정 (0.0 ~ 1.0): 분당/분당토큰 제한 대비 초기 버킷 용량 비율 ---
# 1.0 = 한 번에 100%까지 초기 버스트 허용 (cookbook 스타일)
# 0.8 = 한 번에 80%까지 초기 버스트 허용
# 0.0 = 초기 버스트 금지 (슬라이딩 윈도우 절대 초과 방지)
BURST_FACTOR: float = 0.8

# 슬라이딩 윈도우(정확히 최근 60초) 기준으로 RPM을 절대 초과하지 않도록 강제 여부
# True로 두면 rpm_window의 ZCOUNT로 60초 내 요청 수를 보고 한도를 넘기지 않게 스케줄링합니다.
ENFORCE_STRICT_RPM: bool = True

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