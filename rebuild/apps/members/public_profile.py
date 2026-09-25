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
        from apps.core.permissions import effective_role
        from apps.governance.models import Role
        profiles = MemberProfile.objects.filter(public_profile_enabled=True, public_slug__isnull=False, user__is_active=True).select_related("user").order_by("public_slug")
        return [p for p in profiles if effective_role(p.user) != Role.SUPER_ADMIN]  # compte technique jamais exposé

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
    from PIL import Image, ImageDraw
    from django.contrib.staticfiles import finders
    # box_size=13 vise ~600px de large (net à l'impression et en zoom) ; l'affichage
    # écran reste petit via CSS (.qr-image, max-width: 300px / 240px mobile).
    img = qrcode.make(url, error_correction=ERROR_CORRECT_H, box_size=13, border=4).convert("RGB")
    logo_path = finders.find("images/qr-logo.png")
    if logo_path:
        logo = Image.open(logo_path).convert("RGBA")
        # Le logo occupe ~15% de la largeur du QR (14-16% cible, 18% au maximum) :
        # identifiable sans entamer la marge de récupération d'ERROR_CORRECT_H (~30%).
        target = max(1, round(img.size[0] * 0.15))
        logo.thumbnail((target, target), Image.LANCZOS)
        pad = max(2, round(target * 0.18))
        plate_w, plate_h = logo.size[0] + pad * 2, logo.size[1] + pad * 2
        mask = Image.new("L", (plate_w, plate_h), 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, plate_w - 1, plate_h - 1), radius=min(plate_w, plate_h) // 4, fill=255)
        plate = Image.new("RGBA", (plate_w, plate_h), (255, 255, 255, 255))
        position = ((img.size[0] - plate_w) // 2, (img.size[1] - plate_h) // 2)
        img.paste(plate, position, mask)
        logo_position = ((img.size[0] - logo.size[0]) // 2, (img.size[1] - logo.size[1]) // 2)
        img.paste(logo, logo_position, mask=logo.split()[3] if logo.mode == "RGBA" else None)
    return img


def qr_png_data_uri(url):
    buffer = io.BytesIO()
    _qr_image(url).save(buffer, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")


def qr_png_bytes(url):
    buffer = io.BytesIO()
    _qr_image(url).save(buffer, format="PNG")
    return buffer.getvalue()
