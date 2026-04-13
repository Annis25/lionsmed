from django.core.management.base import BaseCommand
from django.utils import timezone
from django.utils.text import slugify
import random
from datetime import timedelta


class Command(BaseCommand):
    help = 'Créer des données de démo pour le site Lions Club'

    def handle(self, *args, **kwargs):
        from accounts.models import User
        from news.models import Article, Category
        from events.models import Event, EventRegistration
        from gallery.models import Album
        from members.models import Cotisation, Document
        from voting.models import Vote, UserVote
        from notifications.models import Notification

        self.stdout.write('Création des données de démo...')

        # --- CATÉGORIES NEWS ---
        cats = [
            ('Programme Vision', 'programme-vision', '#3B82F6'),
            ('Environnement', 'environnement', '#10B981'),
            ('Vie du Club', 'vie-du-club', '#C9A84C'),
            ('Santé', 'sante', '#EF4444'),
            ('Éducation', 'education', '#8B5CF6'),
        ]
        cat_objects = {}
        for name, slug, color in cats:
            cat, _ = Category.objects.get_or_create(slug=slug, defaults={'name': name, 'color': color})
            cat_objects[slug] = cat
        self.stdout.write('✅ Catégories créées')

        # --- MEMBRES ---
        bureau_data = [
            ('Mehdi', 'Trabelsi', 'mehdi.trabelsi@lionsmed.tn', 'PRESIDENT', 'Directeur général'),
            ('Salma', 'Ben Salah', 'salma.bensalah@lionsmed.tn', 'BUREAU', 'Médecin ophtalmologue'),
            ('Karim', 'Abdallah', 'karim.abdallah@lionsmed.tn', 'BUREAU', "Avocat d'affaires"),
            ('Nadia', 'Miled', 'nadia.miled@lionsmed.tn', 'BUREAU', 'Directrice financière'),
            ('Youssef', 'Chahed', 'youssef.chahed@lionsmed.tn', 'BUREAU', 'Consultant marketing'),
            ('Leila', 'Mansour', 'leila.mansour@lionsmed.tn', 'COMITE', 'Enseignante'),
            ('Ahmed', 'Sfar', 'ahmed.sfar@lionsmed.tn', 'COMITE', 'Ingénieur'),
            ('Fatma', 'Gargouri', 'fatma.gargouri@lionsmed.tn', 'MEMBRE', 'Pharmacienne'),
            ('Rania', 'Msaddak', 'rania.msaddak@lionsmed.tn', 'MEMBRE', 'Architecte'),
            ('Lassaad', 'Bel Haj', 'lassaad.belhaj@lionsmed.tn', 'MEMBRE', 'Médecin généraliste'),
        ]
        users = {}
        for fn, ln, email, role, prof in bureau_data:
            u, created = User.objects.get_or_create(
                email=email,
                defaults={
                    'username': email.split('@')[0],
                    'first_name': fn,
                    'last_name': ln,
                    'role': role,
                    'profession': prof,
                    'is_approved': True,
                    'is_active': True,
                }
            )
            if created:
                u.set_password('lions2025')
                u.save()
            users[email] = u
        self.stdout.write('✅ 10 membres créés')

        # --- ARTICLES ---
        president = users.get('mehdi.trabelsi@lionsmed.tn')
        articles_data = [
            (
                'Plus de 300 paires de lunettes offertes lors de la caravane ophtalmo de Jendouba',
                'programme-vision',
                "Notre dernière caravane médicale dans le gouvernorat de Jendouba a permis d'offrir des consultations gratuites et 312 paires de lunettes correctrices à des personnes défavorisées sans accès aux soins. Une action menée en partenariat avec l'hôpital régional de Jendouba et 15 bénévoles Lions.",
                5,
            ),
            (
                "1 200 arbres plantés lors de la Journée Mondiale de la Forêt à Ain Draham",
                'environnement',
                "Mobilisant 95 membres et bénévoles, notre opération de reboisement dans la forêt d'Ain Draham a battu un record d'engagement pour ce club. Une réussite collective saluée par le district 414-B Tunisie.",
                3,
            ),
            (
                "Passation de service : retour sur l'assemblée élective du club — mars 2026",
                'vie-du-club',
                "Lors de l'assemblée générale extraordinaire, le nouveau bureau 2025-2026 a été élu à l'unanimité. Retour sur les moments forts de cette soirée de transmission et d'engagement.",
                4,
            ),
            (
                'Caravane de dépistage du diabète — Sfax',
                'sante',
                "En partenariat avec l'hôpital Hédi Chaker, notre club a organisé une journée de dépistage gratuit du diabète. Plus de 200 personnes ont bénéficié de cette initiative.",
                3,
            ),
            (
                'Attribution des bourses scolaires 2025-2026',
                'education',
                "40 élèves méritants issus de familles défavorisées ont reçu leurs bourses scolaires lors d'une cérémonie organisée au siège de la délégation de Sfax.",
                4,
            ),
        ]
        for title, cat_slug, content, reading_time in articles_data:
            slug = slugify(title)[:50]
            Article.objects.get_or_create(
                slug=slug,
                defaults={
                    'title': title,
                    'content': content,
                    'excerpt': content[:200],
                    'author': president,
                    'category': cat_objects.get(cat_slug),
                    'status': 'PUBLISHED',
                    'published_at': timezone.now() - timedelta(days=random.randint(1, 60)),
                    'reading_time': reading_time,
                }
            )
        self.stdout.write('✅ 5 articles créés')

        # --- ÉVÉNEMENTS ---
        now = timezone.now()
        events_data = [
            (
                "Gala de Bienfaisance 2026 — Lumière sur l'Avenir", 'GALA',
                now + timedelta(days=21), 'Hôtel The Residence, Tunis',
                True, True, 150, 'Dîner de gala au profit du programme Vision.', True,
            ),
            (
                'Assemblée Générale Ordinaire — Juin 2026', 'REUNION',
                now + timedelta(days=5), 'Maison des Associations, Sfax',
                False, False, 60, 'Réunion mensuelle du club — ordre du jour statutaire.', False,
            ),
            (
                'Caravane de dépistage du diabète — Sfax', 'ACTION',
                now + timedelta(days=12), 'Hôpital Hédi Chaker, Sfax',
                True, False, None, 'Dépistage gratuit du diabète en partenariat avec la STRS.', False,
            ),
            (
                "Cérémonie d'attribution des bourses scolaires 2026", 'ACTION',
                now + timedelta(days=7), 'Salle de conférences, Sfax',
                True, False, None, 'Remise des bourses Lions aux 40 lauréats sélectionnés.', False,
            ),
            (
                'Grande opération de plantation — Forêt de Ain Draham', 'ACTION',
                now + timedelta(days=15), 'Ain Draham, Jendouba',
                True, False, 100, 'Journée de reboisement — départ 07h00 depuis Sfax.', False,
            ),
        ]
        for title, etype, date, location, is_pub, is_pay, cap, desc, featured in events_data:
            slug = slugify(title)[:50]
            Event.objects.get_or_create(
                slug=slug,
                defaults={
                    'title': title,
                    'event_type': etype,
                    'date_start': date,
                    'location': location,
                    'is_public': is_pub,
                    'is_payant': is_pay,
                    'capacity': cap,
                    'description': desc,
                    'is_featured': featured,
                    'price': 150 if is_pay else 0,
                    'created_by': president,
                }
            )
        self.stdout.write('✅ 5 événements créés')

        # --- VOTES ---
        vote1, _ = Vote.objects.get_or_create(
            title='Approbation du budget prévisionnel 2026',
            defaults={
                'question': "Approuvez-vous le budget prévisionnel 2026 d'un montant de 45 000 TND présenté par la trésorière ?",
                'created_by': president,
                'date_start': now - timedelta(hours=2),
                'date_end': now + timedelta(days=7),
                'show_results_live': False,
                'status': 'OPEN',
            }
        )
        vote2, _ = Vote.objects.get_or_create(
            title='Organisation d\'une caravane médicale à Kasserine',
            defaults={
                'question': "Êtes-vous favorable à l'organisation d'une caravane médicale à Kasserine en juillet 2026 ?",
                'created_by': president,
                'date_start': now - timedelta(days=10),
                'date_end': now - timedelta(days=3),
                'show_results_live': True,
                'status': 'CLOSED',
            }
        )
        choices = ['POUR', 'POUR', 'POUR', 'POUR', 'CONTRE', 'ABSTENTION', 'POUR', 'POUR']
        for i, (email, _, _, _, _) in enumerate(bureau_data[:8]):
            u = users.get(email)
            if u:
                UserVote.objects.get_or_create(
                    vote=vote2, member=u,
                    defaults={'choice': choices[i]}
                )
        self.stdout.write('✅ 2 votes créés')

        # --- COTISATIONS 2025 ---
        for email, u in users.items():
            status = random.choice(['PAID', 'PAID', 'PAID', 'PENDING', 'OVERDUE'])
            Cotisation.objects.get_or_create(
                member=u, year=2025,
                defaults={
                    'amount': 200,
                    'status': status,
                    'payment_date': timezone.now().date() if status == 'PAID' else None,
                }
            )
        self.stdout.write('✅ Cotisations 2025 créées')

        # --- NOTIFICATIONS ---
        for email, u in users.items():
            Notification.objects.get_or_create(
                recipient=u,
                title='Bienvenue sur la plateforme Lions Club Sfax Méditerranée',
                defaults={
                    'message': 'Votre espace membre est maintenant actif. Consultez les prochains événements et votes.',
                    'notif_type': 'SYSTEM',
                    'is_read': False,
                }
            )
        self.stdout.write('✅ Notifications créées')

        # --- CANDIDATURES EN ATTENTE ---
        from accounts.models import MembershipRequest
        candidats = [
            ('Sami', 'Karray', 'sami.karray@gmail.com', '+216 55 123 456', "Chef d'entreprise",
             "Je souhaite contribuer aux actions humanitaires du club."),
            ('Ines', 'Boukthir', 'ines.boukthir@gmail.com', '+216 98 765 432', 'Médecin',
             'Motivée par le programme Vision et les actions de santé.'),
            ('Tarek', 'Jlassi', 'tarek.jlassi@gmail.com', '+216 22 334 455', 'Architecte',
             "Passionné par le développement local et l'engagement citoyen."),
        ]
        for fn, ln, email, phone, prof, motiv in candidats:
            MembershipRequest.objects.get_or_create(
                email=email,
                defaults={
                    'first_name': fn, 'last_name': ln,
                    'phone': phone, 'profession': prof,
                    'motivation': motiv, 'status': 'PENDING',
                }
            )
        self.stdout.write('✅ 3 candidatures créées')

        self.stdout.write(self.style.SUCCESS('\n🎉 Données de démo créées avec succès !'))
        self.stdout.write('Comptes membres : email = adresse email, mot de passe = lions2025')
        self.stdout.write('Super admin : admin / admin@lionsmed.tn / admin123')
