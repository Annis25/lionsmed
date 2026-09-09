# Lot 2 — Membres, gouvernance et espace privé

Livraison du 9 septembre 2026. Runtime cible exclusif : `rebuild/`. Sources lues : skill lionsmed-design, architecture validée, rapport Lot 1 et maquettes profil, profil-membre, annuaire, membres, responsables, tableau-de-bord. Aucune modification du legacy, des maquettes ou des migrations initiales. Aucun Lot 3 commencé, aucun commit/push.

## Préalable et environnement

Branche initiale `main`, HEAD `5e23e9e`. Les fichiers du Lot 1 étaient déjà indexés à l'ouverture ; leur index a été conservé. `mockups.zip` était déjà non suivi. L'état de travail du Lot 2 reste séparé de cet état initial, sans reset ni restauration.

Le chemin documenté `rebuild/.venv/bin/python` était absent. Avant modification du code : contrôle avec l'environnement isolé existant `/tmp/lionsmed-lot1-venv`, `check` sans problème et 60 tests découverts, 59 fonctionnels réussis, navigateur explicitement ignoré. Un environnement local ignoré `rebuild/.venv` a ensuite été créé avec les dépendances du Lot 1 et Pillow 12.3.0.

PostgreSQL 16, exclusivement nouvelle base `lionsmed_rebuild_dev`, garde-fous du Lot 1 actifs, base de tests distincte créée/détruite par Django. Le contrôle final confirme zéro compte applicatif dans la base de développement. Les comptes et années synthétiques sont créés uniquement dans la base de tests. Aucun secret ou dotenv historique utilisé.

## Modèles et migrations

- **MemberProfile étendu** : téléphone (32 caractères), profession (150), bio (1 000), clé de photo privée générée au serveur ; apparition dans l'annuaire et partage séparé de profession, bio, coordonnées, photo, expériences et mandats. Tous ces choix sont faux par défaut. Nom, prénom et email restent dans User.
- **AssociationExperience** : UUID, profil propriétaire, réseau fermé Lions/LEO, club, fonction libre, district, mois de début/fin, description et réalisations (1 500 caractères chacun), timestamps. Le premier jour du mois matérialise la précision mensuelle ; la fin est le mois inclus. Contraintes PostgreSQL sur réseau, ordre des dates et précision au premier jour. L'ordre d'affichage est chronologique décroissant, sans champ de classement inutile.
- **Mandate** : UUID, profil, fonction institutionnelle libre, Année Lions, bornes de dates avec fin exclusive, validation datée et auteur, autorisation publique future fausse par défaut, timestamps. Dates ordonnées et paire de validation contraintes en base. Inclusion dans l'année contrôlée par `clean()` et le service transactionnel ; elle n'est pas prétendue garantie par un CHECK inter-table. Aucun lien automatique avec RoleGrant.
- **User, RoleGrant, LionsYear et ClubState** : schéma inchangé. Aucune date de juillet imposée, année ou compte créé par migration.

Migrations nouvelles, appliquées uniquement au rebuild :

1. `members/0002_memberprofile_bio_memberprofile_directory_visible_and_more.py`.
2. `governance/0002_mandate.py` (dépend de la nouvelle migration members).

## Capabilities et matrice réelle

Le contrat central `can(user, capability, obj=None)` est conservé. User actif, profil admissible, grant effectif daté et non révoqué restent requis. Aucun rôle n'est lu depuis le navigateur. Aucun privilège métier ne devient `is_staff` ou `is_superuser`.

| Capacité / surface | SUPER_ADMIN | DIRECTEUR | PRESIDENT | SECRETAIRE | BUREAU | MEMBRE | INVITE |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Dashboard et changement de mot de passe | Oui | Oui | Oui | Oui | Oui | Oui | Oui |
| profile.view_own / profile.edit_own | Propre | Propre | Propre | Propre | Propre | Propre | Propre |
| experience.manage_own | Propre | Propre | Propre | Propre | Propre | Propre | Propre |
| directory.view / member.view | Selon partage | Selon partage | Selon partage | Selon partage | Selon partage | Selon partage | Non |
| members.view_management | Lecture | Non | Lecture | Lecture | Non | Non | Non |
| management.access / year.view | Lecture | Non | Lecture | Lecture | Non | Non | Non |
| mandate.manage | Non | Non | Non | Non | Non | Non | Non |
| account.change_email | Non | Non | Non | Non | Non | Non | Non |

Anonyme : aucune capacité privée. Les autorisations de consultation gestion de SUPER_ADMIN/PRESIDENT/SECRETAIRE viennent de la matrice §10 de l'architecture validée. La mutation des statuts, rôles, mandats et années n'est pas déduite de cette consultation. DIRECTEUR conserve ses droits personnels de membre actif, sans supervision ajoutée. BUREAU n'obtient aucune capacité de gestion.

Les deux capacités de mutation vides correspondent à des points de service concrets ; elles ne permettent aucune mutation en production. Le bootstrap technique des grants du Lot 1 reste inchangé et distinct des délégations métier.

## Profil, parcours et confidentialité

Le profil possède une consultation et une édition séparées, avec photo/résumé, email verrouillé, informations principales en deux colonnes sur desktop, choix de partage et historique. Le formulaire et le service ont des listes blanches : email, role, flags Django, statut, propriétaire et clé de photo forgés ne sont jamais enregistrés. Le service verrouille le compte puis le profil, recontrôle les droits et enregistre nom/prénom et profil ensemble.

Le CRUD des expériences utilise des routes UUID et un selector limité au propriétaire. Les forms et services contrôlent également le propriétaire, y compris le cas d'une expérience propre qu'un appel tenterait de réaffecter à autrui. La suppression demande confirmation via page GET puis POST/CSRF ; aucun effet de bord au GET. Le mini-CV n'est jamais une source de droits actuels.

L'annuaire expose seulement les profils volontairement visibles de comptes actifs, avec statut ACTIVE et grant actuel hors INVITE. Recherche GET bornée à 100 caractères sur noms et **profession partagée uniquement**, filtre de rôle et pagination de 12. Rechercher une profession privée ne révèle pas sa présence. Pas de recherche par email ou téléphone.

Les fiches reçues par les templates sont des dictionnaires construits explicitement par le selector : les champs non autorisés sont absents, aucun objet User d'autrui ne leur est transmis. Les coordonnées exigent `share_contacts`, les photos `share_photo`, les expériences `share_experiences`. Seuls les mandats validés et partagés sont exposés dans l'annuaire. Le propriétaire peut consulter tout son historique, y compris non validé.

Les gestionnaires voient identité, statut, rôle actuel et mandats institutionnels en lecture seule, même pour un profil absent de l'annuaire. Cette consultation ne contourne pas la confidentialité des coordonnées ou portraits. Les requêtes sont paginées et les vérifications restent explicites par objet ; l'optimisation des requêtes de projection pour de grands annuaires reste possible sans changer la politique.

## Photos privées

Pillow 12.3.0 est la seule dépendance ajoutée, dédiée au décodage/réencodage. Le traitement suit les mécanismes documentés de [décodage et limites de pixels Pillow](https://pillow.readthedocs.io/en/stable/reference/Image.html) et d'[orientation EXIF](https://pillow.readthedocs.io/en/stable/reference/ImageOps.html).

- Formats admis : JPEG, PNG, WebP fixes. Extension, MIME annoncé et format effectivement décodé doivent concorder. SVG, images animées, fichiers invalides et extensions mensongères refusés.
- Maximum 5 Mio, 16 millions de pixels et 8 000 pixels sur un axe. Taille contrôlée pendant la réception par un upload handler, puis avant décodage ; dépassement HTTP : 400 sans modification du profil.
- Vérification puis décodage complet ; orientation EXIF appliquée ; réduction à 1 024 × 1 024 maximum ; nouvelle toile RGB et nouveau JPEG. Aucun EXIF, commentaire ou profil ICC original conservé. Aucun original enregistré.
- Nom serveur aléatoire `portraits/<uuid>.jpg`, clé non éditable via formulaire. Stockage sous PRIVATE_MEDIA_ROOT, permissions fichier 0600/répertoire 0700, hors routes publiques. Aucun `.file.url` dans le code ou les templates.
- GET/HEAD photo autorisés au propriétaire ou à un membre admissible lorsque le profil ET la photo sont partagés. Requête d'autrui masquée : 404 ; invité refusé ; anonyme redirigé au login. FileResponse image/jpeg, nosniff, private/no-store et noindex.
- Remplacement/suppression : ancien fichier supprimé après commit ; nouveau fichier supprimé si la transaction échoue. Le service de profil possède une transaction durable pour éviter un rollback externe après publication du fichier. Une interruption brutale du processus peut laisser un fichier orphelin privé ; une purge d'exploitation pourra traiter ces fichiers sans rendre les anciennes clés accessibles.

Aucune photo n'est promue sur le public. L'autorisation future du portrait de bureau demeure distincte. Le proxy de déploiement devra également limiter la taille totale des requêtes avant Django.

## Gouvernance et dashboards

Les responsables autorisés disposent d'une liste avec recherche, rôle, statut, mandats par année et fiche de gestion. Les Années Lions enregistrées et l'année active sont consultables, sans mutation. Mandats et RoleGrant sont complètement séparés : modifier un ancien mandat ne peut pas accorder un rôle courant.

`save_mandate` est un service transactionnel de préparation avec capacité, liste blanche, validation de l'année et audit atomique. Sa capacité est vide : aucun rôle ne peut actuellement l'utiliser et aucune UI de mutation n'est exposée. Le test positif de son contrat utilise une délégation simulée **uniquement dans le test**, sans changer la matrice de production. Validation/publication de mandats et modification des dates d'année restent réservées à une future politique explicite ; aucune API brute ni admin de mandat n'est créée.

Dashboard membre : identité, portrait autorisé pour soi, rôle actuel, année active éventuelle, état du partage, parcours et liens réels. Dashboard responsable : comptes personnels, membres actifs (statut ACTIVE et compte actif), mandats enregistrés (tous états), année et liens de consultation. La zone « À traiter » indique l'absence d'année active si pertinente ; elle n'invente aucune tâche de mutation. Aucun compteur de vote/cotisation/document/présence/notification.

La sidebar repose sur les capabilities et des routes réelles. Les vues vérifient les mêmes droits côté serveur. Tous les écrans privés et photos restent noindex/no-store, sans sitemap ni données personnelles en structured data public.

## Changement d'email : partie préparée, activation différée

L'email est exclu du formulaire profil. Une page séparée explique que la procédure n'est pas disponible. Le service `request_email_change` vérifie la capability vide `account.change_email` ; la validation normalise l'adresse et vérifie format, longueur et unicité. **Aucune adresse n'est modifiée et aucune confirmation factice n'est acceptée.** Même avec une délégation simulée, le service refuse tant que la preuve sur la nouvelle adresse n'existe pas.

Restent à réaliser après décisions humaines : délégants et portée objet, réauthentification, demande expirante et preuve de contrôle de la nouvelle adresse, avertissement ancien/nouveau email, unicité sous transaction à finalisation, invalidation des sessions et audit expurgé dans cette même transaction. Pas d'EmailChangeRequest inutilisé, d'outbox, d'envoi réel ou de token artisanal créé ici. Aucun événement d'audit de « changement réussi » n'est écrit pour une opération refusée. Cette limite est explicite, conformément à l'autorisation de préparer le service sans contourner la sécurité.

## Templates et accessibilité

Bases privées du Lot 1 conservées, CSS privé enrichi avec les jetons existants seulement. Composants utiles : avatar, identité, parcours, mandats, recherche, pagination et icônes de navigation reprises des maquettes. Les composants de formulaire sont conservés, avec disposition compacte des cases à cocher. Aucun framework, JS métier simulé, faux lien ou donnée de démonstration livré hors tests.

Les onze pages contrôlées : dashboard, profil, édition du profil, annuaire, fiche membre, parcours, ajout d'expérience, gestion membres, pilotage, années, fiche de gestion. Suppression d'expérience et information email ont également des templates et contrôles HTTP. Les actions importantes passent par de vrais formulaires POST/CSRF, utilisables sans JS.

Questions du skill : la typographie et les proportions du shell privé restent reconnaissables indépendamment de la couleur ; les arcs sont volontairement absents. L'identité domine le profil, le formulaire l'édition, les personnes l'annuaire, l'historique le parcours et les indicateurs disponibles le pilotage. Les notions Lions/LEO, Années Lions et mandats ancrent cet outil dans son usage associatif. Aucune photo réelle n'est utilisée pour la validation.

## Validation et commandes

Depuis la racine :

```sh
rebuild/.venv/bin/python rebuild/manage.py check
rebuild/.venv/bin/python rebuild/manage.py makemigrations --check --dry-run
rebuild/.venv/bin/python rebuild/manage.py migrate --check
rebuild/.venv/bin/pip check
```

Suite complète depuis `rebuild/` (évite la découverte des tests legacy) :

```sh
.venv/bin/python manage.py test --settings=config.settings.test --noinput
# Avec les outils navigateur disponibles :
LIONSMED_BROWSER_TESTS=1 PLAYWRIGHT_MODULE=/chemin/vers/playwright CHROME_PATH=/chemin/vers/chrome \
  .venv/bin/python manage.py test --settings=config.settings.test --noinput
```

Résultat final : **101 tests réussis sur PostgreSQL, aucun ignoré**, navigateur inclus. Sans activation navigateur : 99 tests fonctionnels et deux contrôles navigateur explicitement ignorés.

Checks Django/migrations/dépendances : OK, aucun schéma en attente. Les tests du Lot 1 restent présents ; seuls deux contrats devenus obsolètes ont été actualisés explicitement : « profil minimal seulement » devient « identité non dupliquée », et sa matrice teste ses deux capacités d'origine au lieu de supposer que toute nouvelle capacité est universelle.

La nouvelle suite couvre les sept rôles et l'anonyme, mutations propres, POST forgés, IDOR de views/forms/services, filtre de profession privée, champs absents du contexte/HTML, consentements, pagination, dates/mois, séparation mandat/grant, services différés, contraintes et transactions PostgreSQL, CSRF, formats d'uploads, dimensions/taille, EXIF, accès GET/HEAD, remplacement/suppression et rollback des fichiers. Les tests de concurrence RoleGrant et throttling du Lot 1 sont conservés.

Le navigateur valide les six largeurs 1440/1280/1024/768/430/375 : 66 contrôles Lot 2 et 30 contrôles Lot 1, H1 unique, absence de débordement, noms accessibles, dimensions de saisie, noindex et absence d'erreur JS. Parcours clavier, erreurs, menu/Escape et modifications/recherche/suppression sans JS vérifiés. Captures desktop et mobile examinées ; ce n'est pas une certification WCAG ni une recette multi-navigateurs complète.

Artefacts temporaires : `/tmp/lionsmed-lot2-responsive.json`, `/tmp/lionsmed-lot2-page*-*.png`, rapport Lot 1 séparé. Un passage a rencontré une erreur ponctuelle du protocole de capture Chrome dans le test Lot 1 ; la suite complète a été relancée, sans supprimer le contrôle.

Revue finale des occurrences demandées : aucun csrf_exempt, mark_safe, filtre safe ou file.url ajouté. `member.role` est un libellé de projection, pas une autorisation ; les flags Django restent uniquement dans le code technique du Lot 1. L'email n'est transmis que pour soi ou selon le partage serveur. Aucun secret ajouté.

## Décisions humaines encore nécessaires

Calendrier institutionnel exact, délégations de mutation des mandats/statuts/rôles/années, changement d'email et confirmation fiable, validation et publication du bureau/portraits, conservation des photos/CV/audits, MFA privilégiés et configuration d'exploitation du Lot 1. Ces limites n'accordent aucun pouvoir à DIRECTEUR ou BUREAU par défaut.

## Fichiers et état Git

L'inventaire ci-dessous décrit le delta de ce lot par rapport aux hashes de début de session, y compris les fichiers Lot 1 déjà indexés. L'environnement `rebuild/.venv` est local et ignoré ; ses dépendances sont consignées dans requirements. Aucun fichier préexistant supprimé.

### Créés (36)

```text
docs/LOT_2_MEMBRES_GOUVERNANCE.md
rebuild/apps/accounts/email_changes.py
rebuild/apps/governance/mandates.py
rebuild/apps/governance/migrations/0002_mandate.py
rebuild/apps/governance/urls.py
rebuild/apps/governance/views.py
rebuild/apps/members/forms.py
rebuild/apps/members/migrations/0002_memberprofile_bio_memberprofile_directory_visible_and_more.py
rebuild/apps/members/selectors.py
rebuild/apps/members/services.py
rebuild/apps/members/tests/__init__.py
rebuild/apps/members/tests/test_browser.py
rebuild/apps/members/tests/test_members.py
rebuild/apps/members/upload_handlers.py
rebuild/apps/members/uploads.py
rebuild/apps/members/urls.py
rebuild/apps/members/views.py
rebuild/templates/components/private/avatar.html
rebuild/templates/components/private/experiences.html
rebuild/templates/components/private/identity.html
rebuild/templates/components/private/mandates.html
rebuild/templates/components/private/nav_icon.html
rebuild/templates/components/private/pagination.html
rebuild/templates/components/private/search.html
rebuild/templates/espace/directory.html
rebuild/templates/espace/email_information.html
rebuild/templates/espace/experience_delete.html
rebuild/templates/espace/experience_form.html
rebuild/templates/espace/experiences.html
rebuild/templates/espace/management_dashboard.html
rebuild/templates/espace/management_detail.html
rebuild/templates/espace/management_members.html
rebuild/templates/espace/profile.html
rebuild/templates/espace/profile_edit.html
rebuild/templates/espace/years.html
rebuild/tools/browser_members.cjs
```

### Modifiés (13)

```text
rebuild/apps/core/context_processors.py
rebuild/apps/core/permissions.py
rebuild/apps/core/tests/test_foundations.py
rebuild/apps/core/views.py
rebuild/apps/governance/models.py
rebuild/apps/members/models.py
rebuild/config/settings/base.py
rebuild/config/urls.py
rebuild/requirements.txt
rebuild/static/css/prive.css
rebuild/templates/base/private.html
rebuild/templates/components/forms/field.html
rebuild/templates/espace/dashboard.html
```

### Supprimés (0)

Aucun.

Vérification SHA-256 : tous les fichiers hors périmètre sont inchangés, notamment `mockups/`, `db.sqlite3`, le legacy et les deux documents antérieurs. Les anciennes migrations du rebuild sont également inchangées.

### git status --short final

```text
M  .gitignore
A  docs/LOT_1_FONDATIONS.md
A  docs/NOUVELLE_ARCHITECTURE_LIONSMED.md
A  rebuild/.env.example
A  rebuild/apps/__init__.py
A  rebuild/apps/accounts/__init__.py
A  rebuild/apps/accounts/admin.py
A  rebuild/apps/accounts/apps.py
A  rebuild/apps/accounts/backends.py
A  rebuild/apps/accounts/forms.py
A  rebuild/apps/accounts/migrations/0001_initial.py
A  rebuild/apps/accounts/migrations/__init__.py
A  rebuild/apps/accounts/models.py
A  rebuild/apps/accounts/urls.py
A  rebuild/apps/accounts/views.py
A  rebuild/apps/core/__init__.py
A  rebuild/apps/core/apps.py
AM rebuild/apps/core/context_processors.py
A  rebuild/apps/core/management/__init__.py
A  rebuild/apps/core/management/commands/__init__.py
A  rebuild/apps/core/management/commands/migrate.py
A  rebuild/apps/core/management/commands/purge_auth_throttles.py
A  rebuild/apps/core/middleware.py
A  rebuild/apps/core/migrations/0001_initial.py
A  rebuild/apps/core/migrations/__init__.py
A  rebuild/apps/core/models.py
AM rebuild/apps/core/permissions.py
A  rebuild/apps/core/tests/__init__.py
A  rebuild/apps/core/tests/test_browser.py
AM rebuild/apps/core/tests/test_foundations.py
A  rebuild/apps/core/throttling.py
AM rebuild/apps/core/views.py
A  rebuild/apps/governance/__init__.py
A  rebuild/apps/governance/apps.py
A  rebuild/apps/governance/management/__init__.py
A  rebuild/apps/governance/management/commands/__init__.py
A  rebuild/apps/governance/management/commands/grant_role.py
A  rebuild/apps/governance/management/commands/revoke_role.py
A  rebuild/apps/governance/migrations/0001_initial.py
A  rebuild/apps/governance/migrations/__init__.py
AM rebuild/apps/governance/models.py
A  rebuild/apps/governance/services.py
A  rebuild/apps/members/__init__.py
A  rebuild/apps/members/apps.py
A  rebuild/apps/members/migrations/0001_initial.py
A  rebuild/apps/members/migrations/__init__.py
AM rebuild/apps/members/models.py
A  rebuild/config/__init__.py
A  rebuild/config/settings/__init__.py
AM rebuild/config/settings/base.py
A  rebuild/config/settings/local.py
A  rebuild/config/settings/production.py
A  rebuild/config/settings/test.py
AM rebuild/config/urls.py
A  rebuild/config/wsgi.py
A  rebuild/manage.py
AM rebuild/requirements.txt
A  rebuild/static/css/lions.css
AM rebuild/static/css/prive.css
A  rebuild/static/images/emblem-256.png
A  rebuild/static/js/lions.js
A  rebuild/templates/403.html
A  rebuild/templates/404.html
A  rebuild/templates/500.html
A  rebuild/templates/accounts/base.html
A  rebuild/templates/accounts/limited.html
A  rebuild/templates/accounts/login.html
A  rebuild/templates/accounts/password_change.html
A  rebuild/templates/accounts/password_change_done.html
A  rebuild/templates/accounts/reset.html
A  rebuild/templates/accounts/reset_complete.html
A  rebuild/templates/accounts/reset_confirm.html
A  rebuild/templates/accounts/reset_done.html
AM rebuild/templates/base/private.html
A  rebuild/templates/base/public.html
A  rebuild/templates/base/site.html
A  rebuild/templates/components/forms/errors.html
AM rebuild/templates/components/forms/field.html
A  rebuild/templates/components/public/access_arcs.html
A  rebuild/templates/components/public/footer.html
A  rebuild/templates/components/public/navbar.html
A  rebuild/templates/emails/password_reset.html
A  rebuild/templates/emails/password_reset.txt
A  rebuild/templates/emails/password_reset_subject.txt
AM rebuild/templates/espace/dashboard.html
A  rebuild/templates/public/home.html
A  rebuild/tools/browser.cjs
?? docs/LOT_2_MEMBRES_GOUVERNANCE.md
?? mockups.zip
?? rebuild/apps/accounts/email_changes.py
?? rebuild/apps/governance/mandates.py
?? rebuild/apps/governance/migrations/0002_mandate.py
?? rebuild/apps/governance/urls.py
?? rebuild/apps/governance/views.py
?? rebuild/apps/members/forms.py
?? rebuild/apps/members/migrations/0002_memberprofile_bio_memberprofile_directory_visible_and_more.py
?? rebuild/apps/members/selectors.py
?? rebuild/apps/members/services.py
?? rebuild/apps/members/tests/
?? rebuild/apps/members/upload_handlers.py
?? rebuild/apps/members/uploads.py
?? rebuild/apps/members/urls.py
?? rebuild/apps/members/views.py
?? rebuild/templates/components/private/
?? rebuild/templates/espace/directory.html
?? rebuild/templates/espace/email_information.html
?? rebuild/templates/espace/experience_delete.html
?? rebuild/templates/espace/experience_form.html
?? rebuild/templates/espace/experiences.html
?? rebuild/templates/espace/management_dashboard.html
?? rebuild/templates/espace/management_detail.html
?? rebuild/templates/espace/management_members.html
?? rebuild/templates/espace/profile.html
?? rebuild/templates/espace/profile_edit.html
?? rebuild/templates/espace/years.html
?? rebuild/tools/browser_members.cjs
```

Les entrées A/M dans la première colonne proviennent du Lot 1 déjà indexé avant cette session. Les modifications du Lot 2 restent non indexées. Aucun commit ni push.
