from django.db import migrations, models
import django.db.models.deletion


def populate_years(apps, schema_editor):
    AssociationExperience = apps.get_model("members", "AssociationExperience")
    for row in AssociationExperience.objects.all():
        row.start_year = row.starts_on.year
        row.end_year = row.ends_on.year if row.ends_on else None
        row.save(update_fields=["start_year", "end_year"])


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("members", "0004_alter_membershipapplication_phone"),
    ]

    operations = [
        migrations.AddField(
            model_name="memberprofile",
            name="public_profile_enabled",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="memberprofile",
            name="public_slug",
            field=models.SlugField(max_length=160, null=True, blank=True, unique=True),
        ),
        migrations.AddField(
            model_name="associationexperience",
            name="start_year",
            field=models.PositiveSmallIntegerField(null=True, help_text="Année de début"),
        ),
        migrations.AddField(
            model_name="associationexperience",
            name="end_year",
            field=models.PositiveSmallIntegerField(null=True, blank=True, help_text="Année de fin, vide si poste actuel"),
        ),
        migrations.RunPython(populate_years, noop),
        migrations.RemoveConstraint(model_name="associationexperience", name="experience_dates_ordered"),
        migrations.RemoveConstraint(model_name="associationexperience", name="experience_month_precision"),
        migrations.AlterField(
            model_name="associationexperience",
            name="start_year",
            field=models.PositiveSmallIntegerField(help_text="Année de début"),
        ),
        migrations.RemoveField(model_name="associationexperience", name="starts_on"),
        migrations.RemoveField(model_name="associationexperience", name="ends_on"),
        migrations.AlterModelOptions(
            name="associationexperience",
            options={"ordering": ["-start_year", "id"]},
        ),
        migrations.AddConstraint(
            model_name="associationexperience",
            constraint=models.CheckConstraint(
                condition=models.Q(("end_year__isnull", True)) | models.Q(("end_year__gte", models.F("start_year"))),
                name="experience_years_ordered",
            ),
        ),
    ]
