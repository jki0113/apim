# monitor.py (프로젝트 루트에 위치)
import os
import time
from datetime import datetime, timezone
import redis
import importlib

# --- 중앙 설정 파일 import ---
# 스크립트가 루트에 있으므로, 간단하게 import 가능합니다.
import config

def clear_screen():
    """터미널 화면을 지웁니다."""
    os.system('cls' if os.name == 'nt' else 'clear')

def get_daily_usage(redis_client, key_prefix: str):
    """지정된 접두사를 사용하여 RPD, TPD 사용량을 가져옵니다."""
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    rpd_key = f"{key_prefix}:rpd:{today_str}"
    tpd_key = f"{key_prefix}:tpd:{today_str}"
    
    rpd, tpd = redis_client.mget(rpd_key, tpd_key)
    return int(rpd) if rpd else 0, int(tpd) if tpd else 0

def get_minute_usage(redis_client, key_prefix: str, is_gateway: bool = False):
    """지정된 접두사를 사용하여 RPM, TPM 사용량을 가져옵니다."""
    rpm_key = f"{key_prefix}:rpm_window"
    tpm_key = f"{key_prefix}:tpm_window"
    
    rpm = redis_client.zcard(rpm_key)
    tpm_members = redis_client.zrange(tpm_key, 0, -1)
    
    total_tokens = 0
    for member in tpm_members:
        try:
            parts = member.split(':')
            if is_gateway and len(parts) >= 2:
                # 게이트웨이 형식: "input:output:uuid" -> input + output
                total_tokens += int(parts[0]) + int(parts[1])
            elif not is_gateway and len(parts) >= 1:
                # APIM 서버 형식: "tokens:uuid" -> tokens
                total_tokens += int(parts[0])
        except (ValueError, IndexError):
            continue
            
    return rpm, total_tokens

def format_status(label: str, current: int, limit: int) -> str:
    """출력 형식을 만듭니다."""
    percentage = (current / limit * 100) if limit > 0 else 0
    return f"{label.ljust(4)}: {str(current).rjust(8)} / {str(limit).ljust(8)} ({percentage:5.1f}%)"

def main():
    """통합 모니터링 스크립트의 메인 함수."""
    print("Connecting to Redis for Unified Monitoring...")
    # 각 서버가 사용하는 DB에 맞춰 별도의 Redis 클라이언트를 생성합니다.
    r_llm = redis.Redis(host=config.REDIS_HOST, port=config.REDIS_PORT, db=config.LLM_REDIS_DB, decode_responses=True)
    r_gateway = redis.Redis(host=config.REDIS_HOST, port=config.REDIS_PORT, db=config.APIM_REDIS_DB, decode_responses=True)
    print("Connection successful. Starting monitoring...")
    time.sleep(1)

    try:
        while True:
            # 중앙 config.py를 매번 다시 로드하여 변경사항을 실시간으로 반영합니다.
            importlib.reload(config)
            clear_screen()

            # --- LLM 서버 데이터 가져오기 ---
            apim_rpd, apim_tpd = get_daily_usage(r_llm, config.LLM_RATE_LIMIT_PREFIX)
            apim_rpm, apim_tpm = get_minute_usage(r_llm, config.LLM_RATE_LIMIT_PREFIX, is_gateway=False)

            # --- APIM 서버 데이터 가져오기 ---
            gw_rpd, gw_tpd = get_daily_usage(r_gateway, config.APIM_USAGE_PREFIX)
            gw_rpm, gw_tpm = get_minute_usage(r_gateway, config.APIM_USAGE_PREFIX, is_gateway=True)

            # --- 화면 출력 ---
            print("=" * 24 + " MONITORING " + "=" * 24)
            
            print("\n--- LLM Server (Enforcer) ---")
            print(format_status("RPD", apim_rpd, config.RPD_LIMIT))
            print(format_status("TPD", apim_tpd, config.TPD_LIMIT))
            print(format_status("RPM", apim_rpm, config.RPM_LIMIT))
            print(format_status("TPM", apim_tpm, config.TPM_LIMIT))
            
            print("\n--- APIM Server (Scheduler) ---")
            print(f"LATENCY FACTOR: {config.LATENCY:.2f}")
            # 게이트웨이의 목표 제한값은 LATENCY 적용하여 계산합니다.
            gw_rpd_limit = int(config.RPD_LIMIT * config.LATENCY)
            gw_tpd_limit = int(config.TPD_LIMIT * config.LATENCY)
            gw_rpm_limit = int(config.RPM_LIMIT * config.LATENCY)
            gw_tpm_limit = int(config.TPM_LIMIT * config.LATENCY)
            print(format_status("RPD", gw_rpd, gw_rpd_limit))
            print(format_status("TPD", gw_tpd, gw_tpd_limit))
            print(format_status("RPM", gw_rpm, gw_rpm_limit))
            print(format_status("TPM", gw_tpm, gw_tpm_limit))
            
            print("\n" + "=" * 60)
            print("(Config reloaded every second. Press Ctrl+C to exit)")
            
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\nMonitoring stopped.")
    except redis.exceptions.ConnectionError as e:
        print(f"\nCould not connect to Redis: {e}")

if __name__ == "__main__":
    main()