import logging
from typing import List, Dict, Any
from shared.schemas.financial import FinancialRawData
from shared.schemas.recommendation import MatchResult, WhyThisStock, RecommendationResult

logger = logging.getLogger(__name__)

class CrossValidator:
    def __init__(self):
        # 가중치 설정 (네 철학 반영)
        self.FINANCIAL_WEIGHT = 0.70
        self.RAG_WEIGHT = 0.30

    def calculate_confidence_score(
        self, 
        stock: FinancialRawData, 
        rag_distance: float, 
        financial_match_rate: float
    ) -> float:
        """
        정형 데이터(70%)와 벡터 거리(30%)를 결합하여 최종 신뢰도 점수 산출
        - rag_distance는 코사인 거리이므로 작을수록 좋음 (0에 가까울수록 유사)
        """
        # RAG 점수 환산 (거리가 0이면 100점, 거리가 1 이상이면 0점에 가깝게)
        rag_score = max(0.0, (1.0 - rag_distance) * 100.0)
        
        # 재무 매칭 점수 환산 (0.0 ~ 1.0 비율을 100점 만점으로)
        fin_score = financial_match_rate * 100.0
        
        # 가중 평균 스코어
        final_score = (fin_score * self.FINANCIAL_WEIGHT) + (rag_score * self.RAG_WEIGHT)
        
        # 데이터 충족도(Completeness) 페널티 (빈 칸이 많은 재무데이터는 신뢰도 깎음)
        if stock.data_completeness < 80.0:
            final_score *= 0.8 
            
        return round(min(final_score, 100.0), 1)

    def generate_match_results(self, stock: FinancialRawData, filters: dict) -> List[MatchResult]:
        """재무 필터 조건 대비 실제 데이터가 얼마나 일치하는지 교차검증"""
        results = []
        match_count = 0
        total_conditions = len(filters.keys())
        
        if total_conditions == 0:
            return [], 1.0 # 조건이 없으면 매칭률 100%

        # 임시 로직 (실제로는 필터 연산자에 따라 상세 비교 필요)
        for factor, condition in filters.items():
            stock_val = getattr(stock, factor, None)
            if stock_val is None:
                continue
                
            # 간단한 예시 검증 로직 (실제 운영 시 <, >, == 연산자 파싱 필요)
            is_match = True # Mocking
            gap = 0.0 # Mocking
            
            if is_match: match_count += 1
            
            results.append(MatchResult(
                factor=factor,
                paper_condition=str(condition),
                stock_value=stock_val,
                is_match=is_match,
                gap=gap
            ))
            
        match_rate = match_count / total_conditions if total_conditions else 0.0
        return results, match_rate