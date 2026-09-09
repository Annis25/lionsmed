import sqlite3
import tempfile
from pathlib import Path
from django.test import TestCase
from django.utils import timezone
from apps.core.tests.test_foundations import account
from apps.core.models import LegacyImportRecord
from apps.core import legacy_pipeline
from apps.governance.models import Role, LionsYear
from apps.members.models import MembershipApplication
from apps.agenda.models import Event
from apps.dues.models import DuesRecord

SCHEMA = """
CREATE TABLE accounts_user (id INTEGER PRIMARY KEY, email TEXT, first_name TEXT, last_name TEXT,
    role TEXT, phone TEXT, bio TEXT, profession TEXT, is_approved INTEGER);
CREATE TABLE accounts_membershiprequest (id INTEGER PRIMARY KEY, first_name TEXT, last_name TEXT,
    email TEXT, phone TEXT, profession TEXT, motivation TEXT, status TEXT);
CREATE TABLE news_category (id INTEGER PRIMARY KEY, name TEXT);
CREATE TABLE news_article (id INTEGER PRIMARY KEY, title TEXT, slug TEXT, content TEXT, excerpt TEXT,
    status TEXT, category_id INTEGER);
CREATE TABLE events_event (id INTEGER PRIMARY KEY, title TEXT, slug TEXT, description TEXT,
    event_type TEXT, date_start TEXT, date_end TEXT, location TEXT, is_public INTEGER);
CREATE TABLE members_cotisation (id INTEGER PRIMARY KEY, year INTEGER, amount REAL, status TEXT,
    payment_date TEXT, notes TEXT, member_id INTEGER);
"""


def build_source(tmp_path):
    con = sqlite3.connect(tmp_path)
    con.executescript(SCHEMA)
    con.executemany("INSERT INTO accounts_user VALUES (?,?,?,?,?,?,?,?,?)", [
        (1, "Real@Example.invalid", "Prénom", "Nom", "PRESIDENT", "20000000", "Bio", "Profession", 1),
        (2, "", "Sans", "Email", "MEMBRE", "", "", "", 0),  # rejeté : email absent
        (3, "comite@example.invalid", "C", "C", "COMITE", "", "", "", 1),  # rôle inconnu : identité importée, aucun grant
    ])
    con.executemany("INSERT INTO accounts_membershiprequest VALUES (?,?,?,?,?,?,?,?)", [
        (1, "App", "Licant", "applicant@example.invalid", "20000001", "", "Motivation réelle", "PENDING"),
    ])
    con.execute("INSERT INTO news_category VALUES (1, 'Vie du club')")
    con.executemany("INSERT INTO news_article VALUES (?,?,?,?,?,?,?)", [
        (1, "Titre article", "titre-article", "Contenu réel", "Résumé", "PUBLISHED", 1),
    ])
    con.executemany("INSERT INTO events_event VALUES (?,?,?,?,?,?,?,?,?)", [
        (1, "Réunion mensuelle", "reunion-mensuelle", "Description", "REUNION", "2026-01-10 18:00:00", None, "Local", 0),
        (2, "Action solidaire", "action-solidaire", "Description", "ACTION", "2026-01-05 09:00:00", None, "Terrain", 1),
    ])
    con.executemany("INSERT INTO members_cotisation VALUES (?,?,?,?,?,?,?)", [
        (1, 2025, 120.0, "PAID", "2025-03-01", "", 1),
        (2, 2025, 120.0, "OVERDUE", None, "", 2),  # membre rejeté (email absent) : quarantaine attendue
    ])
    con.commit()
    con.close()


class LegacyPipelineTests(TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.source = str(Path(self.tmpdir.name) / "legacy.sqlite3")
        build_source(self.source)
        self.operator = account("operator@example.invalid", role=Role.SUPER_ADMIN)

    def test_dry_run_writes_nothing(self):
        batch, reports = legacy_pipeline.run(self.source, apply=False)
        self.assertEqual(LegacyImportRecord.objects.count(), 0)
        by_table = {r.table: r for r in reports}
        self.assertEqual(by_table["accounts_user"].imported, 2)  # ligne 2 rejetée (email absent)
        self.assertEqual(by_table["accounts_user"].rejected, 1)
        self.assertEqual(by_table["events_event"].quarantined, 1)  # la ligne ACTION

    def test_apply_imports_expected_rows_without_inventing_axis(self):
        batch, reports = legacy_pipeline.run(self.source, apply=True, operator=self.operator)
        self.assertEqual(get_user_count(), 2)  # opérateur + les 2 users valides ? voir assert précis ci-dessous
        by_table = {r.table: r for r in reports}
        self.assertEqual(by_table["accounts_user"].imported, 2)
        self.assertEqual(by_table["accounts_user"].rejected, 1)
        self.assertEqual(by_table["accounts_membershiprequest"].imported, 1)
        self.assertEqual(MembershipApplication.objects.count(), 1)
        self.assertEqual(by_table["events_event"].imported, 1)  # seule la REUNION
        self.assertEqual(by_table["events_event"].quarantined, 1)  # l'ACTION, axe non inventé
        event = Event.objects.get()
        self.assertEqual(event.status, "DRAFT")
        from apps.service_actions.models import Action
        self.assertEqual(Action.objects.count(), 0)  # aucune Action devinée depuis l'ACTION legacy

    def test_no_role_is_granted_and_no_password_reused(self):
        legacy_pipeline.run(self.source, apply=True, operator=self.operator)
        from django.contrib.auth import get_user_model
        from apps.governance.models import RoleGrant
        president_legacy = get_user_model().objects.get(email="real@example.invalid")
        self.assertFalse(RoleGrant.objects.filter(user=president_legacy).exists())
        self.assertFalse(president_legacy.has_usable_password())

    def test_unmapped_role_still_imports_identity_quarantines_no_privilege(self):
        legacy_pipeline.run(self.source, apply=True, operator=self.operator)
        from django.contrib.auth import get_user_model
        comite_user = get_user_model().objects.get(email="comite@example.invalid")
        record = LegacyImportRecord.objects.get(table="accounts_user", legacy_pk="3")
        self.assertEqual(record.state, "IMPORTED")
        self.assertIn("COMITE", record.reason)
        from apps.governance.models import RoleGrant
        self.assertFalse(RoleGrant.objects.filter(user=comite_user).exists())

    def test_dues_quarantined_without_confirmed_lions_year(self):
        batch, reports = legacy_pipeline.run(self.source, apply=True, operator=self.operator)
        by_table = {r.table: r for r in reports}
        self.assertEqual(DuesRecord.objects.count(), 0)
        self.assertEqual(by_table["members_cotisation"].quarantined, 2)

    def test_dues_imported_once_lions_year_confirmed(self):
        legacy_pipeline.run(self.source, apply=True, operator=self.operator)  # 1er passage : quarantaine
        LionsYear.objects.create(starts_on=timezone.datetime(2025, 1, 1).date(), ends_on=timezone.datetime(2026, 1, 1).date())
        batch, reports = legacy_pipeline.run(self.source, apply=True, operator=self.operator, batch="second-pass")
        by_table = {r.table: r for r in reports}
        self.assertEqual(by_table["members_cotisation"].imported, 1)  # le membre valide, une fois l'année confirmée
        self.assertEqual(DuesRecord.objects.count(), 1)
        record = DuesRecord.objects.get()
        self.assertEqual(float(record.amount), 120.0)  # montant réel repris, jamais inventé

    def test_rerun_is_idempotent_no_duplicates(self):
        legacy_pipeline.run(self.source, apply=True, operator=self.operator)
        first_events = Event.objects.count()
        first_applications = MembershipApplication.objects.count()
        batch, reports = legacy_pipeline.run(self.source, apply=True, operator=self.operator, batch="rerun")
        by_table = {r.table: r for r in reports}
        self.assertEqual(by_table["accounts_user"].skipped_already_imported, 2)
        self.assertEqual(Event.objects.count(), first_events)
        self.assertEqual(MembershipApplication.objects.count(), first_applications)

    def test_legacy_application_without_phone_is_rejected_not_completed(self):
        con = sqlite3.connect(self.source)
        con.execute("INSERT INTO accounts_membershiprequest VALUES (2,'Sans','Tel','sanstel@example.invalid','','','Motivation réelle','PENDING')")
        con.commit();con.close()
        batch, reports = legacy_pipeline.run(self.source, apply=True, operator=self.operator)
        by_table = {r.table: r for r in reports}
        self.assertEqual(by_table["accounts_membershiprequest"].imported, 1)
        self.assertEqual(by_table["accounts_membershiprequest"].rejected, 1)
        self.assertFalse(MembershipApplication.objects.filter(email="sanstel@example.invalid").exists())

    def test_legacy_news_never_imported(self):
        batch, reports = legacy_pipeline.run(self.source, apply=True, operator=self.operator)
        by_table = {r.table: r for r in reports}
        self.assertEqual(by_table["news_article"].imported, 0)
        self.assertEqual(by_table["news_article"].skipped_already_imported, 1)
        record = LegacyImportRecord.objects.get(table="news_article", legacy_pk="1")
        self.assertIn("supprimée", record.reason)

    def test_no_email_sent_during_import(self):
        from apps.communications.models import OutboxMessage
        legacy_pipeline.run(self.source, apply=True, operator=self.operator)
        self.assertEqual(OutboxMessage.objects.count(), 0)


def get_user_count():
    from django.contrib.auth import get_user_model
    return get_user_model().objects.filter(email__in=["real@example.invalid", "comite@example.invalid"]).count()
