from django.urls import path
from quant_portfolio import views

urlpatterns = [
    path("",          views.portfolio_list, name="portfolio-list"),
    path("watchlist/", views.watchlist,     name="watchlist"),
]