from apps.communications.services import notify
from apps.core.permissions import effective_role, MEMBERS
from apps.members.models import MemberProfile


def notify_period_opened(period):
    eligible = MemberProfile.objects.filter(status=MemberProfile.Status.ACTIVE, user__is_active=True).select_related("user")
    for profile in eligible:
        if effective_role(profile.user) not in MEMBERS:
            continue
        notify(recipient=profile.user, category="SATISFACTION", title="Satisfaction du mois",
            excerpt="La consultation mensuelle est ouverte.",
            event_key=f"satisfaction_opened:{period.pk}:{profile.user_id}",
            target_kind="satisfaction", target_id=period.pk, email=True, outbox_kind="SATISFACTION_OPENED")
