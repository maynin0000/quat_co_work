"""ETF 자산배분 전략 백테스트 생성."""

import json
import logging
import math
from datetime import date, datetime, timedelta
from pathlib import Path

import FinanceDataReader as fdr
import pandas as pd


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parents[2]
OUT_PATH = ROOT / "data_pipeline" / "data" / "etf_strategy_backtests.json"

ASSETS = {
    "069500": "KODEX 200",
    "360750": "TIGER 미국S&P500",
    "133690": "TIGER 미국나스닥100",
    "148070": "KOSEF 국고채10년",
    "132030": "KODEX 골드선물(H)",
}

TEMPLATES = [
    {
        "id": "etf_global_balanced",
        "name": "글로벌 주식·채권·금 분산",
        "description": "한국 20%, 미국 40%, 국채 25%, 금 15%로 분산하는 월별 리밸런싱 전략",
        "tags": ["ETF", "글로벌", "자산배분", "분산투자"],
        "risk_level": "medium",
        "weights": {"069500": .20, "360750": .25, "133690": .15, "148070": .25, "132030": .15},
    },
    {
        "id": "etf_60_40",
        "name": "미국주식 60·국채 40",
        "description": "미국 S&P500 ETF 60%와 국고채 ETF 40%를 월별 리밸런싱",
        "tags": ["ETF", "60/40", "미국주식", "채권"],
        "risk_level": "medium",
        "weights": {"360750": .60, "148070": .40},
    },
    {
        "id": "etf_risk_parity",
        "name": "변동성 역가중 자산배분",
        "description": "최근 6개월 변동성이 낮은 자산에 더 높은 비중을 부여하는 전략",
        "tags": ["ETF", "리스크패리티", "저변동성"],
        "risk_level": "low",
        "dynamic": "inverse_vol",
    },
    {
        "id": "etf_momentum_rotation",
        "name": "ETF 모멘텀 로테이션",
        "description": "최근 6개월 수익률 상위 2개 ETF를 보유하고 음수 자산은 제외",
        "tags": ["ETF", "모멘텀", "로테이션"],
        "risk_level": "high",
        "dynamic": "momentum",
    },
]


def metrics(returns):
    returns = returns.dropna()
    curve = (1 + returns).cumprod()
    years = max(len(returns) / 12, 1 / 12)
    dd = curve / curve.cummax() - 1
    vol = returns.std(ddof=0) * math.sqrt(12)
    sharpe = (
        (returns.mean() - .02 / 12) / returns.std(ddof=0) * math.sqrt(12)
        if returns.std(ddof=0) > 0 else 0
    )
    return {
        "cumulative_return": round((curve.iloc[-1] - 1) * 100, 2),
        "cagr": round((curve.iloc[-1] ** (1 / years) - 1) * 100, 2),
        "mdd": round(dd.min() * 100, 2),
        "sharpe": round(float(sharpe), 2),
        "volatility": round(vol * 100, 2),
    }


def curve_points(returns):
    curve = (1 + returns).cumprod()
    return [{"date": d.strftime("%Y-%m-%d"), "value": round(float(v), 4)} for d, v in curve.items()]


def run_template(template, monthly, transaction_cost=.0015):
    output = {}
    previous = {}
    last_weights = {}
    for i in range(6, len(monthly) - 1):
        signal_date, next_date = monthly.index[i], monthly.index[i + 1]
        history = monthly.iloc[:i + 1]
        if "weights" in template:
            weights = template["weights"]
        elif template["dynamic"] == "inverse_vol":
            vol = history.pct_change(fill_method=None).tail(6).std().replace(0, pd.NA).dropna()
            inv = 1 / vol
            weights = (inv / inv.sum()).to_dict()
        else:
            momentum = history.pct_change(6, fill_method=None).iloc[-1].dropna()
            selected = momentum[momentum > 0].nlargest(2).index.tolist()
            weights = {ticker: 1 / len(selected) for ticker in selected} if selected else {}

        next_returns = monthly.pct_change(fill_method=None).loc[next_date]
        gross = sum(weight * float(next_returns.get(ticker, 0) or 0) for ticker, weight in weights.items())
        turnover = sum(abs(weights.get(t, 0) - previous.get(t, 0)) for t in set(weights) | set(previous))
        output[next_date] = gross - turnover * transaction_cost
        previous = weights
        last_weights = weights
    return pd.Series(output, dtype=float), last_weights


def main():
    end = date.today()
    start = end - timedelta(days=365 * 4)
    prices = {}
    for ticker, name in ASSETS.items():
        frame = fdr.DataReader(ticker, start.isoformat(), end.isoformat())
        if not frame.empty:
            prices[ticker] = frame["Close"].astype(float)
            logger.info("%s %s일 수집", name, len(frame))
    frame = pd.DataFrame(prices).sort_index().ffill()
    monthly = frame.resample("ME").last().dropna(how="all")
    if monthly.index[-1].date() > frame.index[-1].date():
        monthly = monthly.iloc[:-1]
    benchmark = monthly["069500"].pct_change(fill_method=None)

    strategies = []
    for template in TEMPLATES:
        returns, weights = run_template(template, monthly)
        bench = benchmark.reindex(returns.index).fillna(0)
        result_metrics = metrics(returns)
        benchmark_metrics = metrics(bench)
        strategies.append({
            **template,
            "asset_type": "etf",
            "conditions": {"rebalancing": "monthly", "transaction_cost_bps": 15},
            "metrics": result_metrics,
            "benchmark_metrics": benchmark_metrics,
            "excess_cagr": round(result_metrics["cagr"] - benchmark_metrics["cagr"], 2),
            "equity_curve": curve_points(returns),
            "benchmark_curve": curve_points(bench),
            "current_holdings": [
                {"ticker": ticker, "name": ASSETS[ticker], "weight": round(weight * 100, 1)}
                for ticker, weight in weights.items()
            ],
        })

    payload = {
        "generated_at": datetime.now().isoformat(),
        "asset_type": "etf",
        "data_source": "FinanceDataReader ETF prices",
        "methodology": "ETF 월말 가격을 사용해 다음 달 수익률을 계산하고 거래비용 15bp를 반영했습니다.",
        "limitations": [
            "세금과 실제 매수 호가 슬리피지는 반영하지 않았습니다.",
            "ETF 운용보수는 가격에 간접 반영되지만 별도로 차감하지 않았습니다.",
            "과거 성과는 미래 수익을 보장하지 않습니다.",
        ],
        "period": {
            "start": strategies[0]["equity_curve"][0]["date"],
            "end": monthly.index[-1].strftime("%Y-%m-%d"),
        },
        "strategies": strategies,
    }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("ETF 전략 %s개 저장: %s", len(strategies), OUT_PATH)


if __name__ == "__main__":
    main()
