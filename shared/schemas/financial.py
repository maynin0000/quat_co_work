"""
shared/schemas/financial.py
Django, FastAPI, data_pipeline 모두 이 스키마를 import해서 사용
절대 각자 따로 정의하지 말것 → 파싱 불일치 원천 차단
"""

from pydantic import BaseModel, Field, validator
from typing import Optional, Literal
from datetime import datetime
import re


class FinancialRawData(BaseModel):
    """
    수집 직후 원본 데이터 정규화 스키마
    DART / KRX / FinanceDataReader 어디서 오든 이 형태로 통일
    """
    ticker          : str
    name            : str                   = ""
    sector          : Optional[str]         = None
    market          : Optional[str]         = None   # KOSPI | KOSDAQ

    # 가치 팩터
    pbr             : Optional[float]       = None
    per             : Optional[float]       = None
    psr             : Optional[float]       = None
    ev_ebitda       : Optional[float]       = None
    fcf_yield       : Optional[float]       = None

    # 퀄리티 팩터
    roe             : Optional[float]       = None
    roa             : Optional[float]       = None
    debt_ratio      : Optional[float]       = None
    current_ratio   : Optional[float]       = None
    op_margin       : Optional[float]       = None
    operating_cash_flow: Optional[float]    = None
    free_cash_flow  : Optional[float]       = None

    # 성장 팩터
    revenue_growth  : Optional[float]       = None
    profit_growth   : Optional[float]       = None
    op_growth       : Optional[float]       = None

    # 모멘텀 팩터
    momentum_1m     : Optional[float]       = None
    momentum_3m     : Optional[float]       = None
    momentum_6m     : Optional[float]       = None
    momentum_1y     : Optional[float]       = None
    volatility      : Optional[float]       = None

    # 배당 팩터
    dividend_yield  : Optional[float]       = None
    dividend_growth : Optional[float]       = None

    # 규모
    market_cap      : Optional[float]       = None   # 시가총액 (억원)
    market_cap_tier : Optional[Literal["large", "mid", "small"]] = None

    # 메타
    price           : Optional[float]       = None
    data_date       : Optional[datetime]    = None
    data_completeness: float                = 0.0

    @validator("*", pre=True)
    def clean_missing(cls, v):
        if v in ["-", "N/A", "n/a", "", "null", "NULL", "없음", "해당없음"]:
            return None
        return v

    @validator(
        "pbr", "per", "psr", "ev_ebitda", "fcf_yield",
        "roe", "roa", "debt_ratio", "current_ratio", "op_margin",
        "operating_cash_flow", "free_cash_flow",
        "revenue_growth", "profit_growth", "op_growth",
        "momentum_1m", "momentum_3m", "momentum_6m", "momentum_1y",
        "volatility", "dividend_yield", "dividend_growth",
        pre=True
    )
    def clean_numeric_string(cls, v):
        if v is None:
            return None
        if isinstance(v, (int, float)):
            return float(v)
        if isinstance(v, str):
            cleaned = re.sub(r"[,\s%원억만달러]", "", v)
            try:
                return float(cleaned)
            except ValueError:
                return None
        return None

    @validator("pbr", "per")
    def reject_negative_ratio(cls, v):
        if v is not None and v < 0:
            return None
        return v

    @validator("market_cap_tier", always=True)
    def auto_set_tier(cls, v, values):
        if v:
            return v
        cap = values.get("market_cap")
        if cap is None:
            return None
        if cap >= 10_000:
            return "large"
        elif cap >= 1_000:
            return "mid"
        else:
            return "small"

    def compute_completeness(self) -> float:
        key_fields = [
            "pbr", "per", "roe", "debt_ratio", "op_margin",
            "revenue_growth", "momentum_1y", "dividend_yield", "market_cap",
            "fcf_yield", "operating_cash_flow"
        ]
        filled = sum(1 for f in key_fields if getattr(self, f) is not None)
        return round(filled / len(key_fields) * 100, 1)

    def to_llm_dict(self) -> dict:
        data = self.dict(exclude={"data_date"})
        return {
            k: v if v is not None else "데이터없음"
            for k, v in data.items()
        }
