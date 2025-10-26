from contextlib import asynccontextmanager
from fastapi import FastAPI
import redis.asyncio as redis
import sys
import os

# --- 프로젝트 루트의 config.py를 찾기 위한 경로 설정 ---
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(project_root)
from config import REDIS_HOST, REDIS_PORT, LLM_REDIS_DB

from llm_mock_server.app.core.logger import get_logger
from llm_mock_server.app.api.v1.router import api_router

logger = get_logger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("starting up...")
    # Redis는 여전히 다른 목적으로 사용할 수 있으므로 연결은 유지합니다.
    redis_client = redis.from_url(
        f"redis://{REDIS_HOST}:{REDIS_PORT}/{LLM_REDIS_DB}",
        encoding="utf-8",
        decode_responses=True
    )
    # Rate Limit과 무관하게 DB 초기화는 유지
    await redis_client.flushdb()
    app.state.redis = redis_client
    logger.info("redis client initialized")
    yield
    logger.info("shutting down...")
    await app.state.redis.close()

app = FastAPI(
    title="Mock LLM Server",
    description="테스트용 LLM 서버 (Rate Limit 없음)",
    version="1.0.0",
    lifespan=lifespan
)

# RateLimitingMiddleware를 제거했습니다.
app.include_router(api_router, prefix="/v1")