import time
from datetime import datetime, timedelta, timezone
from uuid import uuid4
import redis.asyncio as redis

class RateLimiter:
    """
    Redis를 사용하여 Rate Limit 로직을 처리
    하나의 Lua 스크립트로 모든 확인/증가 로직 처리
    """
    def __init__(self, redis_client: redis.Redis, rpm_limit: int, tpm_limit: int, rpd_limit: int, tpd_limit: int):
        self.redis = redis_client
        self.rpm_limit = rpm_limit
        self.tpm_limit = tpm_limit
        self.rpd_limit = rpd_limit
        self.tpd_limit = tpd_limit
        self.lua_script = self._load_lua_script()

    def _load_lua_script(self) -> str:
        """모든 Rate Limit 로직을 처리하는 Lua 스크립트"""
        return """
            -- KEYS[1]: rpd_key, KEYS[2]: tpd_key, KEYS[3]: rpm_key, KEYS[4]: tpm_key
            -- ARGV[1]: request_tokens, ARGV[2]: rpd_limit, ARGV[3]: tpd_limit, ARGV[4]: rpm_limit, ARGV[5]: tpm_limit
            -- ARGV[6]: now, ARGV[7]: one_minute_ago, ARGV[8]: member, ARGV[9]: seconds_to_midnight

            -- RPD/TPD 확인인
            local current_rpd = tonumber(redis.call('GET', KEYS[1]) or 0)
            if current_rpd >= tonumber(ARGV[2]) then
                return {'RPD_EXCEEDED', ARGV[2]}
            end

            local current_tpd = tonumber(redis.call('GET', KEYS[2]) or 0)
            if current_tpd + tonumber(ARGV[1]) > tonumber(ARGV[3]) then
                return {'TPD_EXCEEDED', ARGV[3]}
            end

            -- RPM/TPM 확인
            redis.call('ZREMRANGEBYSCORE', KEYS[3], '-inf', ARGV[7])
            redis.call('ZREMRANGEBYSCORE', KEYS[4], '-inf', ARGV[7])

            local current_rpm = redis.call('ZCARD', KEYS[3])
            if current_rpm >= tonumber(ARGV[4]) then
                return {'RPM_EXCEEDED', ARGV[4]}
            end

            local token_members = redis.call('ZRANGE', KEYS[4], 0, -1)
            local current_tpm = 0
            for _, token_member in ipairs(token_members) do
                current_tpm = current_tpm + tonumber(string.match(token_member, '^(%d+):'))
            end
            if current_tpm + tonumber(ARGV[1]) > tonumber(ARGV[5]) then
                return {'TPM_EXCEEDED', ARGV[5]}
            end

            -- 확인 완료 후 카운터 증가
            local new_rpd = redis.call('INCR', KEYS[1])

            -- 신규 키 만료 시간 설정
            if new_rpd == 1 then
                redis.call('EXPIRE', KEYS[1], ARGV[9])
            end

            local new_tpd = redis.call('INCRBY', KEYS[2], ARGV[1])
            if new_tpd == tonumber(ARGV[1]) then
                redis.call('EXPIRE', KEYS[2], ARGV[9])
            end
            
            redis.call('ZADD', KEYS[3], ARGV[6], ARGV[8])
            redis.call('EXPIRE', KEYS[3], 65)

            redis.call('ZADD', KEYS[4], ARGV[6], ARGV[1] .. ':' .. ARGV[8])
            redis.call('EXPIRE', KEYS[4], 65)

            return {'OK'}
        """

    def _get_seconds_until_midnight(self) -> int:
        """현재 시간 기준으로 다음 날 자정까지 남은 시간을 초 단위로 반환"""
        now = datetime.now(timezone.utc)
        tomorrow = now + timedelta(days=1)
        midnight = tomorrow.replace(hour=0, minute=0, second=0, microsecond=0)
        return int((midnight - now).total_seconds())

    async def check_limit_exceeded(self, request_token_count: int) -> str | None:
        """
        하나의 Lua 스크립트로 모든 Rate Limit 규칙 확인 및 적용
        """
        now = time.time()
        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        
        # Redis 키 정의
        rpd_key = f"rate_limit:rpd:{today_str}"
        tpd_key = f"rate_limit:tpd:{today_str}"
        rpm_key = "rate_limit:rpm_window"
        tpm_key = "rate_limit:tpm_window"
        
        # Lua 스크립트에 전달할 인자들
        args = [
            request_token_count,
            self.rpd_limit, self.tpd_limit, self.rpm_limit, self.tpm_limit,
            now,
            now - 60, # one_minute_ago
            f"{now}:{uuid4()}", # member
            self._get_seconds_until_midnight()
        ]

        # Lua 스크립트 실행
        result = await self.redis.eval(self.lua_script, 4, rpd_key, tpd_key, rpm_key, tpm_key, *args)

        # 결과 처리
        status = result[0]
        if status == 'OK':
            return None
        
        limit_value = result[1]
        if status == 'RPD_EXCEEDED':
            return f"Rate limit exceeded: {limit_value} requests per day."
        if status == 'TPD_EXCEEDED':
            return f"Rate limit exceeded: {limit_value} tokens per day."
        if status == 'RPM_EXCEEDED':
            return f"Rate limit exceeded: {limit_value} requests per minute."
        if status == 'TPM_EXCEEDED':
            return f"Rate limit exceeded: {limit_value} tokens per minute."
        
        return "Unknown rate limit error."