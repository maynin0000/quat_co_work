from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from quant_strategy.models import Strategy
from quant_strategy.serializers import StrategySerializer


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def strategy_list(request):
    if request.method == "GET":
        strategies = Strategy.objects.filter(user=request.user, is_active=True)
        return Response(StrategySerializer(strategies, many=True).data)

    serializer = StrategySerializer(data=request.data)
    if serializer.is_valid():
        serializer.save(user=request.user)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(["GET", "PATCH", "DELETE"])
@permission_classes([IsAuthenticated])
def strategy_detail(request, pk):
    try:
        strategy = Strategy.objects.get(pk=pk, user=request.user)
    except Strategy.DoesNotExist:
        return Response({"error": "없는 전략입니다."}, status=status.HTTP_404_NOT_FOUND)

    if request.method == "GET":
        return Response(StrategySerializer(strategy).data)

    if request.method == "PATCH":
        serializer = StrategySerializer(strategy, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    if request.method == "DELETE":
        strategy.is_active = False
        strategy.save()
        return Response(status=status.HTTP_204_NO_CONTENT)