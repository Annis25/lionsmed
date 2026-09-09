from datetime import timedelta
from django.db import transaction
from django.utils import timezone
from django.utils.crypto import salted_hmac
from .models import AuthThrottle


def consume(scope, value, *, limit, seconds):
    """Fenêtre fixe partagée ; sérialise aussi les premiers appels concurrents."""
    key = salted_hmac("lionsmed.auth-throttle", scope + ":" + value, algorithm="sha256").hexdigest()
    with transaction.atomic():
        now = timezone.now()
        AuthThrottle.objects.get_or_create(key=key, defaults={"expires_at": now + timedelta(seconds=seconds)})
        bucket = AuthThrottle.objects.select_for_update().get(pk=key)
        if bucket.expires_at <= now:
            bucket.count = 0
            bucket.expires_at = now + timedelta(seconds=seconds)
        permitted = bucket.count < limit
        if permitted:
            bucket.count += 1
        bucket.save(update_fields=["count", "expires_at"])
    return permitted
