"""Pipeline de reprise legacy → rebuild : extraction (lecture seule), transformation,
validation, import idempotent. Voir docs/MIGRATE_LEGACY_TO_REBUILD.md.

Principes stricts :
- Lecture seule de la source (`sqlite3` ouverte en `mode=ro`, `PRAGMA query_only=ON`).
- Aucune donnée n'est inventée : un champ requis absent du legacy met la ligne en
  QUARANTINE plutôt que de recevoir une valeur devinée.
- Aucune élévation de rôle, aucun mot de passe legacy réutilisé, aucun email envoyé.
- Idempotent via LegacyImportRecord (source, table, legacy_pk) : un deuxième passage sur
  une ligne déjà IMPORTED ne la retouche pas.
"""
import hashlib
import sqlite3
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from apps.core.models import LegacyImportRecord
from apps.accounts.models import normalize_email
from apps.members.models import MemberProfile, MembershipApplication
from apps.service_actions.models import Action
from apps.agenda.models import Event
from apps.dues import services as dues_services
from apps.governance.models import LionsYear

SOURCE = "legacy_sqlite"
TUNIS = ZoneInfo("Africa/Tunis")


@dataclass
class Report:
    table: str
    total: int = 0
    imported: int = 0
    skipped_already_imported: int = 0
    rejected: int = 0
    quarantined: int = 0
    reasons: list = field(default_factory=list)

    def add(self, state, reason=""):
        if state == "IMPORTED":
            self.imported += 1
        elif state == "SKIPPED":
            self.skipped_already_imported += 1
        elif state == "REJECTED":
            self.rejected += 1
            self.reasons.append(reason)
        elif state == "QUARANTINE":
            self.quarantined += 1
            self.reasons.append(reason)


def open_source(path):
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    con.execute("PRAGMA query_only=ON")
    con.row_factory = sqlite3.Row
    return con


def _hash_row(row):
    return hashlib.sha256(repr(sorted(dict(row).items())).encode()).hexdigest()


def _already_imported(table, legacy_pk):
    return LegacyImportRecord.objects.filter(source=SOURCE, table=table, legacy_pk=str(legacy_pk), state=LegacyImportRecord.State.IMPORTED).exists()


def _record(*, batch, table, legacy_pk, state, reason="", target_type="", target_id="", source_hash=""):
    LegacyImportRecord.objects.update_or_create(source=SOURCE, table=table, legacy_pk=str(legacy_pk), defaults={
        "batch": batch, "state": state, "reason": reason[:300], "target_type": target_type,
        "target_id": str(target_id), "source_hash": source_hash})


# ---------------------------------------------------------------------------
# Comptes
# ---------------------------------------------------------------------------

def import_users(con, *, batch, apply):
    """Identité seulement : aucun RoleGrant créé, aucun hash de mot de passe repris.

    Retourne aussi `eligible_pks` : les PK legacy qui passeraient l'import, utilisé en
    dry-run pour prévisualiser les étapes dépendantes (cotisations) sans rien écrire."""
    report = Report("accounts_user")
    eligible_pks = set()
    User = get_user_model()
    for row in con.execute("SELECT * FROM accounts_user ORDER BY id"):
        report.total += 1
        legacy_pk = row["id"]
        if _already_imported("accounts_user", legacy_pk):
            report.add("SKIPPED")
            continue
        email = normalize_email(row["email"] or "")
        if not email:
            report.add("REJECTED", "email absent")
            if apply:
                _record(batch=batch, table="accounts_user", legacy_pk=legacy_pk, state="REJECTED", reason="email absent")
            continue
        if User.objects.filter(email=email).exists():
            report.add("REJECTED", f"email déjà présent dans le nouveau schéma : {email}")
            if apply:
                _record(batch=batch, table="accounts_user", legacy_pk=legacy_pk, state="REJECTED", reason="email déjà présent")
            continue
        if not apply:
            report.add("IMPORTED")  # aperçu dry-run : compte comme importable, rien n'est écrit
            eligible_pks.add(legacy_pk)
            continue
        with transaction.atomic():
            user = User(email=email, first_name=(row["first_name"] or "")[:150], last_name=(row["last_name"] or "")[:150],
                is_active=True, is_staff=False, is_superuser=False)
            user.set_unusable_password()  # jamais de hash legacy repris, jamais de mot de passe temporaire envoyé
            user.full_clean(exclude=["password"])
            user.save()
            status = MemberProfile.Status.ACTIVE if row["is_approved"] else MemberProfile.Status.GUEST
            profile = MemberProfile(user=user, status=status, phone=(row["phone"] or "")[:32], profession=(row["profession"] or "")[:150],
                bio=(row["bio"] or "")[:1000])
            profile.full_clean()
            profile.save()
            _record(batch=batch, table="accounts_user", legacy_pk=legacy_pk, state="IMPORTED",
                reason=f"rôle legacy '{row['role']}' non repris — grant à décider humainement",
                target_type="accounts.User", target_id=user.pk, source_hash=_hash_row(row))
        report.add("IMPORTED")
        eligible_pks.add(legacy_pk)
    return report, eligible_pks


# ---------------------------------------------------------------------------
# Candidatures
# ---------------------------------------------------------------------------

def import_applications(con, *, batch, apply):
    report = Report("accounts_membershiprequest")
    import uuid
    for row in con.execute("SELECT * FROM accounts_membershiprequest ORDER BY id"):
        report.total += 1
        legacy_pk = row["id"]
        if _already_imported("accounts_membershiprequest", legacy_pk):
            report.add("SKIPPED")
            continue
        email = normalize_email(row["email"] or "")
        if not email or not row["motivation"] or not (row["phone"] or "").strip():
            # Le téléphone est désormais obligatoire côté candidature (recette V1) : une
            # candidature legacy qui en est dépourvue n'est jamais complétée artificiellement.
            report.add("REJECTED", "champ obligatoire manquant (email/téléphone/motivation)")
            if apply:
                _record(batch=batch, table="accounts_membershiprequest", legacy_pk=legacy_pk, state="REJECTED", reason="champ obligatoire manquant (email/téléphone/motivation)")
            continue
        if not apply:
            report.add("IMPORTED")
            continue
        with transaction.atomic():
            # Insertion directe (pas le service `submit()`) : aucun OutboxMessage/email pendant l'import.
            application = MembershipApplication(submission_key=uuid.uuid4(), first_name=(row["first_name"] or "")[:150],
                last_name=(row["last_name"] or "")[:150], email=email, phone=(row["phone"] or "")[:32],
                profession=(row["profession"] or "")[:150], motivation=row["motivation"][:5000], origin="",
                state="RECEIVED", notice_version="legacy-import")
            application.full_clean()
            application.save()
            _record(batch=batch, table="accounts_membershiprequest", legacy_pk=legacy_pk, state="IMPORTED",
                reason=f"statut legacy original : {row['status']}", target_type="members.MembershipApplication",
                target_id=application.pk, source_hash=_hash_row(row))
        report.add("IMPORTED")
    return report


# ---------------------------------------------------------------------------
# Actualités — toujours importées en DRAFT : « publié » côté legacy ne vaut pas validation.
# ---------------------------------------------------------------------------

def import_news(con, *, batch, apply, operator):
    """La fonctionnalité Actualités est supprimée du nouveau produit (recette V1) :
    les actualités legacy ne sont jamais importées, seulement déclarées SKIPPED."""
    report = Report("news_article")
    for row in con.execute("SELECT * FROM news_article ORDER BY id"):
        report.total += 1
        legacy_pk = row["id"]
        report.add("SKIPPED")
        if apply and not _already_imported("news_article", legacy_pk):
            _record(batch=batch, table="news_article", legacy_pk=legacy_pk, state="REJECTED",
                reason="fonctionnalité Actualités supprimée du nouveau produit")
    return report


# ---------------------------------------------------------------------------
# Événements — ACTION mis en quarantaine (axe non renseigné côté legacy, jamais deviné).
# REUNION/GALA importés comme Event en DRAFT.
# ---------------------------------------------------------------------------

def import_events(con, *, batch, apply, operator):
    report = Report("events_event")
    for row in con.execute("SELECT * FROM events_event ORDER BY id"):
        report.total += 1
        legacy_pk = row["id"]
        if _already_imported("events_event", legacy_pk):
            report.add("SKIPPED")
            continue
        if row["event_type"] == "ACTION":
            reason = "type ACTION : axe non renseigné dans le legacy, décision humaine requise avant création d'Action"
            report.add("QUARANTINE", reason)
            if apply:
                _record(batch=batch, table="events_event", legacy_pk=legacy_pk, state="QUARANTINE", reason=reason, source_hash=_hash_row(row))
            continue
        if not row["title"] or not row["date_start"]:
            report.add("REJECTED", "titre ou date de début manquant")
            if apply:
                _record(batch=batch, table="events_event", legacy_pk=legacy_pk, state="REJECTED", reason="titre ou date manquant")
            continue
        if not apply:
            report.add("IMPORTED")
            continue
        slug = row["slug"] or f"legacy-{legacy_pk}"
        if Event.objects.filter(slug=slug).exists():
            slug = f"{slug}-legacy-{legacy_pk}"
        starts_at = _parse_datetime(row["date_start"])
        ends_at = _parse_datetime(row["date_end"]) if row["date_end"] else None
        with transaction.atomic():
            event = Event(title=row["title"][:180], slug=slug[:200], summary=(row["description"] or "")[:500],
                body=(row["description"] or "")[:20000], status="DRAFT", starts_at=starts_at, ends_at=ends_at,
                location=(row["location"] or "")[:200], category="REUNION" if row["event_type"] == "REUNION" else "AUTRE",
                visibility="PUBLIC" if row["is_public"] else "PRIVATE", created_by=operator, updated_by=operator)
            event.full_clean()
            event.save()
            _record(batch=batch, table="events_event", legacy_pk=legacy_pk, state="IMPORTED",
                reason=f"type legacy original : {row['event_type']}", target_type="agenda.Event", target_id=event.pk,
                source_hash=_hash_row(row))
        report.add("IMPORTED")
    return report


def _parse_datetime(value):
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            naive = datetime.strptime(value[:19], fmt)
            return naive.replace(tzinfo=TUNIS).astimezone(ZoneInfo("UTC"))
        except ValueError:
            continue
    return None


# ---------------------------------------------------------------------------
# Cotisations — seulement si l'utilisateur est déjà importé ET qu'une Année Lions
# couvrant la période existe déjà (jamais créée automatiquement : calendrier institutionnel
# non confirmé, cf. architecture §9).
# ---------------------------------------------------------------------------

def import_dues(con, *, batch, apply, operator, preview_user_pks=frozenset()):
    report = Report("members_cotisation")
    for row in con.execute("SELECT * FROM members_cotisation ORDER BY id"):
        report.total += 1
        legacy_pk = row["id"]
        if _already_imported("members_cotisation", legacy_pk):
            report.add("SKIPPED")
            continue
        user_record = LegacyImportRecord.objects.filter(source=SOURCE, table="accounts_user", legacy_pk=str(row["member_id"]),
            state=LegacyImportRecord.State.IMPORTED).first()
        user_previewed = not apply and row["member_id"] in preview_user_pks
        if not user_record and not user_previewed:
            reason = "membre associé non importé"
            report.add("QUARANTINE", reason)
            if apply:
                _record(batch=batch, table="members_cotisation", legacy_pk=legacy_pk, state="QUARANTINE", reason=reason)
            continue
        calendar_start = date(row["year"], 1, 1)
        calendar_end = date(row["year"], 12, 31)
        lions_year = LionsYear.objects.filter(starts_on__lte=calendar_start, ends_on__gt=calendar_end).first() \
            or LionsYear.objects.filter(starts_on__lte=calendar_start, ends_on__gt=calendar_start).first()
        if not lions_year:
            reason = f"aucune Année Lions ne couvre l'année calendaire legacy {row['year']} — calendrier institutionnel non confirmé"
            report.add("QUARANTINE", reason)
            if apply:
                _record(batch=batch, table="members_cotisation", legacy_pk=legacy_pk, state="QUARANTINE", reason=reason)
            continue
        if not apply:
            report.add("IMPORTED")
            continue
        with transaction.atomic():
            profile = MemberProfile.objects.get(user_id=user_record.target_id)
            status = "PAID" if row["status"] == "PAID" else "TO_REGULARIZE"
            record = dues_services.ensure_record(actor=operator, profile=profile, lions_year=lions_year)
            dues_services.record_dues_status(actor=operator, record=record, status=status, amount=row["amount"],
                paid_on=row["payment_date"] or None, motif="Import legacy (donnée historique réelle).")
            _record(batch=batch, table="members_cotisation", legacy_pk=legacy_pk, state="IMPORTED",
                target_type="dues.DuesRecord", target_id=record.pk, source_hash=_hash_row(row))
        report.add("IMPORTED")
    return report


PIPELINE = ["users", "applications", "news", "events", "dues"]


def run(path, *, apply, operator=None, batch=None):
    batch = batch or timezone.now().strftime("legacy-%Y%m%dT%H%M%S")
    con = open_source(path)
    try:
        if apply and operator is None:
            raise ValueError("Un opérateur (User technique) est requis pour appliquer l'import.")
        users_report, eligible_user_pks = import_users(con, batch=batch, apply=apply)
        reports = [users_report, import_applications(con, batch=batch, apply=apply)]
        reports.append(import_news(con, batch=batch, apply=apply, operator=operator))
        reports.append(import_events(con, batch=batch, apply=apply, operator=operator))
        reports.append(import_dues(con, batch=batch, apply=apply, operator=operator, preview_user_pks=eligible_user_pks))
        return batch, reports
    finally:
        con.close()
