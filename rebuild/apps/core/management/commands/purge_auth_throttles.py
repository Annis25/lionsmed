from django.core.management.base import BaseCommand
from django.utils import timezone
from apps.core.models import AuthThrottle


class Command(BaseCommand):
    help = "Purger les compteurs expirés (sans dépendance à un scheduler pour leur expiration)."

    def handle(self, *args, **options):
        count, _ = AuthThrottle.objects.filter(expires_at__lt=timezone.now()).delete()
        self.stdout.write(f"{count} compteurs expirés supprimés.")
