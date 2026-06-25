"""
data_pipeline/scripts/run_financial.py

실제 KRX 재무 데이터 수집 → JSON 캐시 저장.
FastAPI의 JsonFinancialRepo가 이 파일을 읽어서 추천에 사용한다.

[흐름]
  pykrx 시총 상위 N종목 선정
    → KrxCollector.fetch_ticker_data       (종가/시총/시장)
    → KrxCollector.fetch_fundamental_data  (PBR/PER/배당)
    → normalizer 로 FinancialRawData 빌드 + 병합
    → data_pipeline/data/financial_snapshot.json 저장

[실행]  프로젝트 루트에서:
    python -m data_pipeline.scripts.run_financial --top 50 --date 20260623
"""

import os
import sys
import json
import asyncio
import argparse
import logging
from datetime import datetime, timedelta

import FinanceDataReader as fdr

# 루트 경로 보장
sys.path.insert(0, os.getcwd())

from pykrx import stock
from data_pipeline.collectors.krx import KrxCollector
from shared.schemas.financial import FinancialRawData
from shared.constants.stocks import STOCK_CATALOG
from shared.utils.normalizer import (
    normalize_krx_response,
    normalize_krx_fundamental,
    merge_financial_data,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

OUT_DIR = os.path.join("data_pipeline", "data")
OUT_PATH = os.path.join(OUT_DIR, "financial_snapshot.json")


def _latest_business_day() -> str:
    """가장 최근 영업일 추정 (주말이면 금요일로). YYYYMMDD."""
    d = datetime.now()
    # 장 마감 데이터 안정성을 위해 하루 전 기준
    d = d - timedelta(days=1)
    while d.weekday() >= 5:  # 5=토,6=일
        d -= timedelta(days=1)
    return d.strftime("%Y%m%d")


def pick_top_tickers(date_str: str, top_n: int) -> list[tuple[str, str]]:
    """시총 상위 top_n 종목의 (ticker, name) 리스트."""
    df = stock.get_market_cap(date_str)              # 전 종목 시총
    df = df.sort_values("시가총액", ascending=False)  # 시총 내림차순
    tickers = list(df.index[:top_n])
    result = []
    for t in tickers:
        try:
            name = stock.get_market_ticker_name(t)
        except Exception:
            name = t
        result.append((t, name))
    return result


def pick_catalog_tickers(limit: int | None = None) -> list[tuple[str, str]]:
    pairs = list(STOCK_CATALOG.items())
    return pairs[:limit] if limit else pairs


def historical_metrics(ticker: str, date_str: str) -> dict:
    end = datetime.strptime(date_str, "%Y%m%d")
    start = end - timedelta(days=500)
    frame = fdr.DataReader(ticker, start.date().isoformat(), end.date().isoformat())
    if frame.empty or "Close" not in frame:
        return {}
    close = frame["Close"].astype(float).dropna()
    returns = close.pct_change(fill_method=None).dropna()

    def momentum(days: int):
        if len(close) <= days:
            return None
        return round((close.iloc[-1] / close.iloc[-days - 1] - 1) * 100, 2)

    return {
        "price": round(float(close.iloc[-1]), 2),
        "momentum_1m": momentum(21),
        "momentum_3m": momentum(63),
        "momentum_6m": momentum(126),
        "momentum_1y": momentum(252),
        "volatility": (
            round(returns.tail(252).std(ddof=0) * (252 ** 0.5) * 100, 2)
            if len(returns) >= 20 else None
        ),
    }


async def build_one(collector: KrxCollector, date_str: str, ticker: str, name: str):
    """단일 종목 → FinancialRawData (시세+펀더멘털 병합)."""
    base = FinancialRawData(
        ticker=ticker,
        name=name,
        data_date=datetime.strptime(date_str, "%Y%m%d"),
    )

    price_raw = await collector.fetch_ticker_data(date_str, ticker)
    if price_raw:
        base = merge_financial_data(base, normalize_krx_response(price_raw, ticker))

    fund_raw = await collector.fetch_fundamental_data(date_str, ticker)
    if fund_raw:
        base = merge_financial_data(base, normalize_krx_fundamental(fund_raw, ticker))

    history = await asyncio.to_thread(historical_metrics, ticker, date_str)
    if history:
        base = merge_financial_data(base, history)

    base.data_completeness = base.compute_completeness()
    return base


async def run(top_n: int, date_str: str, use_catalog: bool = True):
    target_label = f"공통 카탈로그 {top_n}종목" if use_catalog else f"시총 상위 {top_n}종목"
    logger.info(f"[Financial] 수집 시작 — 기준일 {date_str}, {target_label}")
    collector = KrxCollector()

    if use_catalog:
        pairs = pick_catalog_tickers(top_n)
    else:
        pairs = await asyncio.to_thread(pick_top_tickers, date_str, top_n)
    logger.info(f"[Financial] 대상 종목 {len(pairs)}개 선정 완료")

    results: list[FinancialRawData] = []
    for i, (ticker, name) in enumerate(pairs, 1):
        try:
            row = await build_one(collector, date_str, ticker, name)
            results.append(row)
            if i % 10 == 0:
                logger.info(f"  … {i}/{len(pairs)} 진행")
        except Exception as e:
            logger.warning(f"  ⚠ {ticker}({name}) 수집 실패: {e}")

    os.makedirs(OUT_DIR, exist_ok=True)
    payload = {
        "date": date_str,
        "generated_at": datetime.now().isoformat(),
        "count": len(results),
        "universe": "shared.constants.stocks.STOCK_CATALOG" if use_catalog else "market_cap_top",
        "data_sources": ["FinanceDataReader price history", "pykrx fundamentals when available"],
        "limitations": [
            "KRX 인증 또는 응답 장애 시 PBR·PER·배당·시가총액은 비어 있을 수 있습니다.",
            "DART 기반 ROE·부채비율은 DART 기업코드 연결 전까지 제공되지 않습니다.",
        ],
        "stocks": [r.model_dump(mode="json") for r in results],
    }
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    logger.info(f"✅ [Financial] {len(results)}종목 저장 완료 → {OUT_PATH}")
    # 샘플 출력
    for r in results[:3]:
        logger.info(f"   {r.name}({r.ticker}) PBR={r.pbr} PER={r.per} 배당={r.dividend_yield} 시총={r.market_cap}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=48, help="수집할 종목 수")
    ap.add_argument("--date", type=str, default=None, help="기준일 YYYYMMDD (생략시 최근 영업일)")
    ap.add_argument("--market-cap-top", action="store_true", help="공통 카탈로그 대신 시총 상위 종목 수집")
    args = ap.parse_args()

    date_str = args.date or _latest_business_day()
    asyncio.run(run(args.top, date_str, use_catalog=not args.market_cap_top))
