from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("communications", "0003_alter_notification_category_alter_outboxmessage_kind")]

    operations = [
        migrations.AddField(
            model_name="contactrequest",
            name="phone",
            field=models.CharField(blank=True, max_length=32),
        ),
    ]
