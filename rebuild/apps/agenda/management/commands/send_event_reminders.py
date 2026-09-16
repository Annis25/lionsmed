from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from apps.agenda.models import Event
from apps.communications.services import broadcast_recipients, notify
from apps.core.permissions import can


class Command(BaseCommand):
    help = "Crée les rappels J-7/J-1 pour tous les membres actifs concernés, quelle que soit leur réponse RSVP."

    def handle(self, *args, **options):
        today = timezone.localdate()
        created = 0
        for offset, tag in ((7, "J7"), (1, "J1")):
            target = today + timedelta(days=offset)
            for event in Event.objects.filter(status="PUBLISHED", starts_at__date=target):
                # La version dérive de la dernière modification : une replanification change la clé, donc le rappel.
                version = int(event.updated_at.timestamp())
                for recipient in broadcast_recipients():
                    if not can(recipient, "event.register", event):
                        continue
                    key = f"event_reminder:{event.pk}:{recipient.pk}:{version}:{tag}"
                    notify(recipient=recipient, category="EVENT", title=f"Rappel — {event.title}",
                        excerpt=f"Rendez-vous le {timezone.localtime(event.starts_at):%d/%m/%Y à %H:%M}.",
                        event_key=key, target_kind="event", target_id=event.pk, email=True)
                    created += 1
        self.stdout.write(f"{created} rappels traités.")
