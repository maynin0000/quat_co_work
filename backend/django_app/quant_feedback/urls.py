from django.urls import path
from quant_feedback import views

urlpatterns = [
    path("",       views.feedback,       name="feedback"),
    path("stats/", views.feedback_stats, name="feedback-stats"),
]