from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.db.models import Count, Q
from .models import User, MembershipRequest


def superadmin_required(view_func):
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
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
        if not request.user.is_bureau_or_above and not request.user.is_superuser:
            messages.error(request, 'Accès réservé au bureau.')
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
        new_role = request.POST.get('role', member.role)
        if request.user.role == 'SUPER_ADMIN' or request.user.is_superuser:
            member.role = new_role
        member.is_approved = request.POST.get('is_approved') == 'on'
        member.is_active = request.POST.get('is_active') == 'on'
        member.save()
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
            membership_req.status = 'APPROVED'
            membership_req.reviewed_by = request.user
            membership_req.reviewed_at = timezone.now()
            membership_req.save()
            password = User.objects.make_random_password()
            User.objects.create_user(
                username=membership_req.email.split('@')[0],
                email=membership_req.email,
                first_name=membership_req.first_name,
                last_name=membership_req.last_name,
                phone=membership_req.phone,
                profession=membership_req.profession,
                role='MEMBRE',
                is_approved=True,
                password=password,
            )
            from django.core.mail import send_mail
            send_mail(
                subject='Bienvenue au Lions Club Sfax Méditerranée !',
                message=(
                    f'Bonjour {membership_req.first_name},\n\n'
                    f'Votre candidature a été approuvée.\n\n'
                    f'Email : {membership_req.email}\n'
                    f'Mot de passe temporaire : {password}\n\n'
                    f'Connectez-vous sur notre site pour accéder à votre espace membre.'
                ),
                from_email='secretariat@lionsmed.tn',
                recipient_list=[membership_req.email],
                fail_silently=True,
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
