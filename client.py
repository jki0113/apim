import asyncio
import aiohttp
import time
import logging
from typing import List, Dict, Any, Tuple
from tqdm.asyncio import tqdm # --- 변경된 부분: tqdm의 비동기 버전을 import 합니다.

# --- 변경된 부분: 표준 로깅 모듈을 설정합니다. ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# --- 클라이언트 설정 (기본값) ---
DEFAULT_API_URL = "http://127.0.0.1:8001/v1/chat/completions"
DEFAULT_API_KEY = "DUMMY_KEY"

# --- 추가된 부분: 재시도 설정 ---
MAX_RETRIES = 5
RETRY_COOLDOWN_SECONDS = 10

async def _send_single_request(
    session: aiohttp.ClientSession, 
    task_id: int, 
    prompt: str, 
    api_url: str
) -> Tuple[int, Dict[str, Any]]:
    """단일 요청을 브로커 서버에 비동기적으로 보내는 내부 헬퍼 함수."""
    payload = {"messages": [{"role": "user", "content": prompt}]}
    
    # --- 수정된 부분: 재시도 로직 추가 ---
    for attempt in range(MAX_RETRIES):
        try:
            async with session.post(api_url, json=payload, headers={"Authorization": f"Bearer {DEFAULT_API_KEY}"}) as response:
                # 성공 (2xx) 또는 클라이언트 오류 (4xx)는 즉시 반환 (재시도 안 함)
                if response.status < 500:
                    result = await response.json()
                    if response.status != 200:
                        logging.warning(f"Task #{task_id}: Received non-200 status: {response.status} - Response: {result}")
                    return task_id, result

                # 서버 오류 (5xx)인 경우 재시도
                logging.warning(f"Task #{task_id}: Attempt {attempt + 1}/{MAX_RETRIES} failed with server error: {response.status}. Retrying in {RETRY_COOLDOWN_SECONDS}s...")

        except Exception as e:
            # 타임아웃 등 aiohttp 관련 예외 발생 시 재시도
            logging.error(f"Task #{task_id}: Attempt {attempt + 1}/{MAX_RETRIES} failed with client error: {e}. Retrying in {RETRY_COOLDOWN_SECONDS}s...")
        
        # 마지막 시도가 아니면 재시도 전 대기
        if attempt < MAX_RETRIES - 1:
            await asyncio.sleep(RETRY_COOLDOWN_SECONDS)
    
    # 모든 재시도 실패 시 최종 에러 반환
    logging.error(f"Task #{task_id}: FAILED after {MAX_RETRIES} attempts.")
    return task_id, {"error": f"Failed after {MAX_RETRIES} attempts."}

async def send_request(
    prompt_list: List[str],
    api_url: str = DEFAULT_API_URL
) -> List[Tuple[int, Dict[str, Any]]]:
    """
    주어진 프롬프트 목록을 요청 브로커에 병렬로 전송하고 모든 결과를 수집합니다.
    Jupyter Notebook에서 사용하기에 최적화된 함수입니다.
    """
    num_requests = len(prompt_list)
    logging.info(f"--- Sending {num_requests} prompts to APIM at {api_url} ---")

    start_time = time.perf_counter()
    
    async with aiohttp.ClientSession() as session:
        tasks = [
            asyncio.create_task(_send_single_request(session, i, prompt, api_url))
            for i, prompt in enumerate(prompt_list)
        ]
        
        # --- 변경된 부분: asyncio.gather를 tqdm.gather로 감싸 프로그레스 바를 표시합니다. ---
        results = await tqdm.gather(*tasks, desc="Processing prompts")

    end_time = time.perf_counter()
    
    logging.info(f"--- All {num_requests} tasks completed in {end_time - start_time:.2f} seconds ---")
    
    return sorted(results, key=lambda x: x[0])

# --- 변경된 부분: 테스트를 위한 if __name__ == "__main__" 블록 추가 ---
if __name__ == "__main__":
    # 이 파일을 직접 실행하여 테스트할 수 있습니다.
    
    # 1. 처리할 프롬프트 목록 준비
    my_prompts = [f"This is a test prompt number {i}." for i in range(200)]
    
    # 2. 함수 호출
    # Jupyter가 아닌 일반 .py 파일에서 실행할 때는 asyncio.run()을 사용합니다.
    results = asyncio.run(send_request(prompt_list=my_prompts))
    
    # 3. 결과 요약
    logging.info(f"총 {len(results)}개의 결과를 받았습니다.")
    succeeded_count = sum(1 for _, res in results if "error" not in res)
    failed_count = len(results) - succeeded_count
    logging.info(f"성공: {succeeded_count}, 실패: {failed_count}")

    # 4. 샘플 결과 출력
    logging.info("--- 첫 5개 결과 ---")
    for task_id, result in results[:5]:
        content = result.get('choices', [{}])[0].get('message', {}).get('content', 'Error')
        logging.info(f"Task {task_id}: {content[:80]}...")