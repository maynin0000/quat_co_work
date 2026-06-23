from rest_framework import serializers
from quant_portfolio.models import Portfolio, WatchList


class PortfolioSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Portfolio
        fields = ["id", "name", "created_at"]
        read_only_fields = ["id", "created_at"]


class WatchListSerializer(serializers.ModelSerializer):
    class Meta:
        model  = WatchList
        fields = ["id", "ticker", "name", "added_at"]
        read_only_fields = ["id", "added_at"]