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
