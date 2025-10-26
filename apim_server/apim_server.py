import asyncio
import uuid
from contextlib import asynccontextmanager
from typing import Dict, Any

import aiohttp
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
import redis.asyncio as redis

import config
from apim_server.rate_limiter import RateLimiter
def count_input_tokens(payload: dict) -> int:
    try:
        return sum(len(msg.get("content", "")) for msg in payload.get("messages", []))
    except Exception: return 0

def count_output_tokens(response_json: dict) -> int:
    try:
        return sum(len(c.get("message", {}).get("content", "")) for c in response_json.get("choices", []))
    except Exception: return 0

# --- 전역 상태 객체 ---
REQUEST_QUEUE = asyncio.Queue()
RESULTS_STORE: Dict[str, Any] = {}
COMPLETION_EVENTS: Dict[str, asyncio.Event] = {}

# --- 백그라운드 워커 ---
async def background_worker(rate_limiter: RateLimiter):
    async with aiohttp.ClientSession() as session:
        while True:
            request_id, payload, event = await REQUEST_QUEUE.get()
            
            try:
                input_tokens = count_input_tokens(payload)
                await rate_limiter.wait_for_capacity(input_tokens)

                headers = {"Authorization": f"Bearer {config.LLM_APIM_API_KEY}"}
                async with session.post(config.APIM_URL, json=payload, headers=headers) as response:
                    result_json = await response.json()
                    result_status = response.status
                    
                if result_status == 200:
                    output_tokens = count_output_tokens(result_json)
                    await rate_limiter.record_successful_request(input_tokens, output_tokens)
                
                RESULTS_STORE[request_id] = (result_json, result_status)

            except Exception as e:
                RESULTS_STORE[request_id] = ({"error": str(e)}, 500)
            finally:
                event.set()
                REQUEST_QUEUE.task_done()

# --- FastAPI 생명주기 관리 ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    redis_client = redis.from_url(f"redis://{config.REDIS_HOST}:{config.REDIS_PORT}/{config.APIM_REDIS_DB}", decode_responses=True)
    rate_limiter = RateLimiter(redis_client, config.RPM_LIMIT, config.TPM_LIMIT, config.RPD_LIMIT, config.TPD_LIMIT)
    worker_task = asyncio.create_task(background_worker(rate_limiter))
    yield
    worker_task.cancel()
    await redis_client.close()

# --- FastAPI 앱 및 엔드포인트 ---
app = FastAPI(title="LLM Request APIM", lifespan=lifespan)

@app.post("/v1/chat/completions")
async def process_request(request: Request):
    request_id = str(uuid.uuid4())
    payload = await request.json()
    event = asyncio.Event()
    COMPLETION_EVENTS[request_id] = event

    await REQUEST_QUEUE.put((request_id, payload, event))

    try:
        await asyncio.wait_for(event.wait(), timeout=300.0) # 5분 타임아웃
    except asyncio.TimeoutError:
        return JSONResponse(content={"error": "Request timed out in APIM queue."}, status_code=status.HTTP_504_GATEWAY_TIMEOUT)
    finally:
        result_payload, result_status = RESULTS_STORE.pop(request_id, ({"error": "Result not found"}, 500))
        COMPLETION_EVENTS.pop(request_id, None)
    
    return JSONResponse(content=result_payload, status_code=result_status)