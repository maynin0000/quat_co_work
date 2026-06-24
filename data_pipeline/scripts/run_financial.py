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

# 루트 경로 보장
sys.path.insert(0, os.getcwd())

from pykrx import stock
from data_pipeline.collectors.krx import KrxCollector
from shared.schemas.financial import FinancialRawData
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


async def build_one(collector: KrxCollector, date_str: str, ticker: str, name: str):
    """단일 종목 → FinancialRawData (시세+펀더멘털 병합)."""
    base = FinancialRawData(ticker=ticker, name=name, data_date=datetime.now())

    price_raw = await collector.fetch_ticker_data(date_str, ticker)
    if price_raw:
        base = merge_financial_data(base, normalize_krx_response(price_raw, ticker))

    fund_raw = await collector.fetch_fundamental_data(date_str, ticker)
    if fund_raw:
        base = merge_financial_data(base, normalize_krx_fundamental(fund_raw, ticker))

    base.data_completeness = base.compute_completeness()
    return base


async def run(top_n: int, date_str: str):
    logger.info(f"[Financial] 수집 시작 — 기준일 {date_str}, 상위 {top_n}종목")
    collector = KrxCollector()

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
    ap.add_argument("--top", type=int, default=50, help="시총 상위 N종목")
    ap.add_argument("--date", type=str, default=None, help="기준일 YYYYMMDD (생략시 최근 영업일)")
    args = ap.parse_args()

    date_str = args.date or _latest_business_day()
    asyncio.run(run(args.top, date_str))
