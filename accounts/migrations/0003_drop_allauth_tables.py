"""Supprime les tables laissées par django-allauth, retiré du projet.

Le paquet n'était utilisé nulle part (aucune URL, aucun template, aucun
fournisseur social) et portait 3 vulnérabilités connues. Retirer une application
d'INSTALLED_APPS ne supprime pas ses tables : elles resteraient en base sans
propriétaire, et leurs migrations resteraient marquées comme appliquées.

Les deux tables concernées étaient vides au moment du retrait (vérifié). La
migration refuse de s'exécuter si ce n'est plus le cas, pour ne jamais détruire
de données silencieusement.

Écrite dans `accounts` faute d'application `account` encore installée.
"""

from django.db import migrations

TABLES = [
    # L'ordre compte : emailconfirmation référence emailaddress.
    'account_emailconfirmation',
    'account_emailaddress',
]


def _table_exists(schema_editor, table):
    return table in schema_editor.connection.introspection.table_names()


def drop_allauth_tables(apps, schema_editor):
    connection = schema_editor.connection
    with connection.cursor() as cursor:
        for table in TABLES:
            if not _table_exists(schema_editor, table):
                continue
            cursor.execute(f'SELECT COUNT(*) FROM "{table}"')
            count = cursor.fetchone()[0]
            if count:
                raise RuntimeError(
                    f"La table {table} contient {count} ligne(s) : suppression "
                    "annulée. Sauvegardez ces données et videz la table avant "
                    "de rejouer cette migration."
                )
            cursor.execute(f'DROP TABLE "{table}"')
        # Les migrations d'allauth ne doivent plus figurer comme appliquées :
        # sinon une réinstallation future les croirait déjà jouées.
        cursor.execute("DELETE FROM django_migrations WHERE app = %s", ['account'])


def restore_not_supported(apps, schema_editor):
    raise RuntimeError(
        "Retour arrière impossible : réinstallez django-allauth et exécutez ses "
        "propres migrations pour recréer ces tables."
    )


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0002_alter_user_photo'),
    ]

    operations = [
        migrations.RunPython(drop_allauth_tables, restore_not_supported),
    ]
