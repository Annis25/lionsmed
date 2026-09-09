from pathlib import Path
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from apps.core import legacy_pipeline


class Command(BaseCommand):
    help = ("Reprise contrôlée des données legacy utiles (utilisateurs, candidatures, "
        "actualités, événements, cotisations). Lecture seule de la source ; idempotent. "
        "Dry-run par défaut : passer --apply pour écrire.")

    def add_arguments(self, parser):
        parser.add_argument("--source", default=str(Path(__file__).resolve().parents[5] / "db.sqlite3"),
            help="Chemin du db.sqlite3 legacy (lecture seule).")
        parser.add_argument("--apply", action="store_true", help="Écrit réellement les imports (sinon dry-run).")
        parser.add_argument("--operator-email", default="", help="Email du compte technique opérateur (requis avec --apply).")
        parser.add_argument("--batch", default="", help="Identifiant de lot (par défaut : horodatage).")

    def handle(self, *args, **options):
        source = options["source"]
        if not Path(source).exists():
            raise CommandError(f"Source introuvable : {source}")
        operator = None
        if options["apply"]:
            if not options["operator_email"]:
                raise CommandError("--operator-email est requis avec --apply (compte technique traçant l'import).")
            try:
                operator = get_user_model().objects.get(email=options["operator_email"])
            except get_user_model().DoesNotExist:
                raise CommandError("Compte opérateur introuvable.")
        batch, reports = legacy_pipeline.run(source, apply=options["apply"], operator=operator, batch=options["batch"] or None)
        self.stdout.write(f"Lot : {batch} — {'APPLIQUÉ' if options['apply'] else 'DRY-RUN (rien écrit)'}")
        for report in reports:
            self.stdout.write(f"\n{report.table} : source={report.total} importé={report.imported} "
                f"déjà_importé={report.skipped_already_imported} rejeté={report.rejected} quarantaine={report.quarantined}")
            for reason in report.reasons[:20]:
                self.stdout.write(f"  - {reason}")
        if not options["apply"]:
            self.stdout.write("\nAucune écriture effectuée. Relancer avec --apply --operator-email=... pour importer réellement.")
