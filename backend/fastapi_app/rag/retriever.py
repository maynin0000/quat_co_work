import asyncio
import chromadb
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

class ChromaVectorStore:
    def __init__(self, host: str = "127.0.0.1", port: int = 8002):
        self.client = chromadb.HttpClient(host=host, port=port)
        
        # 🌟 아키텍트 포인트 유지: 코사인(cosine) 유사도 적용
        self.paper_collection = self.client.get_or_create_collection(
            name="paper_strategies",
            metadata={"hnsw:space": "cosine"} 
        )

    async def add_papers_async(
        self, 
        ids: List[str], 
        embeddings: List[List[float]], 
        documents: List[str], 
        metadatas: List[Dict[str, Any]]
    ):
        """[Async Wrapper] DB 쓰기 작업 (upsert 사용하여 중복 적재 에러 원천 차단)"""
        try:
            # 🚨 리뷰 반영: add 대신 upsert 사용
            await asyncio.to_thread(
                self.paper_collection.upsert,
                ids=ids,
                embeddings=embeddings,
                documents=documents,
                metadatas=metadatas
            )
            logger.info(f"✅ [ChromaDB] {len(ids)}개의 논문 청크 적재(upsert) 완료")
        except Exception as e:
            logger.error(f"🚨 [ChromaDB Error] 데이터 적재 실패: {e}")

    async def search_papers_async(
        self, 
        query_embedding: List[float], 
        n_results: int = 3, 
        sector_filter: Optional[str] = None,  # 🚨 리뷰 반영: 하위 호환성을 위해 파라미터 유지
        min_completeness: float = 80.0        # Fallback 데이터(0.0) 필터링용
    ) -> dict:
        """[Async Wrapper] 임베딩된 질문으로 고품질 논문 전략 검색"""
        if not query_embedding:
            logger.warning("⚠ 쿼리 벡터가 비어있습니다.")
            return {"ids": [], "documents": [], "metadatas": [], "distances": []}

        # 🚨 품질 점수 필터링 (Fallback 제외 및 고품질 데이터만 추출)
        where_clause = {"completeness": {"$gte": min_completeness}}

        # 향후 메타데이터에 sectors가 추가되면 아래 로직을 $and 조건으로 활성화하면 됨
        # if sector_filter and sector_filter != "전체":
        #     pass 

        try:
            results = await asyncio.to_thread(
                self.paper_collection.query,
                query_embeddings=[query_embedding],
                n_results=n_results,
                where=where_clause
            )
            return results
        except Exception as e:
            logger.error(f"🚨 [ChromaDB Error] 검색 실패: {e}")
            return {"ids": [], "documents": [], "metadatas": [], "distances": []}