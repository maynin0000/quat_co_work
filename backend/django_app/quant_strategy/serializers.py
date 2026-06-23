from rest_framework import serializers
from quant_strategy.models import Strategy, StockAnalysis


class StrategySerializer(serializers.ModelSerializer):
    class Meta:
        model  = Strategy
        fields = [
            "id", "name", "description", "conditions",
            "risk_level", "sectors", "rebalancing",
            "is_active", "created_at", "updated_at"
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class StockAnalysisSerializer(serializers.ModelSerializer):
    class Meta:
        model  = StockAnalysis
        fields = ["ticker", "name", "sector", "analysis_result", "data_completeness", "analyzed_at"]