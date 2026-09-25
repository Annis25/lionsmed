from datetime import timedelta
from django.test import TestCase
from django.utils import timezone
from apps.core.tests.test_foundations import account
from apps.governance.models import ClubState, LionsYear, Mandate, Role
from apps.governance.selectors import function_key, public_bureau
from apps.members.models import MemberProfile


class FunctionLabelTests(TestCase):
    def test_labels_are_recognised_without_guessing(self):
        self.assertEqual(function_key("1er Vice-Président"), "VICE_PRESIDENT_1")
        self.assertEqual(function_key("Première vice-présidente"), "VICE_PRESIDENT_1")
        self.assertEqual(function_key("2ème Vice-Président"), "VICE_PRESIDENT_2")
        self.assertEqual(function_key("Trésorière"), "TRESORIER")
        self.assertEqual(function_key("Chef du protocole"), "PROTOCOLE")
        self.assertEqual(function_key("Past-Président"), "PAST_PRESIDENT")
        self.assertEqual(function_key("Vice-Président"), "VICE_PRESIDENT")  # jamais promu 1er ou 2e
        self.assertIsNone(function_key("Présidente de commission"))  # pas de rapprochement approximatif


class PublicBureauTests(TestCase):
    def setUp(self):
        self.actor = account("actor@example.invalid", role=Role.SUPER_ADMIN)
        today = timezone.localdate()
        self.previous = LionsYear.objects.create(starts_on=today - timedelta(days=400), ends_on=today - timedelta(days=35))
        self.year = LionsYear.objects.create(starts_on=today - timedelta(days=35), ends_on=today + timedelta(days=330))
        ClubState.objects.update_or_create(id=1, defaults={"active_year": self.year})
        self.n = 0

    def mandate(self, function, *, year=None, validated=True, public=True, last_name=None, **profile):
        self.n += 1
        user = account(f"m{self.n}@example.invalid", role=Role.MEMBRE)
        user.last_name = last_name or f"Nom{self.n}"
        user.save()
        MemberProfile.objects.filter(user=user).update(**profile)
        year = year or self.year
        return Mandate.objects.create(profile=user.member_profile, function=function, lions_year=year,
            starts_on=year.starts_on, ends_on=year.ends_on, validated_at=timezone.now() if validated else None,
            validated_by=self.actor if validated else None, public_authorized=public)

    def test_institutional_order_and_unranked_functions_last(self):
        for function in ["Responsable effectif", "Trésorier", "Chef du protocole", "Secrétaire",
                         "2e Vice-Président", "Président", "1er Vice-Président"]:
            self.mandate(function)
        functions = [m["function"] for m in public_bureau()["members"]]
        self.assertEqual(functions, ["Président", "1er Vice-Président", "2e Vice-Président", "Secrétaire",
                                     "Trésorier", "Chef du protocole", "Responsable effectif"])

    def test_past_president_derived_from_previous_year_president(self):
        self.mandate("Président", year=self.previous, last_name="Sortant")
        self.mandate("Président", last_name="Actuel")
        members = public_bureau()["members"]
        self.assertEqual([m["function"] for m in members], ["Past President", "Président"])
        self.assertEqual(members[0]["name"], "Compte Sortant")
        self.assertEqual(members[0]["note"], f"Président {self.previous.label}")

    def test_explicit_past_president_mandate_wins_over_derivation(self):
        self.mandate("Président", year=self.previous, last_name="Sortant")
        self.mandate("Past President", last_name="Explicite")
        self.mandate("Président", last_name="Actuel")
        members = public_bureau()["members"]
        self.assertEqual([m["name"] for m in members], ["Compte Explicite", "Compte Actuel"])

    def test_no_derivation_when_previous_presidency_is_ambiguous_or_private(self):
        self.mandate("Président", year=self.previous)
        self.mandate("Président", year=self.previous)
        self.mandate("Président")
        self.assertEqual([m["function"] for m in public_bureau()["members"]], ["Président"])
        Mandate.objects.filter(lions_year=self.previous).delete()
        self.mandate("Président", year=self.previous, public=False)
        self.assertEqual([m["function"] for m in public_bureau()["members"]], ["Président"])

    def test_derived_past_president_never_shown_alone(self):
        self.mandate("Président", year=self.previous)
        self.assertEqual(public_bureau()["members"], [])

    def test_only_validated_public_active_mandates(self):
        self.mandate("Secrétaire", validated=False)
        self.mandate("Trésorier", public=False)
        self.mandate("Protocole", status=MemberProfile.Status.SUSPENDED)
        ended = self.mandate("Président")
        Mandate.objects.filter(pk=ended.pk).update(ends_on=timezone.localdate())
        self.assertEqual(public_bureau()["members"], [])

    def test_new_active_year_replaces_the_bureau(self):
        self.mandate("Président", last_name="Ancien")
        following = LionsYear.objects.create(starts_on=self.year.ends_on, ends_on=self.year.ends_on + timedelta(days=365))
        self.mandate("Président", year=following, last_name="Nouveau")
        self.assertEqual([m["name"] for m in public_bureau()["members"]], ["Compte Ancien"])
        ClubState.objects.filter(id=1).update(active_year=following)
        members = public_bureau()["members"]
        self.assertEqual([m["name"] for m in members], ["Compte Ancien", "Compte Nouveau"])
        self.assertEqual([m["function"] for m in members], ["Past President", "Président"])

    def test_photo_and_profile_link_only_with_public_profile(self):
        mandate = self.mandate("Président", photo_key="portrait.jpg")
        member = public_bureau()["members"][0]
        self.assertEqual((member["photo_url"], member["profile_url"]), ("", ""))
        self.assertEqual(member["initials"], "CN")
        MemberProfile.objects.filter(pk=mandate.profile_id).update(public_profile_enabled=True, public_slug="compte-nom")
        member = public_bureau()["members"][0]
        self.assertEqual(member["photo_url"], "/membres/compte-nom/photo/")
        self.assertEqual(member["profile_url"], "/membres/compte-nom/")
        self.assertEqual(set(member), {"name", "initials", "function", "note", "profile_url", "photo_url"})

    def test_club_page_renders_bureau_without_private_data(self):
        mandate = self.mandate("Président", phone="+21620000000")
        html = self.client.get("/notre-club/").content.decode()
        self.assertIn('id="bureau"', html)
        self.assertIn("Année Lions " + self.year.label, html)
        self.assertIn('"roleName": "Président"', html)
        self.assertNotIn(mandate.profile.user.email, html)
        self.assertNotIn("+21620000000", html)

    def test_club_page_hides_empty_bureau(self):
        self.assertNotIn('id="bureau"', self.client.get("/notre-club/").content.decode())
