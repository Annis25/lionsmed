from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth import login, logout, authenticate
from django.contrib import messages
from django.utils import timezone
from .models import User, MembershipRequest


def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    if request.method == 'POST':
        email = request.POST.get('email', '').strip()
        password = request.POST.get('password', '').strip()
        try:
            user_obj = User.objects.get(email=email)
            user = authenticate(request, username=user_obj.username, password=password)
            if user:
                if not user.is_approved and not user.is_superuser:
                    messages.error(request, 'Votre compte est en attente de validation par le bureau.')
                    return render(request, 'registration/login.html', {})
                login(request, user)
                next_url = request.GET.get('next', 'dashboard')
                return redirect(next_url)
            else:
                messages.error(request, 'Email ou mot de passe incorrect.')
        except User.DoesNotExist:
            messages.error(request, 'Aucun compte trouvé avec cet email.')
    return render(request, 'registration/login.html', {})


def logout_view(request):
    logout(request)
    messages.success(request, 'Vous avez été déconnecté.')
    return redirect('home')


@login_required
def dashboard(request):
    from events.models import Event, EventRegistration
    from voting.models import Vote
    from notifications.models import Notification
    from members.models import Cotisation
    now = timezone.now()
    upcoming_events = Event.objects.filter(
        date_start__gte=now, is_public=True
    ).order_by('date_start')[:3]
    my_registrations = EventRegistration.objects.filter(
        member=request.user
    ).select_related('event').order_by('-registered_at')[:5]
    open_votes = Vote.objects.filter(
        status='OPEN',
        date_start__lte=now,
        date_end__gte=now
    )
    my_voted_ids = request.user.my_votes.values_list('vote_id', flat=True)
    pending_votes = open_votes.exclude(id__in=my_voted_ids)
    unread_notifications = Notification.objects.filter(
        recipient=request.user, is_read=False
    ).order_by('-created_at')[:5]
    try:
        current_cotisation = Cotisation.objects.get(
            member=request.user, year=now.year
        )
    except Cotisation.DoesNotExist:
        current_cotisation = None
    context = {
        'upcoming_events': upcoming_events,
        'my_registrations': my_registrations,
        'pending_votes': pending_votes,
        'unread_notifications': unread_notifications,
        'current_cotisation': current_cotisation,
        'unread_count': unread_notifications.count(),
    }
    return render(request, 'members/dashboard.html', context)


@login_required
def profile_view(request):
    if request.method == 'POST':
        user = request.user
        user.first_name = request.POST.get('first_name', user.first_name)
        user.last_name = request.POST.get('last_name', user.last_name)
        user.phone = request.POST.get('phone', user.phone)
        user.bio = request.POST.get('bio', user.bio)
        user.profession = request.POST.get('profession', user.profession)
        if 'photo' in request.FILES:
            user.photo = request.FILES['photo']
        user.save()
        messages.success(request, 'Profil mis à jour avec succès.')
        return redirect('profile')
    return render(request, 'members/profile.html', {'user': request.user})


@login_required
def calendar_view(request):
    from events.models import Event, EventRegistration
    import json
    now = timezone.now()
    events = Event.objects.filter(
        date_start__gte=now
    ).order_by('date_start')
    my_event_ids = list(EventRegistration.objects.filter(
        member=request.user
    ).values_list('event_id', flat=True))
    events_data = []
    for event in events:
        events_data.append({
            'id': event.id,
            'title': event.title,
            'date_start': event.date_start.isoformat(),
            'date_end': event.date_end.isoformat() if event.date_end else None,
            'location': event.location,
            'event_type': event.event_type,
            'event_type_display': event.get_event_type_display(),
            'is_registered': event.id in my_event_ids,
            'slug': event.slug,
            'is_payant': event.is_payant,
            'price': str(event.price),
        })
    context = {
        'events': events,
        'events_json': json.dumps(events_data),
        'my_event_ids': my_event_ids,
    }
    return render(request, 'members/calendar.html', context)


@login_required
def votes_view(request):
    from voting.models import Vote, UserVote
    now = timezone.now()
    open_votes = Vote.objects.filter(
        status='OPEN', date_start__lte=now, date_end__gte=now
    )
    closed_votes = Vote.objects.filter(status='CLOSED').order_by('-date_end')[:10]
    my_votes = {uv.vote_id: uv.choice for uv in request.user.my_votes.all()}
    if request.method == 'POST':
        vote_id = request.POST.get('vote_id')
        choice = request.POST.get('choice')
        if vote_id and choice in ['POUR', 'CONTRE', 'ABSTENTION']:
            try:
                vote = Vote.objects.get(id=vote_id, status='OPEN')
                if int(vote_id) not in my_votes:
                    UserVote.objects.create(
                        vote=vote, member=request.user, choice=choice
                    )
                    messages.success(request, f'Vote enregistré : {choice}')
                else:
                    messages.error(request, 'Vous avez déjà voté sur ce sujet.')
            except Vote.DoesNotExist:
                messages.error(request, 'Vote introuvable ou clôturé.')
        return redirect('votes')
    context = {
        'open_votes': open_votes,
        'closed_votes': closed_votes,
        'my_votes': my_votes,
    }
    return render(request, 'members/votes.html', context)


@login_required
def notifications_view(request):
    from notifications.models import Notification
    notifs = Notification.objects.filter(
        recipient=request.user
    ).order_by('-created_at')
    notifs.filter(is_read=False).update(is_read=True)
    return render(request, 'members/notifications.html', {'notifications': notifs})


@login_required
def documents_view(request):
    from members.models import Document
    role = request.user.role
    role_order = ['MEMBRE', 'COMITE', 'BUREAU', 'PRESIDENT', 'PAST_PRESIDENT', 'SUPER_ADMIN']
    role_index = role_order.index(role) if role in role_order else 0
    visible_map = {'ALL': 0, 'BUREAU': 2, 'PRESIDENT': 3, 'ADMIN': 5}
    docs = [d for d in Document.objects.all()
            if role_index >= visible_map.get(d.visible_to, 0)]
    return render(request, 'members/documents.html', {'documents': docs})
