from .models import MembershipRequest


def admin_context(request):
    if request.user.is_authenticated and (
        request.user.is_bureau_or_above or request.user.is_superuser
    ):
        return {
            'pending_count': MembershipRequest.objects.filter(status='PENDING').count()
        }
    return {'pending_count': 0}
