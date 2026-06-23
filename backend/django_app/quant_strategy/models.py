from django.db import models
from django.conf import settings


class Strategy(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="strategies"
    )
    name        = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    conditions  = models.JSONField(default=list)   # 전략 조건 리스트
    risk_level  = models.CharField(
        max_length=10,
        choices=[("low","안정형"),("medium","중립형"),("high","공격형")],
        default="medium"
    )
    sectors      = models.JSONField(default=list)
    rebalancing  = models.CharField(max_length=20, blank=True)
    is_active    = models.BooleanField(default=True)
    created_at   = models.DateTimeField(auto_now_add=True)
    updated_at   = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.email} - {self.name}"


class StockAnalysis(models.Model):
    """LLM 분석 결과 캐시"""
    ticker            = models.CharField(max_length=20, unique=True)
    name              = models.CharField(max_length=100)
    sector            = models.CharField(max_length=50, blank=True)
    analysis_result   = models.JSONField(default=dict)
    data_completeness = models.FloatField(default=0.0)
    analyzed_at       = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.ticker} - {self.name}"