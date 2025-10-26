#!/bin/bash

# --- 설정 ---
# 실행할 파이썬 '모듈' 경로를 지정합니다.
# '폴더명.파일명' 형식으로 작성합니다.
LLM_SERVER_MODULE="llm_mock_server.run"
API_GATEWAY_MODULE="apim_server.run"

# 실행된 서버들의 PID를 저장할 파일 이름
PID_FILE=".service_pids"

# --- 함수 정의 ---

start_servers() {
    if [ -f "$PID_FILE" ]; then
        echo "PID file '$PID_FILE' already exists. Servers might be running."
        echo "Please run './manage_services.sh shutdown' first."
        exit 1
    fi

    echo "--- Starting all servers in background (from project root) ---"

    # 1. LLM Mock Server 실행
    echo "Starting LLM Mock Server..."
    # python -m 옵션을 사용하여 모듈로 실행합니다.
    python -m "$LLM_SERVER_MODULE" &
    PID_LLM=$!
    echo $PID_LLM > "$PID_FILE"
    echo "[STARTED] LLM Mock Server with PID: $PID_LLM"

    # 2. API Gateway Server 실행
    echo "Starting API Gateway Server..."
    # python -m 옵션을 사용하여 모듈로 실행합니다.
    python -m "$API_GATEWAY_MODULE" &
    PID_GATEWAY=$!
    echo $PID_GATEWAY >> "$PID_FILE"
    echo "[STARTED] API Gateway Server with PID: $PID_GATEWAY"

    echo -e "\nAll servers are running. PIDs are stored in '$PID_FILE'."
    echo "To stop them, run './manage_services.sh shutdown'"
}

shutdown_servers() {
    if [ ! -f "$PID_FILE" ]; then
        echo "PID file '$PID_FILE' not found. No servers to shut down."
        exit 0
    fi

    echo "--- Shutting down all servers ---"
    
    while read -r pid; do
        if [ -n "$pid" ] && ps -p $pid > /dev/null; then
            echo "Stopping process with PID: $pid"
            kill $pid
        else
            echo "Process with PID $pid not found or already stopped."
        fi
    done < "$PID_FILE"

    rm "$PID_FILE"
    echo "Cleanup complete. PID file removed."
}

# --- 메인 로직 ---
case "$1" in
    start)
        start_servers
        ;;
    shutdown)
        shutdown_servers
        ;;
    *)
        echo "Usage: $0 {start|shutdown}"
        exit 1
        ;;
esac