from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.utils import timezone
from events.models import Event
from news.models import Article
from accounts.models import MembershipRequest


def home(request):
    upcoming_events = Event.objects.filter(
        date_start__gte=timezone.now(),
        is_public=True
    ).order_by('date_start')[:5]

    featured_event = Event.objects.filter(
        date_start__gte=timezone.now(),
        is_public=True,
        is_featured=True
    ).first()

    latest_news = Article.objects.filter(
        status='PUBLISHED'
    ).order_by('-published_at')[:3]

    context = {
        'upcoming_events': upcoming_events,
        'featured_event': featured_event,
        'latest_news': latest_news,
        'stats': {
            'founded': 2025,
            'members': 45,
            'projects': 12,
            'beneficiaries': 500,
        }
    }
    return render(request, 'pages/home.html', context)


def about(request):
    from accounts.models import User
    bureau_members = User.objects.filter(
        role__in=['PRESIDENT', 'PAST_PRESIDENT', 'BUREAU'],
        is_approved=True,
        is_active=True
    ).order_by('role')

    context = {
        'bureau_members': bureau_members,
        'stats': {
            'years': 1,
            'members': 45,
            'projects': 12,
            'beneficiaries': 500,
        }
    }
    return render(request, 'core/about.html', context)


def actions(request):
    actions_list = Event.objects.filter(
        event_type='ACTION',
        is_public=True
    ).order_by('-date_start')
    context = {
        'actions': actions_list,
        'domaines': [
            {'icon': 'eye', 'title': 'Programme Vision', 'desc': 'Distribution de lunettes, dépistage de la cataracte et soutien aux personnes déficientes visuelles.', 'stat': '1 200 bénéficiaires/an', 'color': 'blue'},
            {'icon': 'heart', 'title': 'Santé & Diabète', 'desc': 'Dépistage gratuit du diabète, sensibilisation et soutien aux patients dans les quartiers périurbains.', 'stat': '3 campagnes/an', 'color': 'red'},
            {'icon': 'graduation-cap', 'title': 'Éducation & Jeunesse', 'desc': "Bourses scolaires, Lions Quest et accompagnement des enfants issus de familles précaires.", 'stat': '40 bourses attribuées', 'color': 'amber'},
            {'icon': 'leaf', 'title': 'Environnement', 'desc': "Plantation d'arbres, nettoyage de plages et sensibilisation des jeunes à la préservation de l'environnement.", 'stat': '2 000 arbres plantés', 'color': 'green'},
            {'icon': 'moon', 'title': 'Lutte contre la faim', 'desc': 'Distribution de couffins alimentaires durant Ramadan, opérations solidaires dans les zones rurales.', 'stat': '500 familles aidées', 'color': 'orange'},
            {'icon': 'zap', 'title': "Aide d'urgence", 'desc': 'Mobilisation rapide lors de catastrophes naturelles ou de crises humanitaires.', 'stat': 'Réseau mondial actif', 'color': 'purple'},
        ]
    }
    return render(request, 'pages/actions.html', context)


def evenements_list(request):
    now = timezone.now()
    upcoming = Event.objects.filter(date_start__gte=now, is_public=True).order_by('date_start')
    past = Event.objects.filter(date_start__lt=now, is_public=True).order_by('-date_start')[:6]
    event_type = request.GET.get('type', '')
    if event_type:
        upcoming = upcoming.filter(event_type=event_type)
    context = {
        'upcoming_events': upcoming,
        'past_events': past,
        'event_types': Event.TYPE_CHOICES,
        'selected_type': event_type,
    }
    return render(request, 'pages/evenements.html', context)


def evenement_detail(request, slug):
    from events.models import EventRegistration
    event = get_object_or_404(Event, slug=slug, is_public=True)
    is_registered = False
    if request.user.is_authenticated:
        is_registered = EventRegistration.objects.filter(event=event, member=request.user).exists()
    context = {
        'event': event,
        'is_registered': is_registered,
        'registrations_count': event.registrations.filter(status='CONFIRMED').count(),
    }
    return render(request, 'pages/evenement_detail.html', context)


def actualites_list(request):
    from news.models import Category
    articles = Article.objects.filter(status='PUBLISHED').order_by('-published_at')
    categories = Category.objects.all()
    cat_slug = request.GET.get('categorie', '')
    if cat_slug:
        articles = articles.filter(category__slug=cat_slug)
    context = {
        'articles': articles,
        'categories': categories,
        'selected_cat': cat_slug,
    }
    return render(request, 'pages/actualites.html', context)


def actualite_detail(request, slug):
    article = get_object_or_404(Article, slug=slug, status='PUBLISHED')
    related = Article.objects.filter(
        status='PUBLISHED',
        category=article.category
    ).exclude(pk=article.pk)[:3]
    context = {'article': article, 'related_articles': related}
    return render(request, 'pages/actualite_detail.html', context)


def rejoindre(request):
    if request.method == 'POST':
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        email = request.POST.get('email', '').strip()
        phone = request.POST.get('phone', '').strip()
        profession = request.POST.get('profession', '').strip()
        motivation = request.POST.get('motivation', '').strip()
        if all([first_name, last_name, email, phone, profession, motivation]):
            if MembershipRequest.objects.filter(email=email).exists():
                messages.error(request, 'Une candidature avec cet email existe déjà.')
            else:
                MembershipRequest.objects.create(
                    first_name=first_name, last_name=last_name,
                    email=email, phone=phone,
                    profession=profession, motivation=motivation
                )
                messages.success(request, 'Votre candidature a été soumise avec succès ! Nous vous contacterons bientôt.')
                return redirect('rejoindre')
        else:
            messages.error(request, 'Veuillez remplir tous les champs obligatoires.')
    return render(request, 'pages/rejoindre.html', {})


def contact(request):
    if request.method == 'POST':
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        email = request.POST.get('email', '').strip()
        subject = request.POST.get('subject', '').strip()
        message_text = request.POST.get('message', '').strip()
        if all([first_name, email, message_text]):
            from django.core.mail import send_mail
            try:
                send_mail(
                    subject=f'[Lions Club] {subject} - {first_name} {last_name}',
                    message=f'De: {first_name} {last_name}\nEmail: {email}\n\n{message_text}',
                    from_email=email,
                    recipient_list=['secretariat@lionsmed.tn'],
                    fail_silently=True,
                )
            except Exception:
                pass
            messages.success(request, 'Votre message a été envoyé avec succès !')
            return redirect('contact')
        else:
            messages.error(request, 'Veuillez remplir les champs obligatoires.')
    return render(request, 'pages/contact.html', {})
