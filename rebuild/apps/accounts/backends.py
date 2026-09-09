from django.contrib.auth.backends import ModelBackend


class EmailBackend(ModelBackend):
    """ModelBackend s'appuie sur get_by_natural_key normalisé du UserManager."""
