from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from quant_feedback.models import RecommendationFeedback
from quant_feedback.serializers import FeedbackSerializer


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def feedback(request):
    serializer = FeedbackSerializer(data=request.data)
    if serializer.is_valid():
        serializer.save(user=request.user)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def feedback_stats(request):
    ticker = request.query_params.get("ticker")
    qs = RecommendationFeedback.objects.filter(ticker=ticker) if ticker else RecommendationFeedback.objects.all()
    positive = qs.filter(is_positive=True).count()
    negative = qs.filter(is_positive=False).count()
    total    = positive + negative
    return Response({
        "positive": positive,
        "negative": negative,
        "score"   : round(positive / total * 100, 1) if total else 0.0
    })