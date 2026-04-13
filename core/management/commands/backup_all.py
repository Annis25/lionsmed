"""Sauvegarde complète : base de données + media/ + private_media/.

`mediabackup` de django-dbbackup ne couvre que MEDIA_ROOT. Les documents
internes du club vivent dans PRIVATE_MEDIA_ROOT (hors de MEDIA_ROOT depuis la
correction B1) et seraient donc absents d'une sauvegarde standard. Cette commande
enchaîne les trois volets et échoue franchement si l'un d'eux ne passe pas.
"""

import tarfile
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Sauvegarde la base, les médias publics et les documents privés."

    def add_arguments(self, parser):
        parser.add_argument(
            '--no-cleanup', action='store_true',
            help="Conserve toutes les sauvegardes au lieu d'appliquer la rétention.",
        )
        parser.add_argument(
            '--quiet', action='store_true',
            help="Réduit la sortie (utile en tâche planifiée).",
        )

    def handle(self, *args, **options):
        quiet = options['quiet']
        backup_root = Path(settings.BACKUP_ROOT)
        stamp = datetime.now().strftime(settings.DBBACKUP_DATE_FORMAT)
        produced = []

        def log(message, style=None):
            if not quiet:
                self.stdout.write(style(message) if style else message)

        # 1. Base de données
        try:
            call_command('dbbackup', '--noinput', verbosity=0 if quiet else 1)
        except Exception as exc:
            raise CommandError(f"Échec de la sauvegarde de la base : {exc}")
        log('Base de données sauvegardée.', self.style.SUCCESS)

        # 2. Médias publics (images d'événements, d'articles, photos de profil)
        media_root = Path(settings.MEDIA_ROOT)
        if media_root.exists() and any(media_root.iterdir()):
            try:
                call_command('mediabackup', '--noinput', verbosity=0 if quiet else 1)
            except Exception as exc:
                raise CommandError(f"Échec de la sauvegarde des médias : {exc}")
            log('Médias publics sauvegardés.', self.style.SUCCESS)
        else:
            log('Médias publics : dossier vide, ignoré.', self.style.WARNING)

        # 3. Documents privés — archivés à part, car hors du périmètre de dbbackup
        private_root = Path(settings.PRIVATE_MEDIA_ROOT)
        if private_root.exists() and any(private_root.rglob('*')):
            archive = backup_root / f'lionsmed-private-{stamp}.tar.gz'
            try:
                with tarfile.open(archive, 'w:gz') as tar:
                    tar.add(private_root, arcname='private_media')
            except Exception as exc:
                raise CommandError(f"Échec de l'archivage des documents privés : {exc}")
            produced.append(archive)
            log(f'Documents privés archivés : {archive.name}', self.style.SUCCESS)
        else:
            log('Documents privés : dossier vide, ignoré.', self.style.WARNING)

        # 4. Rétention
        if not options['no_cleanup']:
            try:
                call_command('dbbackup', '--clean', '--noinput', verbosity=0)
            except Exception:
                # La rétention est secondaire : son échec ne doit pas faire
                # passer une sauvegarde réussie pour un échec.
                log("Nettoyage des anciennes sauvegardes impossible.", self.style.WARNING)
            self._cleanup_private_archives(backup_root, log)

        log(f'\nSauvegarde terminée dans {backup_root}', self.style.SUCCESS)

    def _cleanup_private_archives(self, backup_root, log):
        keep = settings.DBBACKUP_CLEANUP_KEEP_MEDIA
        archives = sorted(
            backup_root.glob('lionsmed-private-*.tar.gz'),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        for old in archives[keep:]:
            old.unlink()
            log(f'Archive privée ancienne supprimée : {old.name}')
