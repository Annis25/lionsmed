from .models import SiteConfig


def site_config(request):
    """Expose la configuration du site à tous les templates (footer, navbar, etc.)."""
    return {'config': SiteConfig.get_config()}
