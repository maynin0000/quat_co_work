"""
shared/utils/normalizer.py
데이터 정규화 유틸리티 - 수집 직후 호출
"""

from shared.schemas.financial import FinancialRawData
from shared.constants.sectors import normalize_sector
from datetime import datetime


def normalize_dart_response(raw: dict, ticker: str, name: str) -> FinancialRawData:
    """DART API 응답 → FinancialRawData"""
    return FinancialRawData(
        ticker         = ticker,
        name           = name,
        sector         = normalize_sector(raw.get("induty_code", "")),
        pbr            = raw.get("pbr"),
        per            = raw.get("per"),
        roe            = raw.get("roe"),
        debt_ratio     = raw.get("de_ratio"),
        op_margin      = raw.get("bsns_incm_rate"),
        revenue_growth = raw.get("revenue_growth"),
        dividend_yield = raw.get("dvd_yield"),
        market_cap     = raw.get("mktcap"),
        data_date      = datetime.now(),
    )


def normalize_krx_response(raw: dict, ticker: str) -> dict:
    """KRX 응답 → 재무데이터 보완용 dict"""
    return {
        "price"      : raw.get("TDD_CLSPRC"),
        "market_cap" : raw.get("MKTCAP"),
        "market"     : raw.get("MKT_TP_NM"),  # KOSPI | KOSDAQ
    }


def merge_financial_data(
    dart_data : FinancialRawData,
    krx_patch : dict
) -> FinancialRawData:
    """DART + KRX 데이터 병합 후 충족도 계산"""
    merged = dart_data.copy(update={
        k: v for k, v in krx_patch.items() if v is not None
    })
    merged.data_completeness = merged.compute_completeness()
    return merged
