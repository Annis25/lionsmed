# Lionsmed — contexte final de projet

## Produit

Lionsmed est le nouveau portail du Lions Club Sfax-Méditerranée : site public éditorial et espace privé des membres. Le runtime actif est `rebuild/`; les mockups et le legacy ne sont pas le runtime de production.

## Architecture

- Django 5 / PostgreSQL, configuration par environnement.
- Applications : comptes, agenda, communications, core, documents, cotisations, éditorial, gouvernance, membres, satisfaction, actions de service et votes.
- Données privées stockées hors URL publique ; images de contenu public servies par la couche `PublicImage`.
- Migrations nouvelles de la phase courante : agenda, cotisations, gouvernance, membres, actions, votes.

## Règles d'autorisation

La source unique est `rebuild/apps/core/permissions.py`.

- Gestion générique : SUPER_ADMIN, PRESIDENT, SECRETAIRE.
- Contact : PRESIDENT et SECRETAIRE.
- Candidatures : PRESIDENT et GMT.
- Cotisations : modification SUPER_ADMIN/TRESORIER ; consultation bureau élargi.
- Membre : calendrier, vote, satisfaction, annuaire privé et informations personnelles selon statut.
- Invité : accès personnel limité, sans annuaire/vote/satisfaction.
- Un rôle actif unique est requis ; ambiguïté = refus d'accès.

## Fonctions livrées

- Site public : accueil, club, valeurs, actions, détail d'action avec galerie et lightbox, rejoindre et contact.
- Espace privé : tableau de bord, profils, parcours, annuaire, calendrier et flux ICS, présences, notifications, documents, votes, satisfaction, cotisations, contenus publics, membres/mandats, années Lions et MFA.
- Boîtes de traitement séparées : candidatures (PRESIDENT/GMT) et messages de contact (PRESIDENT/SECRETAIRE).
- Actions : brouillon/publication, image principale, galerie plafonnée, impact, bénéficiaires, heures, partenaires et lien Instagram.

## Garde-fous techniques

- CSRF, limitation de débit, MFA TOTP, mots de passe Django, audit des mutations.
- Transactions et verrous pour inscriptions d'événement, votes et cotisations.
- Documents privés, contrôle de format, structure et antivirus ClamAV en échec fermé.
- Migrations legacy bloquées dans la base rebuild ; import legacy explicite, traçable et non automatique.

## État de l'audit du 9 septembre 2026

**Statut : prêt pour la préproduction, pas pour la production.**

- Schéma Django : vérifié, migrations synchronisées, aucune migration manquante.
- Tests : 339 collectés ; 0 failure, 0 error après correction de la validation extension–MIME des portraits ; trois tests sont ignorés selon les dépendances/environnement de test.
- Upload portrait : MIME déclaré cohérent avec l'extension exigé avant le décodage et la normalisation JPEG ; PNG, JPEG, WebP et HEIC/HEIF légitimes restent supportés.
- Backup/restore local validé sur une base temporaire sans écraser la base de développement.
- Avant production : configurer secrets/SMTP/ClamAV/HTTPS, sauvegardes automatisées, recette des rôles et décisions humaines restantes.
- Hygiène Git : `rebuild/.env.before-recipe` est local et ignoré, jamais livré ; `DJANGO_SECRET_KEY` doit être renouvelée avant la mise à jour production.

## E-mails et communication membres

- Les e-mails transactionnels utilisent une base HTML Lionsmed commune, avec version texte, logo absolu depuis `SITE_ORIGIN` et salutation au prénom.
- Les rôles Bureau autorisés disposent de la capability `communication.send_member_broadcast` pour préparer, prévisualiser, tester et mettre en file une campagne individuelle via l’outbox.
- Les campagnes conservent un historique d’audit et des compteurs d’envoi, sans stocker de copie personnalisée par destinataire.

## Passe finale — 10 septembre 2026

- L’invitation d’un nouveau membre est mise dans l’outbox sans mot de passe connu : l’e-mail « Bienvenue parmi nous » porte un lien Django sécurisé permettant à la personne de choisir son propre mot de passe. Son renvoi exige une confirmation et reste idempotent sur une courte fenêtre.
- Les e-mails utilisent une base HTML et texte communs, avec logo absolu depuis `SITE_ORIGIN`, footer institutionnel, salutation au prénom et CTA jaune compatible clients e-mail.
- Les liens de retour POST du calendrier et des cotisations sont désormais limités à l’hôte courant : aucun `next` ou `Referer` externe n’est suivi.
- Les résultats de vote envoyés par e-mail restent strictement agrégés ; aucun électeur, bulletin ou choix individuel n’est fourni au modèle.
- Les décisions non techniques restent : seuil de satisfaction, audience finale des résultats de vote, activation de l’indexation publique, politique MFA obligatoire et préparation réelle SMTP/ClamAV/backup avant production.

## Fiabilisation outbox — 10 septembre 2026

- **Aucun e-mail Lionsmed n'est envoyé de manière synchrone** (hors réinitialisation de
  mot de passe, volontairement à part — vue Django standard, action interactive
  attendue immédiatement par l'utilisateur). Tout le reste passe par `OutboxMessage` +
  `manage.py deliver_outbox`, qui **doit** être planifié en continu : sans worker actif,
  les messages restent `PENDING` indéfiniment (incident déjà rencontré en production,
  résolu manuellement par un timer systemd).
- Unités systemd désormais versionnées dans `rebuild/deploy/systemd/`
  (`lionsmed-outbox.service/.timer` — toutes les minutes — et
  `lionsmed-event-reminders.service/.timer` — une fois par jour) ; voir le
  `README.md` du dossier pour l'installation et la vérification (`active (waiting)`
  attendu sur le timer, `inactive (dead)` normal sur le service `oneshot`).
- `manage.py outbox_status` ajouté : compteurs par état et âge du plus ancien `PENDING`,
  sans jamais afficher destinataire, sujet ou contenu — à utiliser pour la surveillance
  opérationnelle plutôt qu'une requête ORM manuelle.
- Correctif de fond dans `deliver_batch()` : un message devenu **définitivement** non
  pertinent avant l'envoi (mot de passe déjà défini, droit de consulter un résultat de
  vote retiré, événement/document/vote/période de satisfaction disparu, destinataire
  d'une campagne désactivé) passe désormais directement en `FAILED` avec
  `error_code="not_applicable"`, sans les cinq tentatives de retry inutiles réservées
  aux échecs SMTP réellement transitoires (`error_code="delivery_failed"`). Aucune
  migration nécessaire (champ `error_code` déjà existant).
- Un test préexistant (`governance.tests.test_view_creates_account_and_sends_activation_link`)
  supposait un envoi synchrone à la création d'un membre ; il correspondait exactement
  au bug de production décrit ci-dessus. Corrigé pour refléter le comportement réel :
  l'e-mail est mis en file, puis livré seulement après passage de `deliver_batch()`.
- Le type `DOCUMENT` (modèle, rendu, gabarit HTML/texte, traitement outbox) est
  entièrement fonctionnel mais **n'est déclenché par aucun code actuel** : aucun dépôt
  de document ne crée de `Notification`/`OutboxMessage`. Décision produit à confirmer :
  notifier par e-mail au dépôt d'un nouveau document, ou laisser la découverte se faire
  uniquement dans l'espace « Documents ».

Le détail, les priorités et la checklist sont dans `docs/AUDIT_FINAL_AVANT_PRODUCTION.md`.

## Lot fonctionnel — 15 septembre 2026

- Satisfaction : axes libres, notes par axe, modification protégée après premières
  réponses et résultats graphiques agrégés ; permissions centrales existantes conservées.
- Vote : double POST reproduit (2 scrutins), corrigé par clé unique et verrou serveur.
- Téléphone : widget Tunisie +216, nettoyage frontend et validation/normalisation serveur.
- Cotisations : workspace de tous les membres actifs, recherche/filtres/compteurs,
  états explicites par tranche réservés au trésorier/SUPER_ADMIN.
- Événement proche : annonce EVENT_CREATED en outbox si début futur dans ≤7 jours,
  à la création calendrier/première publication ; idempotence et rappels préservés.
- Documents : health check PING/VERSION, protocole et fail-closed renforcés.
  **ClamAV absent/inactif localement : activation réelle et recette restent à faire.**
- Quatre migrations créées, appliquées en tests seulement ; base locale non migrée.
- Suite complète unique : 390 tests, 0 failure/error, 5 skips. Recette navigateur
  séparée : 21 checks aux tailles 1440×900, 390×844 et 430×932, verts.
- Aucun commit/push/déploiement ni changement mockups/legacy/SEO.

Détails et procédure : `docs/FUNCTIONAL_CORRECTIONS_REPORT.md` et
`docs/CLAMAV_PRODUCTION_CHECK.md`.

### Extension des parcours fonctionnels — 15 septembre 2026

- Ajout de `apps/core/tests/test_functional_journeys.py` : 14 tests HTTP de parcours
  avec CSRF actif, vérifications des états en base, audits, refus et rejeux.
- Satisfaction, documents/ACL/antivirus, vote jusqu’aux résultats, téléphone
  profil/contact/candidature, cycle de cotisations et email événement couverts.
- Matrice GET/POST des 14 rôles sur les trois interfaces de gestion testées
  (84 contrôles), accès anonyme et POST sans CSRF ; refus sans mutation.
- Scanner mocké et email locmem : aucune infrastructure production sollicitée.
- Tests ciblés : 14 verts. Suite complète unique de cette extension : 404 tests,
  0 failure, 0 error, 5 skips. Check Django et git diff --check propres.
- Aucun changement de permission, modèle, migration ou code métier dans cette passe.
- Matrice et limites explicites : `docs/FUNCTIONAL_SCENARIOS.md`.

### Cadrage individuel des portraits — 15 septembre 2026

- Éditeur privé dans Modifier mon profil : aperçu circulaire, zoom 1–4,
  positions horizontale/verticale, glisser souris/tactile, recentrage ; curseurs
  accessibles au clavier. JS vanilla, cadrage appliqué côté serveur avec Pillow.
- Original normalisé conservé dans stockage privé et servi uniquement au
  propriétaire (`members:photo_original`, private/no-store). Portrait carré JPEG
  512 px réutilisé par les routes existantes partout, y compris profil public.
- Nouveaux champs `photo_original_key` et `photo_crop`. Migration members `0009`
  appliquée uniquement en local ; aucune conversion massive des photos existantes.
  Ancienne photo conservée comme source lors de son premier recadrage.
- Validation serveur des bornes et des valeurs non finies ; photo supprimée =
  source/cadrage/portrait supprimés, nettoyage des nouveaux fichiers sur rollback.
- 55 tests profils verts (1 skip), 4 tests cadrage verts ; Chrome : 24 contrôles
  responsive et zoom/curseurs/reset verts à 1440/390/430 px. Capture mobile inspectée.
- Aucun commit/push/déploiement ni changement de permission.
- Suite complète unique finale : 417 tests en 55,924 s, 0 failure, 0 error,
  5 skips. Check Django, détection des migrations et git diff --check propres ;
  migrate --check local vert après la migration members 0009.

### Présentation cotisations — 15 septembre 2026

- Dashboard Trésorier/Super Admin : encaissé, restant et total attendu en TND,
  progression textuelle, calcul sur membres actifs éligibles et tranches payées
  au barème courant. Aucun total inventé si barème incomplet ; année active seule.
- Accès protégé par `dues.manage`, pas de changement de rôle ou de permission.
  Aucune migration. Tests ciblés : 6 verts ; navigateur : 24 contrôles à
  1440/390/430 px verts, capture dashboard mobile inspectée.

- Recherche avec suggestions natives de noms (`datalist`), liste complète des
  membres actifs éligibles indépendante des filtres et de la pagination ; selector
  partagé avec la liste cotisations. Noms uniquement, espace privé protégé.
- Tests cotisations après cette extension : 3 verts, dont suggestions au-delà de
  20 membres, filtres vides, exclusions et refus de permission.

- Cartes membres avec initiales, badges d’état distincts et progression textuelle
  des deux tranches (pas un pourcentage de montant encaissé).
- Tranches repliables avec repères numérotés et formulaire vertical, bouton bleu.
- Charte du skill Lionsmed reprise comme référence visuelle dans `rebuild/` ;
  aucune modification des maquettes, permissions, modèles ou paiements.
- Contrôle Chrome opt-in : 21 vérifications à 1440/390/430 px réussies ; capture
  mobile inspectée, pas de débordement. Aucun commit/push/déploiement.

### Rôle Marketing & Communication — 15 septembre 2026

- Nouveau rôle `MARKETING_COMMUNICATION` (15 rôles au total), périmètre confirmé.
- Groupe `CONTENT_MANAGERS` dédié : actions (création/modification/publication),
  images et contenus institutionnels ; communications aux membres via l’outbox.
- Aucun ajout à `MANAGERS` : pas de gestion des votes, satisfaction, documents,
  cotisations, événements, membres/rôles, années, candidatures ou contacts.
  Les accès personnels ordinaires d’un membre sont conservés.
- Navigation et formulaires utilisent les capabilities et `Role.choices` existants.
- Migration governance `0005` nécessaire pour la contrainte SQL et les choix du rôle ;
  non appliquée à la base locale réelle. Aucun rôle attribué à un compte réel.
- Quatre tests nouveaux : matrice exacte, routes autorisées, refus GET/POST sans
  audit de réussite, rejeu communication ; 25 tests ciblés verts.
- Suite complète unique : 408 tests, 5 skips, 0 erreur, 1 échec dans une ancienne
  attente de permissions éditoriales. Test actualisé : Marketing autorisé pour
  les actions uniquement, pas les événements. Recontrôle ciblé final : 5 tests
  verts (matrice HTTP/services et nouveau rôle). Suite complète non relancée.
- Check Django et détection des migrations propres ; `migrate --check` signale
  les migrations en attente des lots récents. Aucun commit/push/déploiement.
