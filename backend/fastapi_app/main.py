import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from openai import AsyncOpenAI
from dotenv import load_dotenv

# 🚨 피드백 1번 반영: 환경 변수 로드 (최상단에서 실행해서 확실하게 잡아줌)
load_dotenv()

# 우리가 만든 모듈들 임포트
from backend.fastapi_app.rag.embedder import QuantEmbedder
from backend.fastapi_app.rag.retriever import ChromaVectorStore
from backend.fastapi_app.services.financial_repo import get_financial_repo
from backend.fastapi_app.services.recommender import QuantRecommender
from backend.fastapi_app.services.strategy_repo import StrategyBacktestRepo
from backend.fastapi_app.services.etf_repo import EtfRepo
from backend.fastapi_app.services.etf_recommender import EtfRecommender
from backend.fastapi_app.routers import backtest, etf, recommend

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    서버 시작 시 전역(Global) 의존성 객체들을 초기화하고 app.state에 바인딩합니다.
    """
    logger.info("🚀 [Lifespan] 서버 기동: 의존성 객체 초기화 시작...")

    # 1. OpenAI 클라이언트 설정 (.env에서 안전하게 로드됨)
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        logger.warning("⚠ OPENAI_API_KEY 미설정 — LLM 호출은 실패할 수 있으나 서버는 기동합니다.")
        api_key = "sk-not-configured"
    
    openai_client = AsyncOpenAI(
        api_key=api_key,
        base_url="https://gms.ssafy.io/gmsapi/api.openai.com/v1/"
    )

    # 2. RAG 컴포넌트 (Embedder, VectorStore)
    embedder = QuantEmbedder(openai_client)
    vector_store = ChromaVectorStore(
        host=os.getenv("CHROMA_HOST", "127.0.0.1"),
        port=int(os.getenv("CHROMA_PORT", "8002")),
    )

    # 3. 데이터 Repo (Mock)
    financial_repo = get_financial_repo()

    # 4. 추천 엔진 (Recommender) 
    recommender = QuantRecommender(
        vector_store=vector_store,
        financial_repo=financial_repo,
        llm_client=openai_client
    )

    # 5. app.state에 바인딩
    app.state.openai_client = openai_client
    app.state.embedder = embedder
    app.state.vector_store = vector_store
    app.state.financial_repo = financial_repo
    app.state.recommender = recommender
    app.state.strategy_repo = StrategyBacktestRepo()
    app.state.etf_repo = EtfRepo()
    app.state.etf_recommender = EtfRecommender(app.state.etf_repo)

    logger.info("✅ [Lifespan] 모든 의존성 객체 초기화 및 바인딩 완료!")
    
    yield
    
    logger.info("🛑 [Lifespan] 서버 종료: 리소스 정리")

# FastAPI 앱 객체 생성
app = FastAPI(
    title="Quant RAG API",
    description="논문 기반 퀀트 전략 종목 추천 API",
    version="1.0.0",
    lifespan=lifespan
)

# 🚨 피드백 4번 반영: CORS 미들웨어 복구 (프론트엔드 연동용)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 운영 환경에서는 실제 프론트엔드 도메인으로 제한 필요
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 라우터 등록
app.include_router(recommend.router, prefix="/ai/recommend", tags=["Recommend"])
app.include_router(backtest.router, prefix="/ai/backtest", tags=["Backtest"])
app.include_router(etf.router, prefix="/ai/etf", tags=["ETF"])

# 🚨 피드백 4번 반영: 기존 운영 확인용 헬스체크 원복
@app.get("/ai/health", tags=["System"])
async def health_check():
    """시스템 및 주요 컴포넌트 연결 상태 확인."""
    from fastapi import Request as _R  # noqa
    chroma_ok = False
    try:
        # ChromaDB 핑: 컬렉션 count 호출
        import asyncio as _a
        cnt = await _a.to_thread(app.state.vector_store.paper_collection.count)
        chroma_ok = True
    except Exception:
        cnt = None
    openai_ok = hasattr(app.state, "openai_client")
    return {
        "status": "ok",
        "message": "Quant RAG API is running!",
        "components": {
            "openai": "connected" if openai_ok else "down",
            "chromadb": "connected" if chroma_ok else "down",
            "paper_count": cnt,
            "financial_repo": type(app.state.financial_repo).__name__,
        },
    }
