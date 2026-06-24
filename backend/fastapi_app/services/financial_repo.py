import os
import json
import logging
from typing import List
from shared.schemas.financial import FinancialRawData

logger = logging.getLogger(__name__)

# run_financial.py 가 저장하는 스냅샷 경로
SNAPSHOT_PATH = os.path.join("data_pipeline", "data", "financial_snapshot.json")


class MockFinancialRepo:
    """
    데모/개발용 재무 데이터 저장소.
    저PBR·고배당·고ROE·저부채 등 다양한 조건에 골고루 걸리도록 구성한 검증 셋.
    """
    async def get_all_stocks(self) -> List[FinancialRawData]:
        rows = [
            # ticker, name, pbr, per, roe, dividend_yield, debt_ratio, momentum_1y, market_cap(억)
            ("005930", "삼성전자",   1.3, 11.0, 11.5, 2.5,  40.0,  8.0, 4200000),
            ("005380", "현대차",     0.7,  6.0, 12.2, 5.1, 150.0, 12.0,  480000),
            ("000660", "SK하이닉스", 1.8, 14.0,  8.0, 1.5,  50.0, 22.0,  900000),
            ("055550", "신한지주",   0.4,  5.5,  9.5, 6.5, 800.0,  4.0,  230000),
            ("035420", "NAVER",     1.5, 28.0, 15.5, 0.5,  45.0, -5.0,  320000),
            ("000270", "기아",       0.8,  5.0, 14.0, 4.2,  90.0, 15.0,  380000),
            ("105560", "KB금융",     0.5,  6.0, 10.2, 5.8, 900.0,  6.0,  280000),
            ("033780", "KT&G",      1.4, 12.0, 13.8, 4.6,  43.0,  2.0,  130000),
            ("030200", "KT",        0.6,  9.0,  7.5, 4.9,  95.0,  3.0,  100000),
            ("000810", "삼성화재",   0.9, 10.0, 11.0, 5.1,  60.0,  5.0,  130000),
            ("012330", "현대모비스", 0.6,  8.0,  8.8, 2.2,  35.0,  7.0,  220000),
            ("051910", "LG화학",     1.1, 18.0,  6.5, 1.8,  80.0,-10.0,  280000),
            ("006400", "삼성SDI",    1.2, 25.0,  7.0, 1.0,  70.0,-15.0,  250000),
            ("015760", "한국전력",   0.3, 99.0, -2.0, 0.0, 180.0, -8.0,  120000),
            ("034730", "SK",        0.8,  9.0,  9.0, 3.2, 120.0,  4.0,  110000),
            ("003550", "LG",        0.7,  8.0,  8.0, 4.0,  30.0,  3.0,   90000),
            ("066570", "LG전자",     0.9, 10.0,  9.2, 2.0,  85.0,  6.0,   95000),
            ("086790", "하나금융",   0.4,  5.0, 10.5, 6.8, 850.0,  5.0,  170000),
            ("316140", "우리금융",   0.4,  5.0,  9.8, 7.0, 880.0,  3.0,  100000),
            ("259960", "크래프톤",   2.8, 22.0, 16.0, 0.0,  20.0, 18.0,  130000),
        ]
        result = []
        for (t, n, pbr, per, roe, dy, dr, mo, mc) in rows:
            # 실데이터 스냅샷이 없을 때도 다중 팩터 로직을 검증할 수 있도록
            # 서로 일관된 범위의 데모 지표를 파생한다.
            row = FinancialRawData(
                ticker=t, name=n, pbr=pbr, per=per, roe=roe,
                dividend_yield=dy, debt_ratio=dr, momentum_1y=mo, market_cap=mc,
                psr=round(max(0.2, pbr * 1.1), 2),
                ev_ebitda=round(max(2.0, per * 0.65), 2),
                fcf_yield=round(max(-2.0, 12.0 - per * 0.45), 2),
                roa=round(roe * 0.55, 2),
                current_ratio=round(max(55.0, 180.0 - dr * 0.12), 2),
                op_margin=round(max(-5.0, roe * 0.8), 2),
                operating_cash_flow=round((roe + mo) * 1000, 2),
                free_cash_flow=round((roe + mo - 4.0) * 700, 2),
                revenue_growth=round(5.0 + mo * 0.6, 2),
                profit_growth=round(roe - 5.0 + mo * 0.4, 2),
                op_growth=round(roe - 4.0 + mo * 0.3, 2),
                momentum_6m=round(mo * 0.6, 2),
                momentum_3m=round(mo * 0.35, 2),
                momentum_1m=round(mo * 0.1, 2),
                volatility=round(18.0 + abs(mo) * 0.6, 2),
                dividend_growth=round(dy - 1.0, 2),
            )
            row.data_completeness = row.compute_completeness()
            result.append(row)
        return result


class JsonFinancialRepo:
    """
    실제 수집 데이터 저장소.
    data_pipeline/scripts/run_financial.py 가 만든 JSON 스냅샷을 읽어 제공한다.
    파일이 없거나 비면 MockFinancialRepo 로 자동 폴백.
    """
    def __init__(self, path: str = SNAPSHOT_PATH):
        self.path = path
        self._fallback = MockFinancialRepo()

    async def get_all_stocks(self) -> List[FinancialRawData]:
        if not os.path.exists(self.path):
            logger.warning(f"⚠ [FinancialRepo] 스냅샷 없음({self.path}) → Mock 폴백")
            return await self._fallback.get_all_stocks()
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                payload = json.load(f)
            stocks = payload.get("stocks", [])
            if not stocks:
                raise ValueError("빈 스냅샷")
            result = [FinancialRawData(**s) for s in stocks]
            logger.info(f"✅ [FinancialRepo] 실수집 데이터 {len(result)}종목 로드 ({payload.get('date')})")
            return result
        except Exception as e:
            logger.error(f"🚨 [FinancialRepo] 스냅샷 로드 실패 → Mock 폴백: {e}")
            return await self._fallback.get_all_stocks()


def get_financial_repo():
    """
    스냅샷 있으면 JsonFinancialRepo, 없으면 MockFinancialRepo.
    main.py lifespan 에서 이 팩토리를 호출.
    """
    if os.path.exists(SNAPSHOT_PATH):
        logger.info("[FinancialRepo] 실수집 스냅샷 발견 → JsonFinancialRepo 사용")
        return JsonFinancialRepo()
    logger.info("[FinancialRepo] 스냅샷 없음 → MockFinancialRepo 사용")
    return MockFinancialRepo()
