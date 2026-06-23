import json
from typing import List, Dict
from backend.fastapi_app.llm.few_shot_pool import StrategyFewShotPool

class QuantPromptBuilder:
    def __init__(self):
        self.few_shot_pool = StrategyFewShotPool()

    def build_extraction_prompt(self, chunk_text: str) -> List[Dict[str, str]]:
        """
        논문 전략 추출을 위한 시스템 프롬프트 + Few-shot 예시 + 실제 유저 쿼리를 병합
        """
        messages = [
            {
                "role": "system",
                "content": (
                    "당신은 세계 최고의 퀀트 리서치 AI입니다. "
                    "주어진 논문 텍스트에서 투자 전략, 팩터 조건, 성과 지표를 추출하세요. "
                    "반드시 아래 Few-shot 예시와 동일한 JSON 스키마를 엄격하게 준수해야 합니다."
                )
            }
        ]
        
        # 1. 황금 예시(Few-shot) 주입
        messages.extend(self.few_shot_pool.get_paper_extraction_examples())
        
        # 2. 실제 분석할 텍스트 주입
        messages.append({
            "role": "user",
            "content": f"이제 다음 텍스트에서 전략을 추출해 JSON으로 반환해:\n\n{chunk_text}"
        })
        
        return messages

    def build_recommendation_prompt(self, user_query: str, retrieved_papers: List[dict], user_risk: str) -> List[Dict[str, str]]:
        """
        [Phase 5 예고] RAG 검색 결과를 바탕으로 유저에게 종목을 추천하는 프롬프트
        """
        # 이 부분은 추천 엔진(Phase 5)에서 완성할 예정
        pass