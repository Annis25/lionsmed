from apps.communications.services import notify
from .models import Elector


def notify_vote_opened(vote):
    for elector in Elector.objects.filter(vote=vote).select_related("profile__user"):
        notify(recipient=elector.profile.user, category="VOTE", title=f"Vote ouvert — {vote.title}",
            excerpt="Un scrutin est ouvert. Consultez les modalités dans votre espace.",
            event_key=f"vote_opened:{vote.pk}:{elector.profile.user_id}",
            target_kind="vote", target_id=vote.pk, email=True, outbox_kind="VOTE_OPENED")


def notify_vote_closed(vote):
    for elector in Elector.objects.filter(vote=vote).select_related("profile__user"):
        notify(recipient=elector.profile.user, category="VOTE", title=f"Résultats disponibles — {vote.title}",
            excerpt="Le scrutin est clôturé, les résultats sont consultables.",
            event_key=f"vote_closed:{vote.pk}:{elector.profile.user_id}",
            target_kind="vote", target_id=vote.pk, email=True, outbox_kind="VOTE_RESULTS")
