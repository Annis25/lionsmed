"""Refonte des dashboards par rôle (Membre/Secrétaire/Président/Trésorier) : chaque
rôle voit les bonnes sections dans le bon ordre, jamais de donnée hors de sa portée,
actions calculées via can() et non via un test de rôle en dur côté template."""
from django.test import TestCase
from django.urls import reverse
from apps.core.tests.test_foundations import account
from apps.dues.tests.test_dues import lions_year
from apps.governance.models import Role, ClubState


class DashboardVariantTests(TestCase):
    def setUp(self):
        self.member = account("dash-member@example.invalid", role=Role.MEMBRE)
        self.secretary = account("dash-secretary@example.invalid", role=Role.SECRETAIRE)
        self.president = account("dash-president@example.invalid", role=Role.PRESIDENT)
        self.treasurer = account("dash-treasurer@example.invalid", role=Role.TRESORIER)
        self.year = lions_year()
        ClubState.objects.update_or_create(pk=1, defaults={"active_year": self.year})

    def get(self, user):
        self.client.force_login(user)
        return self.client.get(reverse("core:dashboard"))

    # --- MEMBRE -----------------------------------------------------------------
    def test_member_variant_and_sections(self):
        response = self.get(self.member)
        self.assertEqual(response.context["dashboard_variant"], "member")
        self.assertContains(response, "Retrouvez vos prochaines actions et informations utiles.")
        self.assertContains(response, "Votre espace")
        self.assertContains(response, "Mon profil et mon parcours")
        self.assertNotContains(response, "Indicateurs")  # pas de section KPI pour le membre
        self.assertNotContains(response, "Actions rapides")

    def test_member_todo_positive_empty_state_when_nothing_pending(self):
        response = self.get(self.member)
        self.assertFalse(response.context["has_todo"])
        self.assertContains(response, "Tout est à jour")
        self.assertContains(response, "Vous n’avez aucune action nécessitant votre attention.")

    def test_member_never_sees_management_or_treasurer_data(self):
        response = self.get(self.member)
        self.assertNotContains(response, "titre-encaissement")
        self.assertNotContains(response, "titre-membres")
        self.assertNotIn("dashboard_kpis", response.context)
        self.assertNotIn("dashboard_quicklinks", response.context)

    # --- SECRETAIRE ---------------------------------------------------------------
    def test_secretary_variant_and_sections(self):
        response = self.get(self.secretary)
        self.assertEqual(response.context["dashboard_variant"], "secretary")
        self.assertContains(response, "Suivez l’activité quotidienne du club et les éléments à traiter.")
        self.assertContains(response, "Documents récents")
        self.assertContains(response, "Actions rapides")
        kpi_labels = {k["label"] for k in response.context["dashboard_kpis"]}
        self.assertEqual(kpi_labels, {"Membres actifs", "Événements à venir", "Documents disponibles", "Messages en attente"})
        # Sections réservées au Président, absentes pour le Secrétaire (la sidebar peut
        # légitimement contenir un lien "Membres et mandats" : on vérifie l'ID de section
        # du dashboard, pas le texte, qui existe aussi dans la navigation).
        self.assertNotContains(response, "titre-votes")
        self.assertNotContains(response, "titre-membres")

    def test_secretary_does_not_see_treasurer_block(self):
        response = self.get(self.secretary)
        self.assertNotContains(response, "titre-encaissement")

    def test_secretary_quicklinks_use_capabilities(self):
        response = self.get(self.secretary)
        labels = {link["label"] for link in response.context["dashboard_quicklinks"]}
        self.assertEqual(labels, {"Gérer les documents", "Calendrier", "Messages de contact", "Communication"})

    def test_secretary_sees_pending_contact_messages_in_todo_and_kpi(self):
        import uuid
        from apps.communications.models import ContactRequest
        ContactRequest.objects.create(submission_key=uuid.uuid4(), name="Visiteur", email="visiteur@example.invalid",
            subject="INFO", message="Bonjour")
        response = self.get(self.secretary)
        self.assertEqual(response.context["contact_pending_count"], 1)
        self.assertContains(response, "Messages de contact à traiter")
        kpi_by_label = {k["label"]: k["value"] for k in response.context["dashboard_kpis"]}
        self.assertEqual(kpi_by_label["Messages en attente"], 1)

    def test_secretary_documents_empty_state(self):
        response = self.get(self.secretary)
        self.assertEqual(response.context["recent_documents"], [])
        self.assertContains(response, "Aucun document récent")

    # --- PRESIDENT ------------------------------------------------------------
    def test_president_variant_and_sections(self):
        response = self.get(self.president)
        self.assertEqual(response.context["dashboard_variant"], "president")
        self.assertContains(response, "Pilotez les activités du club et suivez les indicateurs essentiels.")
        self.assertContains(response, "Votes et satisfaction")
        self.assertContains(response, "Membres et mandats")
        self.assertContains(response, "Actions rapides")

    def test_president_kpis_are_exactly_four_and_curated(self):
        response = self.get(self.president)
        kpis = response.context["dashboard_kpis"]
        self.assertEqual(len(kpis), 4)
        self.assertEqual([k["label"] for k in kpis],
            ["Membres actifs", "Événements à venir", "Votes ouverts", "Cotisations à régulariser"])

    def test_president_without_dues_manage_does_not_see_treasurer_block(self):
        response = self.get(self.president)
        self.assertNotContains(response, "titre-encaissement")

    def test_president_empty_votes_and_satisfaction_states(self):
        response = self.get(self.president)
        self.assertContains(response, "Aucun vote ouvert.")
        self.assertContains(response, "Aucune période ouverte.")

    def test_president_quicklinks_use_capabilities_not_role_check(self):
        response = self.get(self.president)
        labels = {link["label"] for link in response.context["dashboard_quicklinks"]}
        self.assertEqual(labels, {"Membres et mandats", "Années Lions", "Gérer les documents",
            "Gérer les votes", "Communication", "Envoyer une notification"})
        # "Gérer les cotisations" n'apparaît pas : un Président simple n'a pas dues.manage.
        self.assertNotIn("Gérer les cotisations", labels)

    def test_super_admin_sees_president_variant_plus_dues_block(self):
        admin = account("dash-admin@example.invalid", role=Role.SUPER_ADMIN)
        response = self.get(admin)
        self.assertEqual(response.context["dashboard_variant"], "president")
        self.assertContains(response, "titre-encaissement")  # dues.manage inclut SUPER_ADMIN
        labels = {link["label"] for link in response.context["dashboard_quicklinks"]}
        self.assertIn("Gérer les cotisations", labels)

    # --- TRESORIER ------------------------------------------------------------
    def test_treasurer_variant_and_dues_block_first(self):
        response = self.get(self.treasurer)
        self.assertEqual(response.context["dashboard_variant"], "treasurer")
        self.assertContains(response, "Suivez les cotisations et les encaissements de l’année Lions.")
        content = response.content.decode()
        self.assertLess(content.index("titre-encaissement"), content.index("titre-actions"))

    def test_treasurer_does_not_see_generic_pilotage_or_president_sections(self):
        response = self.get(self.treasurer)
        self.assertNotIn("dashboard_kpis", response.context)
        self.assertNotContains(response, "titre-votes")
        self.assertNotContains(response, "titre-membres")
        self.assertNotContains(response, "titre-kpis")

    def test_treasurer_quicklinks(self):
        response = self.get(self.treasurer)
        labels = {link["label"] for link in response.context["dashboard_quicklinks"]}
        self.assertEqual(labels, {"Gérer les cotisations", "Calendrier", "Notifications"})

    def test_treasurer_regularize_count_and_workspace(self):
        from apps.dues.models import DuesSchedule, DuesRecord
        from decimal import Decimal
        DuesSchedule.objects.create(lions_year=self.year, tranche1_amount=Decimal("50"), tranche2_amount=Decimal("50"))
        DuesRecord.objects.create(profile=self.member.member_profile, lions_year=self.year, tranche1_paid=False, tranche2_paid=False)
        response = self.get(self.treasurer)
        self.assertGreaterEqual(response.context["dues_regularize_member_count"], 1)
        self.assertContains(response, "membre")
        self.assertContains(response, "à régulariser")
        self.assertContains(response, "Votre espace")  # espace personnel conservé après cotisations

    # --- Sécurité transverse ---------------------------------------------------
    def test_invite_dashboard_does_not_crash_and_shows_minimal_content(self):
        invite = account("dash-invite@example.invalid", role=Role.INVITE)
        response = self.get(invite)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["dashboard_variant"], "member")

    def test_no_role_check_leak_member_cannot_access_management_urls_from_dashboard_links(self):
        response = self.get(self.member)
        self.assertNotContains(response, reverse("governance:members"))
        self.assertNotContains(response, reverse("voting:manage_list"))
        self.assertNotContains(response, reverse("dues:manage_list"))
