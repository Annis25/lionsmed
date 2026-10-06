from django.core.management.base import BaseCommand
from django.utils import timezone
from apps.mailboxes.access import holders
from apps.mailboxes.catalog import MAILBOXES, is_active
from apps.mailboxes.models import InboundEmail, MailboxState


class Command(BaseCommand):
    help = ("État des boîtes institutionnelles : reliée ou non, dernière synchronisation, nombre de titulaires "
            "et de messages. Ne montre jamais mot de passe, nom, expéditeur, objet ni contenu.")

    def handle(self, *args, **options):
        states = {state.mailbox: state for state in MailboxState.objects.all()}
        for mailbox in MAILBOXES:
            state = states.get(mailbox.key)
            if not is_active(mailbox):
                status = "non reliée (mot de passe absent de la configuration)"
            elif state is None or not state.last_attempt_at:
                status = "reliée, jamais synchronisée"
            elif state.last_error:
                status = f"ERREUR {state.last_error} depuis {state.failures} tentative(s)"
            else:
                minutes = int((timezone.now() - state.last_success_at).total_seconds() // 60)
                status = f"synchronisée il y a {minutes} min"
            self.stdout.write(f"{mailbox.address}: {status} · {len(holders(mailbox))} titulaire(s) · "
                              f"{InboundEmail.objects.filter(mailbox=mailbox.key).count()} message(s)")
