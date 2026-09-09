import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("governance", "0003_remove_rolegrant_grant_role_valid_and_more"),
        ("dues", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RemoveConstraint(model_name="duesrecord", name="dues_status_valid"),
        migrations.RemoveConstraint(model_name="duesrecord", name="dues_amount_non_negative"),
        migrations.RemoveField(model_name="duesrecord", name="status"),
        migrations.RemoveField(model_name="duesrecord", name="amount"),
        migrations.RemoveField(model_name="duesrecord", name="currency"),
        migrations.RemoveField(model_name="duesrecord", name="paid_on"),
        migrations.AddField(model_name="duesrecord", name="tranche1_paid", field=models.BooleanField(default=False)),
        migrations.AddField(model_name="duesrecord", name="tranche1_paid_on", field=models.DateField(blank=True, null=True)),
        migrations.AddField(model_name="duesrecord", name="tranche2_paid", field=models.BooleanField(default=False)),
        migrations.AddField(model_name="duesrecord", name="tranche2_paid_on", field=models.DateField(blank=True, null=True)),
        migrations.RemoveField(model_name="dueschange", name="old_status"),
        migrations.RemoveField(model_name="dueschange", name="new_status"),
        migrations.RemoveField(model_name="dueschange", name="old_amount"),
        migrations.RemoveField(model_name="dueschange", name="new_amount"),
        migrations.AlterField(model_name="dueschange", name="motif", field=models.CharField(blank=True, max_length=300)),
        migrations.AddField(model_name="dueschange", name="tranche", field=models.PositiveSmallIntegerField(default=1), preserve_default=False),
        migrations.AddField(model_name="dueschange", name="old_paid", field=models.BooleanField(default=False), preserve_default=False),
        migrations.AddField(model_name="dueschange", name="new_paid", field=models.BooleanField(default=False), preserve_default=False),
        migrations.AddConstraint(model_name="dueschange", constraint=models.CheckConstraint(condition=models.Q(("tranche__in", [1, 2])), name="dues_change_tranche_valid")),
        migrations.CreateModel(
            name="DuesSchedule",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("tranche1_amount", models.DecimalField(blank=True, decimal_places=2, help_text="Montant de la tranche 1 (6 premiers mois), en TND — laissé vide tant qu'il n'est pas fixé.", max_digits=8, null=True)),
                ("tranche2_amount", models.DecimalField(blank=True, decimal_places=2, help_text="Montant de la tranche 2 (6 derniers mois), en TND — laissé vide tant qu'il n'est pas fixé.", max_digits=8, null=True)),
                ("currency", models.CharField(default="TND", max_length=3)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("lions_year", models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name="dues_schedule", to="governance.lionsyear")),
                ("updated_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="dues_schedules_updated", to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.AddConstraint(model_name="duesschedule", constraint=models.CheckConstraint(condition=models.Q(("tranche1_amount__isnull", True)) | models.Q(("tranche1_amount__gte", 0)), name="dues_schedule_t1_non_negative")),
        migrations.AddConstraint(model_name="duesschedule", constraint=models.CheckConstraint(condition=models.Q(("tranche2_amount__isnull", True)) | models.Q(("tranche2_amount__gte", 0)), name="dues_schedule_t2_non_negative")),
    ]
