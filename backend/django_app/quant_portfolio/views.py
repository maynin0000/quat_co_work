from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from quant_portfolio.models import Portfolio, WatchList
from quant_portfolio.serializers import PortfolioSerializer, WatchListSerializer


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def portfolio_list(request):
    if request.method == "GET":
        return Response(PortfolioSerializer(
            Portfolio.objects.filter(user=request.user), many=True
        ).data)
    serializer = PortfolioSerializer(data=request.data)
    if serializer.is_valid():
        serializer.save(user=request.user)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(["GET", "POST", "DELETE"])
@permission_classes([IsAuthenticated])
def watchlist(request):
    if request.method == "GET":
        return Response(WatchListSerializer(
            WatchList.objects.filter(user=request.user), many=True
        ).data)

    if request.method == "POST":
        serializer = WatchListSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(user=request.user)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    if request.method == "DELETE":
        ticker = request.data.get("ticker")
        WatchList.objects.filter(user=request.user, ticker=ticker).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)