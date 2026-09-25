from datetime import timedelta
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from apps.core.models import AuditEvent
from apps.core.permissions import MANAGERS, can, effective_role
from apps.core.tests.test_foundations import account
from apps.communications.models import OutboxMessage
from apps.governance.functions import canonical_label, function_key, selectable_labels
from apps.governance.models import ClubState, LionsYear, Mandate, Role
from apps.governance.selectors import mandate_candidates, public_bureau
from apps.members.models import MemberProfile


class FunctionCatalogueTests(TestCase):
    def test_catalogue_offers_the_seven_functions_with_feminine_forms(self):
        labels = selectable_labels()
        for label in ["Past President", "Président", "Présidente", "1er Vice-Président", "1re Vice-Présidente",
                      "2e Vice-Président", "2e Vice-Présidente", "Secrétaire", "Trésorier", "Trésorière", "Protocole"]:
            self.assertIn(label, labels)
        self.assertNotIn("Vice-Président", labels)  # le rang doit toujours être précisé

    def test_variants_map_to_canonical_labels_without_guessing(self):
        self.assertEqual(canonical_label("1ère vice présidente"), "1re Vice-Présidente")
        self.assertEqual(canonical_label("Premier vice-président"), "1er Vice-Président")
        self.assertEqual(canonical_label("2ème VP"), "2e Vice-Président")
        self.assertEqual(canonical_label("trésorière"), "Trésorière")
        self.assertIsNone(canonical_label("Responsable effectif"))
        self.assertIsNone(function_key("Présidente de commission"))


class MandateManagementTests(TestCase):
    def setUp(self):
        today = timezone.localdate()
        self.previous = LionsYear.objects.create(starts_on=today - timedelta(days=400), ends_on=today - timedelta(days=35))
        self.year = LionsYear.objects.create(starts_on=today - timedelta(days=35), ends_on=today + timedelta(days=330))
        ClubState.objects.update_or_create(id=1, defaults={"active_year": self.year})
        self.manager = account("secretaire@example.invalid", role=Role.SECRETAIRE)
        self.member = account("membre@example.invalid", role=Role.MEMBRE)
        self.member.first_name, self.member.last_name = "Amel", "Ben Salah"
        self.member.save()

    def post(self, url, **changes):
        data = {"profile": self.member.member_profile.pk, "function_choice": "1re Vice-Présidente", "function_other": "",
                "lions_year": self.year.pk, "starts_on": "", "last_day": "", "validated": "on", "public_authorized": "on"}
        data.update(changes)
        return self.client.post(url, {k: v for k, v in data.items() if v is not None})

    def test_capability_is_limited_to_managers(self):
        for role in Role.values:
            user = account("cap-" + role.lower() + "@example.invalid", role=role)
            self.assertEqual(can(user, "mandate.manage"), role in MANAGERS, role)
        self.assertEqual(MANAGERS, frozenset({Role.SUPER_ADMIN, Role.PRESIDENT, Role.PRESIDENT_FONDATEUR, Role.SECRETAIRE}))

    def test_views_refuse_non_managers(self):
        mandate = Mandate.objects.create(profile=self.member.member_profile, function="Président", lions_year=self.year,
            starts_on=self.year.starts_on, ends_on=self.year.ends_on)
        for role in [Role.MEMBRE, Role.BUREAU, Role.VICE_PRESIDENT, Role.TRESORIER, Role.DIRECTEUR]:
            self.client.force_login(account("vue-" + role.lower() + "@example.invalid", role=role))
            self.assertEqual(self.client.get(reverse("governance:mandates")).status_code, 403, role)
            self.assertEqual(self.post(reverse("governance:mandate_add")).status_code, 403, role)
            self.assertEqual(self.client.post(reverse("governance:mandate_end", args=[mandate.pk])).status_code, 403, role)
            self.assertEqual(self.client.post(reverse("governance:mandate_delete", args=[mandate.pk])).status_code, 403, role)
        self.client.logout()
        self.assertEqual(self.client.get(reverse("governance:mandates")).status_code, 302)
        self.assertEqual(Mandate.objects.count(), 1)

    def test_manager_creates_validated_public_mandate_shown_on_club_page(self):
        self.client.force_login(self.manager)
        form = self.client.get(reverse("governance:mandate_add")).content.decode()
        self.assertIn(f'<option value="{self.year.pk}" selected>', form)  # Année Lions active par défaut
        response = self.post(reverse("governance:mandate_add"))
        self.assertEqual(response.status_code, 302)
        mandate = Mandate.objects.get()
        self.assertEqual((mandate.function, mandate.starts_on, mandate.ends_on), ("1re Vice-Présidente", self.year.starts_on, self.year.ends_on))
        self.assertEqual(mandate.validated_by, self.manager)
        self.assertTrue(mandate.public_authorized)
        self.assertTrue(AuditEvent.objects.filter(action="mandate.saved", object_id=str(mandate.pk)).exists())
        self.assertEqual(effective_role(self.member), Role.MEMBRE)  # un mandat n'accorde aucun rôle
        html = self.client.get("/notre-club/").content.decode()
        self.assertIn("Amel Ben Salah", html)
        self.assertIn("1re Vice-Présidente", html)
        self.assertNotIn(self.member.email, html)

    def test_uncontrolled_variants_are_refused(self):
        self.client.force_login(self.manager)
        for text in ["Premier vice-président", "1ère vice présidente", "Vice-Président", "tresoriere"]:
            response = self.post(reverse("governance:mandate_add"), function_choice="__autre__", function_other=text)
            self.assertEqual(response.status_code, 200, text)
            self.assertContains(response, "aria-invalid", msg_prefix=text)
        response = self.post(reverse("governance:mandate_add"), function_choice="Grand Maître")  # hors liste forgé
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Mandate.objects.count(), 0)
        self.post(reverse("governance:mandate_add"), function_choice="__autre__", function_other="Responsable effectif (GMT)")
        self.assertEqual(Mandate.objects.get().function, "Responsable effectif (GMT)")

    def test_dates_are_bounded_by_the_lions_year_and_last_day_is_inclusive(self):
        self.client.force_login(self.manager)
        start = self.year.starts_on + timedelta(days=10)
        last = self.year.starts_on + timedelta(days=100)
        self.post(reverse("governance:mandate_add"), starts_on=start.isoformat(), last_day=last.isoformat())
        mandate = Mandate.objects.get()
        self.assertEqual((mandate.starts_on, mandate.ends_on), (start, last + timedelta(days=1)))
        response = self.post(reverse("governance:mandate_add"), last_day=(self.year.ends_on + timedelta(days=5)).isoformat())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Mandate.objects.count(), 1)

    def test_edit_end_and_delete(self):
        self.client.force_login(self.manager)
        self.post(reverse("governance:mandate_add"))
        mandate = Mandate.objects.get()
        edit = reverse("governance:mandate_edit", args=[mandate.pk])
        self.assertContains(self.client.get(edit), 'value="1re Vice-Présidente" selected')
        self.post(edit, function_choice="Présidente", public_authorized=None)
        mandate.refresh_from_db()
        self.assertEqual(mandate.function, "Présidente")
        self.assertFalse(mandate.public_authorized)
        self.assertEqual(public_bureau()["members"], [])  # retiré du site sans suppression
        self.post(edit, function_choice="Présidente")
        self.assertEqual([m["function"] for m in public_bureau()["members"]], ["Présidente"])
        self.client.post(reverse("governance:mandate_end", args=[mandate.pk]))
        mandate.refresh_from_db()
        self.assertEqual(mandate.ends_on, timezone.localdate())
        self.assertEqual(public_bureau()["members"], [])  # mandat terminé : sort du bureau public
        self.assertContains(self.client.get(reverse("governance:mandate_delete", args=[mandate.pk])), "Confirmer la suppression")
        self.client.post(reverse("governance:mandate_delete", args=[mandate.pk]))
        self.assertFalse(Mandate.objects.exists())
        self.assertTrue(AuditEvent.objects.filter(action="mandate.deleted", object_id=str(mandate.pk)).exists())

    def test_unvalidated_mandate_is_never_public(self):
        self.client.force_login(self.manager)
        self.post(reverse("governance:mandate_add"), validated=None)
        mandate = Mandate.objects.get()
        self.assertIsNone(mandate.validated_at)
        self.assertEqual(public_bureau()["members"], [])
        self.assertContains(self.client.get(reverse("governance:mandates")), "Autorisé, en attente de validation")

    def test_member_selection_excludes_technical_guest_and_suspended_accounts(self):
        admin = account("admin@example.invalid", role=Role.SUPER_ADMIN)
        guest = account("invite@example.invalid", role=Role.INVITE)
        suspended = account("suspendu@example.invalid", role=Role.MEMBRE)
        MemberProfile.objects.filter(user=suspended).update(status=MemberProfile.Status.SUSPENDED)
        candidates = set(mandate_candidates().values_list("user_id", flat=True))
        self.assertIn(self.member.pk, candidates)
        self.assertFalse({admin.pk, guest.pk, suspended.pk} & candidates)
        self.assertIn(suspended.pk, set(mandate_candidates(include=suspended.member_profile.pk).values_list("user_id", flat=True)))

    def test_management_list_orders_functions_and_previews_derived_past_president(self):
        previous_president = account("ancien@example.invalid", role=Role.MEMBRE)
        previous_president.last_name = "Sortant"; previous_president.save()
        Mandate.objects.create(profile=previous_president.member_profile, function="Président", lions_year=self.previous,
            starts_on=self.previous.starts_on, ends_on=self.previous.ends_on, validated_at=timezone.now(),
            validated_by=self.manager, public_authorized=True)
        self.client.force_login(self.manager)
        self.post(reverse("governance:mandate_add"), function_choice="Trésorière")
        other = account("autre@example.invalid", role=Role.MEMBRE)
        self.post(reverse("governance:mandate_add"), profile=other.member_profile.pk, function_choice="Président")
        html = self.client.get(reverse("governance:mandates")).content.decode()
        self.assertLess(html.index("<strong>Président</strong>"), html.index("<strong>Trésorière</strong>"))
        self.assertIn(f"déduit : Président {self.previous.label}", html)
        self.assertEqual([m["function"] for m in public_bureau()["members"]], ["Past President", "Président", "Trésorière"])

    def test_member_sheet_links_to_mandate_management(self):
        self.client.force_login(self.manager)
        html = self.client.get(reverse("governance:member", args=[self.member.pk])).content.decode()
        self.assertIn(reverse("governance:mandate_add") + f"?membre={self.member.pk}", html)
        form = self.client.get(reverse("governance:mandate_add") + f"?membre={self.member.pk}").content.decode()
        self.assertIn(f'<option value="{self.member.member_profile.pk}" selected>', form)


class ApplicationPromiseTests(TestCase):
    """Les deux phrases du parcours de candidature reposent sur un comportement réel."""
    def test_application_queues_receipt_and_enters_follow_up_workflow(self):
        from django.core import signing
        from uuid import uuid4
        from apps.members.models import MembershipApplication
        token = signing.dumps({"id": str(uuid4()), "kind": "application"}, salt="public-submission")
        page = self.client.get(reverse("communications:application")).content.decode()
        self.assertIn("Vous recevez un accusé de réception par e-mail.", page)
        self.assertIn("Nous revenons vers vous pour faire connaissance.", page)
        self.client.post(reverse("communications:application"), {"submission_token": token, "first_name": "Prénom",
            "last_name": "Nom", "email": "candidat@example.invalid", "phone": "+21620000000",
            "motivation": "Motivation", "consent": "on"})
        application = MembershipApplication.objects.get()
        receipt = OutboxMessage.objects.get(kind="APPLICATION")
        self.assertEqual((receipt.recipient, receipt.object_id), ("candidat@example.invalid", application.pk))
        self.assertEqual(application.state, "RECEIVED")
        self.assertIn("CONTACTED", dict(MembershipApplication._meta.get_field("state").choices))
