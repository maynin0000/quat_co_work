from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class EtfRawData(BaseModel):
    ticker: str
    name: str
    category: Optional[str] = None
    price: Optional[float] = None
    nav: Optional[float] = None
    nav_deviation: Optional[float] = None
    volume: Optional[float] = None
    trading_value: Optional[float] = None
    market_cap: Optional[float] = None
    return_1m: Optional[float] = None
    return_3m: Optional[float] = None
    return_6m: Optional[float] = None
    return_1y: Optional[float] = None
    volatility_1y: Optional[float] = None
    max_drawdown_1y: Optional[float] = None
    sharpe_1y: Optional[float] = None
    tracking_error: Optional[float] = None
    expense_ratio: Optional[float] = None
    holding_count: Optional[int] = None
    top10_weight: Optional[float] = None
    leveraged: bool = False
    inverse: bool = False
    data_date: Optional[datetime] = None
    data_completeness: float = 0.0

    def compute_completeness(self) -> float:
        fields = [
            "nav_deviation", "trading_value", "market_cap",
            "return_1m", "return_3m", "return_6m", "return_1y",
            "volatility_1y", "max_drawdown_1y", "sharpe_1y",
            "tracking_error", "expense_ratio", "holding_count", "top10_weight",
        ]
        filled = sum(getattr(self, field) is not None for field in fields)
        return round(filled / len(fields) * 100, 1)
