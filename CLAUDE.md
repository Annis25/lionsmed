# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Portée du dépôt — lire avant toute modification

Ce dépôt contient **trois zones distinctes**. Confondre l'une avec l'autre est l'erreur la plus
coûteuse possible ici :

| Zone | Statut | À faire |
|---|---|---|
| `rebuild/` | **Runtime actif, seul code en développement** | Toute modification de code Django va ici |
| Racine (`accounts/ core/ events/ gallery/ members/ news/ notifications/ sitecontent/ voting/ lionsclub_platform/`, `db.sqlite3`, `templates/`, `static/` à la racine) | **Legacy figé**, plus le runtime de production | Ne pas modifier ; sert uniquement de source **lecture seule** pour l'import ponctuel via `import_legacy` |
| `mockups/` | Maquettes HTML/CSS/JS statiques, gouvernées par le skill `lionsmed-design` | Ne modifier que si la tâche concerne explicitement les maquettes ; charger le skill avant toute édition. Aucun fichier Django n'est touché depuis ce dossier |

Preuve : les 5 derniers commits ne touchent que `rebuild/` et `docs/`. `docs/FINAL_PROJECT_CONTEXT.md`
confirme : « Le runtime actif est `rebuild/` ; les mockups et le legacy ne sont pas le runtime de
production. » Sauf tâche explicite de migration/legacy, **tout se passe dans `rebuild/`**.

Le reste de ce document décrit uniquement `rebuild/`.

## Commandes

Environnement déjà installé dans `rebuild/.venv/`. Toutes les commandes ci-dessous supposent soit
le cwd `rebuild/` avec le venv activé, soit un appel explicite depuis la racine du dépôt (les deux
formes sont données).

```sh
# Activer l'environnement (depuis rebuild/)
source .venv/bin/activate

# Serveur de dev — settings.local est le défaut de rebuild/manage.py, pas besoin de --settings
python manage.py runserver
# équivalent depuis la racine :
rebuild/.venv/bin/python rebuild/manage.py runserver
```

`config/settings/local.py`/`base.py` exigent un vrai PostgreSQL même en dev (`rebuild/.env` avec
`DB_NAME` commençant par `lionsmed_rebuild_`) — jamais de bascule silencieuse vers SQLite. Voir
`rebuild/.env.example` pour les variables requises.

```sh
# Tests — toute la suite (base Postgres de test dédiée, isolée du dev)
python manage.py test --settings=config.settings.test --noinput

# Un seul module / une seule classe / un seul test
python manage.py test apps.agenda.tests.test_agenda --settings=config.settings.test --noinput
python manage.py test apps.agenda.tests.test_agenda.RegistrationTests --settings=config.settings.test --noinput
python manage.py test apps.agenda.tests.test_agenda.RegistrationTests.test_invite_cannot_register --settings=config.settings.test --noinput

# Migrations (la commande migrate est surchargée, voir plus bas)
python manage.py makemigrations apps.<app>
python manage.py migrate --settings=config.settings.local          # dev
python manage.py migrate --settings=config.settings.production      # prod
python manage.py migrate --check --settings=config.settings.production   # vérif post-restauration

python manage.py collectstatic --noinput --settings=config.settings.production
python manage.py check --deploy --settings=config.settings.production

# Rôles (jamais via l'admin Django — toujours par cette commande, auditée)
python manage.py grant_role --actor <uuid_technique> --user <uuid_personnel> --role PRESIDENT
python manage.py revoke_role --actor <uuid_technique> --user <uuid_personnel> --role PRESIDENT

# Outbox e-mail (voir section « Envoi d'e-mails » plus bas)
python manage.py deliver_outbox --limit 20
python manage.py outbox_status --settings=config.settings.production   # compteurs seulement, jamais contenu/destinataire
python manage.py send_event_reminders

# Import legacy (lecture seule de db.sqlite3, jamais l'inverse)
python manage.py import_legacy --source /chemin/db.sqlite3                                    # dry-run
python manage.py import_legacy --source /chemin/db.sqlite3 --apply --operator-email a@b.tn    # écriture réelle, idempotent
```

QA navigateur manuelle (Playwright, pas de dépendance npm committée) :

```sh
LIONSMED_BROWSER_URL=http://localhost:8000 node tools/browser.cjs
# variantes : tools/browser_members.cjs (espace privé), tools/browser_public.cjs
```
Ces scripts vérifient par page : overflow horizontal, exactement un `<h1>`, aucun contrôle
interactif sans label accessible, cibles tactiles ≥44px, absence d'animation (`reducedMotion`),
et présence de `noindex` tant que `PUBLIC_INDEXING_ENABLED` n'est pas activé.

## Architecture

### Structure de `rebuild/`

```
config/settings/  base.py (commun + validations fail-closed) → local.py / test.py / production.py
config/urls.py    urlconf racine : assemble les urls publiques et « espace/ » de chaque app
apps/<app>/       models.py, forms.py, selectors.py, services.py, views.py, urls.py, tests/
runtime/          fichiers non versionnés : private_media/, public_images/ (créés au runtime)
deploy/systemd/   unités systemd versionnées (outbox, rappels d'événements)
```

`config/settings/base.py` **échoue au démarrage** (`ImproperlyConfigured`) si une variable requise
manque, si `DB_NAME` ne commence pas par `lionsmed_rebuild_`, ou si `DJANGO_SITE_ORIGIN` n'est pas
une origine HTTP(S) propre. C'est volontaire : aucun environnement mal configuré ne démarre
silencieusement en mode dégradé. `local.py`/`test.py`/`production.py` ne font que surcharger
`base.py` (DEBUG, cookies non-secure en local, SMTP conditionnel en prod, etc.).

`config/urls.py` sépare systématiquement, pour chaque app, un module monté à la racine (public) et
un module monté sous `espace/` (privé) — mais **le nom du fichier public n'est pas toujours
`urls.py`**, vérifier `config/urls.py` avant de supposer :

- `editorial.urls` (public) / `editorial.management_urls` (privé, `espace/contenu/...`)
- `service_actions.urls`, `agenda.urls`, `communications.urls` : **publics**, montés à la racine
- `agenda.private_urls`, `communications.private_urls` : privés (`espace/`)
- `members.public_urls` (public, profil public) / `members.urls` (**privé**, `espace/` — nommage
  inversé par rapport aux autres apps, source d'erreur fréquente)
- `governance.urls`, `documents.urls`, `dues.urls`, `voting.urls`, `satisfaction.urls` : privés
  uniquement (`espace/`), pas de routes publiques pour ces domaines

Ne jamais monter un `urls.py` sans vérifier dans `config/urls.py` s'il est inclus à la racine ou
sous `espace/`.

### Les 12 apps métier (`apps/`)

| App | Responsabilité |
|---|---|
| `core` | Transverse : permissions (voir plus bas), middleware, context processor de navigation, import legacy, throttling |
| `accounts` | Identité/auth : `User` custom, backend email, MFA TOTP, changement d'email contrôlé |
| `governance` | `LionsYear`, `ClubState`, `Mandate`, `RoleGrant` — la source des rôles effectifs |
| `members` | `MemberProfile`, parcours associatif, candidatures d'adhésion, annuaire, profil public |
| `service_actions` | Mémoire des réalisations sociales (`Action`, 4 axes fixes : Diabète/Environnement/Humanitaire/Jeunesse) |
| `editorial` | Institution, contenu public, SEO, sitemap, espace de gestion de contenu (`espace/contenu/`) |
| `agenda` | Événements, inscriptions (RSVP), présences, export ICS |
| `voting` | Scrutins, électeurs figés, bulletins anonymes (voir « Votes » plus bas) |
| `satisfaction` | Périodes mensuelles et réponses de satisfaction |
| `documents` | Bibliothèque de documents privés, ACL nominatives, scan antivirus obligatoire |
| `dues` | Cotisations annuelles déclaratives et historique de correction |
| `communications` | Contact, notifications in-app, outbox e-mail, campagnes de diffusion membres |

Convention de fichiers par app (respectée partout, pas une suggestion) : `models.py` porte les
contraintes de données ; `forms.py` valide les entrées HTTP ; `selectors.py` regroupe les requêtes
de lecture (querysets filtrés par permission) ; `services.py` regroupe les mutations sensibles,
toujours transactionnelles ; `views.py` reste un fin routage HTTP qui appelle services/selectors et
vérifie une capability. Pas de logique métier dans les signaux Django.

### Permissions — source unique : `apps/core/permissions.py`

Système **par capability**, pas par hiérarchie de rôles. Ne jamais tester `role == "PRESIDENT"`
dans une vue : toujours passer par `can(user, "capability.name", obj=None)` ou le décorateur
`@capability_required("capability.name")`.

- `CAPABILITIES` : dict `"domaine.action" → frozenset[Role]` autorisés. C'est la seule table de
  vérité des droits ; les groupes nommés (`MANAGERS`, `BUREAU_LEVEL`, `DUES_MANAGERS`, etc.) en
  haut du fichier ne sont que des raccourcis de lecture.
- 14 rôles (`apps/governance/models.py: Role`) : `SUPER_ADMIN, DIRECTEUR, PRESIDENT,
  PRESIDENT_FONDATEUR, VICE_PRESIDENT, SECRETAIRE, TRESORIER, BUREAU, GST, GMT, GLT, LCIF, MEMBRE,
  INVITE`.
- `effective_role(user)` : lit les `RoleGrant` actifs à l'instant (`starts_at`/`ends_at`/
  `revoked_at`). **Un seul rôle actif attendu** — si un utilisateur a deux grants actifs
  simultanément, c'est un état ambigu et `effective_role` retourne `None` (refus), jamais le rôle
  le plus permissif.
- `can()` vérifie ensuite le statut du `MemberProfile` (SUSPENDED refuse tout ; GUEST ne passe que
  pour le rôle INVITE), puis un contrôle objet si `obj` est fourni (propriétaire, statut ACTIVE
  pour l'annuaire, etc.).
- Rôles et grants se gèrent **uniquement** via `manage.py grant_role`/`revoke_role`, jamais via
  Django Admin.

### Envoi d'e-mails — outbox uniquement, jamais synchrone

**Aucun e-mail n'est envoyé de façon synchrone**, à la seule exception de la vue standard Django de
réinitialisation de mot de passe (action interactive attendue immédiatement par l'utilisateur).
Tout le reste (activation de compte, candidature, contact, rappels d'événement, votes,
satisfaction, campagnes de diffusion) passe par `communications.OutboxMessage` +
`apps.communications.outbox.deliver_batch()`, appelé par `manage.py deliver_outbox`.

- **Sans worker planifié, les messages restent `PENDING` indéfiniment** — incident déjà survenu en
  prod. En production, `deliver_outbox` tourne via le timer systemd `lionsmed-outbox.timer`
  (`rebuild/deploy/systemd/`, toutes les minutes) ; `lionsmed-event-reminders.timer` appelle
  `send_event_reminders` une fois par jour.
- Concurrence gérée par `select_for_update(skip_locked=True)` dans `deliver_batch` : deux
  exécutions qui se chevauchent ne posent aucun problème, pas de verrou externe nécessaire.
- Un message devenu définitivement non pertinent avant envoi (mot de passe déjà défini, droit
  retiré, objet cible supprimé...) passe en `FAILED`/`error_code="not_applicable"` immédiatement,
  sans les 5 tentatives de retry réservées aux échecs SMTP transitoires
  (`error_code="delivery_failed"`).
- `outbox_status` est l'outil de supervision opérationnelle : compteurs par état + âge du plus
  ancien `PENDING`. **N'affiche jamais** destinataire, sujet ou contenu — ne pas le remplacer par
  une requête ORM manuelle qui exposerait ces champs dans un log/terminal partagé.
- SMTP est désactivé par défaut (`EMAIL_BACKEND` = dummy) tant que `LIONSMED_SMTP_ENABLED=true`
  n'est pas positionné explicitement (`config/settings/production.py`).

### Fichiers privés et images publiques

- `PRIVATE_MEDIA_ROOT` (documents, portraits) : **aucun mapping URL** vers ce stockage, jamais
  servi par Nginx. Tout accès passe par une vue Django qui revérifie l'ACL à chaque requête
  (`documents:download`, `members:photo`).
- `apps/documents/scanning.py` : scan antivirus ClamAV (protocole INSTREAM direct, pas de lib
  tierce). **Échec fermé** : toute indisponibilité/timeout du scanner lève `ScannerUnavailable` et
  bloque la disponibilité du document — jamais de document rendu disponible faute de scanner
  joignable, y compris si ClamAV n'est simplement pas configuré (`CLAMD_SOCKET`/`CLAMD_HOST` non
  définis dans `config/settings/base.py`).
- `PUBLIC_IMAGE_ROOT` : dérivés d'images publiques (couche `PublicImage`), distincts des originaux
  privés dans `MediaAsset`.
- Upload de photo : `apps.members.upload_handlers.PhotoSizeLimitHandler` en premier
  `FILE_UPLOAD_HANDLERS` (limite avant même l'écriture en mémoire/tmp).

### Import legacy (`apps/core/legacy_pipeline.py`, `manage.py import_legacy`)

Lecture seule de `db.sqlite3` (racine du dépôt) ; jamais de connexion directe du runtime rebuild à
cette base. Idempotent via `core.LegacyImportRecord` (clé `source+table+PK legacy`). Toujours
lancer en dry-run d'abord (comportement par défaut, `--apply` requis pour écrire). Règles précises
de ce qui est importé / mis en quarantaine / délibérément exclu (ex. `news_article` supprimé du
produit, aucun rôle jamais accordé automatiquement) : voir `docs/MIGRATE_LEGACY_TO_REBUILD.md`.

La commande `migrate` est surchargée (`apps/core/management/commands/migrate.py`) : elle **refuse
de s'exécuter** si la base cible contient une table legacy connue
(`sitecontent_siteconfig`, `accounts_membershiprequest`, `voting_vote`, `events_event`,
`members_cotisation`) — garde-fou contre un `DB_NAME` mal configuré qui pointerait sur la base
legacy.

### Votes — intégrité et anonymat

`apps/voting` sépare délibérément `Participation` (preuve qu'un électeur a voté, liée 1-1 à
`Elector`) de `Ballot`/`BallotSelection` (bulletin, **sans aucune FK vers l'électeur, l'IP ou un
timestamp précis**). L'absence de lien applicatif Participation→Ballot est intentionnelle, pas un
oubli. Toute évolution de ce module doit préserver cette séparation ; ne jamais ajouter de FK ou de
log reliant un bulletin à son auteur.

**Seule exception, décidée par le propriétaire (sept. 2026) : le scrutin nominatif.** `Vote.disclosure`
vaut `SECRET` (défaut, tous les scrutins antérieurs) ou `NOMINATIVE`, fixé à la création et annoncé
aux électeurs avant le vote (carte, récapitulatif, notification, e-mail). Pour un scrutin nominatif
uniquement, `cast_vote` enregistre en plus un `NominativeChoice` (électeur → options), sans aucun
lien avec `Ballot`, qui reste anonyme et seule source du décompte. Consultation : capability
`vote.view_nominative` (SUPER_ADMIN seul), après clôture. Un scrutin `SECRET` ne doit jamais
produire de `NominativeChoice`.

### Tests

- `TestCase`/`TransactionTestCase` standard Django. Helper commun :
  `apps.core.tests.test_foundations.account(email, role=Role.MEMBRE, **kwargs)` crée un `User` +
  `MemberProfile` + `RoleGrant` cohérents — à réutiliser plutôt que recréer la mécanique manuellement.
  Chaque app garde ses tests sous `apps/<app>/tests/`.
- `config/settings/test.py` : base Postgres dédiée (`test_<DB_NAME>`), `MD5PasswordHasher` (rapidité,
  jamais en production), backend e-mail `locmem` (les tests lisent `django.core.mail.outbox`, pas
  l'outbox applicative, sauf test explicite de `deliver_outbox`).

### Documentation complémentaire (`docs/`)

- `docs/FINAL_PROJECT_CONTEXT.md` : état courant tenu à jour à chaque session notable (dernière
  source de vérité sur l'avancement réel, les non-régressions et les décisions produit encore
  ouvertes).
- `docs/NOUVELLE_ARCHITECTURE_LIONSMED.md` : proposition d'architecture d'origine (823 lignes,
  schéma conceptuel complet des modèles/permissions/parcours). Très largement mise en œuvre telle
  quelle, mais **pas 100% figée** — ex. le rôle effectif final compte 14 valeurs, pas les 7
  proposées initialement. En cas de doute, le code (`apps/*/models.py`,
  `apps/core/permissions.py`) fait foi sur ce document.
- `docs/MIGRATE_LEGACY_TO_REBUILD.md` : règles exactes de l'import ponctuel legacy → rebuild.
- `docs/DEPLOY_REBUILD.md` : runbook complet de déploiement (PostgreSQL, ClamAV, Gunicorn, Nginx,
  timers systemd, sauvegarde/restauration, rollback).
- `.claude/skills/lionsmed-design/SKILL.md` : système de design verrouillé des maquettes
  (`mockups/`) — palette, typographie, composants partagés. À charger avant toute édition de
  maquette ; ne pas dupliquer ces règles ici.
