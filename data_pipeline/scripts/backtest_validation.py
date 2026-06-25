"""백테스트 산출물의 인코딩과 데이터 정합성을 검증한다."""

from __future__ import annotations

import json
import math
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd


MOJIBAKE_MARKERS = ("\ufffd", "Ã", "Â", "â€", "ï¿½")
EMBEDDED_QUESTION_MARK = re.compile(r"[0-9A-Za-z가-힣]\?[0-9A-Za-z가-힣]")


def last_completed_month_end(as_of: date | datetime | pd.Timestamp) -> pd.Timestamp:
    """기준일 직전에 확정된 마지막 월말을 반환한다."""
    timestamp = pd.Timestamp(as_of).normalize()
    return timestamp.to_period("M").start_time - pd.Timedelta(days=1)


def completed_monthly_prices(prices: pd.DataFrame, as_of: date | datetime) -> pd.DataFrame:
    """진행 중인 월을 제외한 확정 월말 가격만 반환한다."""
    monthly = prices.resample("ME").last().dropna(how="all")
    cutoff = last_completed_month_end(as_of)
    return monthly.loc[monthly.index <= cutoff]


def _walk_strings(value: Any, path: str = "$"):
    if isinstance(value, str):
        yield path, value
    elif isinstance(value, dict):
        for key, child in value.items():
            yield from _walk_strings(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _walk_strings(child, f"{path}[{index}]")


def validate_text_encoding(payload: dict[str, Any]) -> None:
    """대체 문자와 대표적인 한글 mojibake 패턴을 저장 전에 차단한다."""
    errors = []
    for path, text in _walk_strings(payload):
        if any(marker in text for marker in MOJIBAKE_MARKERS):
            errors.append(f"{path}: mojibake marker")
        if EMBEDDED_QUESTION_MARK.search(text):
            errors.append(f"{path}: embedded question mark")
    if errors:
        raise ValueError("Encoding validation failed: " + "; ".join(errors[:10]))


def _returns_from_curve(points: list[dict[str, Any]]) -> pd.Series:
    values = pd.Series([float(point["value"]) for point in points], dtype=float)
    if values.empty:
        return values
    return pd.concat([
        pd.Series([values.iloc[0] - 1], dtype=float),
        values.pct_change(fill_method=None).iloc[1:].reset_index(drop=True),
    ], ignore_index=True)


def _metrics_from_curve(points: list[dict[str, Any]]) -> dict[str, float]:
    returns = _returns_from_curve(points)
    curve = pd.Series([float(point["value"]) for point in points], dtype=float)
    years = max(len(returns) / 12, 1 / 12)
    drawdown = curve / curve.cummax() - 1
    std = returns.std(ddof=0)
    return {
        "cumulative_return": (curve.iloc[-1] - 1) * 100,
        "cagr": (curve.iloc[-1] ** (1 / years) - 1) * 100,
        "mdd": drawdown.min() * 100,
        "sharpe": ((returns.mean() - 0.02 / 12) / std * math.sqrt(12)) if std > 0 else 0,
        "volatility": std * math.sqrt(12) * 100,
        "max_monthly_return": returns.max() * 100,
        "min_monthly_return": returns.min() * 100,
    }


def validate_backtest_payload(
    payload: dict[str, Any],
    *,
    as_of: date | datetime,
) -> dict[str, Any]:
    """날짜 누수, 곡선 정합성, 지표 이상 여부를 검증하고 보고서를 반환한다."""
    validate_text_encoding(payload)
    strategies = payload.get("strategies") or []
    if not strategies:
        raise ValueError("Backtest validation failed: no strategies")

    strategy_ids = [strategy.get("id") for strategy in strategies]
    if len(strategy_ids) != len(set(strategy_ids)):
        raise ValueError("Backtest validation failed: duplicate strategy id")

    cutoff = last_completed_month_end(as_of)
    warnings: list[str] = []
    metric_tolerance = {
        "cumulative_return": 0.10,
        "cagr": 0.15,
        "mdd": 0.10,
        "sharpe": 0.03,
        "volatility": 0.10,
    }

    for strategy in strategies:
        strategy_id = strategy["id"]
        curve = strategy.get("equity_curve") or []
        benchmark_curve = strategy.get("benchmark_curve") or []
        if not curve or len(curve) != len(benchmark_curve):
            raise ValueError(f"{strategy_id}: curve is empty or benchmark length differs")

        dates = [pd.Timestamp(point["date"]) for point in curve]
        benchmark_dates = [pd.Timestamp(point["date"]) for point in benchmark_curve]
        if dates != sorted(set(dates)):
            raise ValueError(f"{strategy_id}: curve dates are duplicated or unsorted")
        if dates != benchmark_dates:
            raise ValueError(f"{strategy_id}: strategy and benchmark dates differ")
        if dates[-1] > cutoff:
            raise ValueError(
                f"{strategy_id}: incomplete/future month included "
                f"({dates[-1].date()} > {cutoff.date()})"
            )

        values = [float(point["value"]) for point in curve]
        if any(not math.isfinite(value) or value <= 0 for value in values):
            raise ValueError(f"{strategy_id}: curve contains non-positive or non-finite value")

        recalculated = _metrics_from_curve(curve)
        benchmark_recalculated = _metrics_from_curve(benchmark_curve)
        reported_groups = [
            ("strategy", strategy.get("metrics") or {}, recalculated),
            ("benchmark", strategy.get("benchmark_metrics") or {}, benchmark_recalculated),
        ]
        for group_name, reported, calculated in reported_groups:
            for metric, tolerance in metric_tolerance.items():
                if metric not in reported:
                    raise ValueError(f"{strategy_id}: missing {group_name} metric {metric}")
                if abs(float(reported[metric]) - calculated[metric]) > tolerance:
                    raise ValueError(
                        f"{strategy_id}: {group_name} {metric} mismatch "
                        f"({reported[metric]} vs {calculated[metric]:.2f})"
                    )

        if max(abs(recalculated["max_monthly_return"]), abs(recalculated["min_monthly_return"])) > 80:
            raise ValueError(f"{strategy_id}: monthly return exceeds 80%; inspect source prices")
        if float(reported["cagr"]) > 40:
            warnings.append(f"{strategy_id}: CAGR {reported['cagr']}% requires presentation review")

    return {
        "status": "passed",
        "validated_at": pd.Timestamp.now().isoformat(),
        "as_of": pd.Timestamp(as_of).date().isoformat(),
        "last_completed_month": cutoff.date().isoformat(),
        "strategy_count": len(strategies),
        "checks": [
            "utf8_text",
            "unique_strategy_ids",
            "completed_months_only",
            "curve_alignment",
            "strategy_and_benchmark_metric_recalculation",
            "monthly_return_outlier",
        ],
        "warnings": warnings,
    }


def write_json_utf8(path: Path, payload: dict[str, Any]) -> None:
    """UTF-8(BOM 없음) JSON으로 저장하고 다시 읽어 동일성을 검증한다."""
    validate_text_encoding(payload)
    encoded = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    if encoded.startswith(b"\xef\xbb\xbf"):
        raise ValueError("UTF-8 BOM is not allowed")
    path.write_bytes(encoded)
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if loaded != payload:
        raise ValueError(f"UTF-8 round-trip validation failed: {path}")
