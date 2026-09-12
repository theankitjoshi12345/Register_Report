"""Django settings shared by local development and future environments."""

from pathlib import Path

import environ
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(DJANGO_DEBUG=(bool, False))
# Real environment variables take precedence over the local .env file.
environ.Env.read_env(BASE_DIR / ".env", overwrite=False)

DEBUG = env("DJANGO_DEBUG")
SECRET_KEY = env("DJANGO_SECRET_KEY")
if not SECRET_KEY:
    raise ImproperlyConfigured("DJANGO_SECRET_KEY must not be empty.")

ALLOWED_HOSTS = env.list(
    "DJANGO_ALLOWED_HOSTS",
    default=["localhost", "127.0.0.1", "[::1]"] if DEBUG else [],
)
CSRF_TRUSTED_ORIGINS = env.list("DJANGO_CSRF_TRUSTED_ORIGINS", default=[])
CORS_ALLOWED_ORIGINS = env.list("DJANGO_CORS_ALLOWED_ORIGINS", default=[])
CROSS_SITE_COOKIES = env.bool("DJANGO_CROSS_SITE_COOKIES", default=False)

# Vercel supplies these hostnames at runtime. Trust only the deployment's own
# generated hostname and production hostname, including preview deployments.
for vercel_host_variable in ("VERCEL_URL", "VERCEL_PROJECT_PRODUCTION_URL"):
    vercel_host = env(vercel_host_variable, default="").strip()
    if vercel_host and vercel_host not in ALLOWED_HOSTS:
        ALLOWED_HOSTS.append(vercel_host)
    vercel_origin = f"https://{vercel_host}" if vercel_host else ""
    if vercel_origin and vercel_origin not in CSRF_TRUSTED_ORIGINS:
        CSRF_TRUSTED_ORIGINS.append(vercel_origin)

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "stores.apps.StoresConfig",
    "reports.apps.ReportsConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "stores.cors.CorsMiddleware",
    "config.security.ApiBoundaryMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "stores.throttling.LoginThrottleMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

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

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASES = {
    "default": env.db(
        "DATABASE_URL",
        default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
    ),
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
# Store-specific business dates and time zones will be defined with the report requirements.
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

CSRF_FAILURE_VIEW = "stores.views.csrf_failure"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "None" if CROSS_SITE_COOKIES else "Lax"
SESSION_COOKIE_SECURE = env.bool("DJANGO_SECURE_COOKIES", default=not DEBUG)
CSRF_COOKIE_SAMESITE = "None" if CROSS_SITE_COOKIES else "Lax"
CSRF_COOKIE_SECURE = env.bool("DJANGO_SECURE_COOKIES", default=not DEBUG)

# Trust proxy headers only on the Vercel ingress that supplies them. Other hosts
# must opt in after configuring their proxy to replace client-supplied headers.
ON_VERCEL = env("VERCEL", default="") == "1"
LOGIN_TRUST_VERCEL_IP = ON_VERCEL
if ON_VERCEL or env.bool("DJANGO_TRUST_PROXY_HTTPS", default=False):
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = env.bool("DJANGO_SSL_REDIRECT", default=not DEBUG)
SECURE_HSTS_SECONDS = 31536000 if not DEBUG else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False

LOGIN_ACCOUNT_LIMIT = 10
LOGIN_IP_LIMIT = 60
LOGIN_WINDOW_SECONDS = 900
DATA_UPLOAD_MAX_MEMORY_SIZE = 1024 * 1024
