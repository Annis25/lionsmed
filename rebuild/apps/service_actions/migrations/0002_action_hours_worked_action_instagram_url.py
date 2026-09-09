from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("service_actions", "0001_initial")]

    operations = [
        migrations.AddField(
            model_name="action",
            name="hours_worked",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="action",
            name="instagram_url",
            field=models.URLField(blank=True, max_length=500),
        ),
    ]
