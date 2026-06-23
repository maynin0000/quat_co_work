"""
shared/constants/factors.py
팩터명 표준화 - 논문/재무제표/LLM 간 팩터명 매핑 통일
"""

# 논문에서 나오는 팩터명 → 재무데이터 필드명 매핑
FACTOR_MAP: dict[str, str] = {
    # 가치
    "PBR"       : "pbr",
    "PER"       : "per",
    "PSR"       : "psr",
    "EV/EBITDA" : "ev_ebitda",
    "주가순자산비율": "pbr",
    "주가수익비율" : "per",

    # 퀄리티
    "ROE"       : "roe",
    "ROA"       : "roa",
    "부채비율"   : "debt_ratio",
    "유동비율"   : "current_ratio",
    "영업이익률" : "op_margin",

    # 성장
    "매출성장률"  : "revenue_growth",
    "순이익성장률" : "profit_growth",
    "영업이익성장률": "op_growth",

    # 모멘텀
    "모멘텀"    : "momentum_1y",
    "모멘텀_1M" : "momentum_1m",
    "모멘텀_3M" : "momentum_3m",
    "모멘텀_6M" : "momentum_6m",
    "모멘텀_1Y" : "momentum_1y",
    "변동성"    : "volatility",

    # 배당
    "배당수익률"  : "dividend_yield",
    "배당성장률"  : "dividend_growth",
}

# 신뢰도 필터 기준
CONFIDENCE_THRESHOLD = {
    "recommend" : 60.0,   # 이 이상만 추천
    "warn"      : 30.0,   # 이 이상은 낮은신뢰도 표시
    "exclude"   : 0.0,    # 이 미만은 완전 제외
}

# 데이터 신선도 기준 (일)
DATA_FRESHNESS = {
    "price"     : 1,    # 주가: 1일
    "financial" : 90,   # 재무제표: 분기(90일)
    "paper"     : 365,  # 논문 전략: 1년
}
