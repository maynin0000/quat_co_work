import logging
from pydantic import BaseModel, Field
from typing import List

logger = logging.getLogger(__name__)

# [아키텍트 포인트] LLM이 뱉어낼 구조를 Pydantic으로 강제하여 파싱 에러 0% 보장
class QueryAnalysisResult(BaseModel):
    expanded_keywords: List[str] = Field(description="벡터 검색용 확장 키워드")
    target_sectors: List[str] = Field(description="관심 섹터 리스트 (sectors.py 기준 표준어, 없으면 ['전체'])")
    financial_filters: dict = Field(description="DB 조회를 위한 재무 필터 조건 (예: {'per': {'<': 10}})")
    risk_tolerance: str = Field(description="유저 리스크 성향 추정 (low, medium, high)")

class QueryAnalyzer:
    def __init__(self, openai_client):
        self.client = openai_client

    async def analyze_user_query(self, user_input: str) -> QueryAnalysisResult:
        """
        유저의 자연어 질문을 RAG 검색용 키워드와 정형 DB 필터링 조건으로 분해합니다.
        """
        system_prompt = """
        당신은 퀀트 투자 전문가입니다. 사용자의 질문을 분석하여 팩터 조건을 구조화하세요.
        - 연산자는 반드시 "<", ">", "<=", ">=" 중 하나를 사용해야 합니다.
        - 예시: "PER 10 이하" -> {"per": {"<": 10}}
        - 예시: "ROE 15 이상" -> {"roe": {">=": 15}}
        """
        
        try:
            # OpenAI의 Structured Output(beta.chat.completions.parse) 사용
            response = await self.client.beta.chat.completions.parse(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_input}
                ],
                response_format=QueryAnalysisResult,
                temperature=0.1
            )
            parsed_result = response.choices[0].message.parsed
            logger.info(f"🔍 [Query Analysis] 분석 완료: {parsed_result.model_dump()}")
            return parsed_result
            
        except Exception as e:
            logger.error(f"🚨 [Analyzer Error] 쿼리 분석 실패: {e}")
            # 폴백: 실패해도 시스템이 멈추지 않도록 기본값 반환
            return QueryAnalysisResult(
                expanded_keywords=[user_input],
                target_sectors=["전체"],
                financial_filters={},
                risk_tolerance="medium"
            )