from django.urls import path
from quant_strategy import views

urlpatterns = [
    path("",        views.strategy_list,   name="strategy-list"),
    path("<int:pk>/", views.strategy_detail, name="strategy-detail"),
]