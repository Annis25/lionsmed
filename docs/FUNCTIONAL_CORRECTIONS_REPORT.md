# LIONSMED — lot de corrections fonctionnelles
Date : 15 septembre 2026. Runtime : `rebuild/`.

## Synthèse

Implémentation fonctionnelle et suite complète verte : **390 tests, 0 failure, 0 error,
5 skips**. Recette navigateur séparée verte : **21 contrôles**, aux formats 1440×900,
390×844 et 430×932.

**Condition opérationnelle restante : ClamAV n’est pas actif localement.** Aucune
validation de scan réel sain/EICAR ne peut être revendiquée sur cette machine.
Le health check échoue et les dépôts restent refusés. Installation et recette
sur un environnement approprié nécessaires avant de déclarer les documents opérationnels.

Aucun commit, push, déploiement, changement d’indexation ou modification des mockups/legacy.
Aucun email réel. Toutes les mutations de test ont utilisé `config.settings.test`.

## 1. Baseline et permissions

Mise à jour après demande complémentaire de couverture fonctionnelle : 14 parcours HTTP
supplémentaires avec CSRF actif ajoutés dans
`rebuild/apps/core/tests/test_functional_journeys.py`. Ciblés verts ; nouvelle suite
complète de cette extension : **404 tests, 0 failure, 0 error, 5 skips**.
La suite à 390 tests ci-dessus correspond au lot initial. Aucun code métier ni migration
modifié dans l’extension. Matrice : `docs/FUNCTIONAL_SCENARIOS.md` (nouveau fichier).

La baseline était propre hors fichiers préexistants non suivis (`.github/`,
`AGENTS.md`, `CLAUDE.md` et leurs équivalents dans rebuild), conservés sans modification.
`git diff --check` était propre. Check Django : 0 problème. Aucune migration manquante,
aucune migration en attente à la baseline après accès PostgreSQL autorisé.

La première tentative sandbox de connexion au socket PostgreSQL a été refusée :
les vérifications concernées ont été relancées avec accès local autorisé.

Le skill Lionsmed demandé et `apps/core/permissions.py` ont été lus avant les modifications.
Le skill a guidé les cartes privées, palette navy/bleu, indicateurs légers et présentation
responsive sans dépendance graphique ajoutée.

### Satisfaction — avant/après

| Capability | Avant | Après |
|---|---|---|
| satisfaction.manage | SUPER_ADMIN, PRESIDENT, PRESIDENT_FONDATEUR, SECRETAIRE | Identique |
| satisfaction.view_results | Les mêmes gestionnaires | Identique |
| satisfaction.respond | Membres actifs ayant un rôle membre, hors INVITE | Identique |

PRESIDENT et SECRETAIRE avaient déjà les capacités demandées : aucune extension de rôles
n’était nécessaire. Les services et vues continuent d’utiliser les capacités centrales,
jamais un contrôle de rôle dispersé dans les templates. MEMBRE/INVITE ne peuvent pas
administrer ; INVITE ne répond pas.

## 2. Satisfaction : axes, modification et résultats

L’existant ne contenait qu’une période mensuelle et une note générale. Réutilisation de
ces modèles ; ajout de `title`, `description`, `SatisfactionAxis` et
`SatisfactionAxisScore`. La note générale existante reste conservée, distincte des notes
par axe. Aucun répondant ni commentaire individuel n’est exposé par les résultats.

Axes libres : une ligne par intitulé dans le formulaire, ordre des lignes utilisé pour
le réordonnancement, ajout/suppression/renommage avant les premières réponses. Limite
de sécurité : 30 axes, 180 caractères par intitulé. Aucun axe métier codé en dur.

Un lien « Modifier » mène à un formulaire dédié. Avant réponse : titre, description,
dates, seuil et axes modifiables. Après réponse : titre et description restent
modifiables ; axes, dates et seuil sont figés. Le formulaire le signale et le service
bloque également une mutation directe dangereuse. Aucune réponse supprimée silencieusement.
Le mois de la consultation reste fixe dans l’interface de modification.

Résultats : participants, moyenne générale, moyenne par axe et distribution des notes
générales avec `meter`/`progress`, accompagnés de valeurs textuelles. Cartes responsive,
aucune dépendance JS graphique. Le seuil de confidentialité est préservé pour les
agrégats généraux **et** par axe.

Pas de taux historique : aucun dénominateur d’éligibles n’est figé par le modèle actuel.
Pas d’évolution artificielle ni de comparaison entre axes incompatibles.
La règle préexistante d’une période par mois est conservée.

## 3. Documents et antivirus

Flux audité : format/MIME, signature/structure, taille ≤50 Mo, puis INSTREAM clamd,
avant écriture/disponibilité du document.

Constat local : paquet `clamav-daemon` absent ; service inactif ; socket standard absent.
`check_antivirus --settings=config.settings.local` retourne un échec fail-closed.

Corrections :
- fermeture du socket Unix si la connexion échoue ;
- refus des réponses trop longues, incomplètes ou inattendues ;
- un résultat sain exige exactement `stream: OK` avec terminaison de protocole ;
- toute exception lors du scan empêche le stockage et devient un refus utilisateur ;
- détection virale toujours refusée et auditée.

Nouvelle commande `check_antivirus` : PING/PONG puis VERSION, sans fichier utilisateur,
sans secret, code de sortie non nul si indisponible.

Tests mockés : sain accepté (tests existants), virus refusé (tests existants),
indisponibilité, timeout, réponse/protocole et exception scanner. Ces tests ne remplacent
pas une installation et une recette ClamAV réelle.

Procédure détaillée : [CLAMAV_PRODUCTION_CHECK.md](CLAMAV_PRODUCTION_CHECK.md).
La fausse commande `echo test | nc` du runbook a été remplacée par le health check réel.
Aucune commande d’installation ni interruption de service production exécutée.

## 4. Vote dupliqué

Cause vérifiée : un POST appelle une seule fois le service, sans signal ni seconde
création frontend. Mais chaque nouveau POST crée un nouveau Vote ; le redirect après
POST ne protège pas d’un double clic/retry navigateur.

Reproduction ajoutée **avant correction** : même formulaire soumis deux fois,
**2 Votes au lieu de 1** (`AssertionError: 2 != 1`).

Protection serveur :
- UUID de création obligatoire dans le formulaire HTTP ;
- champ `Vote.creation_key` unique en base, nullable uniquement pour compatibilité
  avec les anciens scrutins et appels internes existants ;
- service transactionnel, verrou du créateur, lookup avant création ;
- rejeu du même jeton retourne le scrutin existant ;
- réutilisation du jeton d’un autre responsable refusée ;
- notifications d’ouverture conservent leurs clés idempotentes.

Le frontend désactive aussi le bouton au submit pour l’UX, mais la garantie est serveur.
Le jeton reste caché ; JS de création déplacé dans un fichier statique, labels des
choix rendus accessibles. Tests de création normale et double POST verts.
Séparation Participation/Ballot/électeur inchangée : aucune nouvelle liaison identifiante.

## 5. Téléphone

Champs concernés : profil membre, candidature, contact et coordonnées institutionnelles.
Champ/widget partagé, préfixe visible « Tunisie · +216 » et exemple national de 8 chiffres.

Normalisation à la saisie : `20 123 456`, `20123456`, `+21620123456`
→ `+21620123456`. Fixe tunisien également accepté. Un numéro international explicite
commençant par + reste accepté selon une validation E.164 de longueur ; aucun annuaire
mondial de plans téléphoniques n’est prétendu.

Frontend : `type=tel`, `inputmode=numeric`, pattern, suppression des lettres et caractères
non admis. Serveur : refus des lettres et mélanges, longueur tunisienne exacte, espaces
normalisés. Le serveur valide même avec JS désactivé ou POST forgé.

Aucune migration ni réécriture massive des numéros existants. Les anciennes données ne
sont pas changées au chargement ; une nouvelle saisie/modification doit respecter la
validation. Contact/profil restent facultatifs, candidature obligatoire.

Les fixtures anciennement « 00000 » ont été remplacées par un numéro **synthétique**
valide, afin que les tests de photos/profil ne dépendent pas d’un téléphone désormais
interdit.

## 6. Interface trésorier

Réutilisation des deux tranches, dates et note internes existantes. Aucun système de
paiement, comptabilité ou montant individuel inventé.

Page de travail : année active par défaut, choix de l’année, recherche membre, filtres
Payé/Partiel/Non payé, compteurs à jour/partiels/impayés. Tous les membres actifs ayant
un rôle annuaire sont affichés, y compris sans fiche de paiement. Les SUPER_ADMIN
techniques ou métier ne sont pas listés comme membres à cotiser, conformément à
l’exclusion annuaire préexistante.

Cartes par membre, deux sections de tranche repliables pour limiter la hauteur sur
téléphone ; état explicite, date facultative, note/motif, lien vers l’historique existant.

Nouvel endpoint POST : création de la fiche si nécessaire puis affectation explicite
« payée/non payée » ; un double POST identique ne bascule pas à nouveau la valeur.
Le legacy endpoint de bascule est conservé pour compatibilité, mais le nouveau
workspace n’en dépend pas. Tranche invalide refusée.

Droits inchangés : mutation **TRESORIER et SUPER_ADMIN** via `dues.manage`.
PRESIDENT/SECRETAIRE/BUREAU conservent seulement les consultations prévues par la
capability existante. POST direct protégé, CSRF actif, année ou membre inexistant →404.
Les corrections de paiement continuent de créer DuesChange/AuditEvent.

Le filtre historique appliqué après pagination a aussi été corrigé : filtrage SQL
avant pagination. Le workspace pagine après constitution/filtrage de ses lignes
incluant les membres sans fiche. Aucun GET ne crée de fiche.

## 7. Nouvel événement proche et emails

Règle : **now < starts_at ≤ now + 7 jours**. Exactement 7 jours inclus.
Création calendrier publié interne → annonce immédiate **en file outbox**, pas SMTP
synchrone. Événement éditorial en brouillon → aucune annonce ; déclenchement à sa
première publication. Ce choix évite d’envoyer un brouillon invisible.

Type explicite `EVENT_CREATED`, sujet/contenu distincts des rappels, HTML et texte
utilisant la base Lionsmed et SITE_ORIGIN.

Destinataires : selector de diffusion existant + `can(event.register, event)` :
membres actifs, compte actif, rôle autorisé calendrier, email présent ; invités exclus.
Jamais un envoi arbitraire à tous les User.

Clé stable :
`event-created:<event_id>:<recipient_id>:v1`
Outbox : `outbox:` + cette clé. Unicité existante Notification/Outbox préservée.
Ajout rapide calendrier également protégé contre le double POST par UUID unique de
création et verrou du créateur. L’éditeur éditorial conserve son unicité de slug.

Pas d’email nouveau à chaque modification/republication. Au-delà de 7 jours ou événement
passé : aucune annonce immédiate. Rappels J7/J1, destinataires confirmés, clés de version,
commande `send_event_reminders` et timer existants inchangés.

Outbox conserve PENDING/SENDING/SENT/FAILED, lease, retry, backoff et not_applicable.
Avant livraison EVENT_CREATED, événement retiré/supprimé/passé ou destinataire ayant
perdu ses droits → not_applicable, pas de retry SMTP inutile.

Tests : 2/6/7 jours →queue ; 8 jours/passé →aucune ; invités/inactifs exclus ; rejeu
service et double POST →pas de doublon ; deliver_batch locmem →SENT, contenu HTML/texte.
Les tests isolant les rappels suppriment uniquement les annonces synthétiques de setup,
pour ne pas confondre ces deux politiques email.

## 8. Migrations et commandes ultérieures

Quatre migrations nécessaires :
- agenda.0004_event_creation_key ;
- communications.0007_alter_outboxmessage_kind ;
- satisfaction.0002_satisfactionperiod_description_and_more ;
- voting.0004_vote_creation_key.

Elles sont appliquées uniquement à la base isolée pendant les tests.
`makemigrations --check --dry-run` final : **No changes detected**.
`migrate --check` final sur le runtime local : **code 1**, car ces quatre migrations
n’y sont volontairement pas appliquées. `migrate --plan` confirme exactement ces quatre.

À exécuter plus tard, selon le runbook et après sauvegarde/validation :
```sh
# Local, pour pouvoir utiliser les nouvelles interfaces :
.venv/bin/python manage.py migrate --settings=config.settings.local

# Production, seulement dans un déploiement autorisé ultérieur :
.venv/bin/python manage.py migrate --settings=config.settings.production
.venv/bin/python manage.py collectstatic --noinput --settings=config.settings.production
.venv/bin/python manage.py migrate --check --settings=config.settings.production
.venv/bin/python manage.py check_antivirus --settings=config.settings.production
.venv/bin/python manage.py outbox_status --settings=config.settings.production
```

Installer/configurer/recetter ClamAV selon la procédure dédiée, puis vérifier les timers
outbox et rappels existants. Aucun de ces changements production n’a été exécuté ici.

## 9. Tests et QA

- Reproduction initiale vote : 1 test, 1 failure attendu (2 scrutins).
- Passe ciblée large intermédiaire : 230 tests, 2 erreurs de fixture dans les nouveaux
  tests trésorier, ensuite corrigées (helper account définit déjà prénom/nom).
- Nouvelles régressions ciblées après correction : **15 tests, 0 failure, 0 error**.
- Passe dédiée widget/gestion/Chrome : **6 tests, 0 failure, 0 error**.
- Recette navigateur finale indépendante : **1 test vert, 21 checks responsive**.
- Check Django final : **0 problème**.
- **Une seule suite complète** : **390 tests en 37,521 s, 0 failure, 0 error, 5 skips**.
- Git diff --check final : propre.

Skips suite standard : trois recettes navigateur préexistantes opt-in, la nouvelle
recette fonctionnelle opt-in (exécutée séparément avec succès), et décodage QR conditionnel
car pyzbar indisponible. Les skips ne sont pas des échecs métier.

Captures synthétiques contrôlées : `/tmp/lionsmed-functional-<page>-<largeur>.png`.
Les contrôles automatiques couvrent statut/routing réel, absence de débordement horizontal,
un h1 et labels des champs ; vérification visuelle des cartes/graphes et contrôle de
nettoyage des lettres dans le téléphone. Les contrôles ne prétendent pas constituer
un audit accessibilité exhaustif.

## 10. Décisions / conditions restantes

- Installer et recetter réellement ClamAV ; le health check local reste en erreur.
- Appliquer les quatre migrations dans l’environnement choisi avant utilisation.
- Si plusieurs campagnes par mois ou un taux de participation historique sont souhaités,
  une évolution produit/modèle distincte sera nécessaire ; rien n’a été inventé ici.
- Les formats étrangers sont admis en saisie explicite +indicatif, pas validés contre
  chaque plan national ; préciser si le produit doit devenir tunisien uniquement.
- Les rappels J7/J1 existants peuvent toujours suivre l’annonce de création : ce sont
  des intentions distinctes, pas un doublon de la même annonce.

## 11. Liste complète des fichiers modifiés/créés dans ce lot

Les fichiers préexistants non suivis d’instructions/GitHub ne font pas partie du lot.

```text
docs/CLAMAV_PRODUCTION_CHECK.md
docs/DEPLOY_REBUILD.md
docs/FINAL_PROJECT_CONTEXT.md
docs/FUNCTIONAL_CORRECTIONS_REPORT.md
rebuild/apps/agenda/forms.py
rebuild/apps/agenda/migrations/0004_event_creation_key.py
rebuild/apps/agenda/models.py
rebuild/apps/agenda/private_views.py
rebuild/apps/agenda/services.py
rebuild/apps/agenda/tests/test_agenda.py
rebuild/apps/agenda/tests/test_created_email.py
rebuild/apps/communications/emailing.py
rebuild/apps/communications/forms.py
rebuild/apps/communications/migrations/0007_alter_outboxmessage_kind.py
rebuild/apps/communications/models.py
rebuild/apps/communications/outbox.py
rebuild/apps/communications/tests/test_outbox_kinds.py
rebuild/apps/core/phone.py
rebuild/apps/core/templates/components/forms/phone_input.html
rebuild/apps/core/tests/test_functional_browser.py
rebuild/apps/core/tests/test_phone.py
rebuild/apps/documents/management/__init__.py
rebuild/apps/documents/management/commands/__init__.py
rebuild/apps/documents/management/commands/check_antivirus.py
rebuild/apps/documents/scanning.py
rebuild/apps/documents/services.py
rebuild/apps/documents/tests/test_antivirus_health.py
rebuild/apps/dues/forms.py
rebuild/apps/dues/selectors.py
rebuild/apps/dues/tests/test_workspace.py
rebuild/apps/dues/urls.py
rebuild/apps/dues/views.py
rebuild/apps/editorial/management_forms.py
rebuild/apps/editorial/publication.py
rebuild/apps/members/forms.py
rebuild/apps/members/tests/test_members.py
rebuild/apps/satisfaction/forms.py
rebuild/apps/satisfaction/migrations/0002_satisfactionperiod_description_and_more.py
rebuild/apps/satisfaction/models.py
rebuild/apps/satisfaction/selectors.py
rebuild/apps/satisfaction/services.py
rebuild/apps/satisfaction/tests/test_axes.py
rebuild/apps/satisfaction/urls.py
rebuild/apps/satisfaction/views.py
rebuild/apps/voting/forms.py
rebuild/apps/voting/migrations/0004_vote_creation_key.py
rebuild/apps/voting/models.py
rebuild/apps/voting/services.py
rebuild/apps/voting/tests/test_creation_replay.py
rebuild/apps/voting/tests/test_voting.py
rebuild/apps/voting/views.py
rebuild/static/css/lions.css
rebuild/static/js/phone.js
rebuild/static/js/vote_creation.js
rebuild/templates/base/site.html
rebuild/templates/emails/event_created.html
rebuild/templates/emails/event_created.txt
rebuild/templates/espace/calendrier.html
rebuild/templates/espace/dues_management.html
rebuild/templates/espace/satisfaction.html
rebuild/templates/espace/satisfaction_edit.html
rebuild/templates/espace/satisfaction_gestion.html
rebuild/templates/espace/satisfaction_resultats.html
rebuild/templates/espace/vote_creation.html
rebuild/tools/browser_functional.cjs
```
