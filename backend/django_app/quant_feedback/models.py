from django.db import models
from django.conf import settings


class RecommendationFeedback(models.Model):
    user          = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="feedbacks"
    )
    ticker        = models.CharField(max_length=20)
    strategy_name = models.CharField(max_length=100)
    is_positive   = models.BooleanField()
    created_at    = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.email} - {self.ticker} - {'👍' if self.is_positive else '👎'}"