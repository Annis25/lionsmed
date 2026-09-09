# Generated manually from the audited model change; no production database is touched here.
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("communications", "0004_contactrequest_phone"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="MemberEmailCampaign",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("idempotency_key", models.UUIDField(unique=True)),
                ("subject", models.CharField(max_length=180)),
                ("body", models.TextField(max_length=8000)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("status", models.CharField(choices=[("QUEUED", "En attente d'envoi"), ("SENT", "Envoyée"), ("PARTIAL", "Envoi partiel")], default="QUEUED", max_length=8)),
                ("recipient_count", models.PositiveIntegerField(default=0)),
                ("queued_count", models.PositiveIntegerField(default=0)),
                ("sent_count", models.PositiveIntegerField(default=0)),
                ("failed_count", models.PositiveIntegerField(default=0)),
                ("sent_at", models.DateTimeField(blank=True, null=True)),
                ("created_by", models.ForeignKey(on_delete=models.deletion.PROTECT, related_name="member_email_campaigns", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-created_at", "id"]},
        ),
        migrations.AlterField(
            model_name="outboxmessage",
            name="kind",
            field=models.CharField(choices=[("APPLICATION", "Accusé candidature"), ("CONTACT", "Avis contact interne"), ("EVENT_REMINDER", "Rappel de rendez-vous"), ("IMPORTANT", "Notification importante"), ("DOCUMENT", "Nouveau document"), ("VOTE_OPENED", "Ouverture d'un vote"), ("VOTE_RESULTS", "Résultats d'un vote"), ("SATISFACTION_OPENED", "Ouverture satisfaction"), ("MEMBER_BROADCAST", "Communication aux membres")], max_length=20),
        ),
    ]
