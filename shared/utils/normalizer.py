"""
shared/utils/normalizer.py
데이터 정규화 유틸리티 - 수집 직후 호출

[수집 흐름]
  collector(raw dict) → normalize_*_response → FinancialRawData(shared)
  여러 소스를 merge_financial_data 로 합친 뒤 compute_completeness() 호출

[데이터 소스 역할 분담]
  - pykrx get_market_fundamental : PBR / PER / DIV(배당수익률)   ← 비율 출처
  - pykrx get_market_cap         : 종가 / 시가총액 / 시장구분
  - DART fnlttSinglAcnt          : 자산/부채/자본/매출/이익 계정 → 부채비율·ROE 계산
"""

from shared.schemas.financial import FinancialRawData
from shared.constants.sectors import normalize_sector
from datetime import datetime


# ── KRX 시세/시총 ──
def normalize_krx_response(raw: dict, ticker: str) -> dict:
    """pykrx get_market_cap 응답 → 보완용 dict"""
    return {
        "price"      : raw.get("TDD_CLSPRC"),
        "market_cap" : (
            round(raw.get("MKTCAP") / 100_000_000, 2)
            if raw.get("MKTCAP") is not None else None
        ),
        "market"     : raw.get("MKT_TP_NM"),   # KOSPI | KOSDAQ
    }


# ── KRX 펀더멘털(비율) ──
def normalize_krx_fundamental(raw: dict, ticker: str) -> dict:
    """pykrx get_market_fundamental 응답 → 비율 보완용 dict"""
    return {
        "pbr"            : raw.get("PBR"),
        "per"            : raw.get("PER"),
        "dividend_yield" : raw.get("DIV"),   # 배당수익률(%)
    }


# ── DART 계정 → 파생지표 ──
def normalize_dart_response(raw: dict, ticker: str, name: str) -> FinancialRawData:
    """
    DART fnlttSinglAcnt 응답 → FinancialRawData
    DART는 PBR/PER을 직접 주지 않으므로 한글 계정명으로 ROE/부채비율을 계산.
    """
    debt_ratio = None
    roe        = None
    operating_cash_flow = _to_float(raw.get("영업활동현금흐름"))
    try:
        부채총계 = _to_float(raw.get("부채총계"))
        자본총계 = _to_float(raw.get("자본총계"))
        당기순이익 = _to_float(raw.get("당기순이익"))
        if 자본총계 and 자본총계 != 0:
            if 부채총계 is not None:
                debt_ratio = round(부채총계 / 자본총계 * 100, 2)
            if 당기순이익 is not None:
                roe = round(당기순이익 / 자본총계 * 100, 2)
    except Exception:
        pass

    return FinancialRawData(
        ticker     = ticker,
        name       = name,
        sector     = normalize_sector(raw.get("induty_code", "")),
        roe        = roe,
        debt_ratio = debt_ratio,
        operating_cash_flow = operating_cash_flow,
        data_date  = datetime.now(),
    )


# ── 병합 ──
def merge_financial_data(base: FinancialRawData, patch: dict) -> FinancialRawData:
    """
    base에 patch(dict) 덮어쓴 뒤 충족도 재계산.
    여러 소스(KRX 시세/펀더멘털/DART)를 순차 병합. patch의 None은 무시.
    """
    update = {k: v for k, v in patch.items() if v is not None}
    merged = base.model_copy(update=update)      # pydantic v2
    merged.data_completeness = merged.compute_completeness()
    return merged


def _to_float(v):
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        s = v.replace(",", "").replace(" ", "").strip()
        try:
            return float(s)
        except ValueError:
            return None
    return None
