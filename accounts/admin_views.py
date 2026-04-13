import logging

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.utils.crypto import get_random_string
from django.db.models import Count, Q
from .models import User, MembershipRequest

logger = logging.getLogger(__name__)
# Journal dédié aux actions sensibles : approbations, suppressions, changements
# de rôle. Écrit dans logs/securite.log, distinct du journal applicatif général.
audit = logging.getLogger('lionsmed.securite')


def _acteur(request):
    """Identité de l'auteur d'une action, pour les lignes d'audit."""
    u = request.user
    return f"{u.username} ({u.role})"


def _ip(request):
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR', '')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', '?')


def _unique_username(email):
    """Dérive un identifiant unique de l'email, sans collision avec l'existant."""
    base = email.split('@')[0][:140] or 'membre'
    username, counter = base, 2
    while User.objects.filter(username=username).exists():
        username = f'{base}{counter}'
        counter += 1
    return username


def _reject_if_revoked(request):
    """Coupe la session si le compte n'est plus actif/approuvé. None sinon."""
    user = request.user
    if user.is_superuser:
        return None
    if not user.is_active or not getattr(user, 'is_approved', False):
        logout(request)
        messages.error(
            request,
            "Votre compte n'est plus actif. Contactez le secrétariat du club."
        )
        return redirect('login')
    return None


def superadmin_required(view_func):
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        # Un compte révoqué ne doit pas conserver l'accès via sa session ouverte.
        denied = _reject_if_revoked(request)
        if denied:
            return denied
        if request.user.role not in ['SUPER_ADMIN', 'PRESIDENT'] and not request.user.is_superuser:
            messages.error(request, 'Accès réservé aux administrateurs.')
            return redirect('dashboard')
        return view_func(request, *args, **kwargs)
    wrapper.__name__ = view_func.__name__
    return wrapper


def bureau_required(view_func):
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        # Un compte révoqué ne doit pas conserver l'accès via sa session ouverte.
        denied = _reject_if_revoked(request)
        if denied:
            return denied
        if not request.user.is_bureau_or_above and not request.user.is_superuser:
            messages.error(request, 'Accès réservé au bureau.')
            return redirect('dashboard')
        return view_func(request, *args, **kwargs)
    wrapper.__name__ = view_func.__name__
    return wrapper


def can_publish_required(view_func):
    """Accès éditorial : bureau + comité (cf. User.can_publish)."""
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        # Un compte révoqué ne doit pas conserver l'accès via sa session ouverte.
        denied = _reject_if_revoked(request)
        if denied:
            return denied
        if not request.user.can_publish and not request.user.is_superuser:
            messages.error(request, 'Accès réservé aux membres autorisés à publier.')
            return redirect('dashboard')
        return view_func(request, *args, **kwargs)
    wrapper.__name__ = view_func.__name__
    return wrapper


@login_required
@superadmin_required
def admin_dashboard(request):
    from events.models import Event
    from voting.models import Vote
    from members.models import Cotisation
    from news.models import Article
    now = timezone.now()
    stats = {
        'total_members': User.objects.filter(is_approved=True, is_active=True).count(),
        'pending_requests': MembershipRequest.objects.filter(status='PENDING').count(),
        'upcoming_events': Event.objects.filter(date_start__gte=now).count(),
        'open_votes': Vote.objects.filter(status='OPEN').count(),
        'unpaid_cotisations': Cotisation.objects.filter(status__in=['PENDING', 'OVERDUE']).count(),
        'published_articles': Article.objects.filter(status='PUBLISHED').count(),
    }
    recent_requests = MembershipRequest.objects.filter(
        status='PENDING'
    ).order_by('-created_at')[:5]
    recent_members = User.objects.filter(
        is_approved=True
    ).order_by('-date_joined')[:5]
    roles_distribution = User.objects.filter(
        is_approved=True
    ).values('role').annotate(count=Count('role')).order_by('role')
    context = {
        'stats': stats,
        'recent_requests': recent_requests,
        'recent_members': recent_members,
        'roles_distribution': roles_distribution,
    }
    return render(request, 'admin_custom/dashboard.html', context)


@login_required
@bureau_required
def admin_members(request):
    role_filter = request.GET.get('role', '')
    status_filter = request.GET.get('status', '')
    search = request.GET.get('q', '')
    members = User.objects.all().order_by('role', 'last_name')
    if role_filter:
        members = members.filter(role=role_filter)
    if status_filter == 'approved':
        members = members.filter(is_approved=True)
    elif status_filter == 'pending':
        members = members.filter(is_approved=False)
    if search:
        members = members.filter(
            Q(first_name__icontains=search) |
            Q(last_name__icontains=search) |
            Q(email__icontains=search)
        )
    context = {
        'members': members,
        'role_choices': User.ROLE_CHOICES,
        'selected_role': role_filter,
        'selected_status': status_filter,
        'search': search,
        'total': members.count(),
    }
    return render(request, 'admin_custom/members.html', context)


@login_required
@bureau_required
def admin_member_edit(request, user_id):
    member = get_object_or_404(User, id=user_id)
    if request.method == 'POST':
        member.first_name = request.POST.get('first_name', member.first_name)
        member.last_name = request.POST.get('last_name', member.last_name)
        member.email = request.POST.get('email', member.email)
        member.phone = request.POST.get('phone', member.phone)
        member.profession = request.POST.get('profession', member.profession)
        ancien_role = member.role
        ancien_approuve, ancien_actif = member.is_approved, member.is_active
        new_role = request.POST.get('role', member.role)
        if request.user.role == 'SUPER_ADMIN' or request.user.is_superuser:
            member.role = new_role
        member.is_approved = request.POST.get('is_approved') == 'on'
        member.is_active = request.POST.get('is_active') == 'on'
        member.save()
        if member.role != ancien_role:
            audit.warning(
                "ROLE_MODIFIE membre=%s ancien=%s nouveau=%s par=%s ip=%s",
                member.username, ancien_role, member.role, _acteur(request), _ip(request),
            )
        if (member.is_approved, member.is_active) != (ancien_approuve, ancien_actif):
            audit.warning(
                "STATUT_MODIFIE membre=%s approuve=%s->%s actif=%s->%s par=%s ip=%s",
                member.username, ancien_approuve, member.is_approved,
                ancien_actif, member.is_active, _acteur(request), _ip(request),
            )
        messages.success(request, f'Membre {member.get_full_name()} mis à jour.')
        return redirect('admin_members')
    context = {
        'member': member,
        'role_choices': User.ROLE_CHOICES,
    }
    return render(request, 'admin_custom/member_edit.html', context)


@login_required
@bureau_required
def admin_requests(request):
    status_filter = request.GET.get('status', 'PENDING')
    requests_qs = MembershipRequest.objects.all().order_by('-created_at')
    if status_filter:
        requests_qs = requests_qs.filter(status=status_filter)
    context = {
        'requests': requests_qs,
        'status_filter': status_filter,
        'pending_count': MembershipRequest.objects.filter(status='PENDING').count(),
    }
    return render(request, 'admin_custom/requests.html', context)


@login_required
@bureau_required
def admin_request_action(request, req_id):
    if request.method == 'POST':
        membership_req = get_object_or_404(MembershipRequest, id=req_id)
        action = request.POST.get('action')
        if action == 'approve':
            # Longueur pilotée par le même réglage que MinimumLengthValidator :
            # un mot de passe temporaire ne doit jamais être plus court que ce
            # que la politique exige du membre lorsqu'il le changera.
            password = get_random_string(settings.PASSWORD_MIN_LENGTH)
            try:
                # Création du compte, changement de statut et envoi du mail dans la
                # même transaction : si l'un des trois échoue, la candidature reste
                # PENDING et reste traitable, au lieu de sortir de la file sans
                # compte associé — ou avec un compte dont personne n'a le mot de passe.
                with transaction.atomic():
                    membership_req.status = 'APPROVED'
                    membership_req.reviewed_by = request.user
                    membership_req.reviewed_at = timezone.now()
                    membership_req.save()
                    User.objects.create_user(
                        username=_unique_username(membership_req.email),
                        email=membership_req.email,
                        first_name=membership_req.first_name,
                        last_name=membership_req.last_name,
                        phone=membership_req.phone,
                        profession=membership_req.profession,
                        role='MEMBRE',
                        is_approved=True,
                        password=password,
                    )
                    # Pas de fail_silently : un envoi manqué doit être visible,
                    # sans quoi le compte existe mais reste inaccessible.
                    send_mail(
                        subject='Bienvenue au Lions Club Sfax Méditerranée !',
                        message=(
                            f'Bonjour {membership_req.first_name},\n\n'
                            f'Votre candidature a été approuvée.\n\n'
                            f'Email : {membership_req.email}\n'
                            f'Mot de passe temporaire : {password}\n\n'
                            f'Connectez-vous sur notre site pour accéder à votre espace membre.'
                        ),
                        from_email=settings.DEFAULT_FROM_EMAIL,
                        recipient_list=[membership_req.email],
                    )
            except Exception:
                logger.exception(
                    'Échec de l\'approbation de la candidature %s', membership_req.pk
                )
                messages.error(
                    request,
                    "L'approbation a échoué (envoi de l'email ou création du compte). "
                    "Rien n'a été enregistré, la candidature reste en attente. "
                    "Vérifiez la configuration SMTP puis réessayez."
                )
                return redirect('admin_requests')
            audit.info(
                "CANDIDATURE_APPROUVEE candidat=%s par=%s ip=%s",
                membership_req.email, _acteur(request), _ip(request),
            )
            messages.success(
                request,
                f'Candidature approuvée. Compte créé pour {membership_req.first_name} {membership_req.last_name}.'
            )
        elif action == 'reject':
            membership_req.status = 'REJECTED'
            membership_req.reviewed_by = request.user
            membership_req.reviewed_at = timezone.now()
            membership_req.save()
            audit.info(
                "CANDIDATURE_REJETEE candidat=%s par=%s ip=%s",
                membership_req.email, _acteur(request), _ip(request),
            )
            messages.warning(
                request,
                f'Candidature de {membership_req.first_name} {membership_req.last_name} refusée.'
            )
    return redirect('admin_requests')


@login_required
@bureau_required
def admin_cotisations(request):
    from members.models import Cotisation
    now = timezone.now()
    year_filter = request.GET.get('year', str(now.year))
    status_filter = request.GET.get('status', '')
    cotisations = Cotisation.objects.select_related('member').order_by('status', 'member__last_name')
    if year_filter:
        cotisations = cotisations.filter(year=year_filter)
    if status_filter:
        cotisations = cotisations.filter(status=status_filter)
    current_year = int(year_filter) if year_filter else now.year
    members_without = User.objects.filter(
        is_approved=True, is_active=True
    ).exclude(cotisations__year=current_year)

    if request.method == 'POST':
        action = request.POST.get('action')
        cotis_id = request.POST.get('cotisation_id')
        if action == 'mark_paid' and cotis_id:
            cotis = get_object_or_404(Cotisation, id=cotis_id)
            cotis.status = 'PAID'
            cotis.payment_date = timezone.now().date()
            cotis.save()
            messages.success(request, 'Cotisation marquée comme payée.')
        elif action == 'create_all':
            created = 0
            for member in members_without:
                Cotisation.objects.get_or_create(
                    member=member, year=current_year,
                    defaults={'amount': 200, 'status': 'PENDING'}
                )
                created += 1
            messages.success(request, f'{created} cotisations créées pour {current_year}.')
        return redirect(f'/admin-panel/cotisations/?year={year_filter}')

    context = {
        'cotisations': cotisations,
        'members_without': members_without,
        'year_filter': year_filter,
        'status_filter': status_filter,
        'status_choices': Cotisation.STATUS_CHOICES,
        'years': range(2025, now.year + 2),
        'stats': {
            'paid': cotisations.filter(status='PAID').count(),
            'pending': cotisations.filter(status='PENDING').count(),
            'overdue': cotisations.filter(status='OVERDUE').count(),
        },
    }
    return render(request, 'admin_custom/cotisations.html', context)


@login_required
@superadmin_required
def admin_send_notification(request):
    from notifications.models import Notification
    if request.method == 'POST':
        title = request.POST.get('title', '').strip()
        message_text = request.POST.get('message', '').strip()
        notif_type = request.POST.get('notif_type', 'SYSTEM')
        target = request.POST.get('target', 'ALL')
        link = request.POST.get('link', '')
        if title and message_text:
            if target == 'ALL':
                recipients = User.objects.filter(is_approved=True, is_active=True)
            elif target == 'BUREAU':
                recipients = User.objects.filter(
                    role__in=['SUPER_ADMIN', 'PAST_PRESIDENT', 'PRESIDENT', 'BUREAU'],
                    is_approved=True
                )
            else:
                recipients = User.objects.filter(role=target, is_approved=True)
            notifs = [
                Notification(
                    recipient=u, notif_type=notif_type,
                    title=title, message=message_text, link=link
                )
                for u in recipients
            ]
            Notification.objects.bulk_create(notifs)
            messages.success(request, f'Notification envoyée à {len(notifs)} membre(s).')
            return redirect('admin_send_notification')
    context = {
        'notif_types': [
            ('EVENT', 'Événement'), ('VOTE', 'Vote'), ('NEWS', 'Actualité'),
            ('SYSTEM', 'Système'), ('COTISATION', 'Cotisation'),
        ],
        'targets': [
            ('ALL', 'Tous les membres'),
            ('BUREAU', 'Bureau et plus'),
            ('COMITE', 'Comité'),
            ('MEMBRE', 'Membres simples'),
        ],
        'member_counts': {
            'ALL': User.objects.filter(is_approved=True, is_active=True).count(),
            'BUREAU': User.objects.filter(
                role__in=['SUPER_ADMIN', 'PAST_PRESIDENT', 'PRESIDENT', 'BUREAU'],
                is_approved=True
            ).count(),
            'COMITE': User.objects.filter(role='COMITE', is_approved=True).count(),
            'MEMBRE': User.objects.filter(role='MEMBRE', is_approved=True).count(),
        },
    }
    return render(request, 'admin_custom/send_notification.html', context)


# ─────────────────────────────────────────────────────────────
# CRUD Événements
# ─────────────────────────────────────────────────────────────

@login_required
@can_publish_required
def admin_events_list(request):
    from events.models import Event
    now = timezone.now()
    period = request.GET.get('period', '')
    type_filter = request.GET.get('type', '')
    search = request.GET.get('q', '')

    events = Event.objects.all().order_by('-date_start')
    if period == 'upcoming':
        events = events.filter(date_start__gte=now)
    elif period == 'past':
        events = events.filter(date_start__lt=now)
    if type_filter:
        events = events.filter(event_type=type_filter)
    if search:
        events = events.filter(Q(title__icontains=search) | Q(location__icontains=search))

    context = {
        'events': events,
        'type_choices': Event.TYPE_CHOICES,
        'selected_type': type_filter,
        'selected_period': period,
        'search': search,
        'total': events.count(),
        'now': now,
    }
    return render(request, 'admin_custom/events_list.html', context)


@login_required
@can_publish_required
def admin_event_create(request):
    from events.forms import EventForm
    form = EventForm(request.POST or None, request.FILES or None)
    if request.method == 'POST' and form.is_valid():
        event = form.save(commit=False)
        event.created_by = request.user
        form.save()
        messages.success(request, f'Événement « {event.title} » créé.')
        return redirect('admin_events')
    context = {'form': form, 'is_create': True}
    return render(request, 'admin_custom/event_form.html', context)


@login_required
@can_publish_required
def admin_event_edit(request, event_id):
    from events.models import Event
    from events.forms import EventForm
    event = get_object_or_404(Event, id=event_id)
    form = EventForm(request.POST or None, request.FILES or None, instance=event)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, f'Événement « {event.title} » mis à jour.')
        return redirect('admin_events')
    context = {'form': form, 'event': event, 'is_create': False}
    return render(request, 'admin_custom/event_form.html', context)


@login_required
@superadmin_required
def admin_event_delete(request, event_id):
    from events.models import Event
    event = get_object_or_404(Event, id=event_id)
    if request.method == 'POST':
        title = event.title
        event.delete()
        audit.warning(
            "EVENEMENT_SUPPRIME id=%s titre=%r par=%s ip=%s",
            event_id, title, _acteur(request), _ip(request),
        )
        messages.warning(request, f'Événement « {title} » supprimé.')
    return redirect('admin_events')


# ─────────────────────────────────────────────────────────────
# CRUD Actualités
# ─────────────────────────────────────────────────────────────

@login_required
@can_publish_required
def admin_articles_list(request):
    from news.models import Article, Category
    status_filter = request.GET.get('status', '')
    cat_filter = request.GET.get('categorie', '')
    search = request.GET.get('q', '')

    articles = Article.objects.select_related('author', 'category').order_by('-created_at')
    if status_filter:
        articles = articles.filter(status=status_filter)
    if cat_filter:
        articles = articles.filter(category__slug=cat_filter)
    if search:
        articles = articles.filter(Q(title__icontains=search) | Q(content__icontains=search))

    context = {
        'articles': articles,
        'status_choices': Article.STATUS_CHOICES,
        'categories': Category.objects.all(),
        'selected_status': status_filter,
        'selected_cat': cat_filter,
        'search': search,
        'total': articles.count(),
    }
    return render(request, 'admin_custom/articles_list.html', context)


@login_required
@can_publish_required
def admin_article_create(request):
    from news.forms import ArticleForm
    form = ArticleForm(request.POST or None, request.FILES or None)
    if request.method == 'POST' and form.is_valid():
        article = form.save(commit=False)
        article.author = request.user
        form.save()
        messages.success(request, f'Article « {article.title} » créé.')
        return redirect('admin_articles')
    context = {'form': form, 'is_create': True}
    return render(request, 'admin_custom/article_form.html', context)


@login_required
@can_publish_required
def admin_article_edit(request, article_id):
    from news.models import Article
    from news.forms import ArticleForm
    article = get_object_or_404(Article, id=article_id)
    form = ArticleForm(request.POST or None, request.FILES or None, instance=article)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, f'Article « {article.title} » mis à jour.')
        return redirect('admin_articles')
    context = {'form': form, 'article': article, 'is_create': False}
    return render(request, 'admin_custom/article_form.html', context)


@login_required
@can_publish_required
def admin_article_toggle_status(request, article_id):
    """Bascule DRAFT ↔ PUBLISHED sans repasser par le formulaire complet."""
    from news.models import Article
    article = get_object_or_404(Article, id=article_id)
    if request.method == 'POST':
        if article.status == 'PUBLISHED':
            article.status = 'DRAFT'
            article.save(update_fields=['status'])
            messages.warning(request, f'« {article.title} » repassé en brouillon.')
        else:
            article.status = 'PUBLISHED'
            if not article.published_at:
                article.published_at = timezone.now()
            article.save(update_fields=['status', 'published_at'])
            messages.success(request, f'« {article.title} » est maintenant publié.')
    return redirect(request.POST.get('next') or 'admin_articles')


@login_required
@superadmin_required
def admin_article_delete(request, article_id):
    from news.models import Article
    article = get_object_or_404(Article, id=article_id)
    if request.method == 'POST':
        title = article.title
        article.delete()
        audit.warning(
            "ARTICLE_SUPPRIME id=%s titre=%r par=%s ip=%s",
            article_id, title, _acteur(request), _ip(request),
        )
        messages.warning(request, f'Article « {title} » supprimé.')
    return redirect('admin_articles')
