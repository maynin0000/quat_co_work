from django.db import models
from django.conf import settings


class Portfolio(models.Model):
    user       = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="portfolios"
    )
    name       = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.email} - {self.name}"


class WatchList(models.Model):
    user       = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="watchlist"
    )
    ticker     = models.CharField(max_length=20)
    name       = models.CharField(max_length=100)
    added_at   = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ["user", "ticker"]

    def __str__(self):
        return f"{self.user.email} - {self.ticker}"