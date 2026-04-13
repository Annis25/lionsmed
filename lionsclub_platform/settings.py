from datetime import timedelta
from pathlib import Path
import os
from django.core.exceptions import ImproperlyConfigured
from django.core.files.storage import FileSystemStorage
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / '.env')

# Aucune valeur de repli : une clé par défaut en dur signerait les sessions avec
# un secret public. Absence de la variable = refus de démarrer.
SECRET_KEY = os.getenv('SECRET_KEY')
if not SECRET_KEY:
    raise ImproperlyConfigured(
        "La variable d'environnement SECRET_KEY est absente. "
        "Générez-la avec : python -c \"from django.core.management.utils import "
        "get_random_secret_key; print(get_random_secret_key())\" "
        "puis renseignez-la dans le fichier .env du serveur."
    )

# Défaut volontairement à False : une variable d'environnement absente ou mal
# orthographiée sur le serveur ne doit jamais démarrer le site en mode debug.
DEBUG = os.getenv('DEBUG', 'False') == 'True'

# Le domaine de production est une constante du projet, pas un paramètre de
# déploiement : le laisser dans le code évite une couche de configuration pour
# une valeur qui ne change jamais. (Une variable ALLOWED_HOSTS traînait dans le
# .env sans jamais être lue — supprimée pour ne pas laisser croire l'inverse.)
ALLOWED_HOSTS = [
    "lionsmed.tn",
    "www.lionsmed.tn",
]

# Hôtes de développement : jamais acceptés en production, où ils ouvriraient la
# porte à des requêtes dont l'en-tête Host ne correspond pas au domaine réel.
if DEBUG:
    ALLOWED_HOSTS += ["127.0.0.1", "localhost", "testserver"]

AUTH_USER_MODEL = 'accounts.User'

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.sites',
    # Third-party
    'axes',
    'dbbackup',
    # Local apps
    'sitecontent',
    'core',
    'accounts',
    'news',
    'events',
    'gallery',
    'members',
    'voting',
    'notifications',
]

# Outillage de développement uniquement : django-extensions expose des commandes
# (shell_plus, runserver_plus, graph_models) qui n'ont pas leur place en production.
if DEBUG:
    INSTALLED_APPS.append('django_extensions')

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    # Doit rester en dernier : AxesMiddleware traite la réponse produite par les
    # vues d'authentification pour comptabiliser les échecs.
    'axes.middleware.AxesMiddleware',
]

ROOT_URLCONF = 'lionsclub_platform.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'accounts.context_processors.admin_context',
                'sitecontent.context_processors.site_config',
            ],
        },
    },
]

WSGI_APPLICATION = 'lionsclub_platform.wsgi.application'

# ── Base de données ───────────────────────────────────────────────────────────
# Bascule sur PostgreSQL dès que DATABASE_URL ou DB_NAME est présent dans
# l'environnement ; reste sur SQLite sinon. Aucune migration automatique : le
# passage à PostgreSQL est une décision d'exploitation (voir MIGRATION_POSTGRES.md).
def _postgres_from_url(url):
    """Analyse postgres://user:password@host:port/dbname."""
    from urllib.parse import urlparse, unquote
    parsed = urlparse(url)
    if parsed.scheme not in ('postgres', 'postgresql', 'psql'):
        raise ImproperlyConfigured(
            f"DATABASE_URL : schéma « {parsed.scheme} » non pris en charge "
            "(attendu postgres:// ou postgresql://)."
        )
    return {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': unquote(parsed.path.lstrip('/')),
        'USER': unquote(parsed.username or ''),
        'PASSWORD': unquote(parsed.password or ''),
        'HOST': parsed.hostname or 'localhost',
        'PORT': str(parsed.port or 5432),
        'CONN_MAX_AGE': int(os.getenv('DB_CONN_MAX_AGE', '60')),
    }


DATABASE_URL = os.getenv('DATABASE_URL', '').strip()

if DATABASE_URL:
    DATABASES = {'default': _postgres_from_url(DATABASE_URL)}
elif os.getenv('DB_NAME'):
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': os.getenv('DB_NAME'),
            'USER': os.getenv('DB_USER', ''),
            'PASSWORD': os.getenv('DB_PASSWORD', ''),
            'HOST': os.getenv('DB_HOST', 'localhost'),
            'PORT': os.getenv('DB_PORT', '5432'),
            'CONN_MAX_AGE': int(os.getenv('DB_CONN_MAX_AGE', '60')),
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
            # Réduit (sans supprimer) les « database is locked » sous écritures
            # concurrentes, en attendant le passage à PostgreSQL.
            'OPTIONS': {'timeout': 20},
        }
    }

# Cache partagé : le compteur de django-ratelimit doit être commun à tous les
# workers. Un cache local par processus multiplierait la limite par leur nombre.
# Le cache base de données convient au volume attendu ; passer à Redis si le
# trafic augmente (variable CACHE_URL à introduire le cas échéant).
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.db.DatabaseCache',
        'LOCATION': 'lionsmed_cache',
    }
}

RATELIMIT_USE_CACHE = 'default'

# Longueur minimale portée à 12 : ces comptes donnent accès aux documents
# internes du club (procès-verbaux, rapports). Le défaut de Django est 8.
# Cette valeur est reprise par PASSWORD_MIN_LENGTH ci-dessous, qui sert aussi
# à générer les mots de passe temporaires : les deux doivent rester alignés.
PASSWORD_MIN_LENGTH = 12

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
        'OPTIONS': {'min_length': PASSWORD_MIN_LENGTH},
    },
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'fr-fr'
TIME_ZONE = 'Africa/Tunis'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

# Limites d'upload : au-delà de FILE_UPLOAD_MAX_MEMORY_SIZE le fichier est
# écrit sur disque au lieu d'être gardé en mémoire ; DATA_UPLOAD_MAX_MEMORY_SIZE
# plafonne le corps d'une requête non-fichier (protège d'un POST géant).
DATA_UPLOAD_MAX_MEMORY_SIZE = 16 * 1024 * 1024   # 16 Mo
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024    # 5 Mo
DATA_UPLOAD_MAX_NUMBER_FIELDS = 1000

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Fichiers privés (documents internes du club) : stockés HORS de MEDIA_ROOT afin
# qu'aucune configuration de serveur web ne puisse les exposer par URL directe.
# L'accès passe obligatoirement par la vue accounts.views.document_download,
# qui applique Document.is_visible_to().
PRIVATE_MEDIA_ROOT = BASE_DIR / 'private_media'
PRIVATE_STORAGE = FileSystemStorage(location=PRIVATE_MEDIA_ROOT)

# Auth
LOGIN_URL = '/connexion/'
LOGIN_REDIRECT_URL = '/espace-membre/'
LOGOUT_REDIRECT_URL = '/'

# django-allauth a été retiré : aucune URL, aucun template et aucun fournisseur
# social ne l'utilisaient, et la version installée portait 3 vulnérabilités.
# L'authentification passe par accounts.views.login_view, écrite à la main.
# Si une connexion Google/Facebook est souhaitée un jour, réinstaller allauth
# en 65.x directement (voir ALLAUTH_UPGRADE_NOTES.md).

# Requis tant que django.contrib.sites figure dans INSTALLED_APPS.
SITE_ID = 1

AUTHENTICATION_BACKENDS = [
    # AxesStandaloneBackend doit être en premier : il intercepte les tentatives
    # sur un compte verrouillé avant toute vérification de mot de passe.
    'axes.backends.AxesStandaloneBackend',
    'django.contrib.auth.backends.ModelBackend',
]

# ── Email ─────────────────────────────────────────────────────────────────────
# Le backend console écrit les messages sur stdout, donc dans les journaux du
# serveur : inacceptable en production, où ces messages contiennent des mots de
# passe temporaires. Il n'est donc autorisé qu'en développement.
DEFAULT_FROM_EMAIL = os.getenv('DEFAULT_FROM_EMAIL', 'secretariat@lionsmed.tn')

if DEBUG:
    EMAIL_BACKEND = os.getenv(
        'EMAIL_BACKEND', 'django.core.mail.backends.console.EmailBackend'
    )
else:
    EMAIL_BACKEND = os.getenv(
        'EMAIL_BACKEND', 'django.core.mail.backends.smtp.EmailBackend'
    )
    if EMAIL_BACKEND.endswith('console.EmailBackend'):
        raise ImproperlyConfigured(
            "Le backend email « console » écrit les messages dans les journaux du "
            "serveur, mots de passe temporaires compris. Il est interdit hors DEBUG."
        )

EMAIL_HOST = os.getenv('EMAIL_HOST', '')
EMAIL_PORT = int(os.getenv('EMAIL_PORT', '587'))
EMAIL_HOST_USER = os.getenv('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD', '')
EMAIL_USE_TLS = os.getenv('EMAIL_USE_TLS', 'True') == 'True'
EMAIL_USE_SSL = os.getenv('EMAIL_USE_SSL', 'False') == 'True'
EMAIL_TIMEOUT = int(os.getenv('EMAIL_TIMEOUT', '10'))

if not DEBUG and EMAIL_BACKEND.endswith('smtp.EmailBackend') and not EMAIL_HOST:
    raise ImproperlyConfigured(
        "EMAIL_HOST est absent : configurez le serveur SMTP dans le .env de production."
    )

# ── Journalisation ────────────────────────────────────────────────────────────
# Deux fichiers en rotation (5 × 5 Mo) :
#   lionsmed.log  — activité générale et erreurs serveur
#   securite.log  — connexions échouées, verrouillages, actions d'administration
# LOG_DIR permet de pointer vers /var/log/lionsmed en production ; le dossier
# doit être accessible en écriture par l'utilisateur applicatif.
LOG_DIR = Path(os.getenv('LOG_DIR', BASE_DIR / 'logs'))
LOG_DIR.mkdir(parents=True, exist_ok=True)

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'detaille': {
            'format': '{asctime} {levelname:<8} {name} {message}',
            'style': '{',
        },
        'securite': {
            'format': '{asctime} {levelname:<8} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'detaille',
            'level': 'INFO',
        },
        'fichier': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': str(LOG_DIR / 'lionsmed.log'),
            'maxBytes': 5 * 1024 * 1024,
            'backupCount': 5,
            'encoding': 'utf-8',
            'formatter': 'detaille',
            'level': 'INFO',
        },
        'fichier_securite': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': str(LOG_DIR / 'securite.log'),
            'maxBytes': 5 * 1024 * 1024,
            'backupCount': 5,
            'encoding': 'utf-8',
            'formatter': 'securite',
            'level': 'INFO',
        },
    },
    'root': {
        'handlers': ['console', 'fichier'],
        'level': 'INFO',
    },
    'loggers': {
        # Erreurs serveur (500) et requêtes rejetées (SuspiciousOperation…)
        'django.request': {
            'handlers': ['fichier', 'console'],
            'level': 'ERROR',
            'propagate': False,
        },
        'django.security': {
            'handlers': ['fichier_securite', 'console'],
            'level': 'INFO',
            'propagate': False,
        },
        # Verrouillages et tentatives échouées relevés par django-axes
        'axes': {
            'handlers': ['fichier_securite', 'console'],
            'level': 'INFO',
            'propagate': False,
        },
        # Journal métier : échecs de connexion et actions d'administration
        'lionsmed.securite': {
            'handlers': ['fichier_securite', 'console'],
            'level': 'INFO',
            'propagate': False,
        },
        # Bruit inutile en fonctionnement normal
        'django.db.backends': {
            'handlers': ['fichier'],
            'level': 'WARNING',
            'propagate': False,
        },
    },
}

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ── Sécurité HTTPS ────────────────────────────────────────────────────────────
# Actifs uniquement hors DEBUG : en développement local (HTTP), forcer les
# cookies Secure et la redirection SSL rendrait le site inutilisable.
CSRF_TRUSTED_ORIGINS = ['https://lionsmed.tn', 'https://www.lionsmed.tn']

if not DEBUG:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_SSL_REDIRECT = True
    # Valeur basse au départ : HSTS engage le navigateur pour toute sa durée et
    # n'est pas révocable. À monter par paliers (300 → 86400 → 31536000) une fois
    # le certificat TLS vérifié et le renouvellement automatique confirmé.
    SECURE_HSTS_SECONDS = 300
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    # ATTENTION — ce réglage fait confiance à un en-tête HTTP.
    #
    # Django considérera toute requête portant « X-Forwarded-Proto: https »
    # comme sécurisée. Si nginx se contente de *transmettre* l'en-tête reçu au
    # lieu de l'*écraser*, n'importe quel client peut l'envoyer lui-même : la
    # redirection HTTPS est alors contournée, request.is_secure() ment, et les
    # cookies marqués Secure sont émis sur une connexion en clair.
    #
    # nginx DOIT donc contenir, dans le bloc proxy_pass :
    #     proxy_set_header X-Forwarded-Proto $scheme;
    # (`$scheme` = protocole réellement vu par nginx, jamais l'en-tête client)
    #
    # Voir DEPLOIEMENT.md pour la configuration complète et sa vérification.
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# ── django-axes : protection contre le bourrinage de mots de passe ────────────
AXES_FAILURE_LIMIT = 5              # verrouillage au 5e échec
AXES_COOLOFF_TIME = timedelta(minutes=30)
# Verrouillage sur le couple IP + identifiant : évite qu'un attaquant bloque le
# compte d'un tiers depuis une autre IP (déni de service), tout en freinant
# le balayage d'identifiants depuis une même IP.
AXES_LOCKOUT_PARAMETERS = [['ip_address', 'username']]
AXES_RESET_ON_SUCCESS = True
AXES_LOCKOUT_TEMPLATE = 'registration/lockout.html'
AXES_VERBOSE = True

# ── Sauvegardes (django-dbbackup) ─────────────────────────────────────────────
# Destination pilotée par BACKUP_ROOT : par défaut un dossier hors du dépôt, à
# remplacer par un point de montage distant (NAS, stockage objet) en production.
# Une sauvegarde sur le même disque que la base ne protège pas d'une panne disque.
BACKUP_ROOT = Path(os.getenv('BACKUP_ROOT', BASE_DIR.parent / 'lionsmed_backups'))
BACKUP_ROOT.mkdir(parents=True, exist_ok=True)

# django-dbbackup >= 4.2 lit la destination via STORAGES['dbbackup'] et non plus
# via DBBACKUP_STORAGE/DBBACKUP_STORAGE_OPTIONS (dépréciés).
STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage'},
    'dbbackup': {
        'BACKEND': 'django.core.files.storage.FileSystemStorage',
        'OPTIONS': {'location': str(BACKUP_ROOT)},
    },
}
DBBACKUP_CLEANUP_KEEP = int(os.getenv('BACKUP_KEEP', '30'))        # bases conservées
DBBACKUP_CLEANUP_KEEP_MEDIA = int(os.getenv('BACKUP_KEEP_MEDIA', '10'))
DBBACKUP_FILENAME_TEMPLATE = 'lionsmed-{datetime}.{extension}'
DBBACKUP_MEDIA_FILENAME_TEMPLATE = 'lionsmed-media-{datetime}.{extension}'
DBBACKUP_DATE_FORMAT = '%Y%m%d-%H%M%S'

# django-guardian a été retiré : aucune permission d'objet n'était utilisée dans
# le code (vérifié par recherche sur assign_perm / get_objects_for_user / get_perms).
# Ses tables guardian_* subsistent en base, inertes ; elles pourront être
# supprimées par une migration dédiée après confirmation en production.
