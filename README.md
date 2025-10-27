## 프로젝트 개요

이 레포지토리는 LLM API 호출을 안전하고 효율적으로 관리하기 위한 중앙 APIM 서버(스케줄러)와, 실제 모델 호출을 흉내내는 LLM Mock 서버(워커)로 구성됩니다. APIM은 들어오는 모든 요청을 받아 Redis 기반 토큰 버킷·슬라이딩 윈도우 조합으로 전송 속도를 제어하고, LLM과 APIM 양쪽의 사용량을 60초 윈도우 기준으로 모니터링합니다.

### 리포지토리 구조

```
250629-CTO_APIM/
├── apim_server/
│   ├── __init__.py
│   ├── apim_server.py       # FastAPI 앱, 큐, 스케줄러(원자적 Lua)와 모니터링 기록
│   ├── README.md
│   └── run.py               # APIM 실행 스크립트
├── llm_mock_server/
│   ├── app/
│   │   ├── main.py          # Mock LLM FastAPI (Rate Limit 없음)
│   │   ├── api/v1/router.py
│   │   └── api/v1/endpoints/chat.py
│   ├── README.md
│   └── run.py               # LLM 실행 스크립트
├── client.py                # 부하/기능 테스트 클라이언트
├── monitor.py               # Redis 사용량 통합 모니터(LLM/APIM 각각 60초 윈도우)
├── config.py                # 공통 설정(BURST_FACTOR/STRICT 등)
├── requirements.txt
├── server.sh                # 서버 실행/재시작 유틸
└── logs/, temp_memo.md, ...
```

## 동작 개요

1) 클라이언트가 APIM(`/v1/chat/completions`)로 요청을 전송합니다.
2) APIM은 요청을 큐에 적재하고, 백그라운드 스케줄러가 Redis에 저장된 용량(토큰)을 원자적으로 확인·차감합니다.
3) 용량이 확보되면 APIM이 LLM Mock 서버로 요청을 전달합니다. 실패(5xx/네트워크) 시 APIM에서 재시도합니다.
4) 응답이 성공이면 APIM/LLM 양쪽에 RPD/TPD, RPM/TPM을 60초 윈도우 기준으로 기록합니다.
5) `monitor.py`는 두 Redis DB를 조회하여 LLM/APIM의 현재 60초 내 사용량과 일일 사용량을 표기합니다.

## Rate Limiting 전략

- 토큰 버킷(초기 용량 = `limit * BURST_FACTOR`, 초당 충전 = `limit/60`) + 슬라이딩 윈도우(60초 ZSET) 조합
- 원자적 Lua 스크립트로 60초 윈도우 정리 → 현재 카운트 확인 → 토큰 리필/소비 → 윈도우 기록을 한 번에 처리하여 정합성 보장
- 옵션
  - `BURST_FACTOR`(0.0~1.0): 초기 버스트 허용 비율 (예: 0.8 → 시작 시 80%까지 즉시 전송 가능)
  - `ENFORCE_STRICT_RPM`(bool): 60초 윈도우 기준 절대 초과 금지 강제 여부(원자적 검사)

## 실행 방법(요약)

1) LLM Mock 서버 실행
```
python llm_mock_server/run.py
```
2) APIM 서버 실행
```
python apim_server/run.py
```
3) 모니터 실행
```
python monitor.py
```
4) 클라이언트 부하 테스트(선택)
```
python client.py
```

## 설정 가이드(config.py)

- `RPM_LIMIT`, `TPM_LIMIT`, `RPD_LIMIT`, `TPD_LIMIT`: 기준 한도
- `BURST_FACTOR`: 초기 버스트 크기(0.0=금지, 1.0=한도만큼)
- `ENFORCE_STRICT_RPM`: 슬라이딩 60초 절대 초과 방지
- `LLM_REDIS_DB`, `APIM_REDIS_DB`: LLM/APIM 모니터 DB 분리
- `APIM_URL`: APIM이 호출할 LLM 서버 엔드포인트

## 모니터링

- LLM/APIM 각각 `rpm_window`, `tpm_window`는 60초 이전 항목을 자동 정리하고 TTL(120s) 부여로 유휴 시 소멸
- 앱 재기동 시 APIM의 모니터링 키(`rpm_window`, `tpm_window`, `rpd:<today>`, `tpd:<today>`) 초기화로 깨끗한 테스트 시작

## 실패/재시도

- APIM 스케줄러는 LLM에 대한 5xx/네트워크 오류에 대해 최대 `MAX_RETRIES`, 쿨다운 `RETRY_COOLDOWN_SECONDS`로 재시도
- 429를 유발하지 않도록 사전 페이싱(버킷 + 60초 윈도우 검사)을 수행

## 트러블슈팅 팁

- 초기 스파이크가 크다고 느껴지면 `BURST_FACTOR`를 낮추세요
- 슬라이딩 60초 기준 절대 초과 금지는 `ENFORCE_STRICT_RPM=True`
- LLM 모니터가 0이면 LLM DB, 키 프리픽스(`LLM_RATE_LIMIT_PREFIX`)를 확인


