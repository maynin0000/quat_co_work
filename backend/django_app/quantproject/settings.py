"""
Django settings for quantproject
"""

from pathlib import Path
import os
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent.parent.parent / ".env")

BASE_DIR = Path(__file__).resolve().parent.parent

# ──────────────────────────────────────
# 보안
# ──────────────────────────────────────
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "django-insecure-(i+02%gkyfui@jb%dc%bl_lzitaaghwvuqg6gxxd2#$d=^r2pm")
DEBUG = os.getenv("DJANGO_DEBUG", "True") == "True"
ALLOWED_HOSTS = os.getenv("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")

# ──────────────────────────────────────
# 앱
# ──────────────────────────────────────
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework_simplejwt.token_blacklist",

    # 설치 패키지
    "rest_framework",
    "corsheaders",

    # 우리 앱
    "quant_users",
    "quant_strategy",
    "quant_portfolio",
    "quant_feedback",
]

# ──────────────────────────────────────
# 미들웨어
# ──────────────────────────────────────
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware",              # CORS - 반드시 CommonMiddleware 위에
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "quantproject.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "quantproject.wsgi.application"

# ──────────────────────────────────────
# DB (PostgreSQL bitnami)
# ──────────────────────────────────────
DATABASES = {
    "default": {
        "ENGINE"  : "django.db.backends.postgresql",
        "NAME"    : os.getenv("POSTGRES_DB", "quantra"),
        "USER"    : os.getenv("POSTGRES_USER", "quantra"),
        "PASSWORD": os.getenv("POSTGRES_PASSWORD", "1234"),
        "HOST"    : os.getenv("POSTGRES_HOST", "localhost"),
        "PORT"    : os.getenv("POSTGRES_PORT", "5432"),
    }
}

# ──────────────────────────────────────
# 캐시 (Redis)
# ──────────────────────────────────────
CACHES = {
    # 기본 캐시 (추천 결과)
    "default": {
        "BACKEND" : "django.core.cache.backends.redis.RedisCache",
        "LOCATION": os.getenv("REDIS_URL", "redis://localhost:6379/0"),
        "TIMEOUT" : 60 * 60 * 6,    # 6시간
    },
    # 종목 분석결과 캐시
    "analysis": {
        "BACKEND" : "django.core.cache.backends.redis.RedisCache",
        "LOCATION": os.getenv("REDIS_URL", "redis://localhost:6379/1"),
        "TIMEOUT" : 60 * 60 * 24,   # 1일
    },
    # 세션 캐시
    "session": {
        "BACKEND" : "django.core.cache.backends.redis.RedisCache",
        "LOCATION": os.getenv("REDIS_URL", "redis://localhost:6379/2"),
        "TIMEOUT" : 60 * 60 * 24 * 7,  # 1주일
    },
}

# 세션 Redis에 저장
SESSION_ENGINE     = "django.contrib.sessions.backends.cache"
SESSION_CACHE_ALIAS = "session"

# ──────────────────────────────────────
# CORS (FastAPI + 프론트 허용)
# ──────────────────────────────────────
CORS_ALLOWED_ORIGINS = [
    "http://localhost:3000",    # 프론트
    "http://localhost:8001",    # FastAPI 로컬
    "http://fastapi:8001",      # FastAPI 도커 내부
]
CORS_ALLOW_CREDENTIALS = True

# ──────────────────────────────────────
# DRF (Django REST Framework)
# ──────────────────────────────────────
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
}

# ──────────────────────────────────────
# JWT
# ──────────────────────────────────────
from datetime import timedelta
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME" : timedelta(hours=1),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
}

# ──────────────────────────────────────
# 커스텀 유저 모델
# ──────────────────────────────────────
AUTH_USER_MODEL = "quant_users.User"

# ──────────────────────────────────────
# Celery
# ──────────────────────────────────────
CELERY_BROKER_URL        = os.getenv("REDIS_URL", "redis://localhost:6379/0")
CELERY_RESULT_BACKEND    = os.getenv("REDIS_URL", "redis://localhost:6379/0")
CELERY_TIMEZONE          = "Asia/Seoul"

# ──────────────────────────────────────
# 내부 서비스 통신
# ──────────────────────────────────────
FASTAPI_INTERNAL_URL  = os.getenv("FASTAPI_INTERNAL_URL", "http://fastapi:8001")
INTERNAL_SERVICE_TOKEN = os.getenv("INTERNAL_SERVICE_TOKEN", "internal-secret")

# ──────────────────────────────────────
# 기타
# ──────────────────────────────────────
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE    = "ko-kr"
TIME_ZONE        = "Asia/Seoul"
USE_I18N         = True
USE_TZ           = True
STATIC_URL       = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"