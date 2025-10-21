import os
import time
from datetime import datetime, timezone
import redis
import importlib

from app.core import config as app_config

def clear_screen():
    """터미널 화면을 지웁니다."""
    os.system('cls' if os.name == 'nt' else 'clear')

def get_daily_usage(redis_client, key_prefix: str, limit: int):
    """RPD, TPD 사용량을 가져옵니다."""
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    key = f"rate_limit:{key_prefix}:{today_str}"
    value = redis_client.get(key)
    return int(value) if value else 0, limit

def get_rpm_usage(redis_client, limit: int):
    """RPM 사용량을 가져옵니다."""
    key = "rate_limit:rpm_window"
    value = redis_client.zcard(key)
    return value, limit

def get_tpm_usage(redis_client, limit: int):
    """TPM 사용량을 가져옵니다."""
    key = "rate_limit:tpm_window"
    members = redis_client.zrange(key, 0, -1)
    total_tokens = 0
    for member in members:
        try:
            total_tokens += int(member.split(':')[0])
        except (ValueError, IndexError):
            continue
    return total_tokens, limit

def format_status(label: str, current: int, limit: int) -> str:
    """출력 형식을 만듭니다."""
    percentage = (current / limit * 100) if limit > 0 else 0
    return f"{label.ljust(4)}: {str(current).rjust(5)} / {str(limit).ljust(5)} ({percentage:5.1f}%)"

def main():
    """모니터링 스크립트의 메인 함수."""
    print("Connecting to Redis...")
    r = redis.Redis(
        host=app_config.REDIS_HOST,
        port=app_config.REDIS_PORT,
        db=app_config.REDIS_DB,
        decode_responses=True
    )
    print("Connection successful. Starting monitoring...")
    time.sleep(1)

    try:
        while True:
            importlib.reload(app_config)
            
            clear_screen()
            
            rpd_curr, rpd_limit = get_daily_usage(r, "rpd", app_config.RPD_LIMIT)
            tpd_curr, tpd_limit = get_daily_usage(r, "tpd", app_config.TPD_LIMIT)
            
            # --- 이 부분이 수정되었습니다 ---
            # 불필요한 "rpm", "tpm" 인자를 제거했습니다.
            rpm_curr, rpm_limit = get_rpm_usage(r, app_config.RPM_LIMIT)
            tpm_curr, tpm_limit = get_tpm_usage(r, app_config.TPM_LIMIT)

            print("=" * 20 + " LLM SERVER STATUS (Live) " + "=" * 19)
            print(format_status("RPD", rpd_curr, rpd_limit))
            print(format_status("TPD", tpd_curr, tpd_limit))
            print(format_status("RPM", rpm_curr, rpm_limit))
            print(format_status("TPM", tpm_curr, tpm_limit))
            print("=" * 61)
            print("(Config file is reloaded every second. Press Ctrl+C to exit)")
            
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\nMonitoring stopped.")
    except redis.exceptions.ConnectionError as e:
        print(f"\nCould not connect to Redis: {e}")

if __name__ == "__main__":
    main()