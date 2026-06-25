"""
Generate stock strategy backtest data from a broadened KRX universe.

The script prefers `data_pipeline/data/financial_snapshot.json` when present.
If that file is missing, it falls back to a curated market-cap-heavy universe
that is wider than the original 20-name large-cap set.
"""

from __future__ import annotations

import argparse
import json
import logging
import math
from datetime import date, timedelta
from pathlib import Path

import FinanceDataReader as fdr
import pandas as pd

from data_pipeline.scripts.backtest_validation import (
    completed_monthly_prices,
    last_completed_month_end,
    validate_backtest_payload,
    write_json_utf8,
)
from shared.constants.stocks import STOCK_CATALOG


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data_pipeline" / "data"
OUT_PATH = DATA_DIR / "strategy_backtests.json"


DEFAULT_UNIVERSE = STOCK_CATALOG


STRATEGIES = [
    {
        "id": "equal_weight",
        "name": "동일비중",
        "description": "대상 유니버스를 같은 비중으로 보유하는 기준 전략",
        "tags": ["분산", "기준전략", "동일비중"],
        "risk_level": "medium",
    },
    {
        "id": "momentum_12m",
        "name": "12개월 모멘텀",
        "description": "최근 12개월 수익률이 높은 종목을 추종하는 전략",
        "tags": ["모멘텀", "추세", "가격"],
        "risk_level": "high",
    },
    {
        "id": "low_volatility",
        "name": "저변동성 방어",
        "description": "최근 3개월 변동성이 낮은 종목을 중심으로 가져가는 방어 전략",
        "tags": ["저변동성", "방어", "안정"],
        "risk_level": "low",
    },
    {
        "id": "momentum_low_vol",
        "name": "모멘텀 + 저변동성",
        "description": "추세와 변동성을 함께 고려하는 혼합 전략",
        "tags": ["모멘텀", "저변동성", "스마트베타"],
        "risk_level": "medium",
    },
    {
        "id": "trend_defensive",
        "name": "추세 방어",
        "description": "6개월 수익률이 양호한 종목만 보유하고, 약세면 현금처럼 대기하는 전략",
        "tags": ["추세", "방어", "현금"],
        "risk_level": "low",
    },
    {
        "id": "momentum_6m",
        "name": "6개월 모멘텀",
        "description": "최근 6개월 수익률이 높은 종목을 추종해 중기 추세에 대응하는 전략",
        "tags": ["모멘텀", "중기추세", "가격"],
        "risk_level": "high",
    },
    {
        "id": "short_term_reversal",
        "name": "단기 반전",
        "description": "장기 추세가 훼손되지 않은 종목 중 최근 1개월 낙폭이 큰 종목의 반등을 노리는 전략",
        "tags": ["반전", "역발상", "단기"],
        "risk_level": "high",
    },
    {
        "id": "risk_adjusted_momentum",
        "name": "위험조정 모멘텀",
        "description": "12개월 수익률을 최근 변동성으로 나눠 위험 대비 추세가 강한 종목을 선택하는 전략",
        "tags": ["모멘텀", "위험조정", "스마트베타"],
        "risk_level": "medium",
    },
    {
        "id": "trend_consistency",
        "name": "추세 일관성",
        "description": "최근 6개월 동안 상승한 달이 많고 누적 수익률도 양호한 종목을 선택하는 전략",
        "tags": ["추세", "일관성", "퀄리티모멘텀"],
        "risk_level": "medium",
    },
]


def load_universe() -> dict[str, str]:
    snapshot = DATA_DIR / "financial_snapshot.json"
    if not snapshot.exists():
        return DEFAULT_UNIVERSE
    try:
        payload = json.loads(snapshot.read_text(encoding="utf-8"))
        rows = payload.get("stocks") or []
        universe = {
            str(row["ticker"]).zfill(6): str(row.get("name") or row["ticker"])
            for row in rows
            if row.get("ticker")
        }
        return universe or DEFAULT_UNIVERSE
    except Exception as exc:
        logger.warning("financial_snapshot.json loading failed, using fallback universe: %s", exc)
        return DEFAULT_UNIVERSE


def collect_prices(universe: dict[str, str], start: str, end: str) -> pd.DataFrame:
    series: dict[str, pd.Series] = {}
    for index, (ticker, name) in enumerate(universe.items(), 1):
        try:
            frame = fdr.DataReader(ticker, start, end)
            if frame.empty or "Close" not in frame:
                continue
            series[ticker] = frame["Close"].astype(float)
            logger.info("[%s/%s] %s(%s) collected %s days", index, len(universe), name, ticker, len(frame))
        except Exception as exc:
            logger.warning("%s(%s) price fetch failed: %s", name, ticker, exc)
    if len(series) < 5:
        raise RuntimeError(f"Not enough price series collected: {len(series)}")
    return pd.DataFrame(series).sort_index().ffill()


def calculate_metrics(returns: pd.Series) -> dict:
    returns = returns.dropna()
    if returns.empty:
        return {"cumulative_return": 0, "cagr": 0, "mdd": 0, "sharpe": 0, "volatility": 0}
    curve = (1 + returns).cumprod()
    years = max(len(returns) / 12, 1 / 12)
    cagr = curve.iloc[-1] ** (1 / years) - 1
    drawdown = curve / curve.cummax() - 1
    volatility = returns.std(ddof=0) * math.sqrt(12)
    std = returns.std(ddof=0)
    sharpe = ((returns.mean() - 0.02 / 12) / std * math.sqrt(12)) if std and std > 0 else 0
    return {
        "cumulative_return": round((curve.iloc[-1] - 1) * 100, 2),
        "cagr": round(cagr * 100, 2),
        "mdd": round(drawdown.min() * 100, 2),
        "sharpe": round(float(sharpe), 2),
        "volatility": round(volatility * 100, 2),
    }


def select_holdings(
    strategy_id: str,
    signal_date: pd.Timestamp,
    month_close: pd.DataFrame,
    daily_returns: pd.DataFrame,
    top_n: int,
) -> list[str]:
    available = month_close.loc[:signal_date].dropna(axis=1, how="all")
    if available.empty:
        return []

    tickers = list(available.columns)
    if strategy_id == "equal_weight":
        return tickers

    momentum_12m = available.pct_change(12, fill_method=None).iloc[-1]
    momentum_6m = available.pct_change(6, fill_method=None).iloc[-1]
    momentum_1m = available.pct_change(1, fill_method=None).iloc[-1]
    monthly_returns = available.pct_change(fill_method=None).tail(6)
    recent_daily = daily_returns.loc[:signal_date].tail(63)
    volatility = recent_daily.std() * math.sqrt(252)

    if strategy_id == "momentum_12m":
        return momentum_12m.dropna().nlargest(top_n).index.tolist()
    if strategy_id == "low_volatility":
        return volatility.dropna().nsmallest(top_n).index.tolist()
    if strategy_id == "momentum_low_vol":
        mom_rank = momentum_12m.rank(pct=True)
        low_vol_rank = 1 - volatility.rank(pct=True)
        score = (mom_rank + low_vol_rank).dropna()
        return score.nlargest(top_n).index.tolist()
    if strategy_id == "trend_defensive":
        positive = momentum_6m[momentum_6m > 0].dropna()
        return positive.nlargest(top_n).index.tolist()
    if strategy_id == "momentum_6m":
        return momentum_6m.dropna().nlargest(top_n).index.tolist()
    if strategy_id == "short_term_reversal":
        candidates = momentum_1m[(momentum_12m > 0) & momentum_1m.notna()]
        return candidates.nsmallest(top_n).index.tolist()
    if strategy_id == "risk_adjusted_momentum":
        score = (momentum_12m / volatility.replace(0, pd.NA)).dropna()
        return score.nlargest(top_n).index.tolist()
    if strategy_id == "trend_consistency":
        positive_month_ratio = monthly_returns.gt(0).mean()
        score = (positive_month_ratio * 0.6 + momentum_6m.rank(pct=True) * 0.4).dropna()
        return score.nlargest(top_n).index.tolist()
    return momentum_12m.dropna().nlargest(top_n).index.tolist()


def run_strategy(
    strategy_id: str,
    prices: pd.DataFrame,
    top_n: int,
    transaction_cost: float,
    as_of: date,
) -> tuple[pd.Series, list[str]]:
    daily_returns = prices.pct_change(fill_method=None)
    month_close = completed_monthly_prices(prices, as_of)
    month_returns = month_close.pct_change(fill_method=None)
    portfolio_returns = {}
    previous_holdings: set[str] = set()
    latest_holdings: list[str] = []

    for position in range(12, len(month_close) - 1):
        signal_date = month_close.index[position]
        next_date = month_close.index[position + 1]
        holdings = select_holdings(strategy_id, signal_date, month_close, daily_returns, top_n)
        valid = [ticker for ticker in holdings if pd.notna(month_returns.at[next_date, ticker])]
        gross_return = float(month_returns.loc[next_date, valid].mean()) if valid else 0.0

        current = set(valid)
        denominator = max(len(previous_holdings), len(current), 1)
        turnover = len(previous_holdings.symmetric_difference(current)) / denominator
        portfolio_returns[next_date] = gross_return - transaction_cost * turnover
        previous_holdings = current
        latest_holdings = valid

    return pd.Series(portfolio_returns, dtype=float), latest_holdings


def curve_points(returns: pd.Series) -> list[dict]:
    curve = (1 + returns.dropna()).cumprod()
    return [
        {"date": index.strftime("%Y-%m-%d"), "value": round(float(value), 4)}
        for index, value in curve.items()
    ]


def main(years: int, top_n: int, transaction_cost_bps: float):
    end_date = date.today()
    start_date = end_date - timedelta(days=365 * years + 400)
    universe = load_universe()
    prices = collect_prices(universe, start_date.isoformat(), end_date.isoformat())

    benchmark_frame = fdr.DataReader("KS11", start_date.isoformat(), end_date.isoformat())
    benchmark_monthly = benchmark_frame["Close"].resample("ME").last().pct_change(fill_method=None)
    transaction_cost = transaction_cost_bps / 10_000

    results = []
    for template in STRATEGIES:
        holdings_size = len(prices.columns) if template["id"] == "equal_weight" else top_n
        returns, holdings = run_strategy(
            template["id"], prices, top_n, transaction_cost, end_date
        )
        if returns.empty:
            continue
        benchmark = benchmark_monthly.reindex(returns.index).fillna(0)
        metrics = calculate_metrics(returns)
        benchmark_metrics = calculate_metrics(benchmark)
        results.append({
            **template,
            "conditions": {
                "universe_size": len(prices.columns),
                "portfolio_size": holdings_size,
                "rebalancing": "monthly",
                "transaction_cost_bps": transaction_cost_bps,
            },
            "metrics": metrics,
            "benchmark_metrics": benchmark_metrics,
            "excess_cagr": round(metrics["cagr"] - benchmark_metrics["cagr"], 2),
            "equity_curve": curve_points(returns),
            "benchmark_curve": curve_points(benchmark),
            "current_holdings": [
                {"ticker": ticker, "name": universe.get(ticker, ticker)}
                for ticker in holdings
            ],
        })

    payload = {
        "generated_at": pd.Timestamp.now().isoformat(),
        "data_source": "FinanceDataReader (Naver/KRX price data)",
        "methodology": (
            "Monthly rebalanced backtests on a broadened KRX universe. "
            "Transaction cost is applied. Survivorship bias still exists because the universe "
            "is built from a current snapshot rather than a historical constituent list."
        ),
        "limitations": [
            f"Universe expanded to {len(prices.columns)} names when fallback data is used.",
            "No dividend reinvestment, taxes, or slippage.",
            "Fundamental snapshot is still unavailable in this repo, so value screens remain limited.",
            "Past returns do not guarantee future returns.",
        ],
        "period": {
            "start": start_date.isoformat(),
            "end": last_completed_month_end(end_date).date().isoformat(),
        },
        "source_data_as_of": end_date.isoformat(),
        "universe": [
            {"ticker": ticker, "name": universe.get(ticker, ticker)}
            for ticker in prices.columns
        ],
        "strategies": results,
    }
    payload["validation"] = validate_backtest_payload(payload, as_of=end_date)

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    write_json_utf8(OUT_PATH, payload)
    logger.info("saved %s strategies to %s", len(results), OUT_PATH)
    logger.info("universe size: %s", len(prices.columns))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--years", type=int, default=3)
    parser.add_argument("--top", type=int, default=15, help="top holdings per strategy")
    parser.add_argument("--cost-bps", type=float, default=15.0)
    args = parser.parse_args()
    main(args.years, args.top, args.cost_bps)
