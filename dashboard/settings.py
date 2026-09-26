"""Local-first dashboard settings. Configure a real secret and host for deployment."""

from __future__ import annotations

import os
from pathlib import Path

from hrbot.config import ROOT, load_env


load_env()
BASE_DIR = ROOT
SECRET_KEY = os.getenv("DASHBOARD_SECRET_KEY") or "django-insecure-local-only-change-before-deployment"
DEBUG = os.getenv("DASHBOARD_DEBUG", "0") == "1"
ALLOWED_HOSTS = [host.strip() for host in os.getenv("DASHBOARD_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if host.strip()]
CSRF_TRUSTED_ORIGINS = [origin.strip() for origin in os.getenv("DASHBOARD_CSRF_TRUSTED_ORIGINS", "").split(",") if origin.strip()]
if os.getenv("DASHBOARD_PRODUCTION") == "1" and SECRET_KEY == "django-insecure-local-only-change-before-deployment":
    raise RuntimeError("Set DASHBOARD_SECRET_KEY before deploying the dashboard")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "dashboard_app",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
ROOT_URLCONF = "dashboard.urls"
TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [BASE_DIR / "dashboard" / "templates"],
    "APP_DIRS": True,
    "OPTIONS": {"context_processors": [
        "django.template.context_processors.debug",
        "django.template.context_processors.request",
        "django.contrib.auth.context_processors.auth",
        "django.contrib.messages.context_processors.messages",
        "dashboard_app.context.dashboard_context",
    ]},
}]
WSGI_APPLICATION = "dashboard.wsgi.application"
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "data" / "dashboard.sqlite3", "OPTIONS": {"timeout": 20}}}
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
LANGUAGE_CODE = "en-us"
TIME_ZONE = os.getenv("TIMEZONE", "Asia/Karachi")
USE_I18N = True
USE_TZ = True
STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "home"
LOGOUT_REDIRECT_URL = "login"
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = True
SESSION_COOKIE_SECURE = os.getenv("DASHBOARD_PRODUCTION") == "1"
CSRF_COOKIE_SECURE = os.getenv("DASHBOARD_PRODUCTION") == "1"
SECURE_SSL_REDIRECT = os.getenv("DASHBOARD_PRODUCTION") == "1"
