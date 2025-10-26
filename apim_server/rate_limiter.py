import asyncio
import time
from datetime import datetime, timedelta, timezone
from uuid import uuid4
import redis.asyncio as redis
import config

class RateLimiter:
    def __init__(self, redis_client: redis.Redis, rpm_limit: int, tpm_limit: int, rpd_limit: int, tpd_limit: int):
        self.redis = redis_client
        self.rpm_limit = int(config.RPM_LIMIT * config.LATENCY)
        self.tpm_limit = int(config.TPM_LIMIT * config.LATENCY)
        self.rpd_limit = int(config.RPD_LIMIT * config.LATENCY)
        self.tpd_limit = int(config.TPD_LIMIT * config.LATENCY)

        self.today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        self.rpd_key = f"{config.APIM_USAGE_PREFIX}:rpd:{self.today_str}"
        self.tpd_key = f"{config.APIM_USAGE_PREFIX}:tpd:{self.today_str}"
        self.rpm_key = f"{config.APIM_USAGE_PREFIX}:rpm_window"
        self.tpm_key = f"{config.APIM_USAGE_PREFIX}:tpm_window"
    def _get_seconds_until_midnight(self) -> int:
        now = datetime.now(timezone.utc)
        tomorrow = now + timedelta(days=1)
        midnight = tomorrow.replace(hour=0, minute=0, second=0, microsecond=0)
        return int((midnight - now).total_seconds())

    async def wait_for_capacity(self, input_token_count: int):
        lua_script = """
            -- KEYS[1]: rpd_key, KEYS[2]: tpd_key, KEYS[3]: rpm_key, KEYS[4]: tpm_key
            -- ARGV[1]: one_minute_ago, ARGV[2]: rpd_limit, ARGV[3]: tpd_limit,
            -- ARGV[4]: rpm_limit, ARGV[5]: tpm_limit, ARGV[6]: input_token_count

            -- 1. 분당 창 정리
            redis.call('ZREMRANGEBYSCORE', KEYS[3], '-inf', ARGV[1])
            redis.call('ZREMRANGEBYSCORE', KEYS[4], '-inf', ARGV[1])

            -- 2. 현재 사용량 확인
            local rpd = tonumber(redis.call('GET', KEYS[1]) or 0)
            local tpd = tonumber(redis.call('GET', KEYS[2]) or 0)
            local rpm = redis.call('ZCARD', KEYS[3])
            
            local tpm_members = redis.call('ZRANGE', KEYS[4], 0, -1)
            local tpm = 0
            for _, member in ipairs(tpm_members) do
                local in_tok, out_tok = string.match(member, '^(%d+):(%d+):')
                tpm = tpm + tonumber(in_tok) + tonumber(out_tok)
            end

            -- 3. 제한 확인 및 결과 반환
            if rpd >= tonumber(ARGV[2]) then return {'RPD', 99999} end
            if tpd + tonumber(ARGV[6]) > tonumber(ARGV[3]) then return {'TPD', 99999} end
            if rpm >= tonumber(ARGV[4]) then
                local oldest = redis.call('ZRANGE', KEYS[3], 0, 0, 'WITHSCORES')
                if #oldest > 0 then return {'RPM', oldest[2]} end
            end
            if tpm + tonumber(ARGV[6]) > tonumber(ARGV[5]) then
                local oldest = redis.call('ZRANGE', KEYS[4], 0, 0, 'WITHSCORES')
                if #oldest > 0 then return {'TPM', oldest[2]} end
            end

            return {'OK', 0}
        """
        while True:
            now = time.time()
            one_minute_ago = now - 60
            
            result = await self.redis.eval(
                lua_script, 4, self.rpd_key, self.tpd_key, self.rpm_key, self.tpm_key,
                one_minute_ago, self.rpd_limit, self.tpd_limit, self.rpm_limit, self.tpm_limit, input_token_count
            )
            
            status, value = result[0], float(result[1])

            if status == 'OK':
                break
            
            wait_time = 0
            if status in ['RPD', 'TPD']:
                wait_time = self._get_seconds_until_midnight()
                print(f"Daily limit '{status}' reached. Waiting for {wait_time:.2f} seconds until midnight.")
            elif status in ['RPM', 'TPM']:
                wait_time = (value + 60) - now
                print(f"Minute limit '{status}' reached. Waiting for {wait_time:.2f} seconds.")

            await asyncio.sleep(max(0.1, wait_time)) # 최소 0.1초 대기

    async def record_successful_request(self, input_tokens: int, output_tokens: int):
        now = time.time()
        unique_id = uuid4()
        member_rpm = f"{now}:{unique_id}"
        member_tpm = f"{input_tokens}:{output_tokens}:{unique_id}"

        async with self.redis.pipeline(transaction=True) as pipe:
            # 일일 사용량 기록
            pipe.incr(self.rpd_key)
            pipe.incrby(self.tpd_key, input_tokens + output_tokens)
            pipe.ttl(self.rpd_key)
            # 분당 사용량 기록
            pipe.zadd(self.rpm_key, {member_rpm: now})
            pipe.zadd(self.tpm_key, {member_tpm: now})
            results = await pipe.execute()

        key_ttl = results[2]
        if key_ttl == -1:
            seconds_to_midnight = self._get_seconds_until_midnight()
            await self.redis.expire(self.rpd_key, seconds_to_midnight)
            await self.redis.expire(self.tpd_key, seconds_to_midnight)
        
        # 분당 키에도 만료시간을 걸어 트래픽이 없을 때 자동 삭제되도록 함
        await self.redis.expire(self.rpm_key, 60)
        await self.redis.expire(self.tpm_key, 60)