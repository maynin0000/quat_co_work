import json
import os
from pathlib import Path
from typing import Any


def _default_path() -> Path:
    configured = os.getenv("STRATEGY_BACKTEST_PATH")
    if configured:
        return Path(configured)
    cwd_path = Path.cwd() / "data_pipeline" / "data" / "strategy_backtests.json"
    if cwd_path.exists():
        return cwd_path
    project_root = Path(__file__).resolve().parents[3]
    return project_root / "data_pipeline" / "data" / "strategy_backtests.json"


class StrategyBacktestRepo:
    def __init__(self, path: Path | None = None):
        self.path = path or _default_path()

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {
                "generated_at": None,
                "period": {},
                "methodology": "백테스트 데이터가 아직 생성되지 않았습니다.",
                "strategies": [],
            }
        return json.loads(self.path.read_text(encoding="utf-8"))

    def load_etf(self) -> dict[str, Any]:
        path = self.path.with_name("etf_strategy_backtests.json")
        if not path.exists():
            return {"asset_type": "etf", "strategies": [], "limitations": ["ETF 전략 데이터가 없습니다."]}
        return json.loads(path.read_text(encoding="utf-8"))

    def recommend(self, query: str, limit: int = 3, asset_type: str = "stock") -> dict[str, Any]:
        payload = self.load_etf() if asset_type == "etf" else self.load()
        strategies = payload.get("strategies") or []
        query_lower = query.lower()
        synonyms = {
            "value": ["가치", "저평가", "pbr", "per"],
            "momentum": ["모멘텀", "추세", "상승", "수익"],
            "low_vol": ["안정", "방어", "저변동", "변동성", "위험", "리스크"],
            "smart_beta": ["복합", "스마트", "팩터"],
            "reversal": ["반전", "낙폭", "역발상", "반등"],
            "growth": ["성장", "공격", "나스닥", "미국주식"],
            "allocation": ["분산", "자산배분", "올웨더", "채권", "금"],
        }

        wanted = {
            group for group, words in synonyms.items()
            if any(word in query_lower for word in words)
        }

        def score(strategy: dict) -> tuple[float, float]:
            text = " ".join([
                strategy.get("name", ""),
                strategy.get("description", ""),
                *strategy.get("tags", []),
            ]).lower()
            query_terms = [term for term in query_lower.split() if len(term) >= 2]
            lexical = sum(5 for term in query_terms if term in text)
            if "momentum" in wanted and any(word in text for word in ["모멘텀", "추세"]):
                lexical += 3
            if "low_vol" in wanted and any(word in text for word in ["저변동성", "방어"]):
                lexical += 3
            if "smart_beta" in wanted and any(word in text for word in ["복합", "스마트베타"]):
                lexical += 2
            if "reversal" in wanted and any(word in text for word in ["반전", "역발상", "반등"]):
                lexical += 3
            if "growth" in wanted and any(word in text for word in ["성장", "공격형", "나스닥", "미국주식"]):
                lexical += 3
            if "allocation" in wanted and any(word in text for word in ["분산", "자산배분", "올웨더", "채권", "금"]):
                lexical += 3
            metrics = strategy.get("metrics") or {}
            risk_adjusted = float(metrics.get("sharpe") or 0)
            return lexical, risk_adjusted

        ranked = sorted(strategies, key=score, reverse=True)
        warning = None
        if "value" in wanted:
            warning = (
                "가치·저평가 전략은 시점별 PBR·PER·ROE 데이터가 없어 "
                "현재 가격 기반 백테스트 목록에는 포함되지 않습니다."
            )
        return {**payload, "coverage_warning": warning, "strategies": ranked[:limit]}
