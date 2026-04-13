import logging
import os

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth import login, logout, authenticate
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import FileResponse, Http404
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from .decorators import approved_required
from .models import User, MembershipRequest

audit = logging.getLogger('lionsmed.securite')


def _ip(request):
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR', '')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', '?')


def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    if request.method == 'POST':
        email = request.POST.get('email', '').strip()
        password = request.POST.get('password', '').strip()
        # Message unique quelle que soit la cause de l'échec : distinguer
        # « email inconnu » de « mot de passe faux » permettrait de constituer
        # la liste des emails de membres par essais successifs.
        invalid_credentials = 'Email ou mot de passe incorrect.'
        # Recherche insensible à la casse : « Jean@x.tn » et « jean@x.tn »
        # désignent la même boîte, et un membre saisissant son adresse avec une
        # majuscule ne doit pas se voir refuser l'accès.
        candidats = list(User.objects.filter(email__iexact=email)[:2])
        if len(candidats) > 1:
            # User.email n'est pas contraint en unicité : plusieurs comptes
            # peuvent partager la même adresse. On refuse plutôt que de choisir
            # arbitrairement lequel authentifier.
            audit.warning(
                "CONNEXION_AMBIGUE email=%r comptes=%s ip=%s",
                email, [u.username for u in candidats], _ip(request),
            )
            messages.error(
                request,
                "Plusieurs comptes partagent cette adresse. "
                "Contactez le secrétariat du club."
            )
            return render(request, 'registration/login.html', {})
        user_obj = candidats[0] if candidats else None
        if user_obj is not None:
            user = authenticate(request, username=user_obj.username, password=password)
        else:
            # Sans compte correspondant, on hache tout de même le mot de passe
            # fourni : sinon le temps de réponse plus court trahirait l'absence
            # de compte (énumération par mesure de latence).
            User().set_password(password)
            user = None

        if user:
            if not user.is_approved and not user.is_superuser:
                messages.error(request, 'Votre compte est en attente de validation par le bureau.')
                return render(request, 'registration/login.html', {})
            audit.info("CONNEXION_REUSSIE utilisateur=%s ip=%s", user.username, _ip(request))
            login(request, user)
            # Un ?next= non validé permettrait de rediriger vers un domaine
            # externe après une connexion légitime (phishing depuis lionsmed.tn).
            next_url = request.GET.get('next', '')
            if next_url and url_has_allowed_host_and_scheme(
                next_url,
                allowed_hosts={request.get_host()},
                require_https=request.is_secure(),
            ):
                return redirect(next_url)
            return redirect('dashboard')
        # Journalisé côté applicatif en plus de django-axes : on garde une trace
        # même si axes est un jour retiré, et on distingue les deux causes dans
        # le journal sans les distinguer dans le message affiché.
        audit.info(
            "CONNEXION_ECHOUEE email=%r compte_existe=%s ip=%s",
            email, user_obj is not None, _ip(request),
        )
        messages.error(request, invalid_credentials)
    return render(request, 'registration/login.html', {})


def logout_view(request):
    logout(request)
    messages.success(request, 'Vous avez été déconnecté.')
    return redirect('home')


@login_required
@approved_required
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
@approved_required
def profile_view(request):
    if request.method == 'POST':
        user = request.user
        user.first_name = request.POST.get('first_name', user.first_name)
        user.last_name = request.POST.get('last_name', user.last_name)
        user.phone = request.POST.get('phone', user.phone)
        user.bio = request.POST.get('bio', user.bio)
        user.profession = request.POST.get('profession', user.profession)
        if 'photo' in request.FILES:
            # Les validateurs déclarés sur le champ ne sont pas appliqués par
            # save() : il faut les déclencher explicitement avant d'enregistrer.
            uploaded = request.FILES['photo']
            try:
                for validator in User._meta.get_field('photo').validators:
                    validator(uploaded)
            except ValidationError as exc:
                for message in exc.messages:
                    messages.error(request, message)
                return redirect('profile')
            user.photo = uploaded
        user.save()
        messages.success(request, 'Profil mis à jour avec succès.')
        return redirect('profile')
    return render(request, 'members/profile.html', {'user': request.user})


@login_required
@approved_required
def calendar_view(request):
    from events.models import Event, EventRegistration
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
        # Transmis en structures Python : le template les sérialise via
        # |json_script, qui échappe les séquences dangereuses (dont </script>).
        'events': events,
        'events_data': events_data,
        'my_event_ids': my_event_ids,
    }
    return render(request, 'members/calendar.html', context)


@login_required
@approved_required
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
@approved_required
def notifications_view(request):
    from notifications.models import Notification
    notifs = Notification.objects.filter(
        recipient=request.user
    ).order_by('-created_at')
    notifs.filter(is_read=False).update(is_read=True)
    return render(request, 'members/notifications.html', {'notifications': notifs})


@login_required
@approved_required
def documents_view(request):
    from members.models import Document
    return render(request, 'members/documents.html', {
        'documents': Document.visible_for(request.user),
    })


@login_required
@approved_required
def document_download(request, doc_id):
    """Sert un document privé après contrôle du rôle.

    Seul point d'accès aux fichiers : ils sont stockés hors de MEDIA_ROOT et ne
    sont donc jamais exposés par le serveur web. On renvoie 404 (et non 403) pour
    ne pas révéler l'existence d'un document qu'on n'a pas le droit de consulter.
    """
    from members.models import Document
    document = get_object_or_404(Document, id=doc_id)
    if not document.is_visible_to(request.user):
        raise Http404
    if not document.file:
        raise Http404
    try:
        handle = document.file.open('rb')
    except FileNotFoundError:
        raise Http404
    return FileResponse(
        handle,
        as_attachment=True,
        filename=os.path.basename(document.file.name),
    )
