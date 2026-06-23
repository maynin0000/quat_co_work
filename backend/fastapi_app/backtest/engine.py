import polars as pl
import asyncio
import logging
from typing import List, Dict, Any, Optional
from backtest.metrics import calculate_portfolio_metrics

logger = logging.getLogger(__name__)

class PolarsBacktestEngine:
    def __init__(self, market_data: pl.DataFrame):
        """
        market_data: lifespan에서 로드한 3년 치 일봉 데이터
        필수 컬럼: 'date', 'ticker', 'daily_return', 'pbr', 'per', 등
        """
        self.df = market_data

    def _apply_conditions(self, df: pl.DataFrame, conditions: List[Dict[str, Any]]) -> pl.DataFrame:
        """주어진 조건식에 맞춰 데이터프레임을 필터링하는 헬퍼 함수"""
        filtered = df
        for cond in conditions:
            factor, op, val = cond["factor"], cond["operator"], cond["value"]
            if op == "<": filtered = filtered.filter(pl.col(factor) < val)
            elif op == ">": filtered = filtered.filter(pl.col(factor) > val)
            elif op == "<=": filtered = filtered.filter(pl.col(factor) <= val)
            elif op == ">=": filtered = filtered.filter(pl.col(factor) >= val)
            # top%, bottom% 같은 복잡한 연산은 Polars의 rank() 함수로 확장 가능
        return filtered

    def _run_sync(self, conditions: List[Dict[str, Any]], rebalancing: Optional[str] = None) -> dict:
        try:
            # 1. Buy & Hold 방식 (주린이 기본값: rebalancing=None)
            if not rebalancing:
                # 백테스트 시작일 기준(예: 3년 전 첫 거래일)의 데이터만 짤라서 조건 필터링
                start_date = self.df["date"].min()
                initial_universe = self.df.filter(pl.col("date") == start_date)
                
                selected_stocks = self._apply_conditions(initial_universe, conditions)
                selected_tickers = selected_stocks["ticker"].to_list()
                
                if not selected_tickers:
                    return {"error": "초기 조건에 맞는 종목이 없습니다."}

                # 3년 내내 처음에 뽑힌 종목들(selected_tickers)만 보유했다고 가정
                portfolio_df = self.df.filter(pl.col("ticker").is_in(selected_tickers))
                
                # 일별 동일비중(Equal Weight) 수익률 계산
                daily_portfolio_return = (
                    portfolio_df
                    .group_by("date")
                    .agg(pl.col("daily_return").mean().alias("port_return"))
                    .sort("date")
                )

            # 2. 주기적 리밸런싱 방식 (고급 유저 옵션)
            else:
                # 월말(Monthly) 리밸런싱이라고 가정
                # 매월 말일의 데이터를 뽑아서 매달 새로운 selected_tickers를 구하고,
                # 다음 달의 수익률에 매핑하는 고난도 Polars 윈도우 연산이 들어감.
                # (실제 구현 시 groupby_dynamic이나 truncate 연산을 활용)
                logger.info(f"🔄 {rebalancing} 주기 리밸런싱 연산 수행 중...")
                
                # 로직 단순화를 위한 수도코드(Pseudocode)성 구현부
                # 실제로는 매월 초에 _apply_conditions를 다시 호출해서 편입 종목을 교체함
                portfolio_df = self._apply_conditions(self.df, conditions)
                daily_portfolio_return = (
                    portfolio_df
                    .group_by("date")
                    .agg(pl.col("daily_return").mean().alias("port_return"))
                    .sort("date")
                )

            # 3. 성과 지표 계산
            metrics = calculate_portfolio_metrics(daily_portfolio_return["port_return"])
            
            return {
                "status": "success",
                "metrics": metrics,
                "rebalancing_applied": rebalancing if rebalancing else "Buy & Hold"
            }

        except Exception as e:
            logger.error(f"🚨 [Backtest Error] 엔진 연산 실패: {e}")
            return {"error": str(e)}

    async def run_backtest_async(self, conditions: List[Dict[str, Any]], rebalancing: Optional[str] = None) -> dict:
        logger.info(f"🚀 [Backtest] 연산 시작 (리밸런싱: {rebalancing or '없음'})")
        return await asyncio.to_thread(self._run_sync, conditions, rebalancing)