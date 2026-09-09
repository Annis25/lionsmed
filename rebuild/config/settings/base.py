from pathlib import Path
import os
from datetime import timedelta
from urllib.parse import urlsplit
from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[2]
# Ne jamais charger le .env du legacy (un répertoire plus haut).
load_dotenv(BASE_DIR / ".env", override=False)

def required(name):
    value = os.environ.get(name, "").strip()
    if not value:
        raise ImproperlyConfigured(f"Variable requise absente : {name}")
    return value

SECRET_KEY = required("DJANGO_SECRET_KEY")
if os.environ.get("LIONSMED_DB_PURPOSE") != "rebuild":
    raise ImproperlyConfigured("LIONSMED_DB_PURPOSE doit identifier explicitement rebuild.")
DB_NAME = required("DB_NAME")
if not DB_NAME.startswith("lionsmed_rebuild_"):
    raise ImproperlyConfigured("Le nouveau schéma exige une base lionsmed_rebuild_* distincte du legacy.")
DB_TEST_NAME = os.environ.get("DB_TEST_NAME") or "test_" + DB_NAME
if not DB_TEST_NAME.startswith("test_lionsmed_rebuild_") or DB_TEST_NAME == DB_NAME:
    raise ImproperlyConfigured("Nom de base de tests non isolé.")
DATABASES = {"default": {
    "ENGINE": "django.db.backends.postgresql",
    "NAME": DB_NAME, "USER": required("DB_USER"),
    "PASSWORD": os.environ.get("DB_PASSWORD", ""),
    "HOST": required("DB_HOST"), "PORT": os.environ.get("DB_PORT") or "5432",
    "CONN_MAX_AGE": 0, "TEST": {"NAME": DB_TEST_NAME},
}}
DEBUG = False
ALLOWED_HOSTS = [x.strip() for x in os.environ.get("DJANGO_ALLOWED_HOSTS", "").split(",") if x.strip()]
SITE_ORIGIN = os.environ.get("DJANGO_SITE_ORIGIN") or "http://localhost:8000"
_origin = urlsplit(SITE_ORIGIN)
if _origin.scheme not in {"http", "https"} or not _origin.netloc or _origin.path not in {"", "/"} or _origin.query or _origin.fragment or _origin.username:
    raise ImproperlyConfigured("DJANGO_SITE_ORIGIN doit être une origine HTTP(S) sans chemin ni credentials.")
SITE_ORIGIN = SITE_ORIGIN.rstrip("/")
INSTALLED_APPS = [
    "django.contrib.admin", "django.contrib.auth", "django.contrib.contenttypes",
    "django.contrib.sessions", "django.contrib.messages", "django.contrib.staticfiles",
    "django.contrib.postgres", "axes", "apps.accounts", "apps.members",
    "apps.governance", "apps.core",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "apps.core.middleware.PrivateHeadersMiddleware",
    "axes.middleware.AxesMiddleware",
]
ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
TEMPLATES = [{"BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [BASE_DIR / "templates"], "APP_DIRS": True,
    "OPTIONS": {"context_processors": [
        "django.template.context_processors.request",
        "django.contrib.auth.context_processors.auth",
        "django.contrib.messages.context_processors.messages",
        "apps.core.context_processors.shell",
    ]}}]
AUTH_USER_MODEL = "accounts.User"
AUTHENTICATION_BACKENDS = ["axes.backends.AxesStandaloneBackend", "apps.accounts.backends.EmailBackend"]
LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "core:dashboard"
LOGOUT_REDIRECT_URL = "accounts:login"
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 12}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
LANGUAGE_CODE = "fr-fr"
TIME_ZONE = "Africa/Tunis"
USE_I18N = True
USE_TZ = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "runtime" / "staticfiles"
# Aucun mapping URL vers ce stockage. Futurs fichiers internes uniquement.
PRIVATE_MEDIA_ROOT = BASE_DIR / "runtime" / "private_media"
STORAGES = {"default": {"BACKEND": "django.core.files.storage.FileSystemStorage", "OPTIONS": {"location": PRIVATE_MEDIA_ROOT}},
            "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}}
SESSION_COOKIE_NAME = "lionsmed_rebuild_session"
CSRF_COOKIE_NAME = "lionsmed_rebuild_csrf"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SESSION_COOKIE_AGE = 60 * 60 * 12
PASSWORD_RESET_TIMEOUT = 3600
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"
# Toutes les pages de ce lot sont non indexables, même en production.
ROBOTS_NOINDEX = True
EMAIL_BACKEND = "django.core.mail.backends.dummy.EmailBackend"
DEFAULT_FROM_EMAIL = "noreply@example.invalid"
AXES_HANDLER = "axes.handlers.database.AxesDatabaseHandler"
AXES_FAILURE_LIMIT = 5
AXES_COOLOFF_TIME = timedelta(minutes=15)
AXES_LOCKOUT_PARAMETERS = [["username", "ip_address"]]
AXES_USERNAME_FORM_FIELD = "username"
AXES_RESET_ON_SUCCESS = True
AXES_ENABLE_ACCESS_FAILURE_LOG = False
AXES_DISABLE_ACCESS_LOG = True
AXES_VERBOSE = False
AXES_IPWARE_PROXY_COUNT = 0
AXES_LOCKOUT_CALLABLE = "apps.accounts.views.lockout"
LOGGING = {"version": 1, "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "WARNING"},
    "loggers": {"axes": {"handlers": ["console"], "level": "ERROR", "propagate": False},
                "django.security": {"handlers": ["console"], "level": "WARNING", "propagate": False}}}

# Limites du corps non fichier et du nombre de fichiers ; limite photo au service.
DATA_UPLOAD_MAX_MEMORY_SIZE = 1024 * 1024
DATA_UPLOAD_MAX_NUMBER_FILES = 1
FILE_UPLOAD_MAX_MEMORY_SIZE = 1024 * 1024
FILE_UPLOAD_HANDLERS = [
    "apps.members.upload_handlers.PhotoSizeLimitHandler",
    "django.core.files.uploadhandler.MemoryFileUploadHandler",
    "django.core.files.uploadhandler.TemporaryFileUploadHandler",
]
