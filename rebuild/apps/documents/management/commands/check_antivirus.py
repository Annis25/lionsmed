from django.core.management.base import BaseCommand, CommandError
from apps.documents.scanning import check_scanner, ScannerUnavailable


class Command(BaseCommand):
    help = "Vérifie ClamAV par PING/VERSION, sans document utilisateur."

    def handle(self, *args, **options):
        try:
            version = check_scanner()
        except ScannerUnavailable as error:
            raise CommandError("Antivirus indisponible : dépôts bloqués (fail-closed).") from error
        self.stdout.write(self.style.SUCCESS(f"Antivirus disponible — {version}"))
