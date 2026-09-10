from django.core.management.base import BaseCommand
from django.utils import timezone
from apps.communications.models import OutboxMessage


class Command(BaseCommand):
    help = "Aperçu non destructif de l'état de l'outbox (comptes par état, âge du plus ancien PENDING). Ne montre jamais destinataire, sujet, contenu ni jeton."

    def handle(self, *args, **options):
        counts = {state: OutboxMessage.objects.filter(state=state).count() for state, _ in OutboxMessage._meta.get_field("state").choices}
        oldest_pending = OutboxMessage.objects.filter(state="PENDING").order_by("available_at").values_list("available_at", flat=True).first()
        self.stdout.write(f"PENDING: {counts.get('PENDING', 0)}")
        self.stdout.write(f"SENDING: {counts.get('SENDING', 0)}")
        self.stdout.write(f"SENT: {counts.get('SENT', 0)}")
        self.stdout.write(f"FAILED: {counts.get('FAILED', 0)}")
        if oldest_pending:
            age = timezone.now() - oldest_pending
            self.stdout.write(f"Plus ancien PENDING : {int(age.total_seconds() // 60)} min")
        else:
            self.stdout.write("Plus ancien PENDING : aucun")
