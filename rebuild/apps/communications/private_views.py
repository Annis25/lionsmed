from django.contrib import messages
from django.contrib.auth import get_user_model
from django.core.paginator import Paginator
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_safe
from apps.core.permissions import capability_required
from .models import Notification
from .services import send_important_notification
from .forms import ImportantNotificationForm


def resolve_target(actor, notification):
    try:
        if notification.target_kind == "event":
            return reverse("agenda_private:calendar")
        if notification.target_kind == "document":
            from apps.documents.selectors import document_for_actor
            document_for_actor(actor, notification.target_id)
            return reverse("documents:detail", args=[notification.target_id])
        if notification.target_kind == "dues":
            return reverse("dues:own")
        if notification.target_kind == "vote":
            return reverse("voting:member_list")
        if notification.target_kind == "satisfaction":
            return reverse("satisfaction:respond")
    except Exception:
        return None
    return None


@capability_required("notification.view_own")
@require_safe
def notification_list(request):
    qs = Notification.objects.filter(recipient=request.user)
    page = Paginator(qs, 20).get_page(request.GET.get("page"))
    items = [{"notification": n, "url": resolve_target(request.user, n)} for n in page.object_list]
    return render(request, "espace/notifications.html", {
        "page_obj": page, "items": items, "unread_count": qs.filter(read_at__isnull=True).count(),
    })


@capability_required("notification.view_own")
@require_http_methods(["POST"])
def notification_mark_read(request, notification_id):
    notification = get_object_or_404(Notification, pk=notification_id, recipient=request.user)
    if notification.read_at is None:
        notification.read_at = timezone.now()
        notification.save(update_fields=["read_at"])
    return redirect("notifications:list")


@capability_required("notification.view_own")
@require_http_methods(["POST"])
def notification_mark_all_read(request):
    Notification.objects.filter(recipient=request.user, read_at__isnull=True).update(read_at=timezone.now())
    return redirect("notifications:list")


@capability_required("notification.send")
@require_http_methods(["GET", "POST"])
def notification_send(request):
    form = ImportantNotificationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            recipient = get_user_model().objects.get(email=form.cleaned_data["email"].strip().lower())
            send_important_notification(actor=request.user, recipient=recipient, title=form.cleaned_data["title"], excerpt=form.cleaned_data["excerpt"])
            messages.success(request, "Notification envoyée.")
            return redirect("notifications:send")
        except get_user_model().DoesNotExist:
            form.add_error("email", "Aucun compte avec cette adresse.")
    return render(request, "espace/notification_send.html", {"form": form})
