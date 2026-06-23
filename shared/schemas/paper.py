"""
shared/schemas/paper.py
논문 수집 및 전략 추출 스키마
"""

from pydantic import BaseModel, Field, validator
from typing import Optional, Literal


class PaperFactorCondition(BaseModel):
    factor   : str
    operator : Literal["<", ">", "<=", ">=", "==", "top%", "bottom%"]
    value    : float
    unit     : Literal["ratio", "percent", "won", "rank"]


class PaperPerformance(BaseModel):
    return_type  : Literal["annual", "cumulative", "excess"]
    return_value : float
    benchmark    : Optional[str] = None
    sharpe       : Optional[float] = None
    max_drawdown : Optional[float] = None

    @validator("return_value")
    def reasonable_return(cls, v):
        if abs(v) > 200:
            raise ValueError(f"비상식적 수익률: {v}")
        return v


class PaperValidCondition(BaseModel):
    period  : Optional[str]  = None
    market  : Optional[str]  = None
    sectors : list[str]      = ["전체"]
    exclude : list[str]      = []


class ExtractedStrategy(BaseModel):
    """논문에서 추출된 투자 전략 단위"""
    # ── 필수: 초록에서도 항상 뽑을 수 있는 정성 정보 ──
    name             : str
    strategy_fit     : list[str]        = []   
    confidence       : Literal["high", "medium", "low"]

    # ── 선택: 본문/구체 수치가 있을 때만 채움 ──
    conditions       : list[PaperFactorCondition] = []
    performance      : Optional[PaperPerformance] = None
    valid_condition  : PaperValidCondition        = Field(default_factory=PaperValidCondition)

    # ── 부가 정보 ──
    key_findings     : list[str]        = []   
    risk_notes       : list[str]        = []
    rebalancing      : Optional[str]    = None
    source_sentences : list[str]        = []   

    # ── 데이터 품질 플래그 ──
    has_conditions   : bool             = False  
    source_type      : Literal["full_text", "abstract_only"] = "abstract_only"

    # ── 논문 메타 ──
    paper_id         : Optional[str]    = None
    paper_title      : Optional[str]    = None
    paper_year       : Optional[int]    = None

    # 🚨 [추가] PaperProcessor 런타임 에러 방지용 필수 속성
    data_completeness: float            = 0.0

    @validator("has_conditions", always=True)
    def set_has_conditions(cls, v, values):
        conds = values.get("conditions") or []
        return len(conds) > 0

    # 🚨 [추가] 데이터 퀄리티 점수 계산기
    def compute_completeness(self) -> float:
        score = 0.0
        if self.strategy_fit and len(self.strategy_fit) > 0:
            score += 40.0
        if self.key_findings and len(self.key_findings) > 0:
            score += 40.0
        if self.conditions and len(self.conditions) > 0:
            score += 20.0
            
        self.data_completeness = score
        return score


class PaperMeta(BaseModel):
    paper_id : str
    title    : str
    year     : Optional[int]  = None
    authors  : list[str]      = []
    market   : str            = "한국"
    source   : str            = ""   
    url      : Optional[str]  = None