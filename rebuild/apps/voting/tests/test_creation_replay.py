from django.test import TestCase
from django.urls import reverse
from apps.core.tests.test_foundations import account
from apps.governance.models import Role
from apps.voting.models import Vote


class CreationReplayTests(TestCase):
    def test_same_form_post_creates_one_vote(self):
        actor = account("replay@example.invalid", role=Role.PRESIDENT)
        self.client.force_login(actor)
        url = reverse("voting:manage_create")
        form = self.client.get(url).context["form"]
        data = {"title": "Scrutin synthétique", "mode": "SINGLE", "options": ["Oui", "Non"]}
        if "creation_key" in form.fields:
            data["creation_key"] = str(form.initial["creation_key"])
        self.assertEqual(self.client.post(url, data).status_code, 302)
        self.assertEqual(self.client.post(url, data).status_code, 302)
        self.assertEqual(Vote.objects.count(), 1)
