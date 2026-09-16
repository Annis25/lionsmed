from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("documents", "0001_initial")]

    operations = [
        migrations.RemoveConstraint(model_name="document", name="document_status_valid"),
        migrations.AlterField(
            model_name="document",
            name="status",
            field=models.CharField(
                choices=[
                    ("QUARANTINE", "En quarantaine"),
                    ("AVAILABLE", "Disponible"),
                    ("REJECTED", "Rejeté"),
                    ("DELETED", "Supprimé"),
                ],
                default="QUARANTINE",
                max_length=10,
            ),
        ),
        migrations.AddConstraint(
            model_name="document",
            constraint=models.CheckConstraint(
                condition=models.Q(status__in=["QUARANTINE", "AVAILABLE", "REJECTED", "DELETED"]),
                name="document_status_valid",
            ),
        ),
    ]
