from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    email = models.EmailField(unique=True)

    risk_level = models.CharField(
        max_length=10,
        choices=[
            ("low",    "안정형"),
            ("medium", "중립형"),
            ("high",   "공격형"),
        ],
        default="medium"
    )

    USERNAME_FIELD  = "email"
    REQUIRED_FIELDS = ["username"]

    def __str__(self):
        return self.email