import logging
from typing import List
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

class QuantEmbedder:
    def __init__(self, client: AsyncOpenAI):
        """
        [사수의 아키텍처 포인트] 
        __init__에서 객체를 직접 생성하지 않고 외부(app.state)에서 주입받는다.
        Connection Pool 낭비를 막는 완벽한 DI(Dependency Injection) 패턴.
        """
        self.client = client
        self.model = "text-embedding-3-small"

    async def get_embedding(self, text: str) -> List[float]:
        """단일 텍스트를 벡터로 변환"""
        try:
            # 개행 문자를 공백으로 치환하여 임베딩 품질 향상
            cleaned_text = text.replace("\n", " ")
            response = await self.client.embeddings.create(
                input=[cleaned_text],
                model=self.model
            )
            return response.data[0].embedding
        except Exception as e:
            logger.error(f"🚨 [Embedder Error] 단일 벡터 변환 실패: {e}")
            return []  # 폴백을 위한 빈 리스트 반환

    async def get_embeddings(self, texts: List[str]) -> List[List[float]]:
        """여러 텍스트를 한 번에 벡터로 변환 (배치 처리 - Phase 3 적재용)"""
        try:
            cleaned_texts = [t.replace("\n", " ") for t in texts]
            response = await self.client.embeddings.create(
                input=cleaned_texts,
                model=self.model
            )
            return [data.embedding for data in response.data]
        except Exception as e:
            logger.error(f"🚨 [Embedder Error] 배치 벡터 변환 실패: {e}")
            return []