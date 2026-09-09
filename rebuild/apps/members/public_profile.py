"""Profil public membre (recette V1) : slug stable, jamais réattribué, jamais de
coordonnées exposées. Le slug n'est généré qu'à la première activation et n'est
ensuite jamais recalculé automatiquement, même si le nom change."""
import base64
import io
from django.conf import settings
from django.contrib.sitemaps import Sitemap
from django.utils.text import slugify
from .models import MemberProfile


def ensure_public_slug(profile):
    """Idempotent : ne touche jamais un slug déjà attribué."""
    if profile.public_slug:
        return profile.public_slug
    base = slugify(f"{profile.user.first_name} {profile.user.last_name}")[:150] or "membre"
    slug = base
    suffix = 2
    while MemberProfile.objects.exclude(pk=profile.pk).filter(public_slug=slug).exists():
        slug = f"{base}-{suffix}"[:160]
        suffix += 1
    profile.public_slug = slug
    return slug


def public_profile_url(profile):
    return settings.SITE_ORIGIN + f"/membres/{profile.public_slug}/"


class MemberProfileSitemap(Sitemap):
    """Seuls les profils publics activés apparaissent, jamais un profil désactivé."""
    def items(self):
        if not settings.PUBLIC_INDEXING_ENABLED: return []
        return MemberProfile.objects.filter(public_profile_enabled=True, public_slug__isnull=False, user__is_active=True).order_by("public_slug")

    def location(self, profile):
        return f"/membres/{profile.public_slug}/"

    def lastmod(self, profile):
        return profile.updated_at

    def get_urls(self, page=1, site=None, protocol=None):
        from urllib.parse import urlsplit
        from types import SimpleNamespace
        origin = urlsplit(settings.SITE_ORIGIN)
        return super().get_urls(page, SimpleNamespace(domain=origin.netloc, name=origin.netloc), origin.scheme)


def _qr_image(url):
    import qrcode
    from qrcode.constants import ERROR_CORRECT_H
    from PIL import Image
    from django.contrib.staticfiles import finders
    img = qrcode.make(url, error_correction=ERROR_CORRECT_H, box_size=10, border=4).convert("RGB")
    logo_path = finders.find("images/qr-logo.png")
    if logo_path:
        logo = Image.open(logo_path).convert("RGBA")
        # Le logo occupe environ 20% de la largeur : assez petit pour ne pas casser
        # la lecture d'un code protégé par une correction d'erreur élevée (~30%).
        target = img.size[0] // 5
        logo.thumbnail((target, target))
        position = ((img.size[0] - logo.size[0]) // 2, (img.size[1] - logo.size[1]) // 2)
        background = Image.new("RGB", logo.size, "white")
        background.paste(logo, mask=logo.split()[3] if logo.mode == "RGBA" else None)
        img.paste(background, position)
    return img


def qr_png_data_uri(url):
    buffer = io.BytesIO()
    _qr_image(url).save(buffer, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")


def qr_png_bytes(url):
    buffer = io.BytesIO()
    _qr_image(url).save(buffer, format="PNG")
    return buffer.getvalue()
