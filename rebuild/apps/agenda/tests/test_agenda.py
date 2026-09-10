from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import connections, IntegrityError
from django.test import TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone
from apps.core.tests.test_foundations import account
from apps.core.permissions import can
from apps.governance.models import Role
from apps.editorial.publication import publish_content
from .. import services
from ..models import Event, Registration, Attendance
from ..selectors import upcoming_events, own_registration
from apps.members.models import MemberProfile


def event(actor, **kwargs):
    data = dict(title="Réunion synthétique", slug="reunion-"+str(timezone.now().timestamp()).replace(".", ""),
        summary="Résumé", body="Récit", created_by=actor, updated_by=actor,
        starts_at=timezone.now()+timedelta(days=3), ends_at=timezone.now()+timedelta(days=3, hours=2),
        location="Local du club", visibility="PRIVATE", registration_enabled=True)
    data.update(kwargs)
    obj = Event.objects.create(**data)
    return publish_content(actor=actor, obj=obj, kind="event")


class RegistrationTests(TestCase):
    def setUp(self):
        self.president = account("president@example.invalid", role=Role.PRESIDENT)
        self.member = account("member@example.invalid", role=Role.MEMBRE)
        self.invite = account("guest@example.invalid", role=Role.INVITE)
        self.event = event(self.president)

    def test_private_event_visible_in_member_calendar(self):
        self.assertIn(self.event, list(upcoming_events(self.member)))

    def test_invite_cannot_register(self):
        with self.assertRaises(PermissionDenied):
            services.set_registration(actor=self.invite, event=self.event, status=Registration.Status.CONFIRMED)
        self.assertFalse(can(self.invite, "event.register"))

    def test_confirm_then_cancel_round_trip(self):
        registration = services.set_registration(actor=self.member, event=self.event, status=Registration.Status.CONFIRMED)
        self.assertEqual(registration.status, Registration.Status.CONFIRMED)
        self.assertEqual(own_registration(self.member, self.event).status, Registration.Status.CONFIRMED)
        services.set_registration(actor=self.member, event=self.event, status=Registration.Status.CANCELLED)
        self.assertEqual(own_registration(self.member, self.event).status, Registration.Status.CANCELLED)

    def test_registration_requires_registration_enabled(self):
        closed = event(self.president, slug="ferme", registration_enabled=False)
        with self.assertRaises(ValidationError):
            services.set_registration(actor=self.member, event=closed, status=Registration.Status.CONFIRMED)

    def test_rsvp_view_is_scoped_to_own_profile(self):
        other = account("other-member@example.invalid", role=Role.MEMBRE)
        self.client.force_login(self.member)
        self.client.post(reverse("agenda_private:rsvp", args=[self.event.pk]), {"action": "confirm"})
        self.client.force_login(other)
        self.client.post(reverse("agenda_private:rsvp", args=[self.event.pk]), {"action": "confirm"})
        self.assertEqual(own_registration(self.member, self.event).status, Registration.Status.CONFIRMED)
        self.assertEqual(own_registration(other, self.event).status, Registration.Status.CONFIRMED)
        self.assertEqual(Registration.objects.filter(event=self.event).count(), 2)

    def test_rsvp_confirmation_does_not_create_attendance(self):
        """RSVP != présence : confirmer une inscription ne renseigne jamais Attendance."""
        services.set_registration(actor=self.member, event=self.event, status=Registration.Status.CONFIRMED)
        self.assertFalse(Attendance.objects.filter(event=self.event, profile=self.member.member_profile).exists())


class AttendanceTests(TestCase):
    def setUp(self):
        self.president = account("president@example.invalid", role=Role.PRESIDENT)
        self.member = account("member@example.invalid", role=Role.MEMBRE)
        self.bureau = account("bureau@example.invalid", role=Role.BUREAU)
        self.event = event(self.president)

    def test_bureau_cannot_record_attendance(self):
        with self.assertRaises(PermissionDenied):
            services.record_attendance(actor=self.bureau, event=self.event, profile=self.member.member_profile, status="PRESENT")

    def test_president_records_attendance(self):
        attendance = services.record_attendance(actor=self.president, event=self.event, profile=self.member.member_profile, status="EXCUSED", note="Voyage")
        self.assertEqual(attendance.status, "EXCUSED")
        self.assertEqual(attendance.recorded_by, self.president)

    def test_missing_row_is_not_recorded_absent(self):
        """Absence de ligne Attendance = non renseigné, jamais ABSENT implicite."""
        self.assertIsNone(Attendance.objects.filter(event=self.event, profile=self.member.member_profile).first())

    def test_attendance_view_requires_capability(self):
        self.client.force_login(self.member)
        response = self.client.get(reverse("agenda_private:attendance_sheet", args=[self.event.pk]))
        self.assertEqual(response.status_code, 403)


class CapacityConcurrencyTests(TransactionTestCase):
    def test_last_seat_is_awarded_exactly_once(self):
        president = account("president@example.invalid", role=Role.PRESIDENT)
        rendezvous = event(president, slug="capacite", capacity=1)
        first = account("first@example.invalid", role=Role.MEMBRE)
        second = account("second@example.invalid", role=Role.MEMBRE)

        def attempt(user):
            try:
                services.set_registration(actor=user, event=rendezvous, status=Registration.Status.CONFIRMED)
                return True
            except ValidationError:
                return False
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(attempt, [first, second]))
        self.assertEqual(sum(results), 1)
        self.assertEqual(Registration.objects.filter(event=rendezvous, status=Registration.Status.CONFIRMED).count(), 1)


class CalendarQuickAddTests(TestCase):
    def setUp(self):
        self.president = account("president-cal@example.invalid", role=Role.PRESIDENT)
        self.member = account("member-cal@example.invalid", role=Role.MEMBRE)
        self.bureau = account("bureau-cal@example.invalid", role=Role.BUREAU)

    def test_authorized_member_can_create_event(self):
        created = services.create_calendar_event(actor=self.president, title="Réunion mensuelle",
            description="Ordre du jour", starts_at=timezone.now()+timedelta(days=1),
            ends_at=timezone.now()+timedelta(days=1, hours=2), all_day=False, location="Local", meeting_link="")
        self.assertEqual(created.status, "PUBLISHED")
        self.assertEqual(created.visibility, "PRIVATE")  # jamais public par défaut

    def test_unauthorized_member_cannot_create_event(self):
        for actor in [self.member, self.bureau]:
            with self.subTest(actor=actor.email):
                with self.assertRaises(PermissionDenied):
                    services.create_calendar_event(actor=actor, title="x", description="", starts_at=timezone.now(),
                        ends_at=None, all_day=False, location="", meeting_link="")

    def test_view_requires_event_create_capability(self):
        self.client.force_login(self.member)
        response = self.client.post(reverse("agenda_private:calendar_event_add"), {
            "title": "Interdit", "description": "", "starts_at": "2030-01-01T10:00", "all_day": "",
        })
        self.assertEqual(response.status_code, 403)
        self.assertFalse(Event.objects.filter(title="Interdit").exists())

    def test_missing_title_or_start_rejected(self):
        with self.assertRaises(ValidationError):
            services.create_calendar_event(actor=self.president, title="", description="", starts_at=timezone.now(),
                ends_at=None, all_day=False, location="", meeting_link="")
        with self.assertRaises(ValidationError):
            services.create_calendar_event(actor=self.president, title="Sans date", description="", starts_at=None,
                ends_at=None, all_day=False, location="", meeting_link="")

    def test_created_event_visible_in_shared_calendar_for_other_member(self):
        created = services.create_calendar_event(actor=self.president, title="Assemblée générale",
            description="", starts_at=timezone.now()+timedelta(days=2),
            ends_at=timezone.now()+timedelta(days=2, hours=1), all_day=False, location="Salle A", meeting_link="")
        self.assertIn(created, list(upcoming_events(self.member)))
        self.client.force_login(self.member)
        response = self.client.get(reverse("agenda_private:calendar"))
        self.assertContains(response, "Assemblée générale")

    def test_view_created_via_http_appears_for_everyone(self):
        self.client.force_login(self.president)
        response = self.client.post(reverse("agenda_private:calendar_event_add"), {
            "title": "Formation secourisme", "description": "Premiers secours", "all_day": "",
            "starts_at": (timezone.now()+timedelta(days=5)).strftime("%Y-%m-%dT%H:%M"),
            "ends_at": (timezone.now()+timedelta(days=5, hours=3)).strftime("%Y-%m-%dT%H:%M"),
            "location": "Siège du club",
        })
        self.assertRedirects(response, reverse("agenda_private:calendar"))
        self.assertTrue(Event.objects.filter(title="Formation secourisme", status="PUBLISHED").exists())

    def test_calendar_post_rejects_external_return_url(self):
        self.client.force_login(self.president)
        response = self.client.post(reverse("agenda_private:calendar_event_add"), {
            "title": "Retour sûr", "description": "", "all_day": "",
            "starts_at": (timezone.now()+timedelta(days=5)).strftime("%Y-%m-%dT%H:%M"),
            "next": "https://example.invalid/phishing",
        })
        self.assertRedirects(response, reverse("agenda_private:calendar"))


class CalendarIcsTests(TestCase):
    def setUp(self):
        self.president = account("president-ics@example.invalid", role=Role.PRESIDENT)
        self.member = account("member-ics@example.invalid", role=Role.MEMBRE)
        self.member.first_name = "Secret"; self.member.last_name = "Membre"; self.member.save()
        self.event = event(self.president, title="Réunion privée ICS")

    def test_token_required_for_subscription(self):
        self.assertEqual(self.client.get("/espace/calendrier/abonnement/inconnu.ics").status_code, 404)

    def test_token_generated_on_first_calendar_view(self):
        self.client.force_login(self.member)
        self.client.get(reverse("agenda_private:calendar"))
        self.member.member_profile.refresh_from_db()
        self.assertIsNotNone(self.member.member_profile.calendar_token)
        self.assertGreaterEqual(len(self.member.member_profile.calendar_token), 32)

    def test_ics_feed_contains_authorized_event(self):
        self.client.force_login(self.member)
        self.client.get(reverse("agenda_private:calendar"))  # provisionne le jeton
        token = MemberProfile.objects.get(user=self.member).calendar_token
        response = self.client.get(f"/espace/calendrier/abonnement/{token}.ics")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/calendar; charset=utf-8")
        content = response.content.decode()
        self.assertIn("BEGIN:VCALENDAR", content)
        self.assertIn("Réunion privée ICS", content)
        self.assertIn("X-Robots-Tag", response)
        self.assertIn("noindex", response["X-Robots-Tag"])
        self.assertIn("no-store", response["Cache-Control"])

    def test_old_token_invalid_after_regeneration(self):
        self.client.force_login(self.member)
        self.client.get(reverse("agenda_private:calendar"))
        old_token = MemberProfile.objects.get(user=self.member).calendar_token
        self.client.post(reverse("agenda_private:calendar_token_regenerate"))
        new_token = MemberProfile.objects.get(user=self.member).calendar_token
        self.assertNotEqual(old_token, new_token)
        self.assertEqual(self.client.get(f"/espace/calendrier/abonnement/{old_token}.ics").status_code, 404)
        self.assertEqual(self.client.get(f"/espace/calendrier/abonnement/{new_token}.ics").status_code, 200)

    def test_ics_feed_never_leaks_email_or_name_of_subscriber(self):
        self.client.force_login(self.member)
        self.client.get(reverse("agenda_private:calendar"))
        token = MemberProfile.objects.get(user=self.member).calendar_token
        content = self.client.get(f"/espace/calendrier/abonnement/{token}.ics").content.decode()
        self.assertNotIn(self.member.email, content)
        self.assertNotIn("Secret", content)
        self.assertNotIn(str(self.member.pk), content)

    def test_authenticated_download_returns_valid_ics(self):
        self.client.force_login(self.member)
        response = self.client.get(reverse("agenda_private:calendar_download"))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertTrue(content.startswith("BEGIN:VCALENDAR"))
        self.assertTrue(content.rstrip().endswith("END:VCALENDAR"))
        self.assertIn("Réunion privée ICS", content)
        self.assertEqual(response["Content-Disposition"], 'attachment; filename="lionsmed-calendrier.ics"')

    def test_regenerate_requires_login(self):
        response = self.client.post(reverse("agenda_private:calendar_token_regenerate"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/connexion/", response.url)


class CalendarResponsiveViewsTests(TestCase):
    """Refonte responsive (Mois/Semaine/Jour) : positions de la timeline, structure de
    grille mensuelle constante (jamais 1 colonne, cause du bug mobile précédent), et
    présence des données nécessaires aux <dialog> côté client."""

    def setUp(self):
        self.president = account("president-responsive@example.invalid", role=Role.PRESIDENT)
        self.member = account("member-responsive@example.invalid", role=Role.MEMBRE)
        from datetime import datetime, time
        today = timezone.localdate()
        starts_at = timezone.make_aware(datetime.combine(today, time(14, 0)))
        ends_at = timezone.make_aware(datetime.combine(today, time(15, 30)))
        self.event = event(self.president, title="Réunion après-midi", starts_at=starts_at, ends_at=ends_at)

    def test_timeline_positions_use_period_decimal_not_locale_comma(self):
        """Régression : {{ }} sur un float en template FR rend une virgule décimale,
        ce qui casserait silencieusement tout style inline top/height/left/width."""
        self.client.force_login(self.member)
        for view in ("day", "week"):
            with self.subTest(view=view):
                content = self.client.get(reverse("agenda_private:calendar"), {"view": view}).content.decode()
                self.assertIn('style="top:50.00%;height:10.71%;left:0.00%;width:100.00%;"', content)
                self.assertNotIn("top:50,00%", content)

    def test_month_grid_is_always_seven_columns_never_single_column(self):
        import pathlib, re
        self.client.force_login(self.member)
        content = self.client.get(reverse("agenda_private:calendar"), {"view": "month"}).content.decode()
        day_count = len(re.findall(r'<div class="cal-day(?:"| )', content))
        self.assertGreaterEqual(day_count, 28)
        self.assertEqual(day_count % 7, 0)  # toujours un multiple exact de 7, jamais 1 colonne
        css_path = pathlib.Path(__file__).resolve().parents[3] / "static" / "css" / "prive.css"
        css = css_path.read_text()
        self.assertIn(".cal-month__grid { display: grid; grid-template-columns: repeat(7, minmax(0,1fr))", css)
        self.assertNotRegex(css, r"\.cal-month__grid[^}]*grid-template-columns:\s*1fr[^0-9]")

    def test_events_json_available_for_dialog(self):
        self.client.force_login(self.member)
        content = self.client.get(reverse("agenda_private:calendar")).content.decode()
        self.assertIn('id="cal-events-data"', content)
        self.assertIn(str(self.event.pk), content)
        self.assertIn('data-cal-event="' + str(self.event.pk) + '"', content)

    def test_ics_link_never_rendered_as_visible_text_field(self):
        """Le lien d'abonnement reste dans un champ hidden, jamais un texte affiché en clair."""
        self.client.force_login(self.member)
        content = self.client.get(reverse("agenda_private:calendar")).content.decode()
        self.assertIn('type="hidden" id="lien-abonnement"', content)

    def test_all_three_views_render_without_error_for_authorized_member(self):
        self.client.force_login(self.member)
        for view in ("month", "week", "day"):
            with self.subTest(view=view):
                response = self.client.get(reverse("agenda_private:calendar"), {"view": view})
                self.assertEqual(response.status_code, 200)
