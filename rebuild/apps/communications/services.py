from django.conf import settings
from django.core.exceptions import PermissionDenied,ValidationError
from django.db import transaction
from django.utils import timezone
from django.core.validators import validate_email
from apps.core.permissions import can, effective_role
from apps.editorial.publication import require,audit
from apps.governance.models import Role
from apps.members.models import MembershipApplication
from .models import ContactRequest,OutboxMessage,Notification,MemberEmailCampaign

Audience = MemberEmailCampaign.Audience
# Rôles jamais qualifiés de « responsables » même s'ils étaient un jour ajoutés à
# BROADCAST_EMAIL_ROLES : définition métier fixe, indépendante de la liste des rôles
# autorisés à déclencher une diffusion (apps.core.permissions.BROADCAST_EMAIL_ROLES).
_NOT_RESPONSIBLE = frozenset({Role.MEMBRE, Role.INVITE})

@transaction.atomic
def submit(form):
    if not form.is_valid():raise ValidationError("Formulaire invalide.")
    Model=type(form.instance)
    defaults={key:form.cleaned_data[key] for key in form.Meta.fields}
    obj,created=Model.objects.get_or_create(submission_key=form.cleaned_data["submission_token"],defaults=defaults)
    if created:
        if isinstance(obj,MembershipApplication):
            OutboxMessage.objects.create(event_key="application:"+str(obj.pk),kind="APPLICATION",recipient=obj.email,object_id=obj.pk)
        elif settings.CONTACT_RECIPIENT:
            validate_email(settings.CONTACT_RECIPIENT)
            OutboxMessage.objects.create(event_key="contact:"+str(obj.pk),kind="CONTACT",recipient=settings.CONTACT_RECIPIENT,object_id=obj.pk)
    return obj

@transaction.atomic
def change_state(*,actor,obj,state):
    kind="application" if isinstance(obj,MembershipApplication) else "contact"
    obj=type(obj).objects.select_for_update().get(pk=obj.pk)
    require(actor,kind+".manage",obj)
    if state not in {"RECEIVED","CONTACTED","FOLLOW_UP","CLOSED"}:raise ValidationError("État invalide.")
    obj.state=state;obj.full_clean();obj.save(update_fields=["state","updated_at"])
    audit(actor,kind+".state_changed",obj)
    return obj

@transaction.atomic
def notify(*,recipient,category,title,event_key,excerpt="",target_kind="",target_id="",email=False,outbox_kind=None):
    """Intention in-app idempotente ; e-mail facultatif réutilisant l'outbox existante, jamais une file séparée."""
    if category not in Notification.Category.values:raise ValidationError("Catégorie de notification invalide.")
    notification,created=Notification.objects.get_or_create(event_key=event_key,defaults={
        "recipient":recipient,"category":category,"title":title[:180],"excerpt":excerpt[:300],
        "target_kind":target_kind[:20],"target_id":str(target_id)[:64]})
    if created and email and recipient.email:
        kind=outbox_kind or {"IMPORTANT":"IMPORTANT","EVENT":"EVENT_REMINDER","DOCUMENT":"DOCUMENT"}.get(category)
        if kind:OutboxMessage.objects.get_or_create(event_key="outbox:"+event_key,defaults={
            "kind":kind,"recipient":recipient.email,"object_id":notification.pk})
    return notification

@transaction.atomic
def send_important_notification(*,actor,recipient,title,excerpt):
    if not can(actor,"notification.send"):raise PermissionDenied
    import uuid
    notification=notify(recipient=recipient,category="IMPORTANT",title=title,excerpt=excerpt,
        event_key=f"important:{uuid.uuid4()}",target_kind="",target_id="",email=True)
    audit(actor,"notification.sent",notification)
    return notification


def eligible_broadcast_members():
    """[(compte, rôle effectif)] des membres auxquels une communication peut être adressée.

    Seule définition de l'éligibilité, partagée par la liste de sélection, « Tout
    sélectionner », les annonces d'agenda et la validation des envois : profil ACTIVE,
    compte actif, adresse renseignée, rôle résolu sans ambiguïté et différent d'INVITE
    (effective_role() refuse déjà de trancher un rôle ambigu — voir apps.core.permissions).
    Invités, suspendus et comptes désactivés n'y figurent donc jamais."""
    from apps.members.models import MemberProfile
    profiles = MemberProfile.objects.filter(
        status=MemberProfile.Status.ACTIVE, user__is_active=True,
    ).select_related("user").order_by("user__first_name", "user__last_name", "user__email")
    eligible = []
    for profile in profiles:
        role = effective_role(profile.user)
        if role is not None and role != Role.INVITE and profile.user.email:
            eligible.append((profile.user, role))
    return eligible


def is_responsible(role):
    """Rôle actif différent de MEMBRE/INVITE — résolu uniquement via la logique
    officielle effective_role(), jamais une liste de rôles recopiée à la main."""
    return role not in _NOT_RESPONSIBLE


def broadcast_recipients(audience=Audience.ALL_ACTIVE):
    """Groupe entier de membres éligibles (annonces d'agenda, rappels, raccourcis de
    sélection). ALL_ACTIVE : tout rôle métier. RESPONSIBLES : voir is_responsible()."""
    if audience not in (Audience.ALL_ACTIVE, Audience.RESPONSIBLES):
        raise ValidationError("Audience invalide.")
    return [user for user, role in eligible_broadcast_members()
            if audience == Audience.ALL_ACTIVE or is_responsible(role)]


INELIGIBLE_EXTERNAL_MESSAGE = ("Cette adresse appartient à un compte du club qui ne peut pas recevoir de communication "
                               "(compte inactif, suspendu ou invité) : %s. Retirez-la pour continuer.")


def ineligible_known_addresses(addresses, eligible):
    """Adresses « externes » qui sont en réalité celles d'un compte connu mais non
    éligible : le champ externe ne doit jamais servir à contourner l'éligibilité.

    Une adresse sans compte (véritable externe) et celle d'un membre éligible non coché
    restent permises. Les adresses de comptes sont stockées recadrées et en minuscules
    (contrainte user_email_normalized), d'où la comparaison directe."""
    from django.contrib.auth import get_user_model
    typed = {address.strip().lower(): address.strip() for address in addresses}
    known = get_user_model().objects.filter(email__in=list(typed)).exclude(
        pk__in=[user.pk for user, _ in eligible]).values_list("email", flat=True)
    return sorted(typed[email] for email in known)


def _resolve_selection(member_ids, extra_emails):
    eligible = eligible_broadcast_members()
    by_id = {str(user.pk): user for user, _ in eligible}
    wanted = {str(value) for value in member_ids}
    if not wanted <= by_id.keys():
        # Identifiant inconnu, invité, suspendu, désactivé ou fabriqué : refus explicite
        # plutôt qu'un retrait silencieux, l'auteur doit savoir que sa sélection a changé.
        raise ValidationError("Un membre sélectionné n’est plus disponible pour la communication. Vérifiez la sélection.")
    members = [user for key, user in by_id.items() if key in wanted]
    seen = {member.email.strip().lower() for member in members}
    external = []
    for email in extra_emails:
        address = email.strip()
        key = address.lower()
        if not key or key in seen:
            continue
        validate_email(address)
        seen.add(key)
        external.append(address)
    blocked = ineligible_known_addresses(external, eligible)
    if blocked:
        raise ValidationError(INELIGIBLE_EXTERNAL_MESSAGE % ", ".join(blocked))
    return members, external, eligible


def resolve_broadcast_selection(member_ids, extra_emails):
    """(membres, externes) réellement destinataires, recalculés côté serveur.

    Les identifiants transmis par le navigateur ne sont jamais crus : seuls les membres
    éligibles à l'instant du calcul sont acceptés, tout autre identifiant lève
    ValidationError — de même qu'une adresse externe qui est celle d'un compte non
    éligible. Les adresses externes sont indépendantes de la sélection : sans
    membre coché, elles sont les seules destinataires. Dédoublonnage insensible à la
    casse — une adresse externe identique à celle d'un membre sélectionné est absorbée
    par celui-ci, jamais envoyée deux fois."""
    members, external, _ = _resolve_selection(member_ids, extra_emails)
    return members, external


def _audience_label(members, eligible):
    selected = {member.pk for member in members}
    if selected and selected == {user.pk for user, _ in eligible}:
        return Audience.ALL_ACTIVE
    if selected and selected == {user.pk for user, role in eligible if is_responsible(role)}:
        return Audience.RESPONSIBLES
    return Audience.SELECTION


def _external_event_key(campaign_id, email):
    import hashlib
    digest = hashlib.sha1(email.strip().lower().encode()).hexdigest()
    return f"broadcast:{campaign_id}:ext:{digest}"


@transaction.atomic
def queue_member_broadcast(*, actor, subject, body, idempotency_key, member_ids=(), extra_emails=(), sender_mailbox=""):
    """Met en file un e-mail individuel par destinataire : membres cochés et adresses
    externes, jamais un groupe implicite. Sans member_ids, aucun membre ne reçoit rien.

    L'expéditeur est décidé ici : la boîte institutionnelle de l'auteur s'il en tient une
    (apps.mailboxes.access.sender_for), sinon l'adresse générale du site. `sender_mailbox`
    ne sert qu'à choisir entre plusieurs boîtes tenues ; toute autre valeur est refusée."""
    if not can(actor, "communication.send_member_broadcast"):
        raise PermissionDenied
    from apps.mailboxes.access import sender_for
    from django.contrib.auth import get_user_model
    # Verrou sur l'auteur : deux soumissions simultanées du même formulaire s'exécutent
    # l'une après l'autre, la seconde retrouve la campagne créée par la première.
    actor = get_user_model().objects.select_for_update().get(pk=actor.pk)
    existing = MemberEmailCampaign.objects.filter(idempotency_key=idempotency_key).first()
    if existing is not None:
        # Une resoumission du même POST est un succès idempotent, sans second envoi.
        return existing, False
    members, external, eligible = _resolve_selection(member_ids, extra_emails)
    if not members and not external:
        raise ValidationError("Sélectionnez au moins un membre ou ajoutez une adresse externe.")
    mailbox = sender_for(actor, sender_mailbox or "")
    sender = mailbox.key if mailbox else ""
    campaign, created = MemberEmailCampaign.objects.get_or_create(
        idempotency_key=idempotency_key,
        defaults={"subject": subject, "body": body, "created_by": actor, "sender_mailbox": sender,
                  "audience": _audience_label(members, eligible), "external_emails": external},
    )
    if not created:
        return campaign, False
    messages = [OutboxMessage(
        event_key=f"broadcast:{campaign.pk}:{recipient.pk}", kind="MEMBER_BROADCAST",
        recipient=recipient.email, object_id=campaign.pk, sender_mailbox=sender,
    ) for recipient in members]
    messages += [OutboxMessage(
        event_key=_external_event_key(campaign.pk, email), kind="MEMBER_BROADCAST",
        recipient=email, object_id=campaign.pk, sender_mailbox=sender,
    ) for email in external]
    OutboxMessage.objects.bulk_create(messages, ignore_conflicts=True)
    campaign.recipient_count = campaign.queued_count = len(messages)
    campaign.internal_recipient_count = len(members)
    campaign.save(update_fields=["recipient_count", "queued_count", "internal_recipient_count"])
    audit(actor, "communication.member_broadcast_queued", campaign)
    return campaign, True


def refresh_campaign_status(campaign_id):
    """Consolide les états depuis l'outbox, sans conserver de données supplémentaires."""
    campaign = MemberEmailCampaign.objects.filter(pk=campaign_id).first()
    if campaign is None:
        return
    rows = OutboxMessage.objects.filter(kind="MEMBER_BROADCAST", object_id=campaign.pk)
    sent = rows.filter(state="SENT").count()
    failed = rows.filter(state="FAILED").count()
    terminal = sent + failed == campaign.queued_count
    campaign.sent_count, campaign.failed_count = sent, failed
    if terminal:
        campaign.status = MemberEmailCampaign.Status.SENT if not failed else MemberEmailCampaign.Status.PARTIAL
        campaign.sent_at = timezone.now()
    else:
        # Une relance manuelle (retry_failed_broadcast) rouvre une campagne déjà close.
        campaign.status = MemberEmailCampaign.Status.QUEUED
        campaign.sent_at = None
    campaign.save(update_fields=["sent_count", "failed_count", "status", "sent_at"])


# Échecs de livraison uniquement. « not_applicable » (compte désactivé ou adresse
# modifiée avant l'envoi) est un refus métier définitif : le relancer ne changerait rien.
RETRYABLE_ERROR_CODES = frozenset({"delivery_failed", "recipient_refused", "attempt_limit", "sender_unavailable"})


@transaction.atomic
def retry_failed_broadcast(*, actor, campaign):
    """Remet en file les échecs de livraison d'une campagne, dans l'outbox existante.

    Aucune ligne n'est créée : chaque message garde son identifiant, son event_key et
    donc son Message-ID. Seul l'état FAILED est repris, en une seule requête : un double
    clic ne relance rien une seconde fois, et un message PENDING, SENDING ou SENT n'est
    jamais touché. Le compteur de tentatives repart de zéro (c'est le budget de reprise
    automatique de deliver_batch, pas un historique) ; la relance elle-même est tracée
    dans le journal d'audit."""
    if not can(actor, "communication.send_member_broadcast"):
        raise PermissionDenied
    campaign = MemberEmailCampaign.objects.select_for_update().get(pk=campaign.pk)
    retried = OutboxMessage.objects.filter(
        kind="MEMBER_BROADCAST", object_id=campaign.pk, state="FAILED", error_code__in=RETRYABLE_ERROR_CODES,
    ).update(state="PENDING", attempts=0, available_at=timezone.now(), error_code="",
             lease_token=None, lease_until=None, sent_at=None)
    if retried:
        audit(actor, "communication.member_broadcast_retried", campaign)
        refresh_campaign_status(campaign.pk)
    return retried
