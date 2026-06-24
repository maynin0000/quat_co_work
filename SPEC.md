# Quantra — 설계 명세서 & 운영 설명서

> 주식 용어를 몰라도 자연어로 질문하면, **논문 근거 + 실제 재무 데이터 교차검증**으로
> 종목을 추천하는 RAG 퀀트 서비스.

---

## 1. 시스템 한눈에 보기

```
┌─────────────────────────────────────────────────────────────┐
│  프론트엔드  frontend/demo.html  (단일 HTML, 브라우저로 실행)    │
│   - 자연어 입력 → SSE 수신 → 추천 카드 렌더                      │
│   - FastAPI 미연결 시 Mock 자동 폴백                            │
└───────────────┬─────────────────────────────────────────────┘
                │  POST /ai/recommend/stream   (SSE)
                ▼
┌─────────────────────────────────────────────────────────────┐
│  FastAPI  backend/fastapi_app   (AI 추천 엔진)                  │
│   main.py(lifespan DI) → routers/recommend.py(SSE)            │
│     → services/recommender.py (핵심 추천 로직)                  │
│         ├ rag/embedder.py       질문 임베딩                     │
│         ├ rag/retriever.py      ChromaDB 논문 검색              │
│         └ services/financial_repo.py  재무데이터(JSON or Mock)  │
└──────┬───────────────────────────────┬──────────────────────┘
       │ 논문 벡터                       │ 재무 스냅샷(JSON)
       ▼                                ▼
┌──────────────┐              ┌──────────────────────────────┐
│  ChromaDB    │              │ data_pipeline (수집 파이프라인) │
│ paper_       │◀─ 적재 ──────│  scripts/run_kci.py   논문      │
│ strategies   │              │  scripts/run_financial.py 재무  │
└──────────────┘              │   └ collectors/krx.py (pykrx)  │
                              └──────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  Django  backend/django_app   (사용자/전략/포트폴리오/피드백)    │
│   - JWT 인증, CRUD. FastAPI와는 shared 스키마로 계약            │
└─────────────────────────────────────────────────────────────┘

           shared/  ← Django·FastAPI·pipeline 공통 스키마/유틸
```

---

## 2. 폴더 구조와 역할

```
PJT_FINAL/
├── .env                         ← 모든 비밀키/접속정보 (공용)
├── docker-compose.yml           ← postgres·redis·chromadb·django·fastapi
│
├── shared/                      ★ 세 모듈 공통. 여기 수정은 합의 후 PR
│   ├── schemas/
│   │   ├── financial.py         FinancialRawData (재무 원본 정규화)
│   │   ├── paper.py             ExtractedStrategy (논문 전략)
│   │   ├── strategy.py          LLMAnalysisOutput / UserStrategy
│   │   └── recommendation.py    RecommendationResult (최종 응답 계약)
│   ├── utils/
│   │   ├── normalizer.py        수집 dict → FinancialRawData 변환
│   │   └── validators.py        LLM 출력 검증
│   └── constants/
│       ├── factors.py           팩터명 매핑, 신뢰도 임계값
│       └── sectors.py           섹터명 표준화
│
├── backend/
│   ├── fastapi_app/             ── AI 추천 엔진 ──
│   │   ├── main.py              앱 생성 + lifespan DI + /ai/health
│   │   ├── routers/recommend.py /ai/recommend/stream (SSE)
│   │   ├── services/
│   │   │   ├── recommender.py   질문→팩터추출→논문검색→종목매칭→설명
│   │   │   └── financial_repo.py JsonFinancialRepo / MockFinancialRepo
│   │   └── rag/
│   │       ├── embedder.py      OpenAI 임베딩
│   │       └── retriever.py     ChromaDB 검색(지연연결+문턱완화)
│   │
│   └── django_app/              ── 사용자/CRUD ──
│       ├── quant_users/         커스텀 유저 + JWT
│       ├── quant_strategy/      전략 저장 + internal API
│       ├── quant_portfolio/     포트폴리오/관심종목
│       └── quant_feedback/      추천 피드백
│
├── data_pipeline/               ── 데이터 수집 ──
│   ├── collectors/
│   │   ├── krx.py               pykrx 시세+펀더멘털 (PBR/PER/배당)
│   │   ├── dart.py              DART 재무제표(계정)
│   │   └── paper_collector.py   KCI 논문 검색
│   ├── processors/
│   │   └── paper_processor.py   논문→전략 추출→ChromaDB 적재
│   ├── scripts/
│   │   ├── run_kci.py           논문 수집 실행
│   │   └── run_financial.py     ★ 재무 수집 실행 → JSON 스냅샷
│   └── data/
│       └── financial_snapshot.json  (run_financial 결과물)
│
└── frontend/
    └── demo.html                단일 HTML 데모 프론트
```

---

## 3. 데이터 흐름 (추천 1회)

```
1. 사용자: "배당 많이 주는 안정적인 주식" 입력
2. demo.html → POST /ai/recommend/stream
3. recommend.py:
   a. embedder.get_embeddings([질문])      → 질문 벡터
   b. recommender.generate_recommendation()
      - 질문에서 팩터 추출 (dividend, debt, value …)
      - retriever.search_papers_async()    → 관련 논문 전략 검색
        · completeness 80 → 없으면 40 → 0 → 무필터 자동 완화
      - financial_repo.get_all_stocks()     → 재무데이터(실/Mock)
      - 논문 전략 ↔ 종목 재무 교차 매칭 + 스코어링
      - LLM이 추천 사유/요약/리스크 생성
   c. 결과를 SSE로 스트리밍 (processing… → complete)
4. demo.html: 카드 렌더 (신뢰도/논문근거/교차검증표/리스크)
```

핵심 계약: 최종 응답은 항상 `shared/schemas/recommendation.py`의
`RecommendationResult` 형태. 프론트·Django·FastAPI가 같은 모양을 공유.

---

## 4. 무엇을 켜고 무엇을 실행하나 (운영)

### 4-1. 처음 1회 세팅
```bash
cp .env.example .env
# .env 채우기: OPENAI_API_KEY, OPENAI_BASE_URL(GMS), KCI_API_KEY,
#              POSTGRES_*, REDIS_URL
```

### 4-2. 인프라 컨테이너
```bash
docker compose up -d postgres redis chromadb
docker compose ps     # 3개 Up 확인
```
| 컨테이너 | 포트 | 용도 |
|---|---|---|
| postgres | 5432 | Django DB |
| redis | 6379 | Django 캐시/세션 |
| chromadb | 8002 | 논문 벡터 검색 |

### 4-3. 데이터 수집 (★ 루트에서, 한 번만)
```bash
# 논문 → ChromaDB 적재
python -m data_pipeline.scripts.run_kci --per-query 10 --max-papers 100

# 가격 기반 전략 5종 백테스트 결과 생성
python -m data_pipeline.scripts.run_backtest_data --years 3 --top-n 5

# ETF 추천·전략 데이터 생성
python -m data_pipeline.scripts.run_etf --limit 100
python -m data_pipeline.scripts.run_etf_backtest

# 재무 → JSON 스냅샷 (KRX 실데이터)
python -m data_pipeline.scripts.run_financial --top 50
#   결과: data_pipeline/data/financial_snapshot.json
#   이게 있으면 FastAPI가 자동으로 실데이터 사용, 없으면 Mock
```

### 4-4. 서버 기동
```bash
# FastAPI (★ 반드시 루트에서)
uvicorn backend.fastapi_app.main:app --port 8001 --reload

# Django (별 터미널)
cd backend/django_app && python manage.py runserver
```

### 4-5. 상태 확인
```bash
curl http://localhost:8001/ai/health
# components.chromadb: connected / financial_repo: JsonFinancialRepo
# (수집 안 했으면 chromadb: down / financial_repo: MockFinancialRepo)
```

### 4-6. 데모
`frontend/demo.html` 더블클릭 → 질문 입력.

---

## 5. 무엇을 사용하나 (기술 스택)

| 영역 | 사용 |
|---|---|
| AI 추천 | FastAPI, OpenAI(GMS 프록시), ChromaDB(cosine) |
| 재무 수집 | pykrx(get_market_cap / get_market_fundamental) |
| 논문 수집 | KCI OpenAPI + GPT-4o-mini 추출 |
| 사용자/CRUD | Django, DRF, SimpleJWT |
| 저장소 | PostgreSQL, Redis, ChromaDB |
| 공통 계약 | Pydantic v2 스키마 (shared/) |
| 프론트 | 단일 HTML + SSE (fetch ReadableStream) |

---

## 6. 안전장치 (데모 무사고 설계)

| 실패 지점 | 자동 대응 |
|---|---|
| ChromaDB 미기동 | retriever 지연연결 → 서버는 기동, health에 down 표시 |
| 논문 검색 0건 | completeness 문턱 80→40→0→무필터 자동 완화 |
| 재무 스냅샷 없음 | JsonFinancialRepo → MockFinancialRepo 자동 폴백 |
| OpenAI 호출 실패 | SSE error 전송 → 프론트가 Mock 폴백 |
| FastAPI 자체 미기동 | 프론트 health 체크 실패 → 데모 모드 전환 |

→ 어느 단계가 죽어도 화면에는 결과가 나온다.

---

## 7. 자주 막히는 것

| 증상 | 원인 / 해결 |
|---|---|
| `ModuleNotFoundError: backend` | 루트 아닌 곳에서 uvicorn 실행. 루트에서 실행 |
| health `chromadb: down` | `docker compose up -d chromadb` 누락 |
| 추천이 Mock만 나옴 | `run_financial` 미실행. 돌리면 실데이터 |
| 포트 8002 충돌 | 기존 chroma 떠 있음. `docker compose down` 후 재기동 |
| pykrx 수집 실패 | 사내 방화벽/휴장일. `--date 20260623`로 영업일 지정 |

---

## 8. 남은 확장 (이후 작업)

- DART corp_code 매핑 붙여서 ROE/부채비율 정밀화 (현재 KRX 비율 위주)
- 논문 전략 metadata에 `factors: [pbr, dividend]` 넣어 retriever 정밀화
- Django ↔ FastAPI internal API 실연결 (현재 스키마 계약만 완료)
- 백테스트 엔진(engine.py) 추천 결과에 연결
- 사용자 피드백 → Few-shot Pool 품질 개선 루프
