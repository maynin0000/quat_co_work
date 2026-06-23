"""
shared/schemas/recommendation.py
추천 결과 스키마 - FastAPI 생성, Django 저장, 프론트 소비
"""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class MatchResult(BaseModel):
    """논문 조건 vs 재무데이터 교차검증 결과"""
    factor          : str
    paper_condition : str
    stock_value     : float
    is_match        : bool
    gap             : float


class Evidence(BaseModel):
    claim  : str
    source : str   # "Kim et al. 2021 + 현재 PBR 0.8"


class WhyThisStock(BaseModel):
    paper_basis    : str
    current_status : str
    match_summary  : str


class RecommendationResult(BaseModel):
    """최종 추천 결과 - 프론트로 내려가는 형태"""
    ticker               : str
    name                 : str
    recommendation_score : float = Field(..., ge=0, le=100)
    confidence_score     : float = Field(..., ge=0, le=100)
    matched_strategies   : list[str]
    why_this_stock       : WhyThisStock
    match_results        : list[MatchResult]
    risk_factors         : list[str]
    simple_summary       : str
    evidence             : list[Evidence]
    data_freshness_days  : Optional[int]   = None  # 데이터 신선도
    generated_at         : datetime        = Field(default_factory=datetime.now)


class RecommendationRequest(BaseModel):
    """사용자 추천 요청"""
    user_input   : str
    risk_level   : Optional[str] = None   # low | medium | high
    sectors      : list[str]     = ["전체"]
    top_n        : int           = 5
