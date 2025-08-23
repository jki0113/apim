# RPM_LIMIT: int = 10000 # 분당 요청 수 제한
# TPM_LIMIT: int = 2000000 # 분당 토큰 수 제한 (간단한 계산을 위해 글자 수로 대체)
# RPD_LIMIT: int = RPM_LIMIT * 100 # 일일 요청 수 제한
# TPD_LIMIT: int = TPM_LIMIT * 100 # 일일 토큰 수 제한

RPM_LIMIT: int = 20 # 분당 요청 수 제한
TPM_LIMIT: int = 4000 # 분당 토큰 수 제한 (간단한 계산을 위해 글자 수로 대체)
RPD_LIMIT: int = 100 # 일일 요청 수 제한
TPD_LIMIT: int = 20000 # 일일 토큰 수 제한

REDIS_HOST: str = "localhost"
REDIS_PORT: int = 6379
REDIS_DB: int = 0