"""
shared/schemas/strategy.py
LLM 분석 출력 스키마 - 두 서버 공통 사용
"""

from pydantic import BaseModel, Field, validator
from typing import Optional, Literal


class FactorScores(BaseModel):
    value    : float = Field(..., ge=0, le=100)
    growth   : float = Field(..., ge=0, le=100)
    quality  : float = Field(..., ge=0, le=100)
    momentum : float = Field(..., ge=0, le=100)
    dividend : float = Field(..., ge=0, le=100)


class ChainOfThought(BaseModel):
    value_reasoning    : str
    growth_reasoning   : str
    quality_reasoning  : str
    momentum_reasoning : str
    overall_reasoning  : str


class LLMAnalysisOutput(BaseModel):
    """
    LLM이 생성하는 종목 분석 결과 스키마
    Top100 고급 모델 / 나머지 Few-shot 모델 출력 동일 형식
    """
    ticker            : str
    name              : str
    sector            : str
    market_cap_tier   : Literal["large", "mid", "small"]
    factor_scores     : FactorScores
    overall_score     : float = Field(..., ge=0, le=100)
    strategy_fit      : list[str]
    risk_level        : Literal["low", "medium", "high"]
    chain_of_thought  : ChainOfThought
    summary           : str
    data_completeness : float = Field(..., ge=0, le=100)
    estimated_fields  : list[str] = []
    fewshot_examples_used: list[str] = []   # 추적용


class StrategyCondition(BaseModel):
    """사용자가 설정한 전략 조건"""
    factor   : str
    operator : Literal["<", ">", "<=", ">=", "==", "top%", "bottom%"]
    value    : float
    unit     : Literal["ratio", "percent", "won", "rank"]


class UserStrategy(BaseModel):
    """사용자가 저장하는 전략"""
    name        : str
    description : str                   = ""
    conditions  : list[StrategyCondition]
    risk_level  : Literal["low", "medium", "high"]
    sectors     : list[str]             = ["전체"]
    rebalancing : Optional[str]         = None
