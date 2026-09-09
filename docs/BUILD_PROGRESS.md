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

## Vérifications finales

- `manage.py check` : aucun problème.
- `manage.py makemigrations --check --dry-run` : aucune migration manquante.
- `manage.py migrate --check` : aucune migration en attente.
- `manage.py test --settings=config.settings.test --noinput` : **163 tests, OK (3 ignorés)**.
- `git diff --check` : aucune erreur d'espace.
- `git status` : uniquement des fichiers sous `rebuild/` et `docs/` ; aucun fichier du legacy ni de `mockups/` modifié ; aucun commit créé.
