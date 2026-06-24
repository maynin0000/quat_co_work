import asyncio
import chromadb
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

class ChromaVectorStore:
    """
    ChromaDB 래퍼.

    [데모 안정성] 생성자에서 곧바로 연결하지 않고 '지연 연결(lazy)'한다.
    ChromaDB 서버가 아직 안 떠 있어도 FastAPI lifespan/기동은 성공해야 하므로,
    실제 연결은 컬렉션이 처음 필요할 때 시도하고 실패하면 빈 결과로 폴백한다.
    """
    def __init__(self, host: str = "127.0.0.1", port: int = 8002):
        self.host = host
        self.port = port
        self._client = None
        self._collection = None
        self._connect()  # 한번 시도하되 실패해도 예외 안 던짐

    def _connect(self):
        if self._collection is not None:
            return self._collection
        try:
            self._client = chromadb.HttpClient(host=self.host, port=self.port)
            self._collection = self._client.get_or_create_collection(
                name="paper_strategies",
                metadata={"hnsw:space": "cosine"}
            )
            logger.info(f"✅ [ChromaDB] 연결 성공 ({self.host}:{self.port})")
        except Exception as e:
            logger.warning(f"⚠ [ChromaDB] 연결 실패 — 지연 재시도 모드: {e}")
            self._collection = None
        return self._collection

    @property
    def paper_collection(self):
        """기존 코드 호환: 접근 시 필요하면 재연결 시도."""
        return self._connect()

    async def add_papers_async(
        self,
        ids: List[str],
        embeddings: List[List[float]],
        documents: List[str],
        metadatas: List[Dict[str, Any]]
    ):
        col = self._connect()
        if col is None:
            logger.error("🚨 [ChromaDB] 미연결 상태 — 적재 건너뜀")
            return
        try:
            await asyncio.to_thread(
                col.upsert,
                ids=ids, embeddings=embeddings,
                documents=documents, metadatas=metadatas
            )
            logger.info(f"✅ [ChromaDB] {len(ids)}개 논문 청크 적재(upsert) 완료")
        except Exception as e:
            logger.error(f"🚨 [ChromaDB Error] 데이터 적재 실패: {e}")

    async def _query(self, query_embedding, n_results, where_clause):
        col = self._connect()
        if col is None:
            return None
        return await asyncio.to_thread(
            col.query,
            query_embeddings=[query_embedding],
            n_results=n_results,
            where=where_clause
        )

    async def search_papers_async(
        self,
        query_embedding: List[float],
        n_results: int = 3,
        sector_filter: Optional[str] = None,
        min_completeness: float = 80.0
    ) -> dict:
        """
        고품질 논문 전략 검색.
        [안전장치] completeness 문턱으로 검색 시 결과가 비면 문턱을 단계적으로
        낮춰 재검색(마지막은 필터 없음). '추천 결과 없음' 방지.
        """
        empty = {"ids": [], "documents": [], "metadatas": [], "distances": []}
        if not query_embedding:
            logger.warning("⚠ 쿼리 벡터가 비어있습니다.")
            return empty

        thresholds = [min_completeness, 40.0, 0.0, None]
        for th in thresholds:
            where_clause = {"completeness": {"$gte": th}} if th is not None else None
            try:
                results = await self._query(query_embedding, n_results, where_clause)
                if results is None:
                    return empty  # 미연결
                docs = results.get("documents") or [[]]
                if docs and docs[0]:
                    if th != min_completeness:
                        logger.info(f"[Retriever] completeness 문턱 완화: {th}")
                    return results
            except Exception as e:
                logger.error(f"🚨 [ChromaDB Error] 검색 실패(th={th}): {e}")
        return empty
