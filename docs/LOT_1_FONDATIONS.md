# Lot 1 — Fondations, comptes et shells Django

Livraison du 9 septembre 2026. Périmètre arrêté au Lot 1. Aucun commit, push, import de données, changement des maquettes ou suppression du legacy.

## Architecture réelle et isolation

Le nouveau runtime est installé dans `rebuild/` : `config/settings/{base,local,test,production}.py`, `apps/`, `templates/`, `static/`, `manage.py`, `requirements.txt` et `.env.example`. Cette isolation évite de remplacer le custom User dans un schéma déjà migré. Le `manage.py`, les settings, dépendances, migrations, templates et fichiers statiques historiques restent intacts. Le document `NOUVELLE_ARCHITECTURE_LIONSMED.md` préexistait et n'a pas été modifié.

Les quatre apps sont `accounts`, `members`, `governance`, `core`. Aucune app des lots suivants n'est créée. La consigne actuelle autorise explicitement Django et prévaut sur le périmètre historique « mockups uniquement » du skill. Ses règles graphiques sont conservées ; l'intitulé institutionnel demandé maintenant est **District 414 Tunisie**.

Dépendances du nouveau runtime : Django 5.2.17, psycopg 3.3.5 avec son paquet binaire, django-axes 8.3.1, python-dotenv 1.2.3. Un seul pilote PostgreSQL est utilisé. Le psycopg2 et l'environnement Python du legacy ne sont pas modifiés. La validation a utilisé Python 3.12.3 et PostgreSQL 16 disponibles localement. La version PostgreSQL de déploiement reste à arrêter avec l'exploitation.

## Modèles et migrations

| App | Modèle | Contrat |
| --- | --- | --- |
| accounts | User | UUID, email unique normalisé, prénom, nom, compte actif, timestamps, primitives de sécurité Django. Aucun champ role ni username. |
| members | MemberProfile | OneToOne protégé, statut ACTIVE/GUEST/SUSPENDED, timestamps. Aucun profil complet ou photo. |
| governance | LionsYear | Dates ordonnées, borne finale exclusive, libellé dérivé, archivage nullable, exclusion PostgreSQL des chevauchements. |
| governance | ClubState | Singleton contraint à la clé 1, année active nullable et protégée contre suppression. |
| governance | RoleGrant | Compte, un des sept rôles, période, révocation, auteur, création. Historique conservé. |
| core | AuditEvent | Auteur, action, référence de l'objet, résultat et date ; aucun payload libre ou secret. |
| core | AuthThrottle | Infrastructure uniquement : compteur atomique partagé PostgreSQL, clé HMAC, expiration. Pas de Redis nécessaire. |

L'email est normalisé par trim et minuscules sur l'ensemble de l'adresse, au login et au reset également. Les contraintes PostgreSQL empêchent les écritures en masse non normalisées et les doublons.

Quatre migrations `0001_initial.py` créent ces modèles. Le custom User existe dès la première migration `accounts`. La migration `governance` installe `btree_gist` avant les exclusions ; l'opérateur de migration doit pouvoir créer cette extension, ou la faire installer au préalable dans la **nouvelle base**. Les migrations Django/axes nécessaires sont également appliquées. Aucune migration de données, année active ou compte réel n'est livré.

Deux grants non révoqués ne peuvent pas se chevaucher pour un même compte, même lors d'écritures concurrentes. Un changement de rôle passe par expiration ou révocation de l'ancien grant, puis nouvelle attribution. Les services verrouillent le compte et réalisent mutation et audit dans la même transaction. La révocation est idempotente. Les écritures directes ORM/SQL ne constituent pas une API d'administration et doivent rester réservées aux opérateurs techniques ; elles ne produisent pas automatiquement l'audit des services.

## Permissions et bootstrap

Rôles exacts : SUPER_ADMIN, DIRECTEUR, PRESIDENT, SECRETAIRE, BUREAU, MEMBRE, INVITE.

Le contrat central est `can(user, capability, obj=None)`. Deux capacités seulement existent : `account.access_private_area` et `account.change_own_password`. Elles sont explicitement autorisées aux sept rôles pour les deux vues de ce lot. Une capacité inconnue, un compte inactif, l'absence de profil ou de grant, un profil suspendu, un grant futur/expiré/révoqué ou une situation ambiguë entraînent un refus. Un profil GUEST exige le rôle INVITE. Il n'existe aucun repli implicite vers MEMBRE. L'objet facultatif doit être le compte lui-même, y compris lorsque Django fournit un utilisateur chargé paresseusement.

Le grant est évalué à chaque requête, sur `[starts_at, ends_at)`, sans cron. La navigation et les vues utilisent le même contrat, mais les vues vérifient elles-mêmes les droits. DIRECTEUR et BUREAU n'ont aucun pouvoir avancé ; `management.access` est inconnu et refusé, également pour SUPER_ADMIN.

`is_staff`/`is_superuser` sont strictement techniques. Le rôle métier SUPER_ADMIN ne modifie aucun de ces attributs. L'admin Django permet uniquement aux superutilisateurs techniques actifs de gérer les comptes ; la suppression des comptes est désactivée. Aucune UI d'audit, de grants ou d'administration métier n'est créée.

Bootstrap futur, à exécuter par un opérateur autorisé, sans mot de passe dans la ligne de commande :

```sh
python rebuild/manage.py createsuperuser
python rebuild/manage.py grant_role --actor UUID_TECHNIQUE --user UUID_PERSONNEL --role MEMBRE
python rebuild/manage.py revoke_role --actor UUID_TECHNIQUE --grant IDENTIFIANT_GRANT
```

Créer le compte personnel via l'admin technique, puis utiliser son UUID. Les comptes doivent correspondre à des personnes, pas à des boîtes génériques. `grant_role` accepte aussi `--ends-at` avec une date ISO et un fuseau ; il crée le profil minimal s'il manque. Il ne modifie pas silencieusement un statut existant. Un passage d'invité à membre nécessite donc également une décision explicite sur le statut, par l'opérateur, en attendant le Lot 2. Aucun compte technique ou personnel n'a été créé dans la base de développement pendant cette livraison.

## Authentification et sécurité

- Login email avec AuthenticationForm/LoginView Django, erreurs neutres, CSRF, email conservé et mot de passe jamais réaffiché. La destination `next` est validée par Django ; une URL externe est refusée.
- Logout POST uniquement avec CSRF ; GET retourne 405.
- Reset : demande, réponse neutre connue/inconnue, lien valide, définition, succès et lien invalide/expiré. Jeton Django à usage unique, durée d'une heure, sans connexion automatique après reset. Le lien utilise l'origine configurée, jamais un Host fourni librement par le client. Le token est remplacé dans l'URL par le mécanisme Django avant saisie.
- L'email texte/HTML utilise le contexte Django. La seule adaptation d'envoi intercepte l'échec SMTP avec un code de log fixe, sans exception ni adresse ni token. Pas de worker, queue, retry ou outbox. L'envoi synchrone ne garantit pas un temps de réponse identique entre adresse connue et inconnue ; l'outbox future devra traiter cette limite.
- Changement du mot de passe protégé, ancien mot de passe requis, validateurs Django, session actualisée par Django.
- Rotation de session au login ; cookies dédiés, HttpOnly, SameSite Lax. Fermeture à la fin du navigateur par défaut, option de conservation plafonnée à 12 heures. Secure activé en production, désactivé en local/test.
- Axes : cinq échecs par paire email/IP, blocage 15 minutes ; compteur PostgreSQL supplémentaire limitant le login à 20 POST/IP/15 minutes. Reset : 5 POST/IP/15 minutes et 3 demandes/adresse/heure. Les clés des compteurs supplémentaires sont HMAC ; Axes conserve ses données techniques d'échecs dans ses tables propres.
- Aucun en-tête proxy client n'est pris pour une IP fiable. La configuration d'un reverse proxy réel doit être arrêtée avant déploiement ; sans cela plusieurs visiteurs derrière un proxy partageraient la limite IP.
- Nettoyage facultatif : `python rebuild/manage.py purge_auth_throttles`. Le refus/renouvellement des fenêtres fonctionne sans ce nettoyage ; prévoir la rétention des tables Axes à l'exploitation.
- X-Frame-Options DENY, nosniff, Referrer-Policy same-origin, HTTPS/HSTS en production. Pages privées/auth sans cache, noindex dans les balises et en-têtes. Tout le Lot 1 reste noindex, robots.txt interdit l'exploration et aucun sitemap n'est créé.
- Stockage média futur hors routes publiques ; aucun endpoint de téléchargement n'est créé.

Recherche finale effectuée sur le nouveau code : aucune occurrence de `csrf_exempt`, `mark_safe`, `|safe` ou `?role=`. Les occurrences de password/SECRET_KEY correspondent aux primitives, champs, variables d'environnement, templates et fixtures synthétiques. Les privilèges Django n'apparaissent que dans le bootstrap, l'admin et leurs tests. Les redirections sont celles des vues Django ou une destination interne constante. Aucun rôle reçu du navigateur ne décide des permissions.

**MFA PRIVILÉGIÉS À FINALISER** : aucune fausse MFA ou TOTP artisanal. La mise en production des comptes privilégiés nécessitera une bibliothèque maintenue et une procédure de récupération validées. Configurer également les logs du serveur HTTP/proxy pour expurger les URLs de reset et ne jamais journaliser leurs jetons, ni les corps POST. Aucun secret réel ne doit alimenter les fixtures ou les captures.

## Templates et design

Les CSS validés `lions.css` et `prive.css` sont copiés dans le nouveau runtime ; seul le premier reçoit de petites adaptations pour les erreurs Django, le menu de compte, les destinations différées et le fonctionnement sans JS. Les jetons existants sont conservés. L'emblème existant est le seul fichier image repris. Aucun framework UI, photo externe, démonstrateur, backup ou faux traitement n'est importé.

Bases `site`, `public`, `private`, includes publics partagés, composants de formulaires et erreurs 403/404/500. La connexion et le reset reprennent les maquettes correspondantes. L'accueil est une simple entrée vers l'espace membre avec les arcs publics ; ce n'est pas la future page éditoriale complète. Le shell privé reprend la sidebar/header et affiche uniquement l'identité réelle, le rôle effectif et l'année active éventuelle. Pas de KPI fictif.

Navbar : Accueil, Notre Club, Nos Actions, Nous rejoindre, Contact, Se connecter. Les quatre destinations publiques non livrées sont des textes non focusables `aria-disabled`, en attendant leurs lots : aucune fausse route ni lien `#` inerte. Le footer conserve sa structure commune et ses intitulés différés ; l'adresse email issue de la maquette porte sa réserve de validation. L'institution est indiquée « District 414 Tunisie », sans limiter la portée du service à Sfax.

Blocs SEO : title, meta_description, canonical, robots et structured_data. Les données éditoriales structurées seront ajoutées avec les pages éditoriales ; les canonicals de reset n'exposent pas le token. JS limité aux menus, focus clavier, visibilité du mot de passe et année du footer. Le formulaire fonctionne sans JS.

Réponses aux trois questions du skill :

1. La composition publique conserve les arcs et la typographie, reconnaissables sans dépendre de la couleur ou du logo. Le privé conserve volontairement son identité de travail sans arc. Pas de photographie utilisée.
2. Dominantes : titre du hero d'entrée, carte d'authentification, identité/état du compte dans le dashboard, marque institutionnelle dans le footer.
3. La marque, l'ancrage, le District, la devise et l'Année Lions relient le shell au club. Le contenu métier qui le distinguera davantage est volontairement différé, conformément au Lot 1.

## Configuration et commandes

Ne jamais lancer le `manage.py` historique pour ce runtime. Depuis la racine :

```sh
python3 -m venv rebuild/.venv
rebuild/.venv/bin/pip install -r rebuild/requirements.txt
cp rebuild/.env.example rebuild/.env
chmod 600 rebuild/.env
# Renseigner les variables localement, sans les publier.
rebuild/.venv/bin/python rebuild/manage.py check
rebuild/.venv/bin/python rebuild/manage.py makemigrations --check
rebuild/.venv/bin/python rebuild/manage.py migrate
rebuild/.venv/bin/python rebuild/manage.py runserver
```

Créer au préalable une **base PostgreSQL neuve et dédiée**. La connexion doit la désigner sans ambiguïté. Le rôle de test doit pouvoir créer/détruire sa base de tests ; les permissions de production seront plus restrictives. Les settings exigent `LIONSMED_DB_PURPOSE=rebuild`, `DB_NAME` commençant par `lionsmed_rebuild_`, et une base de test distincte commençant par `test_lionsmed_rebuild_`. La commande migrate refuse aussi les tables legacy connues. Ces garde-fous complètent la vérification du cluster et du propriétaire ; ils ne remplacent pas cette vérification.

Le seul dotenv lu est `rebuild/.env` ; jamais celui du legacy. Les variables déjà exportées priment. Variables du fichier exemple, sans valeurs réelles :

| Variables | Usage |
| --- | --- |
| DJANGO_SECRET_KEY | Clé propre au nouveau runtime, obligatoire ; forte et au moins 50 caractères en production. |
| LIONSMED_DB_PURPOSE | Marqueur explicite rebuild. |
| DB_NAME, DB_USER, DB_HOST | Obligatoires, exclusivement nouvelle base. |
| DB_PASSWORD, DB_PORT | Authentification du nouveau serveur ; port 5432 par défaut. |
| DB_TEST_NAME | Facultatif, défaut test_ suivi du nom de la nouvelle base. |
| DJANGO_ALLOWED_HOSTS | Hôtes exacts séparés par virgules en production. |
| DJANGO_SITE_ORIGIN | Origine sans chemin, HTTPS en production ; localhost:8000 par défaut local. |
| LIONSMED_SMTP_ENABLED | Seule la valeur true active SMTP en production. |
| EMAIL_HOST, EMAIL_PORT, EMAIL_HOST_USER, EMAIL_HOST_PASSWORD, DEFAULT_FROM_EMAIL | Requis pour l'activation SMTP, port 587 par défaut, TLS. |

Backend mail local dummy (aucun message envoyé ou imprimé), test locmem (mémoire), production dummy jusqu'à activation explicite. MD5 n'est utilisé que dans les settings de tests synthétiques ; local/production gardent les hashers Django normaux. Les répertoires `.venv`, `.env`, `runtime/` sont ignorés par Git.

Pour cette validation, environnement temporaire `/tmp/lionsmed-lot1-venv`, cluster PostgreSQL neuf `/tmp/lionsmed-lot1-pg`, socket `/tmp/lionsmed-lot1-socket`, port 55439, sans écoute TCP. Le socket est dans un répertoire privé ; aucune credential legacy utilisée. Le dotenv local ignoré pointe vers ce cluster. Les données et outils sous `/tmp` sont temporaires et devront être recréés après nettoyage/redémarrage. Aucun compte applicatif ou année n'est initialisé dans la base de développement.

## Validation exécutée

- `check` : aucun problème.
- `makemigrations --check --dry-run` : aucune modification détectée.
- `migrate` puis `migrate --check` sur la nouvelle base : migrations appliquées, aucune en attente.
- **60 tests passent sur PostgreSQL**, navigateur inclus ; aucun test ignoré dans cette exécution complète. Sans activation navigateur : 59 tests fonctionnels et un test navigateur explicitement ignoré.
- Email, erreurs neutres, reset invalide/expiré/usage unique/échec SMTP, CSRF, logout POST/GET, next externe, rôles/périodes/révocation, matrice des sept rôles, objets propres/autrui, profils suspendus, année active absente, singleton/chevauchements, audit transactionnel, protection de migration legacy, concurrence des grants et compteurs, noindex et templates couverts.
- **30 contrôles responsive** : accueil, connexion, reset, dashboard et changement de mot de passe à **1440, 1280, 1024, 768, 430 et 375 px**. Aucun débordement horizontal, un H1, noms accessibles, saisies ≥44 px, reduced motion, noindex et zéro erreur JS.
- Navigation clavier : skip link, menus et fermeture Escape, boucle de focus sidebar ; connexion réelle et navigation privée sans JS. Captures desktop/mobile inspectées pour connexion et dashboard ; ces contrôles ne constituent pas une certification WCAG complète.
- `check --deploy --settings=config.settings.production`, avec une clé éphémère et un domaine fictif : seulement **security.W005** (HSTS sous-domaines) et **security.W021** (preload). Choix conservateurs explicites jusqu'à validation HTTPS de tous les sous-domaines. HSTS initial 3600 secondes. Aucun warning masqué.

Reproduction des tests :

```sh
rebuild/.venv/bin/python rebuild/manage.py test apps.core.tests --settings=config.settings.test --noinput
# Avec Node, Playwright et Chrome disponibles (outils de test uniquement) :
LIONSMED_BROWSER_TESTS=1 PLAYWRIGHT_MODULE=/chemin/vers/playwright CHROME_PATH=/chemin/vers/chrome \
  rebuild/.venv/bin/python rebuild/manage.py test apps.core.tests --settings=config.settings.test --noinput
```

Le test navigateur crée son compte synthétique uniquement dans la base de tests, génère son mot de passe en mémoire, puis Django détruit la base. Rapport temporaire `/tmp/lionsmed-lot1-responsive.json`, captures `/tmp/lionsmed-lot1-*.png`. Aucun identifiant réel dans ces fichiers.

## Décisions reportées

Calendrier exact des Années Lions (proposition 1er juillet à confirmer), délégations avancées DIRECTEUR/BUREAU et gestion future des rôles, règles détaillées d'adhésion, MFA privilégiés, fournisseur SMTP/délivrabilité de l'adresse de contact, hôtes/proxy/HSTS/retenue des logs et version PostgreSQL d'exploitation. Aucun de ces choix n'a été remplacé par des données fictives de production.

Le Lot 2 n'est pas commencé.

## Inventaire exact des fichiers de cette livraison

Créés (85) :

```text
docs/LOT_1_FONDATIONS.md
rebuild/.env.example
rebuild/apps/__init__.py
rebuild/apps/accounts/__init__.py
rebuild/apps/accounts/admin.py
rebuild/apps/accounts/apps.py
rebuild/apps/accounts/backends.py
rebuild/apps/accounts/forms.py
rebuild/apps/accounts/migrations/0001_initial.py
rebuild/apps/accounts/migrations/__init__.py
rebuild/apps/accounts/models.py
rebuild/apps/accounts/urls.py
rebuild/apps/accounts/views.py
rebuild/apps/core/__init__.py
rebuild/apps/core/apps.py
rebuild/apps/core/context_processors.py
rebuild/apps/core/management/__init__.py
rebuild/apps/core/management/commands/__init__.py
rebuild/apps/core/management/commands/migrate.py
rebuild/apps/core/management/commands/purge_auth_throttles.py
rebuild/apps/core/middleware.py
rebuild/apps/core/migrations/0001_initial.py
rebuild/apps/core/migrations/__init__.py
rebuild/apps/core/models.py
rebuild/apps/core/permissions.py
rebuild/apps/core/tests/__init__.py
rebuild/apps/core/tests/test_browser.py
rebuild/apps/core/tests/test_foundations.py
rebuild/apps/core/throttling.py
rebuild/apps/core/views.py
rebuild/apps/governance/__init__.py
rebuild/apps/governance/apps.py
rebuild/apps/governance/management/__init__.py
rebuild/apps/governance/management/commands/__init__.py
rebuild/apps/governance/management/commands/grant_role.py
rebuild/apps/governance/management/commands/revoke_role.py
rebuild/apps/governance/migrations/0001_initial.py
rebuild/apps/governance/migrations/__init__.py
rebuild/apps/governance/models.py
rebuild/apps/governance/services.py
rebuild/apps/members/__init__.py
rebuild/apps/members/apps.py
rebuild/apps/members/migrations/0001_initial.py
rebuild/apps/members/migrations/__init__.py
rebuild/apps/members/models.py
rebuild/config/__init__.py
rebuild/config/settings/__init__.py
rebuild/config/settings/base.py
rebuild/config/settings/local.py
rebuild/config/settings/production.py
rebuild/config/settings/test.py
rebuild/config/urls.py
rebuild/config/wsgi.py
rebuild/manage.py
rebuild/requirements.txt
rebuild/static/css/lions.css
rebuild/static/css/prive.css
rebuild/static/images/emblem-256.png
rebuild/static/js/lions.js
rebuild/templates/403.html
rebuild/templates/404.html
rebuild/templates/500.html
rebuild/templates/accounts/base.html
rebuild/templates/accounts/limited.html
rebuild/templates/accounts/login.html
rebuild/templates/accounts/password_change.html
rebuild/templates/accounts/password_change_done.html
rebuild/templates/accounts/reset.html
rebuild/templates/accounts/reset_complete.html
rebuild/templates/accounts/reset_confirm.html
rebuild/templates/accounts/reset_done.html
rebuild/templates/base/private.html
rebuild/templates/base/public.html
rebuild/templates/base/site.html
rebuild/templates/components/forms/errors.html
rebuild/templates/components/forms/field.html
rebuild/templates/components/public/access_arcs.html
rebuild/templates/components/public/footer.html
rebuild/templates/components/public/navbar.html
rebuild/templates/emails/password_reset.html
rebuild/templates/emails/password_reset.txt
rebuild/templates/emails/password_reset_subject.txt
rebuild/templates/espace/dashboard.html
rebuild/templates/public/home.html
rebuild/tools/browser.cjs
```

Modifié : `.gitignore` uniquement (exclusions du runtime isolé).

Supprimés : aucun fichier préexistant.

Un `rebuild/.env` local a aussi été créé, ignoré et protégé ; ses valeurs ne sont pas livrées. Les caches Python sont ignorés.

Vérification SHA-256 de tous les fichiers préexistants : seuls les changements de `.gitignore` sont constatés ; aucune suppression. Le contenu de `mockups/`, `db.sqlite3`, les anciennes migrations et le document d’architecture sont inchangés.

État Git final (les entrées `docs/` et `mockups.zip` existaient déjà comme non suivies avant ce lot) :

```text
 M .gitignore
?? docs/
?? mockups.zip
?? rebuild/
```

Aucun commit ni push.
