from .base import *
ALLOWED_HOSTS = ["testserver", "localhost", "127.0.0.1"]
SITE_ORIGIN = "http://testserver"
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]  # Tests synthétiques seulement.
