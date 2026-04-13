from django.core.management.base import BaseCommand
from django.db import transaction

from sitecontent.models import (
    SiteConfig, DomainAction, ClubStats, ClubValue,
    HistoricalMilestone, BureauMember, MembershipBenefit,
)


DOMAINES = [
    {
        'title': 'Programme Vision', 'icon': 'eye', 'color': 'blue',
        'stat_label': 'Actions à venir', 'order': 1,
        'description': "Actions de dépistage, sensibilisation à la santé visuelle et orientation "
                       "vers les structures spécialisées à Sfax et dans sa région.",
    },
    {
        'title': 'Santé & Diabète', 'icon': 'heart', 'color': 'red',
        'stat_label': 'Prévention de proximité', 'order': 2,
        'description': "Sensibilisation au diabète, dépistages de proximité et relais vers les "
                       "professionnels de santé partenaires à Sfax.",
    },
    {
        'title': 'Éducation & Jeunesse', 'icon': 'graduation-cap', 'color': 'amber',
        'stat_label': 'Priorité jeunesse', 'order': 3,
        'description': "Soutien à la jeunesse, accompagnement scolaire et initiatives éducatives "
                       "construites avec les acteurs locaux.",
    },
    {
        'title': 'Environnement', 'icon': 'leaf', 'color': 'green',
        'stat_label': 'Mobilisation locale', 'order': 4,
        'description': "Nettoyages de proximité, sensibilisation à l’environnement méditerranéen "
                       "et gestes concrets pour préserver le littoral de Sfax.",
    },
    {
        'title': 'Lutte contre la faim', 'icon': 'moon', 'color': 'orange',
        'stat_label': 'Solidarité de proximité', 'order': 5,
        'description': "Soutien ponctuel aux familles vulnérables, notamment lors des périodes "
                       "sensibles de l’année et des besoins urgents.",
    },
    {
        'title': "Aide d'urgence", 'icon': 'zap', 'color': 'purple',
        'stat_label': 'Réponse coordonnée', 'order': 6,
        'description': "Mobilisation rapide en cas de besoin, en coordination avec le réseau Lions "
                       "et les partenaires institutionnels.",
    },
]

VALEURS = [
    {
        'title': 'Service', 'icon_svg_name': 'heart', 'tagline': 'We Serve', 'order': 1,
        'description': "Le service aux autres est au centre de tout ce que nous faisons. "
                       "Chaque heure, chaque don, chaque geste compte et transforme une vie.",
    },
    {
        'title': 'Intégrité', 'icon_svg_name': 'shield', 'tagline': 'Éthique absolue', 'order': 2,
        'description': "Nous agissons avec une transparence totale dans la gestion des fonds, "
                       "la gouvernance du club et nos relations avec les partenaires et bénéficiaires.",
    },
    {
        'title': 'Amitié', 'icon_svg_name': 'users', 'tagline': 'Fraternité durable', 'order': 3,
        'description': "Les liens qui se forgent au sein du club vont bien au-delà de l'association. "
                       "Nous construisons des amitiés sincères qui traversent les générations.",
    },
    {
        'title': 'Diversité & Inclusion', 'icon_svg_name': 'leaf', 'tagline': '210 pays, une famille', 'order': 4,
        'description': "Notre club est ouvert à toutes et tous, sans distinction de profession, "
                       "d'origine ou de génération. La diversité de nos membres est notre force.",
    },
    {
        'title': 'Excellence', 'icon_svg_name': 'sparkles', 'tagline': 'Toujours mieux', 'order': 5,
        'description': "Nous nous engageons à réaliser chaque projet avec le plus haut niveau "
                       "de qualité, de préparation et de suivi. L'excellence est un standard, pas un luxe.",
    },
    {
        'title': 'Responsabilité', 'icon_svg_name': 'clock', 'tagline': "S'engager vraiment", 'order': 6,
        'description': "Chaque membre s'engage personnellement. Être Lions, c'est accepter "
                       "une responsabilité envers sa communauté, ses partenaires et les générations futures.",
    },
]

JALONS = [
    {
        'year': 2025, 'title': 'Fondation du club', 'order': 1, 'is_active_milestone': True,
        'description': "Un groupe de professionnels sfaxiens fonde le club, affilié dès sa création "
                       "à Lions Clubs International.",
    },
    {
        'year': 2026, 'title': 'Premières actions de terrain', 'order': 2, 'is_active_milestone': False,
        'description': "Lancement des premières caravanes de dépistage et des actions "
                       "environnementales sur le littoral sfaxien.",
    },
]

AVANTAGES = [
    {
        'title': 'Réseau international', 'icon_name': 'users', 'order': 1,
        'description': "Accès au réseau mondial de Lions Clubs International dans plus de 200 pays",
    },
    {
        'title': 'Impact réel', 'icon_name': 'zap', 'order': 2,
        'description': "Participer à des projets concrets au service de Sfax et de ses habitants",
    },
    {
        'title': 'Formation continue', 'icon_name': 'book', 'order': 3,
        'description': "Programmes de formation, d’échange et de développement des compétences",
    },
    {
        'title': 'Reconnaissance', 'icon_name': 'star', 'order': 4,
        'description': "Valorisation de l’engagement, de la constance et de l’esprit de service",
    },
]


class Command(BaseCommand):
    help = "Remplit les modèles de sitecontent avec le contenu public actuel du site."

    def add_arguments(self, parser):
        parser.add_argument(
            '--reset', action='store_true',
            help="Vide les tables de contenu avant de les remplir.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        if options['reset']:
            for model in (DomainAction, ClubValue, HistoricalMilestone, MembershipBenefit, ClubStats):
                model.objects.all().delete()
            self.stdout.write(self.style.WARNING('Tables de contenu vidées.'))

        config = SiteConfig.get_config()
        config.name = "Lions Club Sfax-Méditerranée"
        config.founded_year = 2025
        config.email_contact = "secretariat@lionsmed.tn"
        config.phone_contact = "+216 00 000 000"
        config.address = "Sfax — Tunisie"
        config.monthly_meeting_day = "2e lundi de chaque mois"
        config.monthly_meeting_time = "19:00"
        config.mission_text = (
            "Nous réunissons des femmes et des hommes d'action pour identifier les besoins "
            "de nos communautés et y répondre concrètement — qu'il s'agisse de santé visuelle, "
            "d'alimentation, d'éducation, d'environnement ou d'aide d'urgence."
        )
        config.vision_text = (
            "Être le club humanitaire de référence à Sfax, reconnu pour l'impact mesurable "
            "de ses actions, la diversité de ses membres et son ancrage local."
        )
        config.history_intro = (
            "Fondé en 2025 à Sfax, le Lions Club Sfax-Méditerranée rassemble des membres "
            "fondateurs animés par une même volonté : servir utilement la ville, ses quartiers "
            "et ses initiatives citoyennes."
        )
        config.save()
        self.stdout.write(self.style.SUCCESS('SiteConfig mis à jour.'))

        stats, _ = ClubStats.objects.update_or_create(
            year=2025,
            defaults={
                'members_count': 45,
                'projects_count': 12,
                'beneficiaries_count': 500,
                'years_of_existence': 1,
            },
        )
        self.stdout.write(self.style.SUCCESS(f'ClubStats {stats.year} enregistrées.'))

        for data in DOMAINES:
            DomainAction.objects.update_or_create(title=data['title'], defaults=data)
        self.stdout.write(self.style.SUCCESS(f'{len(DOMAINES)} domaines d\'action enregistrés.'))

        for data in VALEURS:
            ClubValue.objects.update_or_create(title=data['title'], defaults=data)
        self.stdout.write(self.style.SUCCESS(f'{len(VALEURS)} valeurs enregistrées.'))

        for data in JALONS:
            HistoricalMilestone.objects.update_or_create(
                year=data['year'], title=data['title'], defaults=data
            )
        self.stdout.write(self.style.SUCCESS(f'{len(JALONS)} jalons historiques enregistrés.'))

        for data in AVANTAGES:
            MembershipBenefit.objects.update_or_create(title=data['title'], defaults=data)
        self.stdout.write(self.style.SUCCESS(f'{len(AVANTAGES)} avantages d\'adhésion enregistrés.'))

        # Les profils de bureau s'appuient sur les User existants : on ne crée pas
        # de comptes fictifs, on rattache simplement ceux qui ont un rôle de bureau.
        from django.contrib.auth import get_user_model
        User = get_user_model()
        bureau_users = User.objects.filter(
            role__in=['PRESIDENT', 'PAST_PRESIDENT', 'BUREAU'], is_active=True
        )
        created = 0
        for index, user in enumerate(bureau_users, start=1):
            _, was_created = BureauMember.objects.get_or_create(
                user=user,
                defaults={
                    'role_description': user.get_role_display(),
                    'bio': user.bio or '',
                    'email_bureau': user.email or '',
                    'order': index,
                },
            )
            created += int(was_created)
        if bureau_users:
            self.stdout.write(self.style.SUCCESS(f'{created} profil(s) de bureau créé(s).'))
        else:
            self.stdout.write(self.style.WARNING(
                'Aucun utilisateur avec un rôle de bureau : section bureau vide pour le moment.'
            ))

        self.stdout.write(self.style.SUCCESS('Seed sitecontent terminé.'))
