from contextlib import asynccontextmanager
from fastapi import FastAPI
import redis.asyncio as redis

from app.core.logger import get_logger
logger = get_logger(__name__)
from app.api.v1.router import api_router
from app.core.config import REDIS_HOST, REDIS_PORT, REDIS_DB
from app.middleware.rate_limiting import RateLimitingMiddleware
from app.core.config import RPM_LIMIT, TPM_LIMIT, RPD_LIMIT, TPD_LIMIT
from app.services.rate_limiter import RateLimiter

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("starting up...")

    # Redis 클라이언트 생성
    redis_client = redis.from_url(
        f"redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}",
        encoding="utf-8",
        decode_responses=True
    )
    await redis_client.flushdb()
    app.state.redis = redis_client
    logger.info("redis client initialized")

    rate_limiter_instance = RateLimiter(
        redis_client=redis_client,
        rpm_limit=RPM_LIMIT,
        tpm_limit=TPM_LIMIT,
        rpd_limit=RPD_LIMIT,
        tpd_limit=TPD_LIMIT,
    )
    app.state.rate_limiter = rate_limiter_instance
    logger.info("rate limiter initialized")

    yield

    logger.info("shutting down...")
    await app.state.redis.close()

app = FastAPI(
    title="Mock LLM Server",
    description="테스트용 LLM 서버",
    version="1.0.0",
    lifespan=lifespan  # 2. 생성된 앱에 lifespan 핸들러를 등록합니다.
)
app.add_middleware(RateLimitingMiddleware)
app.include_router(api_router, prefix="/v1")