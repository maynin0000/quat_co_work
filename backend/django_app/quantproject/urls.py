from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path("admin/",        admin.site.urls),
    path("api/users/",    include("quant_users.urls")),
    path("api/strategy/", include("quant_strategy.urls")),
    path("api/portfolio/",include("quant_portfolio.urls")),
    path("api/feedback/", include("quant_feedback.urls")),
    path("internal/",     include("quant_strategy.internal_urls")),
]