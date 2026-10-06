from django.core.management.base import BaseCommand
from apps.mailboxes.sync import sync_all


class Command(BaseCommand):
    help = ("Relève les boîtes e-mail institutionnelles reliées à Lionsmed et enregistre les nouveaux messages. "
            "Sans effet sur le serveur de messagerie (lecture seule). N'affiche jamais expéditeur, objet ni contenu.")

    def handle(self, *args, **options):
        for key, result in sync_all().items():
            if result["status"] != "inactive":
                self.stdout.write(f"{key}: {result['status']} ({result['imported']} nouveau(x))")
