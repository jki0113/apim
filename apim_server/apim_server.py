import asyncio
import uuid
import time
from contextlib import asynccontextmanager
from typing import Dict, Any
import logging
from datetime import datetime, timezone

import aiohttp
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
import redis.asyncio as redis

import config

# --- 설정값 ---
MAX_RETRIES = 5
RETRY_COOLDOWN_SECONDS = 10
SCHEDULER_LOOP_SLEEP_SECONDS = 0.001 

def count_input_tokens(payload: dict) -> int:
    try:
        return sum(len(msg.get("content", "")) for msg in payload.get("messages", []))
    except Exception: return 0

def count_output_tokens(response_json: dict) -> int:
    try:
        return sum(len(c.get("message", {}).get("content", "")) for c in response_json.get("choices", []))
    except Exception: return 0

REQUEST_QUEUE = asyncio.Queue()
RESULTS_STORE: Dict[str, Any] = {}
COMPLETION_EVENTS: Dict[str, asyncio.Event] = {}

async def background_worker(redis_client: redis.Redis, llm_redis_client: redis.Redis):
    lua_schedule = """
        -- KEYS[1]: rpm_capacity_key, KEYS[2]: tpm_capacity_key, KEYS[3]: apim_rpm_window
        -- ARGV[1]: rpm_max_capacity, ARGV[2]: rpm_rate_per_sec, ARGV[3]: rpm_needed
        -- ARGV[4]: tpm_max_capacity, ARGV[5]: tpm_rate_per_sec, ARGV[6]: tpm_needed
        -- ARGV[7]: now, ARGV[8]: one_minute_ago, ARGV[9]: rpm_limit, ARGV[10]: unique_id

        local function refill(key, max_cap, rate, now)
            local data = redis.call('HMGET', key, 'available', 'last_ts')
            local available, last_ts = tonumber(data[1]), tonumber(data[2])
            if not available or not last_ts then available, last_ts = max_cap, now end
            local elapsed = now - last_ts
            if elapsed > 0 then
                available = math.min(max_cap, available + elapsed * rate)
            end
            return available, last_ts
        end

        local now = tonumber(ARGV[7])
        local one_minute_ago = tonumber(ARGV[8])
        local rpm_limit = tonumber(ARGV[9])

        -- 1) Clean old window entries and check current RPM count atomically
        redis.call('ZREMRANGEBYSCORE', KEYS[3], '-inf', one_minute_ago)
        local current_rpm = redis.call('ZCARD', KEYS[3])
        if current_rpm >= rpm_limit then
            return {'WAIT_RPM'}
        end

        -- 2) Refill token buckets and check capacity
        local rpm_available = refill(KEYS[1], tonumber(ARGV[1]), tonumber(ARGV[2]), now)
        local tpm_available = refill(KEYS[2], tonumber(ARGV[4]), tonumber(ARGV[5]), now)

        local rpm_needed = tonumber(ARGV[3])
        local tpm_needed = tonumber(ARGV[6])

        if rpm_available < rpm_needed then
            local wait = (rpm_needed - rpm_available) / tonumber(ARGV[2])
            return {'WAIT_TOKENS', wait}
        end
        if tpm_available < tpm_needed then
            local wait = (tpm_needed - tpm_available) / tonumber(ARGV[5])
            return {'WAIT_TOKENS', wait}
        end

        -- 3) Consume and record atomically
        redis.call('HMSET', KEYS[1], 'available', rpm_available - rpm_needed, 'last_ts', now)
        redis.call('HMSET', KEYS[2], 'available', tpm_available - tpm_needed, 'last_ts', now)
        redis.call('ZADD', KEYS[3], now, ARGV[10])
        redis.call('EXPIRE', KEYS[3], 120)
        return {'OK'}
    """
    
    async with aiohttp.ClientSession() as session:
        while True:
            if REQUEST_QUEUE.empty():
                await asyncio.sleep(SCHEDULER_LOOP_SLEEP_SECONDS)
                continue

            request_id, payload, event = await REQUEST_QUEUE.get()
            input_tokens = count_input_tokens(payload)
            now = time.time()
            
            # --- BURST_FACTOR 반영: 초기 버킷 용량을 제한해 초기 스파이크 제어 ---
            rpm_capacity = float(config.RPM_LIMIT) * float(getattr(config, 'BURST_FACTOR', 1.0))
            tpm_capacity = float(config.TPM_LIMIT) * float(getattr(config, 'BURST_FACTOR', 1.0))

            unique_id = str(uuid.uuid4())
            apim_prefix = config.APIM_USAGE_PREFIX
            one_minute_ago = now - 60
            result = await redis_client.eval(
                lua_schedule, 3,
                f"{apim_prefix}:rpm_capacity", f"{apim_prefix}:tpm_capacity", f"{apim_prefix}:rpm_window",
                rpm_capacity, config.RPM_LIMIT / 60.0, 1,
                tpm_capacity, config.TPM_LIMIT / 60.0, float(input_tokens),
                now, one_minute_ago, int(config.RPM_LIMIT), unique_id
            )

            if result[0] != 'OK':
                wait_time = 0.02
                if result[0] == 'WAIT_TOKENS' and len(result) > 1:
                    try:
                        wait_time = max(0.02, float(result[1]))
                    except Exception:
                        wait_time = 0.02
                await REQUEST_QUEUE.put((request_id, payload, event))
                await asyncio.sleep(wait_time)
                continue

            today_str, one_minute_ago = datetime.now(timezone.utc).strftime("%Y-%m-%d"), now - 60
            
            # --- 수정된 부분: 양쪽 서버의 모니터링 키를 모두 정리 ---
            llm_prefix = config.LLM_RATE_LIMIT_PREFIX
            apim_prefix = config.APIM_USAGE_PREFIX
            async with llm_redis_client.pipeline(transaction=True) as pipe:
                pipe.zremrangebyscore(f"{llm_prefix}:rpm_window", '-inf', one_minute_ago)
                pipe.zremrangebyscore(f"{llm_prefix}:tpm_window", '-inf', one_minute_ago)
                await pipe.execute()
            async with redis_client.pipeline(transaction=True) as pipe:
                pipe.zremrangebyscore(f"{apim_prefix}:rpm_window", '-inf', one_minute_ago)
                pipe.zremrangebyscore(f"{apim_prefix}:tpm_window", '-inf', one_minute_ago)
                await pipe.execute()

            # 1. LLM 서버 RPD, RPM 모니터링 기록 (TTL 부여)
            await llm_redis_client.incr(f"{llm_prefix}:rpd:{today_str}")
            await llm_redis_client.zadd(f"{llm_prefix}:rpm_window", {unique_id: now})
            await llm_redis_client.expire(f"{llm_prefix}:rpm_window", 120)

            # 2. APIM 서버 RPM 기록은 Lua에서 이미 ZADD 처리됨 (TTL 포함)
            
            try:
                headers = {"Authorization": f"Bearer {config.LLM_APIM_API_KEY}"}
                response_json, response_status = None, 500
                for attempt in range(MAX_RETRIES):
                    try:
                        async with session.post(config.APIM_URL, json=payload, headers=headers, timeout=60) as response:
                            response_json, response_status = await response.json(), response.status
                            if response.status < 500: break
                            logging.warning(f"Req {request_id}: Attempt {attempt+1}/{MAX_RETRIES} failed with {response.status}. Retrying...")
                    except Exception as e:
                        logging.error(f"Req {request_id}: Attempt {attempt+1}/{MAX_RETRIES} error: {e}. Retrying...")
                    if attempt < MAX_RETRIES - 1: await asyncio.sleep(RETRY_COOLDOWN_SECONDS)
                
                if response_json:
                    if response_status == 200:
                        output_tokens = count_output_tokens(response_json)
                        # 3. 양쪽 서버의 TPD, TPM 최종 기록 (TTL 부여)
                        tpm_member = f"{input_tokens}:{output_tokens}:{unique_id}"
                        await llm_redis_client.incrby(f"{llm_prefix}:tpd:{today_str}", input_tokens + output_tokens)
                        await llm_redis_client.zadd(f"{llm_prefix}:tpm_window", {tpm_member: now})
                        await llm_redis_client.expire(f"{llm_prefix}:tpm_window", 120)
                        
                        await redis_client.incr(f"{apim_prefix}:rpd:{today_str}")
                        await redis_client.incrby(f"{apim_prefix}:tpd:{today_str}", input_tokens + output_tokens)
                        await redis_client.zadd(f"{apim_prefix}:tpm_window", {tpm_member: now})
                        await redis_client.expire(f"{apim_prefix}:tpm_window", 120)
                    RESULTS_STORE[request_id] = (response_json, response_status)
                else:
                    RESULTS_STORE[request_id] = ({"error": f"Failed after {MAX_RETRIES} attempts."}, 503)
            except Exception as e:
                RESULTS_STORE[request_id] = ({"error": str(e)}, 500)
            finally:
                event.set()
                REQUEST_QUEUE.task_done()

@asynccontextmanager
async def lifespan(app: FastAPI):
    redis_client = redis.from_url(f"redis://{config.REDIS_HOST}:{config.REDIS_PORT}/{config.APIM_REDIS_DB}", decode_responses=True)
    llm_redis_client = redis.from_url(f"redis://{config.REDIS_HOST}:{config.REDIS_PORT}/{config.LLM_REDIS_DB}", decode_responses=True)
    
    # 용량 버킷 초기화
    await redis_client.delete(
        f"{config.APIM_USAGE_PREFIX}:rpm_capacity",
        f"{config.APIM_USAGE_PREFIX}:tpm_capacity"
    )

    # APIM 모니터링 키 초기화 (앱 재기동 시 테스트 리셋 목적)
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    await redis_client.delete(
        f"{config.APIM_USAGE_PREFIX}:rpm_window",
        f"{config.APIM_USAGE_PREFIX}:tpm_window",
        f"{config.APIM_USAGE_PREFIX}:rpd:{today_str}",
        f"{config.APIM_USAGE_PREFIX}:tpd:{today_str}"
    )
    
    worker_task = asyncio.create_task(background_worker(redis_client, llm_redis_client))
    yield
    worker_task.cancel()
    await redis_client.close()
    await llm_redis_client.close()

app = FastAPI(title="LLM Request APIM", lifespan=lifespan)

@app.post("/v1/chat/completions")
async def process_request(request: Request):
    request_id = str(uuid.uuid4())
    payload = await request.json()
    event = asyncio.Event()
    COMPLETION_EVENTS[request_id] = event
    await REQUEST_QUEUE.put((request_id, payload, event))
    try:
        await asyncio.wait_for(event.wait(), timeout=300.0)
    except asyncio.TimeoutError:
        return JSONResponse(content={"error": "Request timed out in APIM queue."}, status_code=status.HTTP_504_GATEWAY_TIMEOUT)
    finally:
        result_payload, result_status = RESULTS_STORE.pop(request_id, ({"error": "Result not found"}, 500))
        COMPLETION_EVENTS.pop(request_id, None)
    return JSONResponse(content=result_payload, status_code=result_status)