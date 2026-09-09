from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from django.utils.dateparse import parse_datetime
from django.utils import timezone
from django.db import transaction
from apps.members.models import MemberProfile
from apps.governance.models import Role
from apps.governance.services import grant_role


class Command(BaseCommand):
    help = "Procédure locale technique : accorder un rôle sans modifier les flags Django."

    def add_arguments(self, parser):
        parser.add_argument("--actor", required=True, help="UUID du compte technique")
        parser.add_argument("--user", required=True, help="UUID du compte personnel")
        parser.add_argument("--role", required=True, choices=Role.values)
        parser.add_argument("--ends-at", help="Date ISO avec fuseau ; facultative")

    @transaction.atomic
    def handle(self, *args, **options):
        User = get_user_model()
        try:
            actor = User.objects.get(pk=options["actor"])
            user = User.objects.get(pk=options["user"])
            end = parse_datetime(options["ends_at"]) if options["ends_at"] else None
            if options["ends_at"] and (end is None or timezone.is_naive(end)):
                raise CommandError("Date de fin avec fuseau requise.")
            grant = grant_role(actor=actor, user=user, role=options["role"], ends_at=end)
            MemberProfile.objects.get_or_create(user=user, defaults={"status": "GUEST" if options["role"] == Role.INVITE else "ACTIVE"})
        except CommandError:
            raise
        except Exception as error:
            raise CommandError("Attribution refusée : vérifier les identifiants, dates, chevauchements et droits techniques.") from error
        self.stdout.write(self.style.SUCCESS(f"Grant {grant.pk} créé et audité."))
