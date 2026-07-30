from pathlib import Path
import os
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[2]
ENV_FILE = os.getenv("DJANGO_ENV_FILE", ".env")
load_dotenv(BASE_DIR / ENV_FILE)

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "dev-secret-key-change-me")
DEBUG = os.getenv("DJANGO_DEBUG", "True") == "True"

ALLOWED_HOSTS = [host.strip() for host in os.getenv("DJANGO_ALLOWED_HOSTS", "127.0.0.1,localhost").split(",") if host.strip()]

INSTALLED_APPS = [
    "unfold",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "drf_spectacular",
    "django_filters",

    "phonenumber_field",
    
    "apps.accounts",
    "apps.pages",
    "apps.catalog",
    "apps.shop",
    "apps.leads",
    "apps.tracking",
    "apps.analytics",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "apps.accounts.middleware.ActiveProfileMiddleware",
    "apps.tracking.middleware.VisitorMiddleware",
    "apps.tracking.middleware.PageVisitMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",

]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.shop.context_processors.shop_counters",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DB_ENGINE = os.getenv("DB_ENGINE", "sqlite")

if DB_ENGINE == "postgres":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.getenv("POSTGRES_DB", "django_b2b"),
            "USER": os.getenv("POSTGRES_USER", "django_b2b"),
            "PASSWORD": os.getenv("POSTGRES_PASSWORD", "django_b2b_password"),
            "HOST": os.getenv("POSTGRES_HOST", "db"),
            "PORT": os.getenv("POSTGRES_PORT", "5432"),
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }


AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "ru"
TIME_ZONE = "Europe/Moscow"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AUTH_USER_MODEL = "accounts.User"

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "accounts:dashboard"
LOGOUT_REDIRECT_URL = "pages:home"

TRACKING_VISITOR_COOKIE_NAME = "visitor_id"
TRACKING_VISITOR_COOKIE_AGE = 60 * 60 * 24 * 365

TRACKING_EXCLUDED_PATH_PREFIXES = [
    "/admin/",
    "/static/",
    "/media/",
    "/favicon.ico",
    "/robots.txt",
    "/.well-known/",
]

# Настройки темы оформления админки (Django Unfold)
UNFOLD = {
    "SITE_TITLE": "LIDER Admin",
    "SITE_HEADER": "LIDER",
    "SITE_URL": "/",
    "COLORS": {
        "primary": {
            "50": "#f4fffa",
            "100": "#8df5de",
            "200": "#70d8c2",
            "300": "#008471",
            "400": "#00725d",
            "500": "#006b58",
            "600": "#006859",
            "700": "#005142",
            "800": "#005045",
            "900": "#002019",
        },
    },
    "SIDEBAR": {
        "show_search": True,
        "show_all_applications": True,
        "navigation":[
            {
                "title": "Аналитика",
                "separator": True,
                "items":[
                    {
                        "title": "Аналитический дашборд",
                        "icon": "analytics",
                        "link": "/admin/analytics/dashboard/",
                    },
                ],
            },
        ],
    },
}

REST_FRAMEWORK = {
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Django B2B E-commerce API",
    "DESCRIPTION": "REST API for B2B product catalog, leads, analytics and lead scoring.",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
}
