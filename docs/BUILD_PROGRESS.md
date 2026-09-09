# Suivi — fonctionnement quotidien du club (agenda, documents, cotisations, notifications)

Runtime exclusif : `rebuild/`. Aucun commit, aucun push. Legacy et `/mockups/` non touchés.

## Terminé

- **Agenda étendu (pas de nouvelle app)** : `Event` reçoit `capacity` et `registration_enabled`. Nouveaux modèles `Registration` (RSVP PENDING/CONFIRMED/CANCELLED, unique événement+profil) et `Attendance` (PRESENT/ABSENT/EXCUSED, unique événement+profil, `recorded_by`). `publish_content` accepte désormais les événements `PRIVATE` (nécessaire au calendrier privé) ; `EventQuerySet.public()` reste filtré sur `PUBLIC`, donc le site public est inchangé.
- **RSVP** : `set_registration` verrouille `Event` (`select_for_update`) puis vérifie capacité/activation avant de confirmer — sérialise les confirmations concurrentes sur un même événement. RSVP ne crée jamais d'`Attendance`.
- **Présences** : `record_attendance` réservé aux capacités de gestion (SUPER_ADMIN/PRESIDENT/SECRETAIRE). Absence de ligne = non renseigné (jamais ABSENT implicite). Feuille de présence actuelle = tous les membres actifs (dénominateur définitif « membres attendus vs inscrits vs invités » encore À CONFIRMER, cf. architecture §17).
- **Documents privés (nouvelle app `documents`)** : stockage hors `MEDIA_URL`/`file.url`, sous `PRIVATE_MEDIA_ROOT/documents`, permissions fichier 0600. Visibilités MEMBRES / BUREAU / RESPONSABLES + `DocumentGrant` nominatif expirant. `scope_documents()` est l'unique source de vérité utilisée par liste, détail, HEAD et téléchargement (même queryset, donc même ACL par construction). Validation à l'upload : extension + MIME annoncé cohérents (PDF/DOCX/XLSX/PNG/JPEG), 15 Mo max. **Pas d'antivirus/quarantaine réelle branché** — limite documentée, pas de sécurité inventée.
- **Notifications in-app (dans `communications`, pas de nouvelle app)** : modèle `Notification` (destinataire, `event_key` idempotent, catégorie, cible). Liste et « marquer comme lue » scopés au destinataire (`recipient=request.user`) ; lecture marquée uniquement par POST (`require_http_methods(["POST"])`, GET → 405). CTA résolu côté vue avec revérification d'accès (jamais une URL brute stockée).
- **Emails/rappels via l'outbox existante** : `OutboxMessage.kind` étendu (EVENT_REMINDER, IMPORTANT, DOCUMENT) au lieu d'une deuxième file. `deliver_batch` route par kind vers un template dédié. Commande `send_event_reminders` (J-7/J-1, clé idempotente incluant la version de l'événement pour invalider les anciens rappels après replanification) — à planifier par l'exploitation, comme `deliver_outbox` déjà existant. Notification importante manuelle : `notification.send` (mêmes rôles gestionnaires).
- **Cotisations (nouvelle app `dues`)** : `DuesRecord` (un par profil+Année Lions, montant nullable, jamais de 300 TND par défaut) et `DuesChange` append-only. `record_dues_status` exige un motif non vide pour toute correction et verrouille la ligne.
- **Dashboards enrichis** : membre (prochains rendez-vous + statut RSVP, notifications non lues, cotisation de l'année active) ; responsable (rendez-vous à venir, cotisations à régulariser, documents disponibles, raccourcis vers présences/documents/cotisations/notifications/statistiques).
- **Statistiques opérationnelles** : `/espace/statistiques/` (capacité `statistics.view`, réservée aux mêmes rôles gestionnaires) — agrégats présence/cotisations/documents, sans dénominateur inventé.
- **Permissions** : nouvelles capacités `event.register` (MEMBRES, hors INVITE), `attendance.record`, `document.view`/`document.manage`, `notification.view_own`/`notification.send`, `dues.view_own`/`dues.manage`, `statistics.view`. DIRECTEUR reste hors `MANAGERS` (aucune capacité avancée). BUREAU n'obtient que la lecture de documents « Bureau » — aucune capacité de gestion inventée. Aucun rôle TRÉSORIER créé.

## Migrations créées

- `agenda/0002_attendance_registration_event_capacity_and_more.py`
- `communications/0002_alter_outboxmessage_kind_notification.py`
- `documents/0001_initial.py`
- `dues/0001_initial.py`

Toutes appliquées sur `lionsmed_rebuild_dev` (PostgreSQL 16, cluster de développement du Lot 1). `makemigrations --check` et `migrate --check` : aucune migration en attente.

## Tests ciblés (PostgreSQL, `config.settings.test`)

- `apps.agenda` (nouveau) : calendrier privé visible aux membres, INVITE refusé au RSVP, aller-retour confirmation/annulation, RSVP exigé `registration_enabled`, RSVP scopé au profil de l'acteur (pas d'IDOR sur l'inscription d'autrui), RSVP ne crée jamais d'Attendance, BUREAU refusé pour saisir une présence, absence de ligne ≠ Absent, **concurrence PostgreSQL réelle sur la dernière place** (`TransactionTestCase` + deux threads + connexions séparées : un seul gagnant).
- `apps.documents` (nouveau) : visibilité MEMBRES/BUREAU/RESPONSABLES, accès nominatif accordé/expiré, **ACL identique pour liste, détail, HEAD et téléchargement** (mêmes assertions 404/200 sur les quatre surfaces), extension déguisée refusée, BUREAU ne peut pas déposer/gérer.
- `apps.dues` (nouveau) : MEMBRE refusé en gestion, motif obligatoire, montant négatif refusé, correction auditée (`DuesChange`), aucun montant par défaut, page personnelle ne fuite pas la cotisation d'autrui.
- `apps.communications.tests.test_notifications` (nouveau) : idempotence par `event_key`, **notification d'autrui invisible et son marquage-lu renvoie 404**, marquage lu POST uniquement (GET → 405), BUREAU refusé pour l'envoi d'une notification importante, envoi PRESIDENT crée bien la notification et l'entrée outbox.
- Suite complète (existant + nouveau) : **163 tests, 0 échec, 3 ignorés** (tests navigateur sans Playwright dans cet environnement, comme aux lots précédents).
- Un test préexistant (`test_invalid_publication_data`) a été mis à jour : il vérifiait qu'un événement `PRIVATE` ne pouvait pas être publié — règle du Lot 3 explicitement levée par cette phase (le calendrier privé exige de publier des événements internes). Le test couvre maintenant les deux cas : lieu manquant toujours refusé, événement `PRIVATE` complet publié mais absent de `EventQuerySet.public()`.

Réutilisation confirmée : pas de deuxième queue email (extension de `OutboxMessage`/`deliver_batch`), pas de nouvelle app calendrier (extension d'`agenda`), capacités et `capability_required`/`can()` réutilisés tels quels, templates/CSS `prive.css` et composants `components/private/*` réutilisés sans nouvelle feuille de style.

## Décisions encore bloquantes (héritées de l'architecture, non tranchées ici)

- Dénominateur exact de la feuille de présence (membres attendus vs inscrits vs invités).
- Antivirus/quarantaine réelle pour les documents (actuellement : contrôle extension+MIME+taille seulement).
- Montants et échéances de cotisation réels (aucun montant par défaut créé).
- Capacités avancées DIRECTEUR/BUREAU : toujours refusées par défaut.
- Ordonnancement de production de `send_event_reminders` et `deliver_outbox` (aucun scheduler installé, cohérent avec le Lot 5).

## Vérifications finales — Phase A

- `manage.py check` : aucun problème.
- `manage.py makemigrations --check --dry-run` : aucune migration manquante.
- `manage.py migrate --check` : aucune migration en attente.
- `manage.py test --settings=config.settings.test --noinput` : **163 tests, OK (3 ignorés)**.
- `git diff --check` : aucune erreur d'espace.
- `git status` : uniquement des fichiers sous `rebuild/` et `docs/` ; aucun fichier du legacy ni de `mockups/` modifié ; aucun commit créé.

# Phase B — Votes + Satisfaction

## Terminé

- **App `voting`** : `Vote` (DRAFT/OPEN/CLOSED, mode SINGLE/MULTIPLE/ELECTION, min/max_choices, blank_allowed, opens_at/closes_at, responsible, lions_year facultative), `VoteOption` (candidat facultatif via `candidate_profile`/`photo`), `Elector` (figé à l'ouverture), `Participation` (O2O Elector, **aucune FK vers Ballot**), `Ballot` (**aucune FK membre/IP/timestamp précis**), `BallotSelection`. Confidentialité = Option A de l'architecture : aucune correspondance durable Participation→Ballot, aucune UI SUPER_ADMIN « qui a voté quoi », y compris en usage normal.
- **`cast_vote()`** : verrouille `Vote` puis `Elector` (ordre déterministe), revalide sous verrou statut/fenêtre temporelle/électorat/absence de Participation/cardinalité/exclusivité du blanc/appartenance des options au scrutin, puis crée Ballot + BallotSelection + Participation dans la même transaction. Fenêtre toujours revérifiée à l'instant du verrou (jamais la seule valeur `status`), donc aucun bulletin accepté après `closes_at` même si la clôture planifiée n'a pas encore tourné.
- **`open_vote()`** fige `Elector` à partir des profils ACTIVE + rôle courant dans `MEMBERS` (INVITE exclu) à l'instant de l'ouverture — pas de recalcul implicite ensuite. **`close_vote()`** idempotent.
- **Trigger PostgreSQL** `voting_ballotselection_vote_match` (migration `0002`) : rejette à l'INSERT toute `BallotSelection` dont l'option n'appartient pas au même vote que le bulletin, même en cas de bug ou d'écriture hors service — défense en profondeur, `cast_vote()` reste la validation de référence. La cardinalité/exclusivité du blanc reste volontairement uniquement au niveau service (verrou `Vote` + seul point d'écriture) : un trigger déclaratif correct pour un agrégat multi-lignes incluant les bulletins blancs à zéro sélection serait disproportionné tant qu'aucune autre voie d'écriture n'existe (Django Admin n'enregistre aucun modèle `voting`).
- **Résultats** : accessibles uniquement après clôture, à l'électeur du scrutin ou au gestionnaire (`can_view_results`) — politique prudente, **audience finale À CONFIRMER HUMAINEMENT** (documenté dans le template). Dénominateur des pourcentages = bulletins exprimés (hors blancs) ; la somme peut dépasser 100 % en choix multiple. Blanc compté séparément, jamais classé.
- **Suivi responsable** (`vote_suivi.html`) : Électeur + a voté/n'a pas voté uniquement — aucune sélection, testé explicitement (`assertNotContains(... option.label)`).
- **App `satisfaction`** : `SatisfactionPeriod` (mois unique, `opens_at`/`closes_at` nuls tant que l'heure n'est pas configurée, seuil `threshold` configurable), `SatisfactionResponse` (échelle 1–5 exacte, commentaire facultatif, une réponse par profil+période). `apps/satisfaction/scheduling.py` : `third_saturday()` et `compute_window()` — ouverture le 1er du mois, fermeture 24 h avant le troisième samedi, à une **heure de référence explicitement configurée** (`SATISFACTION_REFERENCE_HOUR`, non définie par défaut) ; sans elle, `open_period()` refuse (`ValidationError`), aucune heure de production n'est présentée comme officielle.
- **`submit_satisfaction()`** : verrouille la période, revalide fenêtre/note 1–5/absence de réponse existante, transactionnel. **`period_results()`** masque moyenne/distribution si l'effectif de réponses est sous `threshold` (valeur de test explicite dans les tests ; **valeur de production À CONFIRMER HUMAINEMENT**, jamais durcie en dur). Aucun commentaire ni note individuelle exposé aux gestionnaires.
- **Intégration notifications/emails (réutilisation stricte)** : `Notification.Category` étendu (VOTE, SATISFACTION) et `OutboxMessage.kind` étendu (VOTE_OPENED, VOTE_RESULTS, SATISFACTION_OPENED) — aucune nouvelle file. `apps/voting/notifications.py` et `apps/satisfaction/notifications.py` notifient les électeurs/membres éligibles à l'ouverture/clôture, réutilisant `communications.services.notify()` et `deliver_outbox`. Emails HTML+texte dérivés des maquettes `ouverture-vote.html`, `resultats-vote.html`, `satisfaction.html` : jamais de choix, de relation identité/choix, ni de lien votant sans authentification (lien générique vers l'espace, pas de token).
- **Permissions** : `vote.manage`/`satisfaction.manage` = SUPER_ADMIN/PRESIDENT/SECRETAIRE ; `vote.cast`/`satisfaction.respond` = tout rôle sauf INVITE (électorat réel vérifié en service, pas par rôle) ; `vote.view_results` = électeur ou gestionnaire après clôture ; `satisfaction.view_results` = gestionnaires seuls. DIRECTEUR et BUREAU explicitement testés refusés sur toutes les capacités de gestion. Aucun `if role == ...` dans les vues : uniquement `capability_required`/`can()`.
- **Templates** : `votes.html`, `vote_confirm.html` (récapitulatif serveur avant envoi définitif, fonctionne sans JS), `vote_creation.html` (création + ajout de choix + ouverture), `vote_suivi.html`, `vote_resultats.html`, `votes_gestion.html`, `satisfaction.html`, `satisfaction_resultats.html`, `satisfaction_gestion.html` — composants privés existants réutilisés (`workspace-panel`, `lot2-timeline`, `tableau`, `metrics`), aucune nouvelle feuille CSS. Toutes `noindex`/`no-store` via `base/private.html` existant, hors sitemap.
- **Dashboards** : membre affiche « À compléter » (vote ouvert non répondu, satisfaction ouverte non répondue) et masque la tâche dès qu'elle est faite/fermée/non éligible. Responsable affiche votes ouverts + taux de participation et satisfaction du mois (masquée sous le seuil), sans KPI fictif.
- **Django Admin** : aucun modèle `voting`/`satisfaction` enregistré (cohérent avec le reste du projet, où seul `accounts.User` l'est) — élimine par construction tout contournement des invariants via l'admin.

## Migrations créées

- `communications/0003_alter_notification_category_alter_outboxmessage_kind.py`
- `voting/0001_initial.py`
- `voting/0002_ballotselection_vote_match_trigger.py` (RunSQL : fonction + trigger PostgreSQL)
- `satisfaction/0001_initial.py`

**Point technique** : le modèle `Vote` utilise `db_table = "app_voting_vote"` explicite — le nom par défaut `voting_vote` collisionnait avec l'entrée legacy du même nom dans la garde anti-legacy de `apps/core/management/commands/migrate.py`, qui aurait alors refusé toute migration future sur cette base pourtant neuve. Renommer la table est la correction correcte : la garde reste intacte et continue de protéger contre une vraie base legacy.

## Tests ciblés (PostgreSQL, `config.settings.test`)

- `apps.voting` (nouveau, 24 tests) : BUREAU et DIRECTEUR refusés en gestion, SECRETAIRE autorisé, ouverture fige les électeurs et exclut INVITE, INVITE et non-électeur refusés au dépôt, bulletin définitif (deuxième dépôt refusé), option d'un autre scrutin refusée (service **et** trigger PostgreSQL testés séparément, y compris un contournement direct du service), cardinalité et blanc+choix refusés, dépôt avant ouverture et après la fenêtre de clôture refusés (même si le statut n'a pas encore été basculé), résultats refusés avant clôture même au responsable, résultats accessibles à l'électeur après clôture et refusés à un non-électeur, clôture idempotente, suivi expose la participation sans jamais le choix, `Participation` sans champ `ballot` et `Ballot` sans référence membre vérifiés par introspection des champs, **concurrence PostgreSQL réelle** (`TransactionTestCase`, deux threads, connexions séparées : un seul bulletin accepté).
- `apps.satisfaction` (nouveau, 15 tests) : troisième samedi calculé pour les 12 mois 2026 et vérifié sur une année bissextile (2028), fenêtre `None` tant que l'heure n'est pas configurée, fenêtre calculée en Africa/Tunis avec une heure de test explicitement synthétique, ouverture refusée sans capacité et sans heure configurée, note hors 1–5 refusée, INVITE refusé, période fermée refusée, une seule réponse (deuxième refusée), audit sans note ni commentaire, petits effectifs masqués sous le seuil configuré, effectif atteignant le seuil affiche la moyenne, MEMBRE ne peut pas consulter les résultats agrégés, **doublon concurrent réel** (`TransactionTestCase`, deux threads : une seule réponse créée).
- Un test préexistant (`test_shell_templates_and_no_future_routes`) a été mis à jour : `/espace/votes/` n'est plus une route future (elle existe désormais) ; la vérification « aucune route future » a été déplacée sur `/espace/audit/`, toujours hors périmètre.
- Suite complète (existant + nouveau) : **200 tests, 0 échec, 3 ignorés** (tests navigateur sans Playwright dans cet environnement).

Réutilisation confirmée : `Notification`/`OutboxMessage`/`deliver_outbox` étendus, jamais dupliqués ; `capability_required`/`can()` centraux réutilisés sans branche par rôle dans les vues ; composants privés et `prive.css` existants réutilisés sans nouvelle feuille de style ; maquettes votes/satisfaction/emails transformées sans redesign.

## Décisions encore bloquantes (héritées de l'architecture, non tranchées ici)

- Audience finale des résultats de vote (électeurs seuls vs tous les membres vs votants seuls) — politique prudente « électeurs du scrutin » implémentée en attendant.
- Heure de référence de production pour l'ouverture/fermeture satisfaction (`SATISFACTION_REFERENCE_HOUR`) — non définie, aucune période n'est activable en production tant qu'elle ne l'est pas.
- Seuil `k` de confidentialité satisfaction en production (mécanique de masquage prête, valeur par défaut du modèle = 5 à titre indicatif seulement).
- Règles d'entrée/sortie tardive des électeurs, radiations, procurations : refusées par défaut, aucune n'a été inventée.
- Réidentification exceptionnelle (vote ou satisfaction) : non développée, conforme à l'Option A ; resterait une décision humaine séparée si jamais demandée.
- Délégation de gestion des votes/satisfaction à DIRECTEUR/BUREAU : toujours refusée par défaut.

## Vérifications finales — Phase B

- `manage.py check` : aucun problème.
- `manage.py makemigrations --check --dry-run` : aucune migration manquante.
- `manage.py migrate --check` : aucune migration en attente.
- `manage.py test --settings=config.settings.test --noinput` : **200 tests, OK (3 ignorés)**.
- `git diff --check` : aucune erreur d'espace.
- `git status` : uniquement des fichiers sous `rebuild/` et `docs/` ; aucun fichier du legacy ni de `mockups/` modifié ; aucun commit créé.

# Phase C — Finalisation

Documentation opérationnelle : [docs/DEPLOY_REBUILD.md](DEPLOY_REBUILD.md), [docs/MIGRATE_LEGACY_TO_REBUILD.md](MIGRATE_LEGACY_TO_REBUILD.md).

## Terminé

- **Reprise legacy** (`apps/core/legacy_pipeline.py`, commande `import_legacy`) : lecture seule de `db.sqlite3`, idempotente via `core.LegacyImportRecord`. Importe automatiquement identité des comptes (aucun rôle, aucun mot de passe legacy repris — `set_unusable_password()`), candidatures (sans email), actualités (toujours DRAFT), événements REUNION/GALA (DRAFT). **Met en quarantaine** les anciens événements ACTION (axe absent du legacy, jamais deviné) et les cotisations sans Année Lions confirmée. Dry-run exécuté sur le vrai `db.sqlite3` : 2 événements importables, 3 ACTION et 10 cotisations en quarantaine (raisons explicites) — aucune écriture sur la base de développement partagée, seule la suite de tests (base éphémère) a exercé `--apply`.
- **Documents — hardening réel** : `apps/documents/scanning.py` parle le protocole INSTREAM de clamd (socket Unix/TCP configurable, sans dépendance tierce) ; **échec fermé** — scanner non configuré ou injoignable ⇒ dépôt refusé, aucun document ne devient disponible. `apps/documents/office_validation.py` : signature de fichier vérifiée pour tous les formats, structure ZIP réelle pour DOCX/XLSX (entrées, chemins, macro `vbaProject.bin` refusée, ratio de compression anti zip-bomb, entrée requise `word/document.xml`/`xl/workbook.xml`), PDF : signature + repérage heuristique de contenu actif (`/JavaScript`, `/OpenAction`, `/Launch`). Un rejet (y compris infecté) est audité durablement même si l'écriture du document est annulée (validation hors transaction).
- **MFA privilégiés** : `django-otp` 1.7.3 + `qrcode` 8.2 (dépendances maintenues, aucun TOTP artisanal), ajoutées après vérification de compatibilité Django 5.2. Périmètre : SUPER_ADMIN/PRESIDENT/SECRETAIRE (capacité `mfa.manage_own`). Enrôlement avec QR + clé manuelle, confirmation par code, 10 codes de récupération à usage unique affichés une seule fois (`otp_static`). Connexion : un compte privilégié avec dispositif confirmé passe par une session intermédiaire non authentifiée (`mfa_user_id` en session) jusqu'à validation du second facteur ; code invalide → refus, code déjà utilisé → refus (anti-rejeu propre à TOTP/à la consommation des jetons statiques), tentatives limitées (10/15 min). Désactivation : re-authentification par mot de passe, auditée. Un compte privilégié sans dispositif encore enrôlé peut toujours se connecter (pas de verrouillage brutal) — **l'application obligatoire avant toute capacité sensible reste une décision d'exploitation humaine**, documentée comme telle.
- **Cotisations — seuil satisfaction explicite** : le formulaire de gestion (`PeriodOpenForm.threshold`) est désormais **obligatoire, sans valeur pré-remplie** — un responsable doit choisir consciemment le seuil de confidentialité à chaque ouverture ; le défaut de modèle (5) reste un filet technique, jamais une décision institutionnelle silencieuse.
- **Audit transversal permissions/IDOR** (`apps/core/tests/test_idor_audit.py`) : toutes les URLs privées principales redirigent l'anonyme vers la connexion ; `?role=` sans effet ; changer un UUID (expérience, profil, document, notification, cotisation, inscription RSVP, bulletin de vote) d'un autre compte ne donne jamais accès à son objet — complète (sans les dupliquer) les tests déjà ciblés de chaque app.
- **Secrets** : audit du dépôt (grep) — seul `rebuild/.env` contient un vrai secret, correctement ignoré par git (non suivi) ; `.env.example` ne contient que des placeholders vides.
- **`check --deploy`** (settings production, clé/domaine synthétiques) : seulement **security.W005** et **security.W021** (HSTS sous-domaines/preload), désactivés par choix explicite documenté — inchangé depuis le Lot 1, aucune nouvelle alerte introduite par les Phases A–C.
- **Sauvegarde/restauration testée réellement** : `pg_dump -Fc` de la base de développement puis restauration complète sur une base PostgreSQL séparée et temporaire (`lionsmed_rebuild_restoretest`, détruite après vérification) — comptages de tables identiques avant/après (`django_migrations`, `accounts_user`, etc.), `manage.py migrate --check` propre sur la base restaurée. Procédure documentée dans DEPLOY_REBUILD.md.
- **Scheduler outbox/rappels** : documenté avec systemd timers (`deliver_outbox` toutes les 2 min, `send_event_reminders` une fois par jour) — pas de Celery, un seul outbox comme au Lot 5. `select_for_update(skip_locked)` déjà en place rend un chevauchement inoffensif.
- **SEO** : aucune régression introduite (aucune page publique modifiée en Phases A–C) ; les tests SEO du Lot 3 (canonical, OG, JSON-LD, sitemap, robots, noindex) restent verts dans la suite complète.

## Non fait dans cette phase (limites honnêtes, pas d'invention)

- **Recette responsive/accessibilité aux six largeurs** : non exécutée avec un vrai navigateur dans cette session — `playwright` n'est pas installé dans l'environnement et son installation (téléchargement de Chromium) n'a pas été jugée sûre à déclencher sans confirmation. Les suites `test_browser.py` existantes (Lots 1–3) restent disponibles et fonctionnelles dès que `PLAYWRIGHT_MODULE`/`CHROME_PATH` sont fournis ; aucune nouvelle page privée (votes, satisfaction, documents, cotisations, MFA) n'a de couverture navigateur dédiée à ce stade. **Ne pas présenter cette recette comme faite.**
- **Import legacy réel en production** : uniquement dry-run + tests ; aucune donnée réelle du club n'a été importée nulle part.
- **ClamAV** : intégration réelle et testée au niveau protocole (serveur factice simulant clamd dans les tests), mais **aucun démon ClamAV n'est installé sur cet environnement** — à déployer et vérifier en conditions réelles avant mise en production (voir DEPLOY_REBUILD.md §2).
- **DOCX/XLSX/PDF** : validations structurelles réalistes (ZIP, signature, heuristique PDF), pas un moteur d'analyse de contenu actif exhaustif — reste un complément à l'antivirus, pas un remplacement.

## Décisions encore bloquantes avant production

Appellation District, dates Année Lions, droits avancés DIRECTEUR/BUREAU, heure et seuil satisfaction (mécanique prête, valeurs non fixées), audience finale des résultats de vote, montants/échéances cotisations, dénominateur présence, textes légaux, coordonnées officielles, fournisseur SMTP, portraits/photos autorisés, contenus historiques, calendrier institutionnel pour les cotisations legacy. Aucune de ces valeurs n'a été inventée ou fixée silencieusement.

## Vérifications finales — Phase C

- `manage.py check` : aucun problème.
- `manage.py makemigrations --check --dry-run` : aucune migration manquante.
- `manage.py migrate --check` : aucune migration en attente.
- `manage.py test --settings=config.settings.test --noinput` : **243 tests, OK (3 ignorés)** — 232 précédents + 11 tests MFA nouveaux (les tests legacy/hardening/IDOR de cette phase sont déjà comptés dans les 232, ajoutés avant les tests MFA).
- `manage.py check --deploy --settings=config.settings.production` : seulement W005/W021, déjà connus et volontaires.
- `git diff --check` : aucune erreur d'espace.
- `git status` : uniquement des fichiers sous `rebuild/` et `docs/`.

## Correction V1 — Recette utilisateur

Passe de corrections issue de la première recette manuelle. Aucune fonctionnalité hors
demande, aucun import legacy réel, aucun déploiement.

**Corrections réalisées**
- Accueil : image hero restaurée depuis `mockups/accueil.html` (mockup final ; `home.html`
  est un brouillon obsolète, non modifié). Section « Nos axes d'engagement » enrichie
  (intro + quatre axes prioritaires inchangés + bande discrète des causes Lions
  complémentaires, textes fournis par le club). Aucun cinquième axe prioritaire ajouté.
- Notre Club : section « Nos valeurs fondamentales » (six valeurs, texte fourni), design
  propre (pas de copie de la référence visuelle), accent bleu/or discret, hiérarchie claire.
- Rejoindre : CTA principal repassé en `btn--primary` (jaune) conforme à la maquette.
- Candidature : téléphone rendu obligatoire modèle + formulaire + template (validation
  serveur réelle, pas seulement `required` HTML) ; pipeline legacy adapté pour rejeter
  (jamais compléter) une candidature historique sans téléphone.
- Navbar mobile : contraste du bouton menu renforcé par une déclaration directe et
  robuste (`background-color` explicite, scindée de toute feuille de page).
- Footer mobile : disposition compacte en deux colonnes sous 640 px, aucun lien retiré.
- Événements publics : page liste, lien footer et sitemap **masqués tant qu'aucun
  événement public n'est publié** (404 propre) ; réapparaissent dès la première
  publication. Navbar toujours sans Événements (inchangé).
- **Actualités supprimées** : modèle `NewsArticle`, routes publiques et de gestion,
  formulaires, sitemap, JSON-LD, liens footer/accueil/contenu public retirés ; l'app
  `editorial` conservée (identité, rubriques, métriques, redirects). Anciennes URLs
  `/actualites/...` → 404 propre, aucune redirection inventée. Pipeline legacy : les
  actualités historiques sont désormais explicitement `SKIPPED`/`REJECTED`
  (« fonctionnalité Actualités supprimée du nouveau produit »), jamais importées.
- Audit CTA : hiérarchie bouton/lien corrigée sur `/espace/contenu/` (actions de gestion
  en boutons pleins/outline) ; audit non exhaustif sur le reste du privé (voir limites).
- Dashboard membre : cartes « À faire »/cotisation/rendez-vous reconstruites avec les
  composants réels du design system (`carte-action`, `carte-action--urgent`, `badge--*`)
  au lieu de listes neutres — toujours sur données réelles uniquement, aucune valeur
  fictive réintroduite.
- Résumé profil (dashboard/profil/annuaire) : chevauchement photo/texte corrigé
  (`flex-wrap: nowrap`, avatar `flex-shrink:0`/`overflow:hidden`).
- En-tête privé : remplacement de l'ancien `<summary>` (triangle natif + nom) par une
  identité sur une seule ligne (avatar rond + prénom nom, sans rôle, sans second niveau),
  marqueur de repli natif masqué.
- Profil — confidentialité simplifiée : les sept cases de partage granulaire
  (annuaire, profession, présentation, contacts, photo, parcours, mandats) retirées du
  formulaire d'édition et figées à leur valeur actuelle (politique la plus prudente,
  inchangée tant qu'une décision explicite ne la rouvre pas). Un seul nouveau choix :
  « Rendre mon profil public », strictement indépendant de l'annuaire privé.
- **Profil public membre** (nouveau) : route `/membres/<slug>/`, activée uniquement par
  `public_profile_enabled` (opt-in, faux par défaut), 404 sinon — jamais de message
  révélant l'existence d'un profil masqué. Contenu strictement limité à photo, nom,
  présentation, parcours Lions/LEO, mandats validés et `public_authorized`,
  appartenance au club ; aucune coordonnée, aucun statut interne, aucune donnée de
  gouvernance/permission/document/cotisation/présence/vote/satisfaction. SEO complet
  (title, description, canonical basé sur `SITE_ORIGIN`, OG, `BreadcrumbList`, `Person`
  JSON-LD sans coordonnées), sitemap dédié (profils désactivés absents, `lastmod` réel).
  QR code (réutilise `qrcode`, déjà ajouté pour le MFA) encodant uniquement l'URL
  publique canonique, correction d'erreur élevée, logo du club incrusté au centre.
- Slugs : génération à la première activation uniquement (`anis-besbes`, `-2`, `-3`…),
  jamais régénérée automatiquement, jamais réutilisée après un changement de nom.
- Parcours Lions/LEO : précision mensuelle remplacée par une précision annuelle
  (« Poste », « Année de début » obligatoire, « Année de fin » facultative → « poste
  actuel » / affichage « Depuis 2026 » ou « 2019–2021 »). Migration de données réelle
  (`0005_public_profile_and_experience_years`) : les 2 expériences existantes en base de
  développement ont été converties sans perte (années extraites des dates existantes),
  aucune ligne perdue.
- Mot de passe : alignement des trois champs corrigé en réutilisant le composant
  `lot2-reading` déjà éprouvé ailleurs dans l'espace privé (aucune logique de sécurité
  modifiée).
- Confidentialité : mention factuelle ajoutée sur l'opt-in de profil public (activation
  volontaire, réversible, jamais de coordonnées publiées) — aucune durée de conservation
  ni base juridique inventée.
- Sécurité : audit `cursor.execute`/`raw`/`RawSQL`/`.extra`/`RunSQL` — aucune donnée
  requête concaténée dans du SQL dynamique hors migrations ; les requêtes SQLite du
  pipeline legacy sont statiques (aucune donnée de ligne interpolée).

**Migrations**
- `members.0004_alter_membershipapplication_phone` — téléphone obligatoire sur la
  candidature.
- `members.0005_public_profile_and_experience_years` — `public_profile_enabled`,
  `public_slug` sur `MemberProfile` ; `start_year`/`end_year` sur `AssociationExperience`
  (données migrées puis anciens champs mensuels supprimés, contrainte de précision
  mensuelle retirée, nouvelle contrainte d'ordre des années).
- `editorial.0002_delete_newsarticle` — suppression du modèle (0 ligne en base de
  développement au moment de la suppression, vérifié avant migration).

**Tests** : suite complète **255 tests, OK (4 ignorés)** — nouveaux tests ciblés ajoutés
pour le téléphone obligatoire, les 4 axes, les événements conditionnels, la suppression
d'Actualités (routes, sitemap, footer, legacy skip), le profil public (opt-in par défaut,
404/200, absence de fuite email/téléphone, JSON-LD Person, homonymes de slug, stabilité
du slug après renommage, sitemap, génération QR), les années de parcours (bornes,
poste actuel).

**Non traité dans cette passe (limites honnêtes)**
- Audit CTA : traité sur `/espace/contenu/` et `Rejoindre` seulement ; le reste du privé
  (documents, cotisations, présences, votes, satisfaction, candidatures/messages) n'a
  pas été revu action par action faute de temps dans cette session.
- Contraste du bouton menu mobile : corrigé par une déclaration CSS renforcée
  (`background-color` direct, plus robuste face à une éventuelle feuille de page
  concurrente) ; le rendu n'a pas pu être confirmé dans un vrai navigateur pendant
  cette session (contrainte d'environnement), contrairement au reste des captures
  d'écran de cette passe qui, elles, ont été vérifiées visuellement.
- Chevauchement photo/texte du résumé profil : corrigé par une hiérarchie flex
  défensive d'après lecture du code ; non reconfirmé visuellement dans un navigateur
  réel pour la même raison.
- Recette responsive/accessibilité aux six largeurs (1440/1280/1024/768/430/375) sur
  les pages modifiées : effectuée par capture d'écran réelle (Chrome headless) pour
  l'accueil, Notre Club, Nos Actions et Rejoindre à 390 px et à une largeur desktop ;
  **pas exécutée systématiquement aux six largeurs ni sur les pages privées**
  (dashboard, profil, parcours, mot de passe, contenu public, profil public) faute de
  temps — Playwright reste non installé, aucun téléchargement de Chromium déclenché.
- Aucune donnée officielle inventée : coordonnées, heure de satisfaction, contenus
  légaux et historiques restent des décisions humaines en attente (inchangé depuis la
  Phase C).

## Correction V2 — Recette utilisateur (suite)

- **Ajout et gestion des menus dépliables** : Votes, Satisfaction, Documents et
  Cotisations se déplient chacun pour un responsable (actions de gestion regroupées) et
  restent un lien simple pour un membre sans capacité de gestion.
- **Responsables de vote** : désignation nominative (`MemberProfile.is_vote_manager`),
  indépendante du rôle, réservée au bureau (`management.access`) ; un responsable désigné
  ne peut pas en désigner un autre.
- **Satisfaction** : configuration de période avec date/heure de lancement et de
  fermeture manuelles, ou activation automatique — **règle confirmée par le club : 2ᵉ
  vendredi du mois → 3ᵉ vendredi du mois** (remplace la règle provisoire « 1er du mois →
  3ᵉ samedi » de la Phase B).
- **Documents** : taille maximale portée de 15 à 50 Mo.
- **Membres et mandats** : page ouverte à la création de comptes (mot de passe jamais
  inventé, lien de réinitialisation envoyé automatiquement) et à la modification du
  rôle, du statut et de l'adresse e-mail de tout compte — **à l'exception du Super
  administrateur**, toujours hors de portée de cette page (uniquement via la procédure
  technique CLI). Correction connexe : le formulaire de réinitialisation de mot de passe
  excluait par défaut les comptes à mot de passe inutilisable (comportement Django pensé
  pour le SSO), ce qui aurait aussi bloqué l'activation des comptes repris du legacy.
- **Années Lions confirmées : calendrier juillet → juillet.** La page permet désormais
  de créer une Année Lions, de désigner l'année active et d'archiver/désarchiver une
  période, réservé au bureau.
- Tests : 311 tests au total, seul l'échec pré-existant et sans rapport
  (`test_empty_state_and_dashboard`, lié à une réécriture externe de `dashboard.html`)
  subsiste.
- **Page Pilotage supprimée** : son contenu (comptes/membres actifs/mandats/rendez-vous/
  cotisations à régulariser/documents disponibles, votes ouverts, satisfaction du mois,
  raccourcis de gestion) est désormais intégré directement dans le tableau de bord,
  visible uniquement pour un compte disposant de `management.access`.
- **Statistiques et Présences masquées** du menu (URLs toujours fonctionnelles si
  atteintes directement, simplement retirées de la navigation pour l'instant).
- **Année Lions activée automatiquement à la création** — l'activation manuelle reste
  possible pour réactiver une période antérieure.
- **Nouveaux rôles** (décision explicite du club) : Vice-président, Trésorier, GST, GMT,
  GLT, LCIF. Assignables immédiatement depuis « Membres et mandats ». **Aucune capacité
  de gestion élevée par défaut** — ils héritent seulement des capacités de base d'un
  membre (voter, répondre à la satisfaction, voir l'annuaire, ses propres cotisations…),
  strictement rien de plus tant que ce n'est pas explicitement demandé.
- **Cotisations refondues en deux tranches** (décision explicite du club) :
  `DuesRecord` porte désormais `tranche1_paid`/`tranche2_paid` (+ dates) au lieu d'un
  statut/montant unique ; `status` devient une propriété calculée (`PAID` si les deux
  tranches sont réglées, `PARTIAL` si une seule, `TO_REGULARIZE` sinon) — un membre
  n'ayant réglé que la tranche 1 n'est jamais présenté comme à jour.
  - **Montants** : nouveau modèle `DuesSchedule` (un par Année Lions, commun à tous les
    membres, jamais de montant par membre) ; page dédiée en lecture seule par défaut,
    modification uniquement via l'action explicite « Modifier les montants ».
  - **Permissions revues** (vérifiées avant modification, confirmé avec l'utilisateur) :
    seuls **TRESORIER et SUPER_ADMIN** peuvent désormais modifier tranches et montants
    (`dues.manage`) — **PRESIDENT/SECRETAIRE perdent ce droit** et passent, comme
    BUREAU, en consultation seule (`dues.view_management`, nouvelle capacité).
  - **Badges** « Payé »/« Partiellement payé »/« Non payé » affichés dans l'Annuaire et
    Membres et mandats pour l'Année Lions active (absents si aucun `DuesRecord`, jamais
    inventés).
  - **Paiement en ligne** : bouton désactivé « Coming soon » sur la page membre
    (`/espace/cotisations/`) — aucune fonctionnalité de paiement réelle.
  - Pipeline legacy adapté : un paiement annuel unique historique est traduit en « deux
    tranches réglées » si payé (sinon aucune), le montant historique par membre n'étant
    plus un champ structuré est conservé en texte dans la note, jamais réinventé comme
    barème rétroactif.
  - Migration `dues.0002_tranches_and_schedule` (0 ligne existante en base de
    développement au moment du changement, vérifié avant migration).
  - 16 nouveaux tests ciblés (`apps/dues/tests/test_dues.py`), suite complète 323 tests.
  - **Anomalies pré-existantes, sans rapport avec ce travail** : `test_empty_state_and_dashboard`
    (texte de `dashboard.html` modifié en dehors de cette tâche) et
    `test_state_change_permissions_and_audit` (modification concurrente des permissions
    de candidatures/contact ajoutant GMT) échouent indépendamment de ce changement ; deux
    tests de concurrence des votes (`VoteLifecycleTests`) ont ponctuellement rencontré un
    deadlock PostgreSQL transitoire, non reproductible à la relance.
- **Calendrier interne refondu en vrai calendrier partagé** (vues Mois/Semaine/Jour,
  rendues côté serveur avec le module `calendar` de la bibliothèque standard — aucune
  librairie JS, aucune SPA), navigation Aujourd'hui/précédent/suivant, détail d'un
  événement au clic via la pseudo-classe CSS `:target` (sans JavaScript).
  - **Ajout rapide d'événement** depuis le calendrier (`QuickEventForm` : titre,
    description, dates, journée entière, lieu, lien de réunion) via
    `create_calendar_event()` — réutilise le modèle `Event` existant, ne crée aucun
    second système d'événements. L'événement créé est **toujours privé par défaut**
    (`visibility=PRIVATE`) : la publication publique reste une action séparée et
    explicite via le workflow éditorial existant (`/espace/contenu/`), jamais automatique.
  - **Permissions inchangées, vérifiées avant toute modification** : `event.create`
    reste réservé à `MANAGERS` (SUPER_ADMIN, PRESIDENT, SECRETAIRE) — le rôle `BUREAU`
    littéral ne peut pas créer d'événement, seulement consulter le calendrier
    (`event.register`). À confirmer avec le club si « membres autorisés du Bureau »
    doit en réalité inclure le rôle `BUREAU`.
  - **Synchronisation téléphone** : jeton d'abonnement privé par membre
    (`MemberProfile.calendar_token`, `secrets.token_urlsafe(32)`, jamais l'UUID ni
    l'e-mail du compte) exposé par un flux iCalendar anonyme mais protégé par le jeton
    (`/espace/calendrier/abonnement/<token>.ics`), consommable par Google Calendar,
    iPhone/Apple Calendar, Outlook et Android en mode « abonnement par URL » (mise à
    jour automatique, pas de réimport manuel). Téléchargement `.ics` ponctuel également
    disponible. Génération du flux via un générateur iCalendar (RFC 5545) écrit à la
    main dans `apps/agenda/ics.py`, sans dépendance tierce. Action « Régénérer mon lien
    de synchronisation » : invalide immédiatement l'ancien jeton. Flux marqué
    `X-Robots-Tag: noindex, nofollow` et `Cache-Control: private, no-store` (redondant
    avec `PrivateHeadersMiddleware`, déjà en place pour tout l'espace privé).
  - Modèle `Event` complété par `all_day` et `meeting_link` (migration
    `agenda.0003_event_all_day_event_meeting_link`) ; `MemberProfile` complété par
    `calendar_token` (migration `members.0007_memberprofile_calendar_token`) —
    appliquées en base de développement.
  - 13 nouveaux tests ciblés (`apps/agenda/tests/test_agenda.py`) : création autorisée/
    refusée, visibilité partagée de l'événement créé, jeton requis pour le flux ICS,
    ancien jeton invalidé après régénération, absence de fuite d'e-mail/nom dans le
    flux, téléchargement `.ics` valide. Suite `apps.agenda` complète : 24 tests, tous
    au vert. Suite complète du projet : 336 tests, mêmes deux anomalies pré-existantes
    et sans rapport ci-dessus, aucune régression introduite.
