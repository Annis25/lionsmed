"""Lectures de la page Communication : liste des membres sélectionnables et suivi des envois.

Le suivi est toujours recalculé depuis l'outbox, seule source de vérité de l'état d'un
message : aucun statut n'est dupliqué pour l'affichage, et « Envoyé » ne signifie jamais
autre chose que « accepté par le serveur de messagerie » (état SENT de l'outbox)."""
from uuid import UUID

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db.models import Count, Q

from apps.governance.models import Role
from .models import MemberEmailCampaign, OutboxMessage
from .services import RETRYABLE_ERROR_CODES, is_responsible

BROADCAST_KIND = "MEMBER_BROADCAST"

# Raisons lisibles, construites à partir des seuls codes fixes de l'outbox : jamais de
# réponse SMTP brute ni de trace technique (elles pourraient contenir des données
# nominatives et restent du ressort des journaux d'exploitation).
FAILURE_REASONS = {
    "sender_unavailable": "La boîte d’envoi n’est pas reliée à Lionsmed : le message n’est pas parti.",
    "recipient_refused": "Adresse refusée par le serveur de messagerie : elle est peut-être inexistante ou mal saisie.",
    "delivery_failed": "Le serveur de messagerie n’a pas pu prendre en charge le message.",
    "attempt_limit": "Nombre maximal de tentatives atteint.",
    "not_applicable": "Compte désactivé ou adresse modifiée avant l’envoi : le message n’a pas été envoyé.",
}
RETRY_REASONS = {
    "sender_unavailable": "Boîte d’envoi momentanément indisponible, nouvelle tentative programmée.",
    "recipient_refused": "Adresse refusée par le serveur de messagerie, nouvelle tentative programmée.",
    "delivery_failed": "Serveur de messagerie momentanément indisponible, nouvelle tentative programmée.",
}


def visible_campaigns(user):
    """Communications que le compte peut relire : celles parties de l'adresse de sa fonction
    et celles qu'il a lui-même envoyées.

    L'historique suit la fonction, comme la boîte e-mail : à la passation, le nouveau titulaire
    retrouve les envois faits depuis l'adresse de la fonction, l'ancien ne garde que les siens.
    Seule définition de cette visibilité : liste, détail et relance passent tous par ici."""
    from apps.core.permissions import can
    from apps.mailboxes.access import held_mailboxes
    campaigns = MemberEmailCampaign.objects.all()
    if can(user, "communication.view_all_member_broadcasts"):
        return campaigns
    own = Q(created_by_id=user.pk)
    keys = [mailbox.key for mailbox in held_mailboxes(user)]
    return campaigns.filter(own | Q(sender_mailbox__in=keys)) if keys else campaigns.filter(own)


def delivery_enabled():
    """Faux tant que l'envoi réel est coupé (backend factice) : rien ne quitte alors la file."""
    return not settings.EMAIL_BACKEND.endswith("dummy.EmailBackend")


def selectable_members(eligible, selected_ids=()):
    """Lignes de la liste de sélection, dans l'ordre alphabétique de l'éligibilité."""
    selected = {str(value) for value in selected_ids}
    roles = dict(Role.choices)
    return [{
        "id": str(user.pk),
        "name": user.get_full_name() or user.email,
        "email": user.email,
        "responsible": is_responsible(role),
        "role": roles.get(role, "") if is_responsible(role) else "",
        "checked": str(user.pk) in selected,
    } for user, role in eligible]


def _overall(sent, pending, failed):
    if pending:
        return "en_cours", "En cours"
    if not failed:
        return "termine", "Terminé"
    if not sent:
        return "echec", "Échec"
    return "erreurs", "Terminé avec erreurs"


def _tracking(sent, pending, failed):
    code, label = _overall(sent, pending, failed)
    return {"sent": sent, "pending": pending, "failed": failed, "total": sent + pending + failed,
            "status": code, "status_label": label}


def tracking_for(kind, object_ids):
    """{objet: compteurs réels} pour des envois suivis dans l'outbox (une seule requête)."""
    counts = {object_id: {"SENT": 0, "PENDING": 0, "SENDING": 0, "FAILED": 0} for object_id in object_ids}
    rows = (OutboxMessage.objects.filter(kind=kind, object_id__in=list(counts))
            .values_list("object_id", "state").annotate(total=Count("id")))
    for object_id, state, total in rows:
        counts[object_id][state] = total
    return {object_id: _tracking(states["SENT"], states["PENDING"] + states["SENDING"], states["FAILED"])
            for object_id, states in counts.items()}


def with_tracking(campaigns):
    """Ajoute à chaque campagne ses compteurs réels (une seule requête pour toute la page)."""
    campaigns = list(campaigns)
    tracking = tracking_for(BROADCAST_KIND, [campaign.pk for campaign in campaigns])
    for campaign in campaigns:
        campaign.tracking = tracking[campaign.pk]
        campaign.external_count = len(campaign.external_emails)
    return campaigns


def delivery_state(item):
    """État lisible d'une ligne d'outbox : libellé, date, raison et possibilité de relance."""
    row = {"attempts": item.attempts, "at": None, "reason": "", "retryable": False}
    if item.state == "SENT":
        row.update(state="sent", label="Envoyé", at=item.sent_at, order=2)
    elif item.state == "FAILED":
        row.update(state="failed", label="Échec", order=0,
                   reason=FAILURE_REASONS.get(item.error_code, "L’envoi a échoué."),
                   retryable=item.error_code in RETRYABLE_ERROR_CODES)
    elif item.state == "SENDING":
        row.update(state="pending", label="Envoi en cours", order=1)
    else:
        row.update(state="pending", label="En attente", order=1,
                   reason=RETRY_REASONS.get(item.error_code, "") if item.attempts else "")
    return row


def _member_id(item):
    # Clés posées par services.queue_member_broadcast : « broadcast:<campagne>:<compte> »
    # pour un membre, « broadcast:<campagne>:ext:<empreinte> » pour une adresse externe.
    if ":ext:" in item.event_key:
        return None
    try:
        return UUID(item.event_key.rsplit(":", 1)[-1])
    except ValueError:
        return None


def campaign_recipients(campaign):
    """Un état par destinataire : les problèmes d'abord, puis les attentes, puis les envois."""
    items = list(OutboxMessage.objects.filter(kind=BROADCAST_KIND, object_id=campaign.pk))
    member_ids = {item.pk: _member_id(item) for item in items}
    users = get_user_model().objects.in_bulk([value for value in member_ids.values() if value])
    rows = []
    for item in items:
        user = users.get(member_ids[item.pk])
        rows.append({"name": user.get_full_name() if user else "", "email": item.recipient,
                     "external": member_ids[item.pk] is None, **delivery_state(item)})
    rows.sort(key=lambda row: (row["order"], (row["name"] or row["email"]).lower()))
    return rows
