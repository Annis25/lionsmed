from .base import *
ALLOWED_HOSTS = ["testserver", "localhost", "127.0.0.1"]
SITE_ORIGIN = "http://testserver"
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]  # Tests synthétiques seulement.
# Aucune boîte institutionnelle reliée pendant les tests, quel que soit le .env du poste :
# chaque test déclare les siennes, et rien ne part vers le vrai serveur de messagerie.
MAILBOX_PASSWORDS = {}
MAILBOX_USERNAMES = {}
MAILBOX_EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
