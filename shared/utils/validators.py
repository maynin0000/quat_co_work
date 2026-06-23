"""
shared/utils/validators.py
LLM 출력 검증 + 재시도 로직
"""

import json
import re
from pydantic import ValidationError
from shared.schemas.strategy import LLMAnalysisOutput
from shared.schemas.paper import ExtractedStrategy
from shared.schemas.recommendation import RecommendationResult


def parse_llm_json(raw: str) -> dict:
    """
    LLM 출력 → dict 파싱
    마크다운 코드블록 자동 제거
    """
    # ```json ... ``` 제거
    cleaned = re.sub(r"```json|```", "", raw).strip()
    return json.loads(cleaned)


def validate_analysis_output(raw_json: str) -> LLMAnalysisOutput:
    """종목 분석 LLM 출력 검증"""
    try:
        data = parse_llm_json(raw_json)
        return LLMAnalysisOutput(**data)
    except json.JSONDecodeError as e:
        raise ValueError(f"JSON 파싱 실패: {e}")
    except ValidationError as e:
        raise ValueError(f"스키마 검증 실패: {e.errors()}")


def validate_paper_strategies(raw_json: str) -> list[ExtractedStrategy]:
    """논문 전략 추출 LLM 출력 검증"""
    data = parse_llm_json(raw_json)
    valid = []
    for s in data.get("strategies", []):
        try:
            valid.append(ExtractedStrategy(**s))
        except ValidationError as e:
            print(f"  ⚠ 전략 검증 실패 스킵: {e.errors()}")
    return valid
