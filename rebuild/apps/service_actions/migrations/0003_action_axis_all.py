from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("service_actions", "0002_action_hours_worked_action_instagram_url")]

    operations = [
        migrations.RemoveConstraint(model_name="action", name="action_axis_valid"),
        migrations.AlterField(
            model_name="action",
            name="axis",
            field=models.CharField(choices=[("TOUT", "Tous les axes"), ("DIABETE", "Diabète"), ("ENVIRONNEMENT", "Environnement"), ("HUMANITAIRE", "Humanitaire"), ("JEUNESSE", "Jeunesse")], max_length=20),
        ),
        migrations.AddConstraint(
            model_name="action",
            constraint=models.CheckConstraint(condition=models.Q(("axis__in", ["TOUT", "DIABETE", "ENVIRONNEMENT", "HUMANITAIRE", "JEUNESSE"])), name="action_axis_valid"),
        ),
    ]
