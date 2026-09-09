from django.core.management.commands.migrate import Command as DjangoMigrate
from django.core.management.base import CommandError
from django.db import connections


class Command(DjangoMigrate):
    def handle(self, *args, **options):
        connection = connections[options.get("database", "default")]
        tables = set(connection.introspection.table_names())
        legacy = {"sitecontent_siteconfig", "accounts_membershiprequest", "voting_vote", "events_event", "members_cotisation"}
        if tables & legacy:
            raise CommandError("Tables legacy détectées : migration du nouveau schéma refusée.")
        return super().handle(*args, **options)
