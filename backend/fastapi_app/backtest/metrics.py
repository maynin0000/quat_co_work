import polars as pl
import numpy as np

def calculate_portfolio_metrics(daily_returns: pl.Series) -> dict:
    """
    포트폴리오의 일일 수익률(Series)을 받아 주요 성과 지표를 계산합니다.
    (모든 연산은 Polars C/Rust 엔진 위에서 초고속으로 동작)
    """
    if len(daily_returns) == 0:
        return {"cagr": 0.0, "mdd": 0.0, "sharpe": 0.0, "cumulative_return": 0.0}

    # 1. 누적 수익률 (Cumulative Return) 계산: (1 + r).cumprod()
    # 주의: Polars에서 Series 연산을 직관적으로 처리
    cum_returns = (1.0 + daily_returns).cum_prod()
    
    total_days = len(daily_returns)
    final_value = cum_returns[-1]
    
    # 누적 수익률 (%)
    total_return_pct = (final_value - 1.0) * 100

    # 2. CAGR (연평균 성장률) - 1년 영업일 252일 기준
    cagr = (final_value ** (252 / total_days)) - 1.0
    cagr_pct = cagr * 100

    # 3. MDD (최대 낙폭)
    rolling_max = cum_returns.cum_max()
    drawdowns = (cum_returns - rolling_max) / rolling_max
    mdd_pct = drawdowns.min() * 100

    # 4. Sharpe Ratio (무위험 수익률 Rf는 보수적으로 2% 가정 -> 일일 약 0.000079)
    rf_daily = 0.02 / 252
    excess_returns = daily_returns - rf_daily
    std_dev = daily_returns.std()
    
    # 방어적 코딩: 표준편차가 0인 경우(변동성 없음) 0으로 처리
    sharpe = (excess_returns.mean() / std_dev) * np.sqrt(252) if std_dev > 0 else 0.0

    return {
        "cumulative_return": round(total_return_pct, 2),
        "cagr": round(cagr_pct, 2),
        "mdd": round(mdd_pct, 2),
        "sharpe": round(sharpe, 2)
    }