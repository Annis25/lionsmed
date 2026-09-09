from .base import *
if len(SECRET_KEY) < 50 or not ALLOWED_HOSTS or "*" in ALLOWED_HOSTS or not SITE_ORIGIN.startswith("https://"):
    raise ImproperlyConfigured("Configuration production incomplète : clé forte, hôtes exacts et origine HTTPS requis.")
SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS = 3600
# Ne pas engager sous-domaines/preload sans validation d'exploitation.
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False
CSRF_TRUSTED_ORIGINS = [SITE_ORIGIN]
STORAGES["staticfiles"] = {"BACKEND": "django.contrib.staticfiles.storage.ManifestStaticFilesStorage"}
# SMTP reste inactif tant que son activation n'est pas explicite.
if os.environ.get("LIONSMED_SMTP_ENABLED") == "true":
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    EMAIL_HOST = required("EMAIL_HOST")
    EMAIL_PORT = int(os.environ.get("EMAIL_PORT") or "587")
    EMAIL_HOST_USER = required("EMAIL_HOST_USER")
    EMAIL_HOST_PASSWORD = required("EMAIL_HOST_PASSWORD")
    EMAIL_USE_TLS = True
    EMAIL_TIMEOUT = 10
    DEFAULT_FROM_EMAIL = required("DEFAULT_FROM_EMAIL")

# Activation explicite après validation éditoriale ; préproduction reste noindex.
PUBLIC_INDEXING_ENABLED = os.environ.get("LIONSMED_PUBLIC_INDEXING") == "true"
