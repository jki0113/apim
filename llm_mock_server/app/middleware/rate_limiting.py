import json
from fastapi import Request, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from app.core.logger import get_logger
logger = get_logger(__name__)

def count_request_tokens(request_data: dict) -> int:
    """(가상) 요청 본문에서 토큰 수를 계산"""
    try:
        messages = request_data.get("messages", [])
        return sum(len(msg.get("content", "")) for msg in messages)
    except Exception:
        return 0

class RateLimitingMiddleware(BaseHTTPMiddleware):
    """
    Rate Limiting을 수행하는 미들웨어
    """
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # Rate Limit을 적용할 특정 경로만 확인
        if request.url.path != "/v1/chat/completions":
            return await call_next(request)

        # main.py의 lifespan에서 생성된 RateLimiter 인스턴스를 가져옴
        rate_limiter = request.app.state.rate_limiter

        # 요청 본문을 읽고 토큰 수를 계산
        body = await request.body()
        request_token_count = 0
        if body:
            try:
                request_data = json.loads(body)
                request_token_count = count_request_tokens(request_data)
            except json.JSONDecodeError:
                pass
        
        # 엔드포인트에서 다시 body를 읽을 수 있도록 설정
        request._body = body

        # RateLimiter 서비스에 모든 제한 확인 로직을 위임
        error_message = await rate_limiter.check_limit_exceeded(request_token_count)
        
        if error_message:
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={"error": error_message}
            )

        # 제한을 통과했으므로 실제 엔드포인트로 요청을 전달
        response = await call_next(request)
        logger.info(f"{response}")
        return response