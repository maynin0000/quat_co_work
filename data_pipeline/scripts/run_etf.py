"""국내 ETF 실데이터 스냅샷 생성."""

import argparse
import json
import logging
import math
from datetime import date, datetime, timedelta
from pathlib import Path

import FinanceDataReader as fdr
import numpy as np
import pandas as pd

from shared.schemas.etf import EtfRawData


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parents[2]
OUT_PATH = ROOT / "data_pipeline" / "data" / "etf_snapshot.json"

CATEGORY_NAMES = {
    1: "국내주식", 2: "국내채권", 3: "원자재", 4: "해외주식",
    5: "해외채권", 6: "통화", 7: "혼합자산", 8: "기타",
}
EXCLUDED_WORDS = [
    "레버리지", "인버스", "선물인버스", "곱버스", "2X", "2x",
    "ETN", "합성-인버스",
]


def pct_change(close: pd.Series, days: int):
    if len(close) <= days:
        return None
    return round((close.iloc[-1] / close.iloc[-days - 1] - 1) * 100, 2)


def historical_metrics(ticker: str, start: str, end: str) -> dict:
    frame = fdr.DataReader(ticker, start, end)
    if frame.empty or "Close" not in frame:
        return {}
    close = frame["Close"].astype(float).dropna()
    returns = close.pct_change(fill_method=None).dropna()
    recent = returns.tail(252)
    if close.empty or recent.empty:
        return {}
    curve = (1 + recent).cumprod()
    drawdown = curve / curve.cummax() - 1
    volatility = recent.std(ddof=0) * math.sqrt(252)
    sharpe = (
        (recent.mean() - 0.02 / 252) / recent.std(ddof=0) * math.sqrt(252)
        if recent.std(ddof=0) > 0 else 0
    )
    return {
        "return_1m": pct_change(close, 21),
        "return_3m": pct_change(close, 63),
        "return_6m": pct_change(close, 126),
        "return_1y": pct_change(close, 252),
        "volatility_1y": round(volatility * 100, 2),
        "max_drawdown_1y": round(drawdown.min() * 100, 2),
        "sharpe_1y": round(float(sharpe), 2),
    }


def main(limit: int):
    listing = fdr.StockListing("ETF/KR").copy()
    listing["Amount"] = pd.to_numeric(listing["Amount"], errors="coerce").fillna(0)
    listing["MarCap"] = pd.to_numeric(listing["MarCap"], errors="coerce").fillna(0)
    listing = listing[
        ~listing["Name"].astype(str).apply(
            lambda name: any(word.lower() in name.lower() for word in EXCLUDED_WORDS)
        )
    ].sort_values(["Amount", "MarCap"], ascending=False).head(limit)

    end = date.today()
    start = end - timedelta(days=430)
    rows = []
    for index, item in enumerate(listing.to_dict("records"), 1):
        ticker = str(item["Symbol"]).zfill(6)
        name = str(item["Name"])
        try:
            metrics = historical_metrics(ticker, start.isoformat(), end.isoformat())
            price = float(item["Price"]) if pd.notna(item.get("Price")) else None
            nav = float(item["NAV"]) if pd.notna(item.get("NAV")) else None
            deviation = (
                round((price / nav - 1) * 100, 4)
                if price is not None and nav not in (None, 0) else None
            )
            row = EtfRawData(
                ticker=ticker,
                name=name,
                category=CATEGORY_NAMES.get(item.get("Category"), str(item.get("Category"))),
                price=price,
                nav=nav,
                nav_deviation=deviation,
                volume=float(item["Volume"]) if pd.notna(item.get("Volume")) else None,
                trading_value=float(item["Amount"]) if pd.notna(item.get("Amount")) else None,
                market_cap=float(item["MarCap"]) if pd.notna(item.get("MarCap")) else None,
                leveraged="레버리지" in name or "2X" in name.upper(),
                inverse="인버스" in name,
                data_date=datetime.now(),
                **metrics,
            )
            row.data_completeness = row.compute_completeness()
            rows.append(row)
            logger.info("[%s/%s] %s 수집", index, len(listing), name)
        except Exception as exc:
            logger.warning("%s(%s) 수집 실패: %s", name, ticker, exc)

    payload = {
        "generated_at": datetime.now().isoformat(),
        "source": "FinanceDataReader ETF/KR + historical prices",
        "count": len(rows),
        "limitations": [
            "운용보수와 PDF 구성종목은 현재 데이터 소스에서 제공되지 않아 점수에서 제외됩니다.",
            "추적오차는 KRX 인증 데이터 연결 전까지 점수에서 제외됩니다.",
            "레버리지·인버스 ETF는 기본 추천 대상에서 제외됩니다.",
        ],
        "etfs": [row.model_dump(mode="json") for row in rows],
    }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("ETF %s개 저장: %s", len(rows), OUT_PATH)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()
    main(max(20, args.limit))
