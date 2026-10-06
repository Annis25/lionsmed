"""Boîtes e-mail institutionnelles : l'accès suit le rôle de la fonction, jamais la personne.

Les lettres entre crochets renvoient à la liste de contrôle du cahier des charges (A à U).
Aucun test ne contacte un serveur de messagerie : la relève passe par un faux serveur IMAP
et l'envoi par la boîte d'envoi en mémoire de Django.
"""
from datetime import datetime, timedelta, timezone as dt_timezone
from email.message import EmailMessage
from uuid import uuid4

from django.core import mail
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.communications.models import MemberEmailCampaign, Notification, OutboxMessage
from apps.communications.outbox import deliver_batch
from apps.communications.services import queue_member_broadcast
from apps.core.models import AuditEvent
from apps.core.tests.test_foundations import account
from apps.core.permissions import CAPABILITIES, can
from apps.governance.models import Role, RoleGrant
from apps.governance.services import set_role
from apps.members.models import MemberProfile

from .. import catalog
from ..access import holders, mailboxes_for, sender_for
from ..imap import Fetched, ImapSession, SyncError
from ..models import InboundEmail, MailboxState, OutgoingEmail
from ..parsing import NOTICE_DOMAIN, NOTICE_HEADER, NOTICE_SUBJECT
from ..services import NOTICES_PER_HOUR, send_message
from ..sync import sync_mailbox

SECRET = "Mot-de-passe-de-boite-9471"
PASSWORDS = {key: SECRET for key in ("president", "vice-president", "tresorier", "secretariat")}
PRESIDENT, VICE, TREASURY = catalog.get("president"), catalog.get("vice-president"), catalog.get("tresorier")


def raw_message(subject="Demande de partenariat", sender="Contact Externe <contact@example.org>", body="Bonjour, nous souhaitons vous rencontrer.",
                html=None, message_id=None, to="president@lionsmed.tn", headers=None):
    message = EmailMessage()
    message["From"], message["To"], message["Subject"] = sender, to, subject
    message["Message-ID"] = message_id or f"<{uuid4()}@example.org>"
    for name, value in (headers or {}).items():
        message[name] = value
    message.set_content(body)
    if html is not None:
        message.add_alternative(html, subtype="html")
    return message.as_bytes()


class FakeServer:
    """Serveur IMAP simulé : messages par UID, panne ou refus à la demande."""
    def __init__(self):
        self.uid_validity, self.messages, self.error, self.opened = 1, {}, None, 0

    def add(self, raw, uid=None):
        uid = uid or max(self.messages, default=0) + 1
        self.messages[uid] = raw
        return uid

    def session(self, credentials):
        server = self

        class Session:
            def open(self):
                server.opened += 1
                if server.error:
                    raise server.error
                return server.uid_validity

            def uids_after(self, last_uid):
                return sorted(uid for uid in server.messages if uid > last_uid)

            def fetch(self, uid, max_bytes):
                raw = server.messages[uid]
                return Fetched(uid=uid, received_at=datetime.now(tz=dt_timezone.utc), size=len(raw), raw=raw, complete=len(raw) <= max_bytes)

            def close(self):
                pass
        return Session()


@override_settings(MAILBOX_PASSWORDS=PASSWORDS)
class MailboxTestCase(TestCase):
    def setUp(self):
        self.secretary = self.person("secretaire@example.invalid", "Eya", Role.SECRETAIRE)
        self.president = self.person("anis@example.invalid", "Anis", Role.PRESIDENT)
        self.treasurer = self.person("tresoriere@example.invalid", "Leila", Role.TRESORIER)
        # Deux comptes pour un même rôle : ils partagent la boîte de la vice-présidence.
        self.vp1 = self.person("vp1@example.invalid", "Sami", Role.VICE_PRESIDENT)
        self.vp2 = self.person("vp2@example.invalid", "Rania", Role.VICE_PRESIDENT)
        self.member = account("membre@example.invalid", role=Role.MEMBRE)
        self.server = FakeServer()

    def person(self, email, first_name, role):
        user = account(email, role=role)
        user.first_name = first_name
        user.save(update_fields=["first_name"])
        return user

    def hand_over(self, outgoing, incoming, role):
        """Passation faite par le club dans « Membres et mandats » : le rôle change de titulaire."""
        set_role(actor=self.secretary, target_user=outgoing, role=Role.MEMBRE)
        set_role(actor=self.secretary, target_user=incoming, role=role)

    def sync(self, mailbox=PRESIDENT):
        # La relève suivante est possible aussitôt : le délai de reprise ne concerne que les pannes.
        return sync_mailbox(mailbox, session_factory=self.server.session)

    def ready(self, mailbox=PRESIDENT):
        """Première relève d'une boîte vide : les messages suivants sont « nouveaux »."""
        self.assertEqual(self.sync(mailbox)["status"], "ok")

    def url(self, name, mailbox=PRESIDENT, *args):
        return reverse("mailboxes:" + name, args=[mailbox.key, *args])

    def login(self, user):
        self.client.force_login(user)
        return self.client


class AccessTests(MailboxTestCase):
    def test_each_holder_reaches_only_the_mailbox_of_the_function_held(self):
        # [A] le Président n'a que sa boîte ; [B] le Trésorier n'ouvre pas celle du Président.
        self.assertEqual(mailboxes_for(self.president), [PRESIDENT])
        self.assertEqual(mailboxes_for(self.treasurer), [TREASURY])
        client = self.login(self.president)
        self.assertRedirects(client.get(reverse("mailboxes:home")), self.url("inbox"))
        self.assertContains(client.get(self.url("inbox")), "president@lionsmed.tn")
        self.assertEqual(client.get(self.url("inbox", TREASURY)).status_code, 403)
        self.assertEqual(client.get(self.url("sent", VICE)).status_code, 403)
        self.assertEqual(client.get(reverse("mailboxes:inbox", args=["boite-inconnue"])).status_code, 404)
        client = self.login(self.treasurer)
        for name in ("inbox", "sent", "compose"):
            self.assertEqual(client.get(self.url(name)).status_code, 403)
        self.assertRedirects(client.get(reverse("mailboxes:home")), self.url("inbox", TREASURY))

    def test_both_vice_presidents_share_one_mailbox_and_one_history(self):
        # [C] [D] [E] même boîte, mêmes messages pour les deux comptes du rôle Vice-président.
        self.assertEqual(mailboxes_for(self.vp1), [VICE])
        self.assertEqual(mailboxes_for(self.vp2), [VICE])
        self.assertEqual(set(holders(VICE)), {self.vp1, self.vp2})
        self.server.add(raw_message(subject="Réunion de zone", to="vice.president@lionsmed.tn"))
        self.sync(VICE)
        email = InboundEmail.objects.get()
        for user in (self.vp1, self.vp2):
            client = self.login(user)
            self.assertContains(client.get(self.url("inbox", VICE)), "Réunion de zone")
            self.assertContains(client.get(self.url("message", VICE, email.pk)), "Réunion de zone")
        # L'audit distingue les deux lecteurs d'une boîte partagée.
        readers = AuditEvent.objects.filter(action="mailbox.message_opened", object_id=str(email.pk)).values_list("actor_id", flat=True)
        self.assertEqual(set(readers), {self.vp1.pk, self.vp2.pk})
        self.assertContains(client.get(self.url("message", VICE, email.pk)), "Ouvert par Sami")

    def test_account_without_mailbox_has_no_messagerie(self):
        # [G] ni menu, ni page — y compris pour un rôle sans boîte (Bureau, GLT) et le compte technique.
        admin = account("admin@example.invalid", role=Role.SUPER_ADMIN)
        bureau = account("bureau@example.invalid", role=Role.BUREAU)
        glt = account("glt@example.invalid", role=Role.GLT)
        for user in (self.member, bureau, glt, admin):
            client = self.login(user)
            self.assertEqual(mailboxes_for(user), [])
            self.assertEqual(client.get(reverse("mailboxes:home")).status_code, 403)
            self.assertEqual(client.get(self.url("inbox")).status_code, 403)
            self.assertNotContains(client.get(reverse("core:dashboard")), "Messagerie")
        self.assertContains(self.login(self.president).get(reverse("core:dashboard")), "Messagerie")
        self.client.logout()
        self.assertIn("/connexion/", self.client.get(self.url("inbox")).url)

    def test_only_an_active_member_holding_the_role_right_now_opens_a_mailbox(self):
        self.assertTrue(can(self.treasurer, "mailbox.use", TREASURY))
        self.assertFalse(can(self.treasurer, "mailbox.use", PRESIDENT))
        self.assertFalse(can(self.treasurer, "mailbox.use", object()))
        # Rôle prévu pour plus tard, rôle retiré, profil suspendu ou invité, compte désactivé : pas d'accès.
        future = account("futur@example.invalid", role=None)
        RoleGrant.objects.create(user=future, role=Role.SECRETAIRE, starts_at=timezone.now() + timedelta(days=10))
        self.assertEqual(mailboxes_for(future), [])
        RoleGrant.objects.filter(user=self.vp2).update(revoked_at=timezone.now())
        self.assertEqual(mailboxes_for(self.vp2), [])
        self.assertEqual(holders(VICE), [self.vp1])
        MemberProfile.objects.filter(user=self.treasurer).update(status=MemberProfile.Status.SUSPENDED)
        self.assertEqual(mailboxes_for(self.treasurer), [])
        self.assertEqual(holders(TREASURY), [])
        MemberProfile.objects.filter(user=self.secretary).update(status=MemberProfile.Status.GUEST)
        self.assertEqual(mailboxes_for(self.secretary), [])
        self.president.is_active = False
        self.president.save(update_fields=["is_active"])
        self.assertEqual(holders(PRESIDENT), [])
        # Un mandat (« Notre bureau ») ne donne aucun accès : seul le rôle compte.
        from apps.governance.models import LionsYear, Mandate
        today = timezone.localdate()
        year = LionsYear.objects.create(starts_on=today - timedelta(days=60), ends_on=today + timedelta(days=300))
        Mandate.objects.create(profile=self.member.member_profile, function="Trésorier", lions_year=year,
            starts_on=year.starts_on, ends_on=year.ends_on, validated_at=timezone.now(), validated_by=self.vp1)
        self.assertEqual(mailboxes_for(self.member), [])
        # Rôle doté d'une boîte, mais boîte non reliée à Lionsmed (mot de passe absent du serveur).
        gmt = account("gmt@example.invalid", role=Role.GMT)
        self.assertEqual(mailboxes_for(gmt), [])
        with self.settings(MAILBOX_PASSWORDS={**PASSWORDS, "gmt": SECRET}):
            self.assertEqual(mailboxes_for(gmt), [catalog.get("gmt")])

    def test_each_of_the_ten_roles_opens_exactly_its_own_mailbox(self):
        self.assertEqual(len(catalog.MAILBOXES), 10)
        claimed = [role for mailbox in catalog.MAILBOXES for role in mailbox.roles]
        self.assertEqual(len(claimed), len(set(claimed)))  # aucun rôle n'ouvre deux boîtes
        self.assertEqual(set(claimed), set(CAPABILITIES["mailbox.use"]))
        self.assertFalse({Role.SUPER_ADMIN, Role.BUREAU, Role.GLT, Role.MEMBRE, Role.INVITE} & set(claimed))
        expected = {Role.PRESIDENT: "president@lionsmed.tn", Role.VICE_PRESIDENT: "vice.president@lionsmed.tn",
                    Role.SECRETAIRE: "secretariat@lionsmed.tn", Role.TRESORIER: "tresorier@lionsmed.tn",
                    Role.PRESIDENT_FONDATEUR: "president.fondateur@lionsmed.tn", Role.DIRECTEUR: "directeur@lionsmed.tn",
                    Role.GMT: "gmt@lionsmed.tn", Role.GST: "gst@lionsmed.tn", Role.LCIF: "lcif@lionsmed.tn",
                    Role.MARKETING_COMMUNICATION: "marketing.communication@lionsmed.tn"}
        with self.settings(MAILBOX_PASSWORDS={mailbox.key: SECRET for mailbox in catalog.MAILBOXES}):
            for index, (role, address) in enumerate(expected.items()):
                user = account(f"role{index}@example.invalid", role=role)
                self.assertEqual([mailbox.address for mailbox in mailboxes_for(user)], [address])

    def test_role_change_moves_reading_sending_and_history_to_the_new_holder(self):
        # [F] l'ancien titulaire perd tout, le nouveau reprend la boîte et son historique.
        self.server.add(raw_message(subject="Courrier du district"))
        self.sync()
        email = InboundEmail.objects.get()
        successor = self.person("successeur@example.invalid", "Karim", Role.MEMBRE)
        self.hand_over(self.president, successor, Role.PRESIDENT)
        self.assertEqual(mailboxes_for(self.president), [])
        self.assertEqual(holders(PRESIDENT), [successor])
        client = self.login(self.president)
        for target in (self.url("inbox"), self.url("message", PRESIDENT, email.pk), self.url("compose")):
            self.assertEqual(client.get(target).status_code, 403)
        self.assertNotContains(client.get(reverse("core:dashboard")), "Messagerie")
        with self.assertRaises(PermissionDenied):
            send_message(actor=self.president, mailbox=PRESIDENT, to=["a@example.org"], subject="x", body="y", idempotency_key=uuid4())
        client = self.login(successor)
        self.assertContains(client.get(self.url("inbox")), "Courrier du district")
        self.assertEqual(client.get(self.url("message", PRESIDENT, email.pk)).status_code, 200)
        # Rien n'a été réécrit : le message appartient toujours à la boîte, pas à une personne.
        self.assertEqual(InboundEmail.objects.get().mailbox, "president")

    def test_message_of_another_mailbox_cannot_be_opened_by_changing_the_address(self):
        # [R] identifiant d'un message d'une autre boîte : introuvable sous sa propre boîte, refusé sous l'autre.
        self.server.add(raw_message(subject="Relevé bancaire confidentiel", to="tresorier@lionsmed.tn"))
        self.sync(TREASURY)
        email = InboundEmail.objects.get()
        client = self.login(self.president)
        self.assertEqual(client.get(self.url("message", PRESIDENT, email.pk)).status_code, 404)
        self.assertEqual(client.get(self.url("message", TREASURY, email.pk)).status_code, 403)
        self.assertEqual(client.post(self.url("unread", PRESIDENT, email.pk)).status_code, 404)
        self.assertEqual(client.get(self.url("compose") + f"?reponse={email.pk}").status_code, 404)
        self.assertIsNone(InboundEmail.objects.get().read_at)


class SyncTests(MailboxTestCase):
    def test_message_is_imported_once_whatever_the_number_of_runs(self):
        # [J] [K] même UID, même Message-ID, ou boîte renumérotée par le serveur : jamais de doublon.
        self.server.add(raw_message(message_id="<unique-1@example.org>"))
        self.assertEqual(self.sync(), {"status": "ok", "imported": 1})
        self.assertEqual(self.sync(), {"status": "ok", "imported": 0})
        self.server.add(raw_message(subject="Copie", message_id="<unique-1@example.org>"))
        self.assertEqual(self.sync()["imported"], 0)
        self.server.uid_validity = 2
        self.assertEqual(self.sync()["imported"], 0)
        self.assertEqual(InboundEmail.objects.count(), 1)
        email = InboundEmail.objects.get()
        self.assertEqual((email.sender_name, email.sender_address, email.subject), ("Contact Externe", "contact@example.org", "Demande de partenariat"))
        self.assertEqual(email.recipients, [{"name": "", "address": "president@lionsmed.tn"}])
        self.assertIn("nous souhaitons vous rencontrer", email.body_text)
        self.assertIsNone(email.read_at)

    def test_overlapping_runs_do_not_process_the_same_mailbox(self):
        self.ready()
        MailboxState.objects.filter(mailbox="president").update(lease_until=timezone.now() + timedelta(minutes=5))
        self.server.add(raw_message())
        self.assertEqual(self.sync()["status"], "busy")
        self.assertEqual(InboundEmail.objects.count(), 0)

    def test_server_failure_never_crashes_and_keeps_the_last_messages(self):
        # [O] panne du serveur de messagerie : état noté, page disponible, anciens messages conservés.
        self.server.add(raw_message(subject="Avant la panne"))
        self.sync()
        self.server.error = SyncError("unreachable")
        MailboxState.objects.update(next_attempt_at=None)
        with self.assertLogs("lionsmed.mailboxes", level="WARNING") as logs:
            self.assertEqual(self.sync(), {"status": "unreachable", "imported": 0})
        self.assertEqual(logs.output, ["WARNING:lionsmed.mailboxes:mailbox_sync_failed mailbox=president code=unreachable"])
        state = MailboxState.objects.get(mailbox="president")
        self.assertEqual((state.last_error, state.failures), ("unreachable", 1))
        # Reprise espacée : la relève suivante n'insiste pas tout de suite.
        opened = self.server.opened
        self.assertEqual(self.sync()["status"], "deferred")
        self.assertEqual(self.server.opened, opened)
        page = self.login(self.president).get(self.url("inbox"))
        self.assertContains(page, "Impossible de synchroniser la boîte pour le moment.")
        self.assertContains(page, "Avant la panne")
        self.assertNotContains(page, "unreachable")
        self.assertEqual(AuditEvent.objects.filter(action="mailbox.sync_failed", object_id="president").count(), 1)
        # Retour à la normale : l'alerte disparaît.
        self.server.error = None
        MailboxState.objects.update(next_attempt_at=None)
        self.assertEqual(self.sync()["status"], "ok")
        self.assertNotContains(self.client.get(self.url("inbox")), "Impossible de synchroniser")

    def test_refused_password_backs_off_much_longer_than_a_network_failure(self):
        self.server.error = SyncError("auth_failed")
        with self.assertLogs("lionsmed.mailboxes", level="WARNING"):
            self.sync()
        state = MailboxState.objects.get(mailbox="president")
        self.assertGreaterEqual(state.next_attempt_at - timezone.now(), timedelta(minutes=14))

    def test_mailbox_password_never_reaches_a_page_a_log_or_the_database(self):
        # [P] ni dans la représentation du compte, ni dans une erreur, ni en base, ni dans une page.
        self.assertNotIn(SECRET, repr(catalog.account(PRESIDENT)) + str(catalog.account(PRESIDENT)))

        def explode(credentials):
            raise RuntimeError(f"LOGIN failed for {credentials.username} with {credentials.password}")
        with self.assertLogs("lionsmed.mailboxes", level="WARNING") as logs:
            result = sync_mailbox(PRESIDENT, session_factory=explode)
        self.assertEqual(result["status"], "unexpected")
        self.assertNotIn(SECRET, " ".join(logs.output))
        state = MailboxState.objects.get(mailbox="president")
        self.assertNotIn(SECRET, " ".join(str(value) for value in vars(state).values()))
        self.assertFalse(AuditEvent.objects.filter(result__contains="Mot-de-passe").exists())
        client = self.login(self.president)
        for target in (self.url("inbox"), self.url("sent"), self.url("compose"), reverse("communications:broadcast")):
            self.assertNotContains(client.get(target), SECRET)

    def test_unconfigured_mailbox_is_left_alone(self):
        self.assertEqual(sync_mailbox(catalog.get("gst"), session_factory=self.server.session), {"status": "inactive", "imported": 0})
        self.assertEqual(self.server.opened, 0)

    def test_dangerous_html_is_neutralised_before_storage_and_display(self):
        # [Q] script, gestionnaire d'événement, image de suivi, cadre et lien piégé ne ressortent jamais.
        html = ('<p onclick="voler()">Bonjour <b>Anis</b></p><script>alert("xss")</script>'
                '<img src="https://traceur.example/pixel.gif?id=42" onerror="alert(1)"><iframe src="https://piege.example"></iframe>'
                '<a href="javascript:alert(2)">cliquez</a> <a href="https://lions.example/programme">programme</a>'
                '<style>body{background:url(https://traceur.example/fond)}</style>')
        self.server.add(raw_message(html=html))
        self.sync()
        email = InboundEmail.objects.get()
        for forbidden in ("<script", "alert(", "onclick", "onerror", "traceur.example", "<iframe", "piege.example", "javascript:", "<img", "<style"):
            self.assertNotIn(forbidden, email.body_html)
        self.assertIn("<strong>Anis</strong>", email.body_html)
        self.assertIn('<a href="https://lions.example/programme" rel="noopener noreferrer nofollow" target="_blank">programme</a>', email.body_html)
        response = self.login(self.president).get(self.url("message", PRESIDENT, email.pk))
        content = response.content.decode()
        for forbidden in ("alert(", "onclick", "traceur.example", "piege.example", "javascript:"):
            self.assertNotIn(forbidden, content)
        self.assertContains(response, "<strong>Anis</strong>")
        # Seconde barrière : la page interdit au navigateur toute ressource extérieure.
        self.assertIn("img-src 'self' data:", response["Content-Security-Policy"])
        self.assertIn("default-src 'none'", response["Content-Security-Policy"])

    def test_text_only_message_is_escaped_and_attachments_are_listed_without_being_stored(self):
        message = EmailMessage()
        message["From"], message["To"], message["Subject"] = "a@example.org", "president@lionsmed.tn", "<b>Objet</b>"
        message["Message-ID"] = "<pj@example.org>"
        message.set_content("Texte <script>alert(3)</script> et https://lions.example/doc")
        message.add_attachment(b"%PDF-1.4 contenu", maintype="application", subtype="pdf", filename="rapport.pdf")
        self.server.add(message.as_bytes())
        self.sync()
        email = InboundEmail.objects.get()
        self.assertEqual(email.attachments, [{"name": "rapport.pdf", "type": "application/pdf", "size": 16}])
        response = self.login(self.president).get(self.url("message", PRESIDENT, email.pk))
        self.assertContains(response, "&lt;script&gt;alert(3)&lt;/script&gt;")
        self.assertContains(response, "&lt;b&gt;Objet&lt;/b&gt;")
        self.assertContains(response, "rapport.pdf")
        self.assertContains(response, "pas encore consultables dans Lionsmed")
        self.assertNotContains(response, "<script>alert(3)")

    def test_oversized_or_unreadable_message_never_blocks_the_following_ones(self):
        with self.settings(MAILBOX_MAX_MESSAGE_BYTES=400):
            self.server.add(raw_message(subject="Très gros", body="x" * 2000))
            self.server.add(raw_message(subject="Suivant"))
            self.assertEqual(self.sync()["imported"], 2)
        big = InboundEmail.objects.get(subject="Très gros")
        self.assertTrue(big.partial)
        self.assertIn("trop volumineux", big.body_text)
        self.assertTrue(InboundEmail.objects.filter(subject="Suivant", partial=False).exists())

    def test_reading_marks_the_message_read_and_it_can_be_marked_unread_again(self):
        self.server.add(raw_message())
        self.sync()
        email = InboundEmail.objects.get()
        client = self.login(self.president)
        self.assertContains(client.get(self.url("inbox")), "Non lu")
        client.get(self.url("message", PRESIDENT, email.pk))
        email.refresh_from_db()
        self.assertEqual(email.read_by, self.president)
        self.assertNotContains(client.get(self.url("inbox")), "Non lu")
        self.assertRedirects(client.post(self.url("unread", PRESIDENT, email.pk)), self.url("inbox"))
        email.refresh_from_db()
        self.assertIsNone(email.read_at)
        self.assertTrue(AuditEvent.objects.filter(action="mailbox.message_marked_unread", actor=self.president).exists())


class NotificationTests(MailboxTestCase):
    def notices(self):
        return OutboxMessage.objects.filter(kind="MAILBOX_NOTICE")

    def test_new_message_notifies_the_current_holder_at_the_personal_address(self):
        # [L] avis dans Lionsmed et par e-mail personnel, sans le contenu du message.
        self.ready()
        self.server.add(raw_message(body="Contenu confidentiel du partenariat."))
        self.sync()
        email = InboundEmail.objects.get()
        notification = Notification.objects.get()
        self.assertEqual((notification.recipient, notification.category, notification.title),
                         (self.president, "MESSAGE", "Nouveau message reçu sur president@lionsmed.tn"))
        self.assertEqual(self.notices().get().recipient, "anis@example.invalid")
        deliver_batch()
        sent = mail.outbox[0]
        self.assertEqual(sent.to, ["anis@example.invalid"])
        self.assertEqual(sent.subject, "[Nouveau message Lionsmed] president@lionsmed.tn — Demande de partenariat")
        self.assertIn("Bonjour Anis,", sent.body)
        self.assertIn("contact@example.org", sent.body)
        self.assertIn(f"http://testserver/espace/messagerie/president/message/{email.pk}/", sent.body)
        self.assertNotIn("Contenu confidentiel", sent.body + sent.alternatives[0][0])
        self.assertNotIn("president@lionsmed.tn", sent.from_email)
        self.assertEqual(sent.extra_headers["Auto-Submitted"], "auto-generated")
        # Le lien de la notification mène au message, pour le titulaire seulement.
        page = self.login(self.president).get(reverse("notifications:list"))
        self.assertContains(page, self.url("message", PRESIDENT, email.pk))

    def test_messages_already_present_at_first_sync_notify_nobody(self):
        self.server.add(raw_message(subject="Ancien courrier"))
        self.sync()
        self.assertEqual(InboundEmail.objects.count(), 1)
        self.assertFalse(Notification.objects.exists())
        self.assertFalse(self.notices().exists())

    def test_both_vice_presidents_are_notified(self):
        # [M]
        self.ready(VICE)
        self.server.add(raw_message(to="vice.president@lionsmed.tn"))
        self.sync(VICE)
        self.assertEqual(set(Notification.objects.values_list("recipient__email", flat=True)), {"vp1@example.invalid", "vp2@example.invalid"})
        self.assertEqual(set(self.notices().values_list("recipient", flat=True)), {"vp1@example.invalid", "vp2@example.invalid"})

    def test_after_a_role_change_only_the_new_holder_is_notified(self):
        # [N] y compris pour un avis mis en file juste avant le changement.
        self.ready()
        self.server.add(raw_message(subject="Avant le changement"))
        self.sync()
        successor = self.person("successeur@example.invalid", "Karim", Role.MEMBRE)
        self.hand_over(self.president, successor, Role.PRESIDENT)
        self.server.add(raw_message(subject="Après le changement"))
        self.sync()
        deliver_batch()
        self.assertEqual([message.to for message in mail.outbox], [["successeur@example.invalid"]])
        self.assertIn("Après le changement", mail.outbox[0].subject)
        stale = self.notices().get(recipient="anis@example.invalid")
        self.assertEqual((stale.state, stale.error_code), ("FAILED", "not_applicable"))
        # L'ancien titulaire garde la trace dans ses notifications, mais plus aucun lien vers la boîte.
        self.assertNotContains(self.login(self.president).get(reverse("notifications:list")), "/espace/messagerie/")

    def test_a_lionsmed_notice_coming_back_is_never_imported_and_never_loops(self):
        # [U] l'avis porte une marque ; revenu dans une boîte, il est ignoré.
        self.ready()
        self.server.add(raw_message())
        self.sync()
        deliver_batch()
        notice = mail.outbox[0]
        self.assertEqual(notice.extra_headers[NOTICE_HEADER], "mailbox")
        self.assertTrue(notice.extra_headers["Message-ID"].endswith(f"@{NOTICE_DOMAIN}>"))
        self.assertTrue(notice.subject.startswith(NOTICE_SUBJECT))
        # Redirection automatique de l'adresse personnelle vers la boîte : mêmes en-têtes.
        self.server.add(notice.message().as_bytes())
        self.assertEqual(self.sync()["imported"], 0)
        # Réponse automatique, réponse à l'avis, transfert de l'avis, avis de non-remise :
        # visibles dans la boîte, signalés dans Lionsmed, mais sans nouvel e-mail personnel.
        self.server.add(raw_message(subject="Absent du bureau", headers={"Auto-Submitted": "auto-replied"}))
        self.server.add(raw_message(subject="Re: avis", headers={"In-Reply-To": notice.extra_headers["Message-ID"]}))
        self.server.add(raw_message(subject=f"Fwd: {notice.subject}", sender="anis@example.invalid"))
        self.server.add(raw_message(subject="Undelivered Mail Returned to Sender", sender="MAILER-DAEMON@mail.lionsmed.tn"))
        self.assertEqual(self.sync()["imported"], 4)
        self.assertEqual(InboundEmail.objects.filter(automatic=True).count(), 4)
        self.assertEqual(Notification.objects.count(), 5)
        self.assertEqual(self.notices().count(), 1)

    def test_personal_notices_are_capped_per_mailbox_and_per_hour(self):
        self.ready()
        for index in range(NOTICES_PER_HOUR + 5):
            self.server.add(raw_message(subject=f"Message {index}"))
        with self.settings(MAILBOX_SYNC_BATCH=100):
            self.sync()
        self.assertEqual(InboundEmail.objects.count(), NOTICES_PER_HOUR + 5)
        self.assertEqual(Notification.objects.count(), NOTICES_PER_HOUR + 5)
        self.assertEqual(self.notices().count(), NOTICES_PER_HOUR)


class SendingTests(MailboxTestCase):
    def compose(self, client, box=PRESIDENT, query="", **changes):
        data = {"message_key": str(uuid4()), "to": "partenaire@example.org", "cc": "", "subject": "Notre rencontre", "body": "Bonjour,\nMerci pour votre message."}
        data.update(changes)
        return client.post(self.url("compose", box) + query, data)

    def test_message_leaves_from_the_institutional_address_through_the_outbox(self):
        # [H] expéditeur = la boîte ; [T] « Envoyé » = accepté par le serveur, rien de plus.
        client = self.login(self.president)
        self.assertNotContains(client.get(self.url("compose")), 'name="from')
        response = self.compose(client, to="partenaire@example.org, autre@example.org", cc="copie@example.org")
        outgoing = OutgoingEmail.objects.get()
        self.assertRedirects(response, self.url("sent_detail", PRESIDENT, outgoing.pk))
        self.assertEqual((outgoing.mailbox, outgoing.author), ("president", self.president))
        rows = OutboxMessage.objects.filter(kind="MAILBOX_MESSAGE", object_id=outgoing.pk)
        self.assertEqual(set(rows.values_list("recipient", "sender_mailbox")),
                         {("partenaire@example.org", "president"), ("autre@example.org", "president"), ("copie@example.org", "president")})
        self.assertEqual(len(mail.outbox), 0)  # rien de synchrone : tout passe par l'outbox
        self.assertContains(client.get(self.url("sent_detail", PRESIDENT, outgoing.pk)), "En attente")
        deliver_batch()
        self.assertEqual(len(mail.outbox), 3)
        for sent in mail.outbox:
            self.assertEqual(sent.from_email, "Lions Club Sfax-Méditerranée — Présidence <president@lionsmed.tn>")
            self.assertNotIn("anis@example.invalid", sent.message().as_string())
            self.assertEqual(sent.extra_headers["To"], "partenaire@example.org, autre@example.org")
            self.assertEqual(sent.extra_headers["Cc"], "copie@example.org")
            self.assertEqual(sent.extra_headers["Message-ID"], f"<{outgoing.pk}@lionsmed.tn>")
            self.assertEqual(sent.body.strip(), "Bonjour,\nMerci pour votre message.")
        self.assertEqual({tuple(sent.to) for sent in mail.outbox}, {("partenaire@example.org",), ("autre@example.org",), ("copie@example.org",)})
        self.assertEqual(set(rows.values_list("state", flat=True)), {"SENT"})
        page = client.get(self.url("sent_detail", PRESIDENT, outgoing.pk))
        self.assertContains(page, "Envoyé")
        self.assertContains(page, "le serveur de messagerie a accepté le message")
        self.assertNotContains(page, "Délivré")
        self.assertContains(client.get(self.url("sent")), "Notre rencontre")
        self.assertTrue(AuditEvent.objects.filter(action="mailbox.message_sent", actor=self.president, object_id=str(outgoing.pk)).exists())

    def test_forged_post_for_another_mailbox_is_refused(self):
        # [I] ni par l'URL d'une autre boîte, ni par un champ ajouté, ni par le service.
        client = self.login(self.treasurer)
        self.assertEqual(self.compose(client).status_code, 403)
        self.compose(client, TREASURY, **{"from": "president@lionsmed.tn", "mailbox": "president", "sender_mailbox": "president"})
        self.assertEqual(OutgoingEmail.objects.get().mailbox, "tresorier")
        with self.assertRaises(PermissionDenied):
            send_message(actor=self.treasurer, mailbox=PRESIDENT, to=["a@example.org"], subject="x", body="y", idempotency_key=uuid4())
        self.assertEqual(self.compose(self.login(self.member)).status_code, 403)
        self.assertEqual(OutgoingEmail.objects.filter(mailbox="president").count(), 0)

    def test_sending_requires_a_csrf_token(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.president)
        self.assertEqual(self.compose(client).status_code, 403)
        self.assertFalse(OutgoingEmail.objects.exists())

    def test_addresses_and_subject_cannot_inject_headers(self):
        client = self.login(self.president)
        self.assertContains(self.compose(client, to="victime@example.org\nBcc: espion@example.org"), "Adresse(s) invalide(s)")
        self.assertContains(self.compose(client, to="pas-une-adresse"), "Adresse(s) invalide(s)")
        self.assertContains(self.compose(client, to=", ".join(f"a{i}@example.org" for i in range(11))), "10 destinataires maximum")
        self.assertFalse(OutgoingEmail.objects.exists())
        self.compose(client, subject="Objet\r\nBcc: espion@example.org")
        deliver_batch()
        self.assertEqual(mail.outbox[0].subject, "Objet Bcc: espion@example.org")
        self.assertNotIn("\nBcc:", mail.outbox[0].message().as_string())
        with self.assertRaises(ValidationError):
            send_message(actor=self.president, mailbox=PRESIDENT, to=["a@example.org\r\nBcc: b@example.org"], subject="x", body="y", idempotency_key=uuid4())

    def test_double_submission_sends_once(self):
        client = self.login(self.president)
        key = str(uuid4())
        self.compose(client, message_key=key)
        self.compose(client, message_key=key)
        self.assertEqual(OutgoingEmail.objects.count(), 1)
        self.assertEqual(OutboxMessage.objects.filter(kind="MAILBOX_MESSAGE").count(), 1)

    def test_reply_goes_to_the_sender_with_the_thread_headers(self):
        self.server.add(raw_message(message_id="<question@example.org>", headers={"Reply-To": "secretariat-externe@example.org", "Cc": "temoin@example.org"}))
        self.sync()
        email = InboundEmail.objects.get()
        client = self.login(self.president)
        form = client.get(self.url("compose") + f"?reponse={email.pk}&tous=1").context["form"]
        self.assertEqual(form.initial["to"], "secretariat-externe@example.org")
        self.assertEqual(form.initial["cc"], "temoin@example.org")
        self.assertEqual(form.initial["subject"], "Re: Demande de partenariat")
        self.assertIn("> Bonjour, nous souhaitons vous rencontrer.", form.initial["body"])
        self.compose(client, query=f"?reponse={email.pk}", to=form.initial["to"], subject=form.initial["subject"])
        outgoing = OutgoingEmail.objects.get()
        self.assertEqual(outgoing.in_reply_to, email)
        deliver_batch()
        self.assertEqual(mail.outbox[0].extra_headers["In-Reply-To"], "<question@example.org>")
        self.assertEqual(mail.outbox[0].extra_headers["References"], "<question@example.org>")
        self.assertTrue(AuditEvent.objects.filter(action="mailbox.reply_sent", actor=self.president).exists())

    def test_failed_delivery_is_reported_and_retried_on_the_same_row(self):
        client = self.login(self.president)
        self.compose(client)
        outgoing = OutgoingEmail.objects.get()
        # Boîte retirée de la configuration entre la mise en file et l'envoi : aucun repli
        # sur une autre identité, le message attend.
        with self.settings(MAILBOX_PASSWORDS={}):
            deliver_batch()
        row = OutboxMessage.objects.get(kind="MAILBOX_MESSAGE")
        self.assertEqual((row.state, row.error_code), ("PENDING", "sender_unavailable"))
        self.assertEqual(len(mail.outbox), 0)
        OutboxMessage.objects.filter(pk=row.pk).update(state="FAILED", error_code="delivery_failed")
        page = client.get(self.url("sent_detail", PRESIDENT, outgoing.pk))
        self.assertContains(page, "Réessayer l’envoi en échec")
        client.post(self.url("sent_detail", PRESIDENT, outgoing.pk))
        row.refresh_from_db()
        self.assertEqual((row.state, row.attempts), ("PENDING", 0))
        self.assertEqual(OutboxMessage.objects.filter(kind="MAILBOX_MESSAGE").count(), 1)
        self.assertEqual(self.login(self.treasurer).post(self.url("sent_detail", PRESIDENT, outgoing.pk)).status_code, 403)


class CommunicationSenderTests(MailboxTestCase):
    def queue(self, actor, **extra):
        return queue_member_broadcast(actor=actor, subject="Assemblée générale", body="Rendez-vous samedi.",
            idempotency_key=uuid4(), member_ids=[self.member.pk], **extra)[0]

    def test_campaign_leaves_from_the_function_address_of_its_author(self):
        # [S] Président → president@, Trésorier → tresorier@, sans rien saisir.
        campaign = self.queue(self.president)
        self.assertEqual(campaign.sender_mailbox, "president")
        self.assertEqual(self.queue(self.treasurer).sender_mailbox, "tresorier")
        deliver_batch()
        self.assertEqual({sent.from_email for sent in mail.outbox},
                         {"Lions Club Sfax-Méditerranée — Présidence <president@lionsmed.tn>",
                          "Lions Club Sfax-Méditerranée — Trésorerie <tresorier@lionsmed.tn>"})
        self.assertEqual(set(OutboxMessage.objects.filter(kind="MEMBER_BROADCAST").values_list("state", flat=True)), {"SENT"})
        page = self.login(self.president).get(reverse("communications:broadcast_detail", args=[campaign.pk]))
        self.assertContains(page, "president@lionsmed.tn")
        self.assertContains(self.client.get(reverse("communications:broadcast")), "Envoyé depuis <strong>president@lionsmed.tn</strong>")

    def test_author_without_mailbox_keeps_the_general_address(self):
        bureau = account("bureau@example.invalid", role=Role.BUREAU)
        campaign = self.queue(bureau)
        self.assertEqual(campaign.sender_mailbox, "")
        deliver_batch()
        self.assertEqual(mail.outbox[0].from_email, "noreply@example.invalid")
        self.assertNotContains(self.login(bureau).get(reverse("communications:broadcast")), "Envoyé depuis")
        # Rôle doté d'une boîte, mais boîte non reliée à Lionsmed : adresse générale, comme avant.
        with self.settings(MAILBOX_PASSWORDS={}):
            self.assertEqual(self.queue(self.president).sender_mailbox, "")

    def test_another_function_address_cannot_be_forged(self):
        # L'adresse d'envoi ne se choisit nulle part : un champ ajouté au formulaire est sans effet.
        self.assertEqual(sender_for(self.treasurer), TREASURY)
        self.assertIsNone(sender_for(self.member))
        with self.assertRaises(TypeError):
            self.queue(self.treasurer, sender_mailbox="president")
        client = self.login(self.treasurer)
        page = client.get(reverse("communications:broadcast"))
        self.assertNotContains(page, 'name="sender_mailbox"')
        client.post(reverse("communications:broadcast"), {"campaign_key": str(uuid4()), "subject": "Objet", "body": "Texte",
            "members": [str(self.member.pk)], "extra_emails": "", "action": "send", "confirmed": "yes", "sender_mailbox": "president"})
        self.assertEqual(list(MemberEmailCampaign.objects.values_list("sender_mailbox", flat=True)), ["tresorier"])


class ImapSessionTests(TestCase):
    """Dialogue IMAP réel de la classe, face à des réponses au format de la bibliothèque standard."""
    def connection(self, **overrides):
        from unittest.mock import MagicMock
        raw = raw_message(message_id="<imap@example.org>")
        connection = MagicMock()
        connection.select.return_value = ("OK", [b"3"])
        connection.response.return_value = ("UIDVALIDITY", [b"1717171717"])

        def uid(command, *args):
            if command == "SEARCH":
                return "OK", [b"4 7 9"]
            if "RFC822.SIZE" in args[1]:
                return "OK", [b'2 (UID 7 RFC822.SIZE %d INTERNALDATE "06-Oct-2026 18:27:01 +0100")' % len(raw)]
            return "OK", [(b"2 (UID 7 BODY[] {%d}" % len(raw), raw), b")"]
        connection.uid.side_effect = uid
        for name, value in overrides.items():
            setattr(connection, name, value)
        return connection, raw

    def session(self, connection):
        from unittest.mock import patch
        patcher = patch("apps.mailboxes.imap.imaplib.IMAP4_SSL", return_value=connection)
        self.addCleanup(patcher.stop)
        self.factory = patcher.start()
        return ImapSession(catalog.Account("president@lionsmed.tn", SECRET))

    def test_session_reads_without_touching_the_server_state(self):
        connection, raw = self.connection()
        session = self.session(connection)
        self.assertEqual(session.open(), 1717171717)
        self.assertEqual(self.factory.call_args.args, ("mail.lionsmed.tn", 993))
        connection.login.assert_called_once_with("president@lionsmed.tn", SECRET)
        connection.select.assert_called_once_with("INBOX", readonly=True)
        self.assertEqual(session.uids_after(4), [7, 9])  # « n:* » peut renvoyer un UID plus ancien
        fetched = session.fetch(7, max_bytes=10_000_000)
        self.assertEqual((fetched.uid, fetched.size, fetched.raw, fetched.complete), (7, len(raw), raw, True))
        self.assertEqual(fetched.received_at.astimezone(dt_timezone.utc).hour, 17)
        commands = [call.args for call in connection.uid.call_args_list]
        self.assertIn(("FETCH", "7", "(BODY.PEEK[])"), commands)  # PEEK : rien n'est marqué lu sur le serveur
        self.assertEqual(session.fetch(7, max_bytes=10).complete, False)
        self.assertIn(("FETCH", "7", "(BODY.PEEK[HEADER])"), [call.args for call in connection.uid.call_args_list])
        session.close()
        connection.logout.assert_called_once()
        for forbidden in ("store", "expunge", "append", "delete", "copy"):
            self.assertFalse(getattr(connection, forbidden).called)

    def test_refused_login_becomes_a_fixed_code_without_the_server_text(self):
        import imaplib
        from unittest.mock import MagicMock
        connection, _ = self.connection(login=MagicMock(side_effect=imaplib.IMAP4.error(f"[AUTHENTICATIONFAILED] {SECRET}")))
        with self.assertRaises(SyncError) as caught:
            self.session(connection).open()
        self.assertEqual(caught.exception.code, "auth_failed")
        self.assertNotIn(SECRET, str(caught.exception))
        self.assertIsNone(caught.exception.__cause__)

    def test_unreachable_server_and_vanished_message_are_handled(self):
        from unittest.mock import patch
        with patch("apps.mailboxes.imap.imaplib.IMAP4_SSL", side_effect=OSError("réseau")):
            with self.assertRaises(SyncError) as caught:
                ImapSession(catalog.Account("a", "b")).open()
        self.assertEqual(caught.exception.code, "unreachable")
        connection, _ = self.connection()
        connection.uid.side_effect = lambda command, *args: ("OK", [None])
        session = self.session(connection)
        session.open()
        self.assertIsNone(session.fetch(12, max_bytes=1000))
