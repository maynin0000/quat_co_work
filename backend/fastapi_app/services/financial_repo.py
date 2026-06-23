from typing import List
from shared.schemas.financial import FinancialRawData

class MockFinancialRepo:
    """API 테스트를 위한 임시 재무 데이터 저장소"""
    
    async def get_all_stocks(self) -> List[FinancialRawData]:
        # 저PBR, 고배당, 고ROE 등 다양한 조건에 걸리도록 세팅된 테스트 셋
        return [
            FinancialRawData(ticker="005930", name="삼성전자", pbr=1.3, roe=11.5, dividend_yield=2.5, debt_ratio=40.0),
            FinancialRawData(ticker="005380", name="현대차", pbr=0.7, roe=12.2, dividend_yield=5.1, debt_ratio=150.0),
            FinancialRawData(ticker="000660", name="SK하이닉스", pbr=1.8, roe=8.0, dividend_yield=1.5, debt_ratio=50.0),
            FinancialRawData(ticker="055550", name="신한지주", pbr=0.4, roe=9.5, dividend_yield=6.5, debt_ratio=800.0),
            FinancialRawData(ticker="035420", name="NAVER", pbr=1.5, roe=15.5, dividend_yield=0.5, debt_ratio=45.0)
        ]