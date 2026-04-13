from functools import wraps

from django.contrib import messages
from django.contrib.auth import logout
from django.shortcuts import redirect


def approved_required(view_func):
    """Exige un compte approuvé et actif à *chaque* requête.

    Le contrôle fait au moment de la connexion ne suffit pas : une session déjà
    ouverte survit à la révocation de `is_approved` ou `is_active`. On coupe donc
    la session en cours plutôt que de renvoyer un refus silencieux, pour que le
    membre comprenne pourquoi il perd l'accès.
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        user = request.user
        if user.is_superuser:
            return view_func(request, *args, **kwargs)
        if not user.is_active:
            logout(request)
            messages.error(
                request,
                "Votre compte a été désactivé. Contactez le secrétariat du club."
            )
            return redirect('login')
        if not user.is_approved:
            logout(request)
            messages.error(
                request,
                "Votre compte n'est plus approuvé. Contactez le secrétariat du club."
            )
            return redirect('login')
        return view_func(request, *args, **kwargs)
    return wrapper
