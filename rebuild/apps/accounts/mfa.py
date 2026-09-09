"""MFA (TOTP) pour les comptes à capacités sensibles — via django-otp, maintenu,
pas de TOTP artisanal. Périmètre : SUPER_ADMIN/PRESIDENT/SECRETAIRE (capacité
`mfa.manage_own`). Récupération contrôlée par codes statiques à usage unique
(otp_static), jamais par contournement silencieux."""
import base64
from urllib.parse import quote
from django_otp import match_token
from django_otp.plugins.otp_totp.models import TOTPDevice
from django_otp.plugins.otp_static.models import StaticDevice, StaticToken
from django.core.exceptions import ValidationError
from apps.core.models import AuditEvent

ISSUER = "Lions Club Sfax-Méditerranée"


def has_confirmed_device(user):
    return TOTPDevice.objects.filter(user=user, confirmed=True).exists()


def get_or_create_pending_device(user):
    device = TOTPDevice.objects.filter(user=user, confirmed=False).order_by("-id").first()
    if device:
        return device
    return TOTPDevice.objects.create(user=user, name="default", confirmed=False)


def base32_secret(device):
    return base64.b32encode(device.bin_key).decode().rstrip("=")


def provisioning_uri(device, email):
    secret = base32_secret(device)
    label = quote(f"{ISSUER}:{email}")
    return f"otpauth://totp/{label}?secret={secret}&issuer={quote(ISSUER)}&algorithm=SHA1&digits=6&period=30"


def qr_data_uri(uri):
    import qrcode
    from io import BytesIO
    image = qrcode.make(uri)
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode()


def generate_recovery_codes(user):
    """Remplace les codes existants : anciens codes non montrés à nouveau, jamais réutilisables."""
    StaticDevice.objects.filter(user=user).delete()
    static = StaticDevice.objects.create(user=user, name="recovery")
    codes = []
    for _ in range(10):
        token = StaticToken.random_token()
        StaticToken.objects.create(device=static, token=token)
        codes.append(token)
    return codes


def confirm_device(*, user, device, token):
    if not device.verify_token(token):
        raise ValidationError("Code invalide.")
    device.confirmed = True
    device.save()
    AuditEvent.objects.create(actor=user, action="mfa.enabled", object_type="TOTPDevice", object_id=str(device.pk))
    return generate_recovery_codes(user)


def verify_login_token(user, token):
    """Accepte un code TOTP courant ou un code de récupération à usage unique."""
    return match_token(user, token) is not None


def disable(*, user, actor=None):
    TOTPDevice.objects.filter(user=user).delete()
    StaticDevice.objects.filter(user=user).delete()
    AuditEvent.objects.create(actor=actor or user, action="mfa.disabled", object_type="User", object_id=str(user.pk))
