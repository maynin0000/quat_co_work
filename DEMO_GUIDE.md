# Quantra 데모 실행 가이드

발표 직전, 이 순서대로만 하면 됩니다. 어느 단계가 막혀도 데모는 돌아갑니다.

---

## 0. 준비 (한 번만)

```bash
# 프로젝트 루트(PJT_FINAL)에서
cp .env.example .env   # 이미 .env 있으면 생략
# .env 안에 OPENAI_API_KEY, KCI_API_KEY 채워져 있는지 확인
```

---

## 1. 인프라 컨테이너 띄우기

```bash
docker compose up -d postgres redis chromadb
docker compose ps   # 3개 다 Up 확인
```

> ChromaDB가 안 떠도 FastAPI는 기동됩니다(지연 연결).
> 단, 논문 검색은 비니까 가능하면 띄우세요.

---

## 2. 논문 데이터 적재 (한 번만, 이미 했으면 생략)

```bash
# 루트에서
python -m data_pipeline.scripts.run_kci --per-query 10 --max-papers 100
python data_pipeline/scripts/peek_db.py   # 적재 확인(있으면)

# 3년 가격 데이터 기반 전략 백테스트 생성
python -m data_pipeline.scripts.run_backtest_data --years 3 --top-n 5

# ETF 100개 평가 스냅샷 + ETF 전략 백테스트
python -m data_pipeline.scripts.run_etf --limit 100
python -m data_pipeline.scripts.run_etf_backtest
```

---

## 3. FastAPI 서버 기동 (★ 루트에서 실행 ★)

```bash
# 반드시 프로젝트 루트(PJT_FINAL)에서. import가 backend.fastapi_app... 이라 그렇습니다.
uvicorn backend.fastapi_app.main:app --host 0.0.0.0 --port 8001 --reload
```

확인:
```bash
curl http://localhost:8001/ai/health
# {"status":"ok", "components":{"openai":"connected","chromadb":"connected","paper_count":N, ...}}
```

---

## 4. 프론트 열기

`frontend/demo.html` 을 **브라우저로 더블클릭**.

- 우측 상단 배지가 **"FastAPI 연결됨 · 실시간 분석"(초록)** 이면 진짜 백엔드로 동작
- **"데모 모드"(앰버)** 면 백엔드 미연결 → 샘플 데이터로 시연 (그래도 화면 흐름 동일)

---

## 5. 데모 시나리오

입력창에 질문하거나 예시 칩 클릭:

1. **"배당 많이 주는 안정적인 주식 찾아줘"**
2. **"저평가된 가치주 찾아줘"**
3. **"부채 적고 안정적인 우량주"**

→ 진행 로그(질문분석 → 교차검색 → 신뢰도계산) 흐른 뒤
→ 추천 카드: 종목 · 신뢰도 게이지 · 논문근거/현재상태/교차검증 · **재무 교차검증 테이블** · 쉬운 요약 · 리스크

---

## 발표 포인트 (차별점)

- 카드마다 **논문 근거 + 현재 재무 + 교차검증**을 같이 보여줌
  → "왜 이 종목인지 논문으로 설명하고, 지금 재무가 그 조건에 맞는지 검증"
- **재무 교차검증 테이블**(논문 조건 vs 실제 수치 ✓)이 핵심 차별점
- "재무 데이터는 현재 검증용 셋이고, DART/KRX 수집 파이프라인 연결만 남았다"고 말하면 충분

---

## 안전장치 (이미 들어가 있음)

| 상황 | 동작 |
|---|---|
| ChromaDB 안 뜸 | FastAPI는 기동됨, health에 chromadb:down 표시 |
| 논문 검색 0건 | completeness 문턱 자동 완화(80→40→0→무필터) |
| OpenAI 호출 실패 | SSE로 에러 흘리고 프론트가 자동 Mock 폴백 |
| FastAPI 자체 미기동 | 프론트가 데모 모드로 자동 전환 |

→ **어느 단계가 실패해도 화면에는 결과가 나옵니다.**

---

## 자주 막히는 것

- `ModuleNotFoundError: backend` → 루트가 아닌 곳에서 uvicorn 실행한 것. 루트에서 실행.
- health에 `chromadb:down` → `docker compose up -d chromadb` 안 함.
- 포트 8002 충돌 → 다른 ChromaDB 떠 있음. `docker compose down` 후 재기동.
