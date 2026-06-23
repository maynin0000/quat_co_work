from django.urls import path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from quant_users import views

urlpatterns = [
    path("register/", views.register,            name="register"),
    path("login/",    TokenObtainPairView.as_view(), name="login"),
    path("logout/",   views.logout,              name="logout"),
    path("token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("profile/",  views.profile,             name="profile"),
]