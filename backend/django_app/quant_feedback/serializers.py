from rest_framework import serializers
from quant_feedback.models import RecommendationFeedback


class FeedbackSerializer(serializers.ModelSerializer):
    class Meta:
        model  = RecommendationFeedback
        fields = ["id", "ticker", "strategy_name", "is_positive", "created_at"]
        read_only_fields = ["id", "created_at"]