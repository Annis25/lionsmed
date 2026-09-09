# Lot 3 — Site public, contenus et SEO

Date : 9 septembre 2026. Runtime exclusif : `rebuild/`. Aucun import du legacy, aucune modification des maquettes, aucun Lot 4–6. Aucun commit ni push.

## Sources et état initial

Lecture du skill `.claude/skills/lionsmed-design/SKILL.md`, de l’architecture et des documents des Lots 1 et 2 ; inspection des 14 maquettes publiques, de `espace/contenu-public.html` et de l’email candidature. Le runtime reprend leur palette, leurs typographies, leurs arcs publics, leur navigation et leurs espacements à jetons. Les données démonstratives et photos sans autorisation explicite ne deviennent pas des données de production.

État initial : branche `main`, HEAD `9ca9ae4` ; seul `mockups.zip` était non suivi. `check` vert ; 101 tests existants, 99 réussis et 2 suites navigateur désactivées par défaut. Empreintes initiales conservées pour vérifier le périmètre.

L’appellation validée est **District 414 Tunisie**. Le skill applique désormais cette référence ; les mockups historiques restent inchangés.

## Pages et navigation

Routes nommées : `/`, `/notre-club/`, `/nos-actions/`, `/nos-actions/<slug>/`, `/actualites/`, `/actualites/<slug>/`, `/evenements/`, `/evenements/<slug>/`, `/rejoindre/`, `/candidature/`, `/contact/`, `/mentions-legales/`, `/confidentialite/`, `/plan-du-site/`, `/sitemap.xml`, `/robots.txt`.

Navbar : Accueil, Notre Club, Nos Actions, Nous rejoindre, Contact, Se connecter. Actualités et événements accessibles par le pied et le maillage, absents de la navbar principale. L’accueil conserve « Depuis Sfax, nous servons. » Les blocs actions, articles, prochains événements et métriques sont conditionnels ; aucune donnée fictive n’est nécessaire pour l’afficher. Les listes ont un état vide sobre et une pagination serveur de 9 éléments. Filtres GET par axe ; événements à venir/archives. Les contenus essentiels sont rendus côté serveur.

Les pages légales existent, mais les textes définitifs non validés ne sont pas présentés comme acquis : noindex jusqu’à validation éditoriale. Aucune adresse, histoire, photo, personne ou statistique de démonstration n’est importée.

## Domaines et migrations

Quatre apps : `service_actions`, `editorial`, `agenda`, `communications`. Aucune app SEO, statistiques, galerie ou dashboard.

| Migration | Modèles / effets |
| --- | --- |
| `core.0002_publicimage` | Images explicitement autorisées, stockage public distinct |
| `members.0003_membershipapplication` | Demandes d’adhésion indépendantes des comptes |
| `service_actions.0001_initial` | Action et ActionPhoto, quatre axes fermés, ordre/uniqueness galerie |
| `editorial.0001_initial` | NewsArticle, EditorialSection, ClubIdentity, ImpactMetric, Redirect |
| `agenda.0001_initial` | Event public minimal, visibilité et contraintes de dates |
| `communications.0001_initial` | ContactRequest, OutboxMessage, index de traitement |

Migrations sans données, appliquées sur PostgreSQL `lionsmed_rebuild_dev`. Les garde-fous des settings imposent PostgreSQL, `LIONSMED_DB_PURPOSE=rebuild`, un nom `lionsmed_rebuild_*` et une base de tests `test_lionsmed_rebuild_*` distincte. Aucune nouvelle dépendance Python ; Pillow et le pipeline de décodage du Lot 2 sont réutilisés.

## Publication et gestion responsable

Accès : `/espace/contenu/`. Formulaires distincts pour actions, actualités et événements, puis rubriques institutionnelles fixes, coordonnées validées, métriques sourcées et images. Aucun sélecteur transformant un énorme formulaire générique en plusieurs métiers ; aucun CMS Page/Block/JSON.

Les services `save_content`, `publish_action`, `publish_news`, `publish_event` et `withdraw_content` contrôlent les capacités serveur. Sauvegarder remet en brouillon ; publier exige titre, slug, résumé, récit et données métier complètes. Les mutations sont transactionnelles, avec verrouillage et audit. La publication renseigne les métadonnées SEO et la date de publication. Aucun bouton de publication contournant ces services dans Django Admin.

- **Action** : réalisation passée ou actuelle, lieu obligatoire non limité à Sfax, axe DIABETE/ENVIRONNEMENT/HUMANITAIRE/JEUNESSE. Bénéficiaires facultatifs et nullables, bilan/partenaires interdits à la publication sans source. Aucune dépendance à Event.
- **Actualité** : vie institutionnelle, catégorie simple, signature publique facultative, brouillons inaccessibles par slug.
- **Event** : début, fin, lieu, catégorie, visibilité PUBLIC/PRIVATE. Publication publique seulement avec dates cohérentes, lieu et visibilité PUBLIC. Un événement passé reste une archive d’événement et ne devient pas une Action. Aucun RSVP, présence ou calendrier privé.
- **Galerie** : ajout à la suite, retrait, ordre stocké et légende facultative. Modifier la galerie remet l’action en brouillon.
- **Slugs** : générés à la création si vides, conservés lors d’un changement de titre, collisions refusées. Changement explicite : 301, anciennes redirections aplaties vers la dernière URL. Les anciennes URL restent réservées. Destination interne simple seulement, sans encodage ambigu, paramètres, fragment, boucle ou chaîne. La cible doit être un contenu actuellement public.

## Éditorial et bureau

Identité de base centralisée dans `editorial/identity.py` à partir des informations fournies par l’utilisateur. ClubIdentity porte uniquement les coordonnées avec source/validation. EditorialSection est limité à des rubriques nommées : présentation, histoire, valeurs, mouvement Lions, trois motivations pour rejoindre, quatre descriptions d’axes, mentions et confidentialité. Seules les rubriques validées sont affichées.

ImpactMetric exige période, source et validation. Aucun compteur initialisé. Le bureau public projette uniquement nom, fonction et année de mandats courants validés et autorisés, avec compte actif. Les portraits membres privés, emails et autres coordonnées membres ne sont pas publiés.

## Permissions validées

Confirmation humaine reçue pendant le Lot 3 : **SUPER_ADMIN, PRESIDENT et SECRETAIRE peuvent consulter et traiter candidatures et contacts**.

| Rôle effectif | Gestion/publication | Consultation et traitement des demandes |
| --- | --- | --- |
| SUPER_ADMIN métier | Oui | Oui |
| PRESIDENT | Oui | Oui |
| SECRETAIRE | Oui | Oui |
| DIRECTEUR | Non, délégation à confirmer | Non |
| BUREAU | Non | Non |
| MEMBRE | Non | Non |
| INVITE | Non | Non |
| Anonyme | Non | Non |

Matrice centrale `core.permissions`, jamais décision par rôle dans les vues. Les règles existantes d’activité du compte, validité du RoleGrant et suspension du profil restent applicables. `is_staff` et `is_superuser` techniques ne donnent pas ces droits métier.

## Candidature et contact

Candidature : nom, prénom, email, téléphone/profession facultatifs, motivation, origine facultative, consentement et version de notice. Pas de CIN, CV, upload ou création de User. Contact : nom, email, objet fermé et message. États souples RECEIVED → CONTACTED / FOLLOW_UP / CLOSED, sans vote ou acceptation automatique.

CSRF, longueurs bornées et validation Django, normalisation email, jeton signé lié au type de formulaire et valable une heure, honeypot, redirection après succès. La clé UUID de soumission est unique en base : un double POST, y compris concurrent, ne crée qu’une demande et une entrée outbox.

Rate limiting PostgreSQL du Lot 1 réutilisé : 5 essais par IP/type/15 minutes et 3 soumissions par email/type/heure ; fenêtres temporaires, aucune exclusion permanente. Les clés sont hachées. Le compteur email est indépendant du compteur IP. Le proxy de production doit renseigner REMOTE_ADDR correctement ; aucun X-Forwarded-For non fiable n’est accepté ici.

Les pages privées de traitement affichent les données nécessaires et changent l’état via capacité et audit, sans inclure les motivations ou messages dans AuditEvent. Un état falsifié reçoit une erreur contrôlée. Les POST publics sont marqués sensibles pour les rapports d’erreur Django. Aucun contenu de demande n’est journalisé par les services.

## Emails et outbox

La soumission et son OutboxMessage sont enregistrés dans une transaction PostgreSQL ; le SMTP n’est jamais appelé pendant le POST. Candidature : accusé réception HTML + texte inspiré de la maquette, aucune promesse d’acceptation. Contact : notification interne uniquement si `LIONSMED_CONTACT_RECIPIENT` est configuré ; aucune réponse utilisateur inventée. Une adresse configurée invalide empêche le démarrage avec une erreur de configuration sans révéler sa valeur. Une configuration vide conserve les contacts en base, consultables dans l’espace responsable, mais ne crée pas d’email interne rétroactif.

Commande à exécuter depuis `rebuild/` avec le backend SMTP configuré :

```sh
.venv/bin/python manage.py deliver_outbox --limit 20
```

L’exploitation peut lancer cette commande périodiquement ; aucun ordonnanceur n’a été installé ou activé pendant ce lot. `select_for_update(skip_locked)` réserve un message avec bail de 5 minutes ; SMTP hors transaction ; 5 tentatives maximum, délais exponentiels en minutes, état FAILED au-delà. Message-ID stable et sortie en compteurs, jamais traceback SMTP ou données personnelles. Le backend dummy laisse les messages en attente. Une interruption après acceptation SMTP avant marquage SENT peut provoquer une répétition : l’outbox fournit une livraison réessayable, pas une garantie « exactement une fois » SMTP. Les FAILED restent disponibles pour diagnostic technique ; pas de réémission automatique illimitée.

Le reset du Lot 1 reste inchangé. Aucun email réel envoyé pendant les validations : backend mémoire et données synthétiques.

## Images

Décodage partagé `core/image_processing.py` : JPEG/PNG/WebP, cohérence extension/type/contenu, 5 Mo, 16 millions de pixels, dimension maximale 8000, image fixe, orientation corrigée et métadonnées retirées. Deux dérivés WebP 480/1024 maximum, sans agrandissement, générés à l’upload. Les originaux ne sont pas conservés dans le nouveau stockage public.

Alt, source et autorisation explicite obligatoires. Fichiers sous `runtime/public_images`, distincts des photos membres, sans exposition directe de ce répertoire par le serveur web. L’endpoint vérifie une référence à un contenu publié et autorisé. Une image de brouillon n’est pas servie. `srcset`, `sizes`, width/height, lazy loading et priorité pour la couverture de fiche ; aucune réencodage par requête. Nettoyage des fichiers nouvellement créés en cas d’échec transactionnel.

## SEO, sécurité et performance

Titles/descriptions, canonical basé sur `SITE_ORIGIN` configuré côté serveur, OG/Twitter, un H1 par page et fil d’Ariane. La pagination conserve `?page=N` canonique ; recherche/filtres/archives sont noindex. La candidature, ses succès, l’authentification et tout le privé restent noindex. Les brouillons répondent 404.

Sitemap Django : contenus publiés, événements PUBLIC, pages indexables et textes légaux seulement validés ; `lastmod` réel pour les objets édités, aucune date fictive pour les routes statiques. Aucune URL auth, privée, candidature, filtre ou brouillon. Robots local/test/préproduction : Disallow global et en-têtes noindex. En production, l’indexation exige explicitement `LIONSMED_PUBLIC_INDEXING=true` ; configurer `DJANGO_SITE_ORIGIN=https://lionsmed.tn`. Le sitemap ignore le Host utilisateur et utilise l’origine configurée. Robots n’est jamais un contrôle d’accès.

JSON-LD : NGO institutionnel, BreadcrumbList, NewsArticle et Event seulement si pertinent. Action n’est jamais balisée Event. Pas de Person pour un membre non validé. Sérialisation JSON côté Python puis échappement de `<`, `>` et `&` avant l’unique bloc `autoescape off` réservé à ce JSON ; test d’injection `</script>` inclus. Le récit reste du texte échappé avec retours à la ligne, pas du HTML arbitraire.

Audit des occurrences sensibles réalisé : aucun nouveau csrf_exempt, mark_safe, filtre safe, URL de fichier privé, lecture de next ou Host pour le canonical, décision de vue par rôle ou flags Django. Les occurrences de published/slug sont modèles, migrations, services, sélecteurs filtrés et tests. Les images utilisent leur endpoint contrôlé. Les paramètres de recherche passent par l’ORM.

Préchargement cover/social_image et galerie : test garantissant un nombre de requêtes constant entre 1 et 9 cartes et aucune requête de RoleGrant sur les pages publiques. Pagination bornée. Cache conservateur `private, no-store` maintenu pour ce lot ; aucune mise en cache partagée de pages personnalisées. CSS/JS locaux réutilisés, polices configurées comme au Lot 1. HSTS includeSubDomains/preload restent inchangés et prudents.

## Validation

Les commandes finales et résultats sont consignés ci-dessous. Les tests navigateur utilisent Chrome/Playwright déjà disponibles, sans ajout de dépendance de production. Base PostgreSQL de tests séparée, fixtures synthétiques détruites après chaque suite. Les captures restent dans `/tmp/lionsmed-lot3-page*.png`, les mesures dans `/tmp/lionsmed-lot3-responsive.json`.

108 combinaisons du Lot 3 : 14 pages publiques + gestion responsable et ses trois formulaires, chacune à 1440, 1280, 1024, 768, 430 et 375 px. Vérification du statut, d’un H1, de l’absence d’overflow, des labels et alt, des images cassées, du menu mobile au clavier, du skip link et des erreurs accessibles. Reduced motion activé ; contact soumis sans JavaScript. Revue visuelle de captures desktop/mobile et correction des axes, des CTA du hero, des cartes et des cases de consentement. Il s’agit de contrôles techniques et visuels ciblés, pas d’une certification exhaustive avec lecteurs d’écran.

## Données restant à confirmer humainement

Textes légaux définitifs, responsable de publication/hébergement, modalités et durées de conservation, coordonnées institutionnelles, destinataire interne contact et configuration SMTP, histoire/fondation, noms et mandats publics, photos autorisées, véritables réalisations/articles/événements et métriques sourcées. Aucun de ces éléments n’a été inventé. Le droit avancé du DIRECTEUR demeure refusé jusqu’à décision explicite. La délégation de traitement des demandes aux trois rôles ci-dessus est, elle, confirmée.

### Résultats finaux

- `check` : aucune anomalie.
- `makemigrations --check` : aucune migration manquante.
- `migrate --check` : aucune migration en attente.
- Suite complète PostgreSQL avec `LIONSMED_BROWSER_TESTS=1` : **131 tests réussis, aucun ignoré**, 79,524 s.
- Navigateur : **204 contrôles responsive** (Lot 1 : 30, Lot 2 : 66, Lot 3 : 108), aucune erreur JavaScript ; parcours sans JavaScript validés.
- `git diff --check` : vert. Empreintes avant/après : 14 fichiers existants modifiés, tous dans rebuild ; aucun fichier du legacy ou de mockups modifié.

Reproduction depuis `rebuild/` :

```sh
.venv/bin/python manage.py check
.venv/bin/python manage.py makemigrations --check
.venv/bin/python manage.py migrate --check
LIONSMED_BROWSER_TESTS=1 PLAYWRIGHT_MODULE=/chemin/vers/playwright .venv/bin/python manage.py test --settings=config.settings.test --noinput
```

## Inventaire exact du Lot 3

Chemins relatifs à `/home/besbes/Documents/lionsmed`. `mockups.zip`, préexistant et non suivi, est exclu du travail de ce lot.

### Créés (87)

```text
docs/LOT_3_SITE_PUBLIC_SEO.md
rebuild/apps/agenda/__init__.py
rebuild/apps/agenda/apps.py
rebuild/apps/agenda/forms.py
rebuild/apps/agenda/migrations/0001_initial.py
rebuild/apps/agenda/migrations/__init__.py
rebuild/apps/agenda/models.py
rebuild/apps/agenda/services.py
rebuild/apps/agenda/urls.py
rebuild/apps/communications/__init__.py
rebuild/apps/communications/apps.py
rebuild/apps/communications/forms.py
rebuild/apps/communications/management/__init__.py
rebuild/apps/communications/management/commands/__init__.py
rebuild/apps/communications/management/commands/deliver_outbox.py
rebuild/apps/communications/migrations/0001_initial.py
rebuild/apps/communications/migrations/__init__.py
rebuild/apps/communications/models.py
rebuild/apps/communications/outbox.py
rebuild/apps/communications/services.py
rebuild/apps/communications/urls.py
rebuild/apps/communications/views.py
rebuild/apps/core/image_processing.py
rebuild/apps/core/migrations/0002_publicimage.py
rebuild/apps/editorial/__init__.py
rebuild/apps/editorial/apps.py
rebuild/apps/editorial/forms.py
rebuild/apps/editorial/identity.py
rebuild/apps/editorial/images.py
rebuild/apps/editorial/management_forms.py
rebuild/apps/editorial/management_urls.py
rebuild/apps/editorial/management_views.py
rebuild/apps/editorial/migrations/0001_initial.py
rebuild/apps/editorial/migrations/__init__.py
rebuild/apps/editorial/models.py
rebuild/apps/editorial/publication.py
rebuild/apps/editorial/selectors.py
rebuild/apps/editorial/seo.py
rebuild/apps/editorial/services.py
rebuild/apps/editorial/sitemaps.py
rebuild/apps/editorial/tests/__init__.py
rebuild/apps/editorial/tests/test_browser.py
rebuild/apps/editorial/tests/test_public.py
rebuild/apps/editorial/urls.py
rebuild/apps/editorial/views.py
rebuild/apps/members/migrations/0003_membershipapplication.py
rebuild/apps/service_actions/__init__.py
rebuild/apps/service_actions/apps.py
rebuild/apps/service_actions/forms.py
rebuild/apps/service_actions/migrations/0001_initial.py
rebuild/apps/service_actions/migrations/__init__.py
rebuild/apps/service_actions/models.py
rebuild/apps/service_actions/services.py
rebuild/apps/service_actions/urls.py
rebuild/static/css/accueil.css
rebuild/static/css/nos-actions.css
rebuild/static/css/notre-club.css
rebuild/static/css/rejoindre.css
rebuild/templates/components/public/card.html
rebuild/templates/components/public/hero_arcs.html
rebuild/templates/components/public/image.html
rebuild/templates/components/public/page_arcs.html
rebuild/templates/components/public/page_hero.html
rebuild/templates/components/public/pagination.html
rebuild/templates/components/public/priorities.html
rebuild/templates/emails/application_receipt.html
rebuild/templates/emails/application_receipt.txt
rebuild/templates/emails/contact_notice.html
rebuild/templates/emails/contact_notice.txt
rebuild/templates/emails/public_base.html
rebuild/templates/espace/content_form.html
rebuild/templates/espace/content_list.html
rebuild/templates/espace/editorial_form.html
rebuild/templates/espace/public_content.html
rebuild/templates/espace/request_detail.html
rebuild/templates/espace/requests.html
rebuild/templates/public/base.html
rebuild/templates/public/club.html
rebuild/templates/public/detail.html
rebuild/templates/public/join.html
rebuild/templates/public/legal.html
rebuild/templates/public/list.html
rebuild/templates/public/privacy.html
rebuild/templates/public/sitemap.html
rebuild/templates/public/submission.html
rebuild/templates/public/submission_done.html
rebuild/tools/browser_public.cjs
```

### Modifiés (14)

```text
rebuild/.env.example
rebuild/apps/core/context_processors.py
rebuild/apps/core/middleware.py
rebuild/apps/core/models.py
rebuild/apps/core/permissions.py
rebuild/apps/members/models.py
rebuild/apps/members/uploads.py
rebuild/config/settings/base.py
rebuild/config/settings/production.py
rebuild/config/urls.py
rebuild/static/css/lions.css
rebuild/templates/base/site.html
rebuild/templates/components/public/footer.html
rebuild/templates/public/home.html
```

### Supprimés (0)

Aucun.

### git status --short

```text
 M rebuild/.env.example
 M rebuild/apps/core/context_processors.py
 M rebuild/apps/core/middleware.py
 M rebuild/apps/core/models.py
 M rebuild/apps/core/permissions.py
 M rebuild/apps/members/models.py
 M rebuild/apps/members/uploads.py
 M rebuild/config/settings/base.py
 M rebuild/config/settings/production.py
 M rebuild/config/urls.py
 M rebuild/static/css/lions.css
 M rebuild/templates/base/site.html
 M rebuild/templates/components/public/footer.html
 M rebuild/templates/public/home.html
?? docs/LOT_3_SITE_PUBLIC_SEO.md
?? mockups.zip
?? rebuild/apps/agenda/
?? rebuild/apps/communications/
?? rebuild/apps/core/image_processing.py
?? rebuild/apps/core/migrations/0002_publicimage.py
?? rebuild/apps/editorial/
?? rebuild/apps/members/migrations/0003_membershipapplication.py
?? rebuild/apps/service_actions/
?? rebuild/static/css/accueil.css
?? rebuild/static/css/nos-actions.css
?? rebuild/static/css/notre-club.css
?? rebuild/static/css/rejoindre.css
?? rebuild/templates/components/public/card.html
?? rebuild/templates/components/public/hero_arcs.html
?? rebuild/templates/components/public/image.html
?? rebuild/templates/components/public/page_arcs.html
?? rebuild/templates/components/public/page_hero.html
?? rebuild/templates/components/public/pagination.html
?? rebuild/templates/components/public/priorities.html
?? rebuild/templates/emails/application_receipt.html
?? rebuild/templates/emails/application_receipt.txt
?? rebuild/templates/emails/contact_notice.html
?? rebuild/templates/emails/contact_notice.txt
?? rebuild/templates/emails/public_base.html
?? rebuild/templates/espace/content_form.html
?? rebuild/templates/espace/content_list.html
?? rebuild/templates/espace/editorial_form.html
?? rebuild/templates/espace/public_content.html
?? rebuild/templates/espace/request_detail.html
?? rebuild/templates/espace/requests.html
?? rebuild/templates/public/base.html
?? rebuild/templates/public/club.html
?? rebuild/templates/public/detail.html
?? rebuild/templates/public/join.html
?? rebuild/templates/public/legal.html
?? rebuild/templates/public/list.html
?? rebuild/templates/public/privacy.html
?? rebuild/templates/public/sitemap.html
?? rebuild/templates/public/submission.html
?? rebuild/templates/public/submission_done.html
?? rebuild/tools/browser_public.cjs
```
