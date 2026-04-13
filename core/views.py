import logging

from django.conf import settings
from django.core.mail import EmailMessage
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.utils import timezone
from django_ratelimit.decorators import ratelimit
from events.models import Event
from news.models import Article
from accounts.models import MembershipRequest
from sitecontent.models import (
    SiteConfig, DomainAction, ClubStats, ClubValue,
    HistoricalMilestone, BureauMember, MembershipBenefit,
)

logger = logging.getLogger(__name__)


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
        'config': SiteConfig.get_config(),
        'stats': ClubStats.get_latest(),
        'domaines': DomainAction.objects.filter(is_active=True),
        'valeurs': ClubValue.objects.all(),
        'avantages': MembershipBenefit.objects.filter(is_active=True),
    }
    return render(request, 'pages/home.html', context)


def about(request):
    bureau = BureauMember.objects.filter(is_visible=True).select_related('user')
    president = bureau.filter(user__role='PRESIDENT').first()
    context = {
        'president': president,
        'bureau_others': bureau.exclude(pk=president.pk) if president else bureau,
        'config': SiteConfig.get_config(),
        'stats': ClubStats.get_latest(),
        'valeurs': ClubValue.objects.all(),
        'milestones': HistoricalMilestone.objects.all(),
        'avantages': MembershipBenefit.objects.filter(is_active=True),
    }
    return render(request, 'core/about.html', context)


def actions(request):
    actions_list = Event.objects.filter(
        event_type='ACTION',
        is_public=True
    ).order_by('-date_start')
    context = {
        'actions': actions_list,
        'config': SiteConfig.get_config(),
        'domaines': DomainAction.objects.filter(is_active=True),
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


# Nom du champ-piège présent dans les deux formulaires publics. Masqué en CSS :
# un visiteur ne le voit jamais, un robot qui remplit tout le renseigne.
HONEYPOT_FIELD = 'website'


def _is_bot(request):
    return bool(request.POST.get(HONEYPOT_FIELD, '').strip())


def _rate_limited(request):
    return getattr(request, 'limited', False)


@ratelimit(key='ip', rate='5/h', method='POST', block=False)
def rejoindre(request):
    if request.method == 'POST':
        # Piège à robots : on renvoie le même message de succès que pour une
        # soumission valide, sans rien enregistrer. Signaler la détection
        # apprendrait au robot à contourner le champ.
        if _is_bot(request):
            messages.success(request, 'Votre candidature a été soumise avec succès ! Nous vous contacterons bientôt.')
            return redirect('rejoindre')
        if _rate_limited(request):
            messages.error(
                request,
                "Trop de candidatures envoyées depuis cette connexion. Réessayez dans une heure."
            )
            return redirect('rejoindre')
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
    context = {
        'config': SiteConfig.get_config(),
        'avantages': MembershipBenefit.objects.filter(is_active=True),
        'honeypot_field': HONEYPOT_FIELD,
    }
    return render(request, 'pages/rejoindre.html', context)


@ratelimit(key='ip', rate='5/h', method='POST', block=False)
def contact(request):
    config = SiteConfig.get_config()
    if request.method == 'POST':
        if _is_bot(request):
            messages.success(request, 'Votre message a été envoyé avec succès !')
            return redirect('contact')
        if _rate_limited(request):
            messages.error(
                request,
                "Trop de messages envoyés depuis cette connexion. Réessayez dans une heure."
            )
            return redirect('contact')
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        email = request.POST.get('email', '').strip()
        subject = request.POST.get('subject', '').strip()
        message_text = request.POST.get('message', '').strip()
        if all([first_name, email, message_text]):
            try:
                # L'expéditeur doit rester une adresse du domaine, sinon SPF/DKIM
                # échouent et le message est traité comme une usurpation.
                # L'adresse du visiteur va dans Reply-To.
                mail = EmailMessage(
                    subject=f'[Lions Club] {subject} - {first_name} {last_name}',
                    body=f'De: {first_name} {last_name}\nEmail: {email}\n\n{message_text}',
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    to=[config.email_contact],
                    reply_to=[email],
                )
                mail.send(fail_silently=False)
            except Exception:
                logger.exception('Échec de l\'envoi du formulaire de contact')
                messages.error(
                    request,
                    "L'envoi a échoué. Réessayez plus tard ou écrivez directement à "
                    f"{config.email_contact}."
                )
                return redirect('contact')
            messages.success(request, 'Votre message a été envoyé avec succès !')
            return redirect('contact')
        else:
            messages.error(request, 'Veuillez remplir les champs obligatoires.')
    return render(request, 'pages/contact.html', {
        'config': config,
        'honeypot_field': HONEYPOT_FIELD,
    })
