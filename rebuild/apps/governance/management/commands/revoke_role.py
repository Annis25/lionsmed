from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from apps.governance.models import RoleGrant
from apps.governance.services import revoke_role


class Command(BaseCommand):
    help = "Révoquer un grant via le service audité."

    def add_arguments(self, parser):
        parser.add_argument("--actor", required=True)
        parser.add_argument("--grant", required=True, type=int)

    def handle(self, *args, **options):
        try:
            revoke_role(actor=get_user_model().objects.get(pk=options["actor"]), grant=RoleGrant.objects.get(pk=options["grant"]))
        except Exception as error:
            raise CommandError("Révocation refusée.") from error
        self.stdout.write(self.style.SUCCESS("Grant révoqué et audité."))
