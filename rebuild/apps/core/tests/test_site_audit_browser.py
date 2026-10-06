"""Audit d'affichage de tout le site (contrôle navigateur optionnel).

Prépare un club synthétique complet sur la base de test, ouvre une session par profil (sans
mot de passe) et lance tools/browser_site_audit.cjs, qui parcourt toutes les pages
atteignables et échoue si un constat bloquant subsiste (débordement, contraste, bouton au
style navigateur par défaut, entrée de menu sans icône, lien en erreur, erreur console…).

    LIONSMED_SITE_AUDIT=1 PLAYWRIGHT_MODULE=/chemin/vers/playwright \\
        python manage.py test apps.core.tests.test_site_audit_browser --settings=config.settings.test --noinput

LIONSMED_AUDIT_SHOTS=1 ajoute une capture par page dans LIONSMED_AUDIT_OUT."""
import json
import os
import subprocess
from datetime import date, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import skipUnless
from unittest.mock import patch
from uuid import uuid4

from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import Client, override_settings
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from apps.core.tests.test_foundations import account
from apps.governance.models import ClubState, LionsYear, Mandate, Role

R = Role
# (clé de session ou None, prénom, nom, rôle) — noms synthétiques, longueurs réalistes.
PEOPLE = [
    ("president", "Nour", "Zghal", R.PRESIDENT), ("secretaire", "Eya", "Dehech", R.SECRETAIRE), ("tresorier", "Sana", "Gargouri", R.TRESORIER),
    ("superadmin", "Test", "Super Admin", R.SUPER_ADMIN), ("marketing", "Mariam", "Barkallah", R.MARKETING_COMMUNICATION),
    ("membre", "Anis", "Besbes", R.MEMBRE), ("invite", "Invité", "Découverte", R.INVITE),
    (None, "Mohamed", "Elleuch", R.VICE_PRESIDENT), (None, "Rachid", "Jmal", R.PRESIDENT_FONDATEUR), (None, "Mariem", "Radhouani", R.GST),
    (None, "Hatem", "Masmoudi", R.GMT), (None, "Sofiene", "Hadj Kacem", R.GLT), (None, "Wassim", "Feki", R.LCIF), (None, "Nahed", "Jmal", R.BUREAU),
    (None, "Slim", "Turki", R.DIRECTEUR), (None, "Mohamed-Amine", "Ben Abdallah-Chaabouni", R.MEMBRE), (None, "Rania", "Trabelsi", R.MEMBRE),
    (None, "Ahmed", "Gharbi", R.MEMBRE), (None, "Amira", "Nouri", R.MEMBRE), (None, "Chema", "Mekki", R.MEMBRE), (None, "Hakim", "Kchaou", R.MEMBRE),
    (None, "Omar", "Zayani", R.MEMBRE), (None, "Yasmine", "Ben Romdhane", R.MEMBRE), (None, "Zied", "Chaari", R.MEMBRE), (None, "Leïla", "Fourati", R.MEMBRE),
]
PROFESSIONS = ["Médecin généraliste", "Architecte", "Expert-comptable", "Enseignante universitaire", "Pharmacien", "Ingénieure en informatique", "Avocat"]


@skipUnless(os.environ.get("LIONSMED_SITE_AUDIT") == "1", "Audit d'affichage du site : activer LIONSMED_SITE_AUDIT")
class SiteAuditBrowserTests(StaticLiveServerTestCase):
    host = "127.0.0.1"

    def seed(self):
        """Un club complet : chaque module a de quoi afficher ses listes, fiches et états."""
        from apps.agenda import services as agenda_services
        from apps.agenda.models import Event, Registration
        from apps.agenda.tests.test_agenda import event
        from apps.communications.models import ContactRequest, OutboxMessage
        from apps.communications.services import notify, queue_member_broadcast
        from apps.documents.models import Document
        from apps.documents.scanning import ScanResult
        from apps.documents.services import upload_document
        from apps.documents.tests.test_documents import pdf
        from apps.dues.models import DuesRecord, DuesSchedule
        from apps.dues.tests.test_dues import lions_year
        from apps.editorial.publication import publish_content
        from apps.editorial.tests.test_public import content
        from apps.members.models import AssociationExperience, MembershipApplication
        from apps.satisfaction.models import SatisfactionPeriod
        from apps.satisfaction.services import create_period, submit_satisfaction
        from apps.voting.models import Vote
        from apps.voting.services import cast_vote, close_vote, create_and_open_vote

        now = timezone.now()
        users, named = [], {}
        for index, (key, first_name, last_name, role) in enumerate(PEOPLE):
            user = account(f"compte{index}@example.invalid", role=role)
            user.first_name, user.last_name = first_name, last_name
            user.save(update_fields=["first_name", "last_name"])
            profile = user.member_profile
            profile.profession = PROFESSIONS[index % len(PROFESSIONS)]
            profile.phone = f"+216 20 {100 + index} {200 + index}"
            profile.bio = "Membre engagé dans les actions de dépistage et d’accompagnement des familles à Sfax depuis plusieurs années."
            profile.directory_visible = index % 5 != 4
            profile.share_profession = profile.share_bio = index % 2 == 0
            profile.share_contacts = index % 3 == 0
            profile.share_experiences = profile.share_mandates = True
            profile.save()
            users.append(user)
            if key:
                named[key] = user
        president, member, secretary = named["president"], named["membre"], named["secretaire"]
        actives = [user for user, person in zip(users, PEOPLE) if person[3] != R.INVITE]

        year = lions_year()
        ClubState.objects.update_or_create(pk=1, defaults={"active_year": year})
        LionsYear.objects.create(starts_on=date(year.starts_on.year - 1, 7, 1), ends_on=year.starts_on, archived_at=now)
        DuesSchedule.objects.create(lions_year=year, tranche1_amount=100, tranche2_amount=150, updated_by=named["tresorier"])
        for index, user in enumerate(actives[:16]):
            DuesRecord.objects.create(profile=user.member_profile, lions_year=year, tranche1_paid=index % 3 != 0, tranche2_paid=index % 4 == 0,
                                      tranche1_paid_on=year.starts_on if index % 3 != 0 else None, note="Règlement par virement" if index % 5 == 0 else "")
        for user, function in [(president, "Président"), (secretary, "Secrétaire général"), (named["tresorier"], "Trésorière"), (users[7], "1er Vice-président")]:
            Mandate.objects.create(profile=user.member_profile, function=function, lions_year=year, starts_on=year.starts_on, ends_on=year.ends_on,
                                   validated_at=now, validated_by=president, public_authorized=True)
        for user in (president, member, secretary):
            AssociationExperience.objects.create(profile=user.member_profile, network="LEO", club="LEO Club Sfax Doyen", function="Chef du protocole", district="District 414",
                start_year=2016, end_year=2018, description="Organisation des cérémonies et accueil des délégations.", achievements="Prix du meilleur protocole 2017.")
            AssociationExperience.objects.create(profile=user.member_profile, network="LIONS", club="Lions Club Sfax-Méditerranée", function="Responsable des actions jeunesse", start_year=2021)
        profile = member.member_profile
        profile.public_profile_enabled, profile.public_slug, profile.public_title = True, "anis-besbes", "Responsable GMT"
        profile.save()

        events = []
        for index, (title, days, visibility) in enumerate([("Action interclubs « Grandir avec le diabète »", 5, "PUBLIC"), ("Cérémonie de passation", 5, "PRIVATE"),
                ("Collecte alimentaire de la rentrée", 10, "PUBLIC"), ("Réunion statutaire d’octobre", 16, "PRIVATE"), ("Assemblée générale ordinaire", 40, "PRIVATE")]):
            events.append(event(president, title=title, slug=f"evenement-{index}", starts_at=now + timedelta(days=days, hours=index), ends_at=now + timedelta(days=days, hours=index + 2),
                                location="Maison des associations, Sfax", visibility=visibility, summary="Rendez-vous du club ouvert aux membres et à leurs invités.",
                                body="Programme détaillé communiqué par le bureau.\n\nMerci de confirmer votre présence."))
        for user in actives[:6]:
            agenda_services.set_registration(actor=user, event=events[0], status=Registration.Status.CONFIRMED)
        agenda_services.set_registration(actor=member, event=events[1], status=Registration.Status.CANCELLED)

        for index, (title, axis) in enumerate([("Dépistage du diabète au marché central", "DIABETE"), ("Plantation de 200 arbres à Thyna", "ENVIRONNEMENT"), ("Cartables pour la rentrée scolaire", "JEUNESSE")]):
            action = content(president, "action", slug=f"action-{index}", title=title, axis=axis, summary="Une journée de service menée par les membres du club avec nos partenaires locaux.",
                             body="Nous avons accueilli plus de cent personnes.\n\nMerci aux bénévoles et aux partenaires.")
            publish_content(actor=president, obj=action, kind="action")
        content(president, "action", slug="action-brouillon", title="Caravane de santé (brouillon)")

        with patch("apps.documents.services.scan_bytes", return_value=ScanResult(True)):
            for title, category, visibility in [("Règlement intérieur du club", "GOUVERNANCE", "MEMBERS"), ("Budget prévisionnel 2026-2027", "FINANCIER", "BUREAU"),
                                                ("Compte rendu de l’assemblée générale", "GENERAL", "MEMBERS"), ("Circulaire du District 414", "DISTRICT", "RESPONSABLES")]:
                upload_document(actor=president, upload=pdf(), title=title, description="Document de référence pour l’année en cours.", category=category, visibility=visibility)

        opened = create_and_open_vote(actor=president, title="Budget prévisionnel 2026-2027", description="Approuvez-vous le budget présenté par le trésorier ?",
                                      mode=Vote.Mode.SINGLE, blank_allowed=True, option_labels=["Pour", "Contre", "Abstention"])
        for index, user in enumerate(actives[5:12]):
            cast_vote(actor=user, vote=opened, option_ids=[opened.options.all()[index % 2].pk])
        closed = create_and_open_vote(actor=president, title="Choix du thème de la soirée de gala", description="Une seule réponse possible.",
                                      mode=Vote.Mode.SINGLE, blank_allowed=False, option_labels=["Soirée andalouse", "Soirée Sfax d’antan", "Soirée blanche"])
        for index, user in enumerate(actives[:14]):
            cast_vote(actor=user, vote=closed, option_ids=[closed.options.all()[index % 3].pk])
        close_vote(actor=president, vote=closed)
        nominative = create_and_open_vote(actor=president, title="Élection du délégué au congrès", description="Scrutin nominatif annoncé aux électeurs.",
                                          mode=Vote.Mode.SINGLE, blank_allowed=False, option_labels=["Mohamed Elleuch", "Eya Dehech"], disclosure=Vote.Disclosure.NOMINATIVE)
        for index, user in enumerate(actives[:9]):
            cast_vote(actor=user, vote=nominative, option_ids=[nominative.options.all()[index % 2].pk])
        close_vote(actor=president, vote=nominative)

        period = create_period(actor=president, title="Satisfaction du mois d’octobre", description="Votre avis sur la vie du club ce mois-ci.", threshold=3,
                               opens_at=now - timedelta(hours=2), closes_at=now + timedelta(days=6), axes=("Organisation des réunions", "Communication interne", "Convivialité"))
        for index, user in enumerate(actives[6:13]):
            submit_satisfaction(actor=user, period=period, score=3 + index % 3, comment="Très bonne ambiance, continuons ainsi." if index % 2 else "",
                                axis_scores={axis.pk: 3 + (index + axis.pk) % 3 for axis in period.axes.all()})

        for user in (president, secretary, member, named["tresorier"]):
            for index, (category, title) in enumerate([("IMPORTANT", "Rappel : cotisation du premier semestre"), ("EVENT", "Nouvel événement — Cérémonie de passation"),
                    ("VOTE", "Un vote est ouvert : Budget prévisionnel"), ("SATISFACTION", "La consultation d’octobre est ouverte")]):
                notify(recipient=user, category=category, title=title, event_key=f"audit:{user.pk}:{index}", excerpt="Consultez votre espace membre pour en savoir plus.")
        for index, (name, subject, state) in enumerate([("Hakim Kchaou", "ADHESION", "RECEIVED"), ("Association Sfax Solidaire", "PARTENARIAT", "CONTACTED"), ("Radio Sfax", "PRESSE", "CLOSED")]):
            ContactRequest.objects.create(submission_key=uuid4(), name=name, email=f"contact{index}@example.invalid", phone="+216 20 123 456", subject=subject, state=state,
                message="Bonjour,\n\nNous souhaiterions échanger avec le club au sujet d’un projet commun pour la rentrée.\n\nCordialement.")
        for index, (first_name, last_name, state) in enumerate([("Skander", "Ben Salah", "RECEIVED"), ("Ines", "Kammoun", "FOLLOW_UP")]):
            MembershipApplication.objects.create(submission_key=uuid4(), first_name=first_name, last_name=last_name, email=f"candidat{index}@example.invalid", phone="+216 22 456 789",
                profession="Ingénieur", motivation="Je souhaite m’engager au service de ma ville aux côtés de membres actifs.", origin="MEMBRE", state=state)
        done = queue_member_broadcast(actor=president, subject="Réunion statutaire d’octobre", body="Chers amis,\n\nRendez-vous jeudi.", idempotency_key=uuid4(), member_ids=[u.pk for u in actives[:12]])[0]
        OutboxMessage.objects.filter(object_id=done.pk).update(state="SENT", attempts=1, sent_at=now)
        mixed = queue_member_broadcast(actor=president, subject="Invitation – Cérémonie de passation", body="Chers amis,\n\nVous êtes conviés.", idempotency_key=uuid4(),
                                       member_ids=[u.pk for u in actives[:8]], extra_emails=["mairie@example.invalid"])[0]
        rows = list(OutboxMessage.objects.filter(object_id=mixed.pk))
        OutboxMessage.objects.filter(pk__in=[row.pk for row in rows[:5]]).update(state="SENT", attempts=1, sent_at=now)
        OutboxMessage.objects.filter(pk__in=[row.pk for row in rows[5:8]]).update(state="FAILED", attempts=5, error_code="delivery_failed")

        # Pages sans lien entrant (ou réservées à une action), ajoutées au parcours.
        first_event, document = Event.objects.order_by("starts_at").first(), Document.objects.first()
        management = ["/espace/calendrier/?view=week", "/espace/calendrier/?view=day", "/espace/presences/", "/espace/statistiques/", "/espace/contenu/event/", "/espace/contenu/event/ajouter/", "/espace/mot-de-passe/modifie/", "/membres/anis-besbes/",
                      f"/espace/calendrier/evenements/{first_event.pk}/modifier/", f"/espace/presences/{first_event.pk}/", f"/espace/contenu/event/{first_event.pk}/",
                      f"/espace/votes/{opened.pk}/gestion/", f"/espace/documents/{document.pk}/", f"/espace/documents/gestion/{document.pk}/"]
        public = ["/membres/anis-besbes/", "/connexion/", "/mot-de-passe-oublie/", "/mot-de-passe-oublie/demande-recue/", "/mot-de-passe-reinitialise/",
                  "/candidature/", "/candidature/recue/", "/contact/", "/contact/recu/", "/page-inexistante/"]
        guest = named["invite"]
        reset = f"/reinitialiser/{urlsafe_base64_encode(force_bytes(guest.pk))}/{default_token_generator.make_token(guest)}/"
        # Session en attente du code de double authentification (aucun compte connecté).
        pending = Client().session
        pending["mfa_user_id"] = str(president.pk)
        pending.save()
        extras = {"president": management, "secretaire": management, "superadmin": management, "anonyme": public, "mfaSession": pending.session_key,
                  "membre": ["/membres/anis-besbes/", "/espace/calendrier/?view=week", "/espace/calendrier/?view=day"],
                  "presenceSheet": f"/espace/presences/{first_event.pk}/", "passwordReset": reset}
        return named, extras, SatisfactionPeriod.objects.count()

    def test_whole_site_display(self):
        media = TemporaryDirectory()
        self.addCleanup(media.cleanup)
        private_media = override_settings(PRIVATE_MEDIA_ROOT=Path(media.name))
        private_media.enable()
        self.addCleanup(private_media.disable)
        named, extras, _ = self.seed()
        cookies = {"anonyme": None}
        for key, user in named.items():
            client = Client()
            client.force_login(user)
            cookies[key] = client.cookies[settings.SESSION_COOKIE_NAME].value
        env = {**os.environ, "LIONSMED_BROWSER_URL": self.live_server_url, "LIONSMED_AUDIT_COOKIE": settings.SESSION_COOKIE_NAME,
               "LIONSMED_AUDIT_SESSIONS": json.dumps(cookies), "LIONSMED_AUDIT_EXTRA": json.dumps(extras)}
        result = subprocess.run(["node", str(Path(settings.BASE_DIR) / "tools/browser_site_audit.cjs")], env=env, capture_output=True, text=True, timeout=1800)
        print(result.stdout.strip())
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr[-4000:])
