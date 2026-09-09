# Reprise legacy → rebuild

Pipeline : `rebuild/apps/core/legacy_pipeline.py`, commande `manage.py import_legacy`.
Lecture seule de `db.sqlite3` ; jamais de connexion directe du runtime de production à cette
base. Idempotent via `core.LegacyImportRecord` (source+table+PK legacy unique).

## Ce qui est importé automatiquement

| Source | Cible | Règle |
|---|---|---|
| `accounts_user` | `accounts.User` + `members.MemberProfile` | Identité seulement. **Aucun rôle accordé**, **aucun mot de passe legacy repris** (`set_unusable_password()` — activation par lien de réinitialisation). Statut ACTIVE si `is_approved`, sinon GUEST. |
| `accounts_membershiprequest` | `members.MembershipApplication` | Insertion directe, **aucun email envoyé** (pas d'appel au service `submit()`). **Rejetée** (jamais complétée) si le téléphone legacy est vide — le téléphone est obligatoire côté rebuild depuis la recette V1. |
| `events_event` (type REUNION/GALA) | `agenda.Event` | DRAFT, visibilité reprise de `is_public` (donnée réelle, pas une invention). |
| `members_cotisation` | `dues.DuesRecord` | Seulement si (a) le membre associé est déjà importé et (b) une **Année Lions existe déjà** et couvre l'année calendaire. Montant réel repris, jamais de valeur par défaut. |

## Ce qui est mis en quarantaine (décision humaine requise)

- `events_event` de type **ACTION** : `service_actions.Action.axis` est un champ obligatoire à
  choix fermé, absent du schéma legacy. **Aucun axe n'est deviné.** Créer l'Action manuellement
  via `/espace/contenu/action/ajouter/` une fois l'axe confirmé par le bureau.
- Cotisations dont le membre n'est pas importé, ou dont l'année calendaire n'a pas encore
  d'Année Lions correspondante (calendrier institutionnel proposé juillet→juillet, **non
  confirmé** — voir `NOUVELLE_ARCHITECTURE_LIONSMED.md` §9).

## Ce qui n'est délibérément PAS repris

- `news_article` : **décision produit (recette V1)** — la fonctionnalité Actualités est
  supprimée du nouveau produit. Chaque ligne legacy est déclarée `SKIPPED`/`REJECTED`
  avec le motif « fonctionnalité Actualités supprimée du nouveau produit », jamais
  importée sous quelque forme que ce soit.
- Sessions, logs Axes, tables `guardian` — aucune valeur pour le nouveau schéma.
- Rôles legacy → **aucun RoleGrant créé** par le pipeline, quel que soit le rôle (y compris
  un nom identique comme `PRESIDENT`) : l'attribution reste un acte humain via `grant_role`.
  Le rôle legacy est conservé en texte dans `LegacyImportRecord.reason` pour référence.
- `COMITE` : aucun équivalent dans les sept rôles ; identité importée, aucun privilège.
- Photos et fichiers (`accounts_user.photo`, `events_event.image`) :
  un seul fichier legacy existe, droits non vérifiés — à traiter au cas par cas, hors pipeline.
- Contenu institutionnel (`sitecontent_*` : identité du club, valeurs, historique, chiffres,
  bureau, avantages) : nécessite une validation humaine du texte, pas un import mécanique.
  À saisir via `/espace/contenu/` avec les vraies sources.
- Votes/résultats legacy (`voting_vote`, `voting_uservote` s'ils existent) : archive séparée
  si besoin confirmé, jamais réouverts, jamais réinterprétés comme nouveaux scrutins.

## Utilisation

```sh
# Aperçu, aucune écriture :
rebuild/.venv/bin/python rebuild/manage.py import_legacy --source /chemin/db.sqlite3

# Application réelle, une fois le rapport dry-run revu :
rebuild/.venv/bin/python rebuild/manage.py import_legacy --source /chemin/db.sqlite3 \
  --apply --operator-email technique@lionsmed.tn
```

Le rapport donne, par table : `source` (lignes lues), `importé`, `déjà_importé` (rejeu sans
doublon), `rejeté` (raison affichée), `quarantaine` (raison affichée). Rejouer la commande
est sans risque : les lignes déjà `IMPORTED` sont ignorées.

## Validation effectuée (Phase C)

Suite `apps/core/tests/test_legacy_pipeline.py` (8 tests, base PostgreSQL de test) : dry-run
n'écrit rien, application réelle produit les comptages attendus, aucun rôle accordé, aucun mot
de passe repris, identité importée même pour un rôle inconnu (quarantaine du privilège
seulement), cotisations bloquées sans Année Lions confirmée puis importées une fois celle-ci
créée, rejeu strictement idempotent, aucun `OutboxMessage` créé pendant l'import.

Un dry-run a également été exécuté sur le `db.sqlite3` réel du dépôt (11 comptes, 3 candidatures,
5 actualités, 5 événements dont 3 ACTION, 10 cotisations) : résultat conforme à ce tableau —
2 événements REUNION/GALA importables, 3 ACTION en quarantaine, 10 cotisations en quarantaine
faute d'Année Lions encore définie dans la base de développement. **Aucune écriture réelle
n'a été effectuée sur la base de développement partagée** ; seule la suite de tests (base
éphémère) a exercé le mode `--apply`.

## Bascule finale (non exécutée ici)

1. Geler les écritures du site legacy (maintenance ou lecture seule applicative).
2. Nouveau dry-run juste avant bascule ; comparer aux comptages précédents (delta attendu :
   nouvelles candidatures/actualités uniquement).
3. `--apply` sur la base de production rebuild, avec un compte opérateur technique dédié.
4. Smoke tests : connexion (reset), page d'accueil, annuaire, un document, un vote de test.
5. Basculer le domaine ; conserver le legacy accessible en lecture seule pendant une fenêtre
   de retour ; ne jamais le supprimer à ce stade.
