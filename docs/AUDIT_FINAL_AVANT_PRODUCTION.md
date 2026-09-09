# Audit final avant production — Lionsmed

Date de l'audit : 9 septembre 2026
Périmètre audité : `rebuild/`, en lecture seule. Aucun fichier applicatif, migration, donnée, mockup ou fichier legacy n'a été modifié pendant cet audit.

## Verdict

**NON GO pour la production à ce stade.**

Le socle Django, les migrations et la majorité des contrôles fonctionnels/sécurité sont cohérents. Toutefois, la suite de tests n'est pas verte : **2 échecs sur 338 tests collectés**, tous deux sur le contrôle d'intégrité des portraits. Une publication doit attendre la correction et le passage d'une suite complète verte.

## Baseline Git

- Dépôt : `/home/besbes/Documents/lionsmed`
- Branche : `main`
- HEAD court : `8d85696`
- Arbre déjà très chargé au début de l'audit : 81 fichiers suivis modifiés (2415 insertions, 372 suppressions, hors fichiers non suivis) et plusieurs migrations/fichiers nouveaux.
- `git diff --check` : OK.
- Aucun fichier `mockups/` ou `legacy/` n'apparaît dans le diff suivi.
- La compétence de design et des documents de suivi sont eux-mêmes modifiés : le travail doit être relu, découpé et commité avant toute livraison.

## Vérifications Django et migrations

| Contrôle | Résultat |
|---|---|
| `manage.py check --settings=config.settings.test` | OK, aucune anomalie système |
| `makemigrations --check --dry-run` | OK, aucune migration à générer |
| `migrate --check` | OK |
| `showmigrations --plan` | Toutes les migrations listées sont appliquées dans l'environnement contrôlé |
| Suite complète PostgreSQL | 338 tests collectés, **2 échecs** ; pas de skip final constaté |

Les nombreuses lignes `403`, `404`, `405`, CSRF et limitation de débit dans la sortie sont les comportements attendus des tests de refus d'accès ; elles ne constituent pas des échecs en elles-mêmes.

### Échec bloquant de tests

`apps.members.tests.test_members.UploadTests.test_svg_invalid_and_mime_extension_mismatch` échoue deux fois : un fichier nommé `portrait.png` dont le contenu/type ne correspond pas est accepté puis enregistré en `.jpg`. Le test attend le refus HTTP 200 avec erreur de formulaire et aucune mutation du profil ; le résultat observé est `302` et une `photo_key` créée.

La cause probable est la validation d'image devenue permissive pour permettre la conversion de fichiers atypiques : l'extension/type annoncé n'est plus vérifié assez strictement avant normalisation. Cela affaiblit le contrat d'upload et laisse la suite rouge.

## Matrice des rôles et accès effectifs

Les rôles effectifs sont lus dans `apps.governance.models.Role` ; un seul `RoleGrant` actif est requis. En cas d'ambiguïté, `effective_role()` refuse l'accès au lieu de choisir le rôle le plus puissant.

| Rôle | Accès privé / profil / agenda | Annuaire privé | Gestion éditoriale, membres, années, documents, notifications, votes/satisfaction | Particularités |
|---|---|---|---|---|
| SUPER_ADMIN | Oui | Non dans l'annuaire public interne | Oui | Gère aussi cotisations ; exclu de l'annuaire membre |
| DIRECTEUR | Oui | Oui | Non | Membre sans capacités de gestion validées |
| PRESIDENT | Oui | Oui | Oui | Boîte contact ; candidatures ; MFA |
| VICE_PRESIDENT | Oui | Oui | Non | Membre |
| SECRETAIRE | Oui | Oui | Oui | Boîte contact ; MFA |
| TRESORIER | Oui | Oui | Cotisations seulement (gestion) | Consultation cotisations bureau incluse |
| BUREAU | Oui | Oui | Documents et consultation cotisations | Pas de mutation des cotisations |
| GST / GMT / GLT / LCIF | Oui | Oui | Non | GMT voit/traite les candidatures ; les autres sont membres |
| MEMBRE | Oui | Oui | Non | Vote, satisfaction, calendrier, documents selon droits |
| INVITE | Accès personnel limité | Non | Non | Ne vote pas, ne répond pas à la satisfaction, ne voit pas l'annuaire |

Les profils suspendus sont refusés globalement. Un profil `GUEST` n'est utilisable qu'avec le rôle `INVITE`. Les droits de gestion n'utilisent pas un raccourci `is_superuser` : ils passent par la matrice de capacités.

### Navigation constatée

La barre privée expose Tableau de bord, profil, parcours, mot de passe, annuaire, calendrier, puis les rubriques conditionnelles Satisfaction, Documents, Votes, Cotisations, Notifications, Contenu public, Candidatures, Messages de contact, Membres et mandats, MFA et Années Lions.

**Écart UX à arbitrer (P2)** : les routes Pilotage, Présences et Statistiques restent protégées et accessibles par URL aux gestionnaires, mais sont volontairement masquées du menu dans `context_processors.py`. Cela ne viole pas les permissions, mais ne correspond pas à l'ordre de navigation demandé précédemment.

## Contrôles fonctionnels analysés

### Agenda et ICS

- Événements privés par défaut dans le calendrier interne ; publication publique séparée.
- Confirmations d'inscription sérialisées avec verrou `select_for_update()` sur l'événement et contrôle de capacité.
- Jeton ICS aléatoire de 32 octets, régénérable ; ancien jeton invalidé.
- Flux ICS anonyme assumé pour les applications calendrier, avec réponse `noindex, nofollow` et `private, no-store`.
- Génération RFC 5545 : échappement, repli de lignes, dates UTC, UID stable.

### Votes

- Électeurs figés à l'ouverture ; invités exclus.
- Dépôt transactionnel, verrou du scrutin puis électeur, une participation par électeur.
- Bulletin sans lien direct vers l'électeur ; preuve de participation séparée des choix.
- Résultats accessibles après clôture seulement, avec contrôle de l'audience.

### Cotisations

- Deux tranches, montants contrôlés et mutations transactionnelles/auditées.
- Seul SUPER_ADMIN/TRESORIER modifie ; PRESIDENT/SECRETAIRE/BUREAU consultent seulement.
- Détail et bascule de tranche chargent l'enregistrement via sélecteur autorisé : pas d'IDOR relevé.

### Satisfaction

- Une réponse par profil/période, note contrôlée de 1 à 5.
- Fenêtre temporelle obligatoire ; activation automatique impossible si l'heure de référence n'est pas configurée.
- Résultats agrégés uniquement, masqués sous le seuil. Le seuil par défaut `5` est explicitement noté « à confirmer humainement ».

### Profils, annuaire et documents

- Annuaire privé : profils actifs des membres, hors SUPER_ADMIN ; les champs privés sont accessibles uniquement dans l'espace privé selon les règles prévues.
- Profil public opt-in et page publique séparée ; aucun accès aux portraits privés par URL média directe.
- Documents hors URL publique, permissions de fichiers `0600` / dossiers `0700`, téléchargement autorisé par vue applicative.
- Validation extension/MIME/signature/structure ; antivirus ClamAV en échec fermé. En production, l'absence de ClamAV bloque tout dépôt documentaire : configuration et supervision requises avant mise en service.

## Sécurité, confidentialité et exploitation

### Points positifs

- CSRF, authentification et contrôle de capacité présents sur les vues de mutation inspectées.
- Contrôles d'objet dans les sélecteurs : profils, documents, cotisations, votes et présences ne sont pas chargés uniquement par identifiant non autorisé.
- Pas de SQL brut, `extra()`, `raw()`, `mark_safe`, filtre template `safe` ou `csrf_exempt` détecté dans les applications Python inspectées.
- Limitation de débit login, reset et vérification MFA ; mots de passe et paramètres sensibles protégés par Django.
- MFA TOTP (`django-otp`), codes de récupération à usage unique, mot de passe requis pour désactivation.
- Production : HTTPS forcé, HSTS, hôtes exacts requis, secret long requis, cookies sécurisés, CSP non ajoutée (à évaluer au déploiement).
- Migrations legacy isolées : commande `migrate` refuse les tables legacy connues ; import legacy explicite et non automatique, sans reprise de mot de passe ni élévation de rôle.

### Points à traiter avant production

| Priorité | Constat | Action attendue |
|---|---|---|
| P1 | Suite de tests rouge : 2 échecs d'intégrité de portrait. | Corriger la validation, préserver la conversion autorisée sans accepter MIME/contenu incohérent, puis exécuter une suite complète verte. |
| P1 | SMTP est désactivé par défaut et ClamAV n'est pas configuré par défaut. | Configurer SMTP, ClamAV, secrets, origine HTTPS et hôtes exacts en préproduction ; vérifier envoi réel et dépôt document refusé/ouvert selon scanner. |
| P1 | Les fichiers `.env.example` sont suivis et un `.env.before-recipe` est présent dans `rebuild/`. | Revoir les fichiers de configuration avant déploiement, vérifier l'absence de secrets réels dans Git et définir un coffre de secrets. |
| P2 | Indexation publique reste volontairement désactivée par défaut. | N'activer `LIONSMED_PUBLIC_INDEXING=true` qu'après validation SEO éditoriale. |
| P2 | Seuil de satisfaction et audience des résultats de vote portent une mention « à confirmer humainement ». | Décider et documenter ces politiques institutionnelles. |
| P2 | Menu privé masque Pilotage/Présences/Statistiques. | Confirmer le choix ou remettre les liens selon la navigation métier attendue. |
| P2 | Large arbre de travail non commité, avec migrations nouvelles. | Revue de code, tests en CI, migration de préproduction, sauvegarde PostgreSQL et plan de rollback avant mise en production. |

## SEO, accessibilité, affichage et public

- Pages publiques : sitemap/robots et balises SEO sont présents dans l'architecture éditoriale ; l'indexation est explicitement contrôlée par environnement.
- Les formulaires et contrôles analysés utilisent labels, messages d'erreur et boutons ; les galeries ont des boutons nommés et prise en charge clavier dans le JavaScript inspecté.
- Les vérifications automatisées couvrent les profils publics, images et routes principales ; une recette manuelle multi-navigateurs/mobile reste nécessaire avant GO (menu, modal galerie, formulaires, contraste et zoom 200 %).
- Les actions utilisent une galerie publique distincte, avec images servies par la couche d'images publiques ; les documents et portraits restent privés.

## Checklist de passage préproduction

1. Corriger P1 upload puis obtenir `338 tests, 0 failure` dans une exécution complète propre.
2. Revoir les migrations nouvelles sur une copie PostgreSQL et pratiquer backup/restore/rollback.
3. Injecter les secrets hors Git : `DJANGO_SECRET_KEY`, base PostgreSQL dédiée `lionsmed_rebuild_*`, SMTP et ClamAV.
4. Lancer sous `config.settings.production`, HTTPS réel, domaine exact, cookies sécurisés et collecte static manifest.
5. Recetter les rôles PRESIDENT, SECRETAIRE, TRESORIER, GMT, MEMBRE et INVITE avec comptes séparés.
6. Vérifier réception e-mail réelle (reset, contact, candidature, notifications), flux ICS et révocation du jeton.
7. Valider politiques métier encore ouvertes : satisfaction, résultats de vote, indexation et menu gestionnaire.

## Conclusion

Le projet possède un socle de permissions et de confidentialité sérieux, et les vérifications de schéma sont propres. La décision de production reste bloquée par l'échec de validation des uploads et l'absence de preuve d'une configuration d'exploitation complète (secrets, SMTP, ClamAV, sauvegarde/restauration). Aucun correctif n'a été appliqué dans cet audit.

# Correction post-audit

Date : 9 septembre 2026.

## Portrait : correction appliquée

Le défaut provenait de `apps/core/image_processing.py` : le pipeline vérifiait l'extension et le format décodé par Pillow, mais ne contrôlait pas le MIME déclaré par l'upload avant la normalisation JPEG. Ainsi, un PNG réel envoyé comme `image/jpeg` pouvait passer.

La correction ajoute une table extension–MIME stricte et refuse tout MIME déclaré incohérent **avant** lecture/conversion. La vérification de signature/décodage et de format Pillow reste ensuite en place. Les formats PNG, JPEG, WebP et HEIC/HEIF restent admis uniquement avec leur MIME attendu ; un SVG, un texte renommé, une extension trompeuse ou un contenu qui ne correspond pas au format attendu reste refusé. La conversion finale JPEG ne se produit qu'après ces contrôles.

Tests ajoutés/adaptés :

- PNG valide normalisé ;
- JPEG valide normalisé (nouveau test explicite) ;
- extension/type incohérents, SVG, contenu non image et aucune mutation de profil en cas d'échec ;
- suppression des métadonnées EXIF et limite de dimensions conservées.

Résultat ciblé : `apps.members.tests.test_members.UploadTests` — **10 tests, 0 failure, 0 error**.

## Suite complète et migrations

- Suite complète exécutée une seule fois après les tests ciblés : **339 tests collectés, 0 failure, 0 error**.
- Trois tests sont explicitement ignorés par configuration/environnement (tests navigateur conditionnels et contrôle QR dépendant de `pyzbar`) ; ils ne masquent aucun échec.
- `manage.py check --settings=config.settings.test` : OK.
- `makemigrations --check --dry-run` : OK, aucune migration manquante.
- `migrate --check` : OK.
- `git diff --check` : OK.

## Configuration, secrets et environnement

La production reste intentionnellement non configurée ici. Aucune valeur réelle n'a été ajoutée ou affichée.

Checklist de variables à fournir hors Git :

- `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`, `DJANGO_SITE_ORIGIN` (origine HTTPS canonique) ;
- `LIONSMED_DB_PURPOSE`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`, éventuellement `DB_TEST_NAME` ;
- `LIONSMED_SMTP_ENABLED`, `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `DEFAULT_FROM_EMAIL`, `SERVER_EMAIL` ;
- `LIONSMED_CLAMD_SOCKET` ou `LIONSMED_CLAMD_HOST` + `LIONSMED_CLAMD_PORT` ;
- `LIONSMED_CONTACT_RECIPIENT`, `LIONSMED_PUBLIC_INDEXING`, `LIONSMED_SATISFACTION_HOUR`.

`DEBUG` est fixé à `False` dans la base de configuration et ne doit être activé que dans la configuration locale. Le proxy HTTPS doit transmettre correctement le schéma afin que `SECURE_SSL_REDIRECT`, HSTS, cookies sécurisés et origines CSRF puissent fonctionner.

`rebuild/.env.before-recipe` est **suivi par Git** et contient des champs de configuration potentiellement sensibles, dont une clé secrète. Ses valeurs n'ont pas été affichées. Il n'est pas ignoré par le `.gitignore` racine : sa suppression du dépôt/runtime de livraison ou son remplacement par un exemple sans valeurs doit être décidé et réalisé avant livraison.

## SMTP et outbox

Le backend production accepte SMTP externe uniquement lorsque `LIONSMED_SMTP_ENABLED=true`; aucune adresse localhost/dev n'est codée en dur dans le flux inspecté. Les envois reset mot de passe, candidatures, contact, notifications, votes, satisfaction et rappels passent par les mécanismes Django ou l'outbox. L'outbox emploie verrouillage `skip_locked`, clé d'événement idempotente, lease, tentatives bornées et code d'erreur non sensible.

Recette SMTP préproduction à effectuer avec une boîte de test : reset mot de passe, activation membre, candidature, contact, notification importante, ouverture/résultat de vote, satisfaction, rappel événement, rejet SMTP et rejeu idempotent de l'outbox. Ne pas activer SMTP réel avant cette recette.

## ClamAV

L'intégration utilise le protocole INSTREAM de `clamd`. Sans socket/hôte+port opérationnel, tout upload documentaire est refusé proprement : le comportement **fail closed** est conservé. Aucun bypass n'a été ajouté.

En développement sans scanner, ne pas tester de dépôt documentaire réel. En préproduction, vérifier un document sain, une signature détectée, un daemon indisponible et un délai dépassé : les trois derniers cas doivent être refusés sans fuite de détail.

## Backup / restore

Test local effectué sans écrasement : dump PostgreSQL de `lionsmed_rebuild_dev`, restauration dans la base temporaire `lionsmed_rebuild_restore_audit_20260909`, comparaison, puis suppression de la base et du dump temporaires.

Compteurs identiques source/restauration : **10 utilisateurs, 9 profils, 1 action**. Ce test ne remplace pas une politique de sauvegarde automatisée, de rétention et de restauration préproduction.

## MFA, SEO et navigation

- MFA : enrôlement disponible pour SUPER_ADMIN, PRESIDENT et SECRETAIRE ; elle n'est exigée à la connexion pour ces rôles que lorsqu'un appareil confirmé existe. La récupération utilise des codes statiques à usage unique ; la désactivation demande le mot de passe courant. Aucun bypass relevé.
- SEO : `PUBLIC_INDEXING_ENABLED=False` reste la valeur prudente ; robots bloque l'indexation et sitemap n'expose rien tant qu'elle n'est pas activée. Les profils publics actifs et événements publics sont conditionnels ; les pages privées ne sont pas intégrées au sitemap. La canonical est bâtie sur `SITE_ORIGIN`, qui doit être HTTPS et non localhost en préproduction.
- Pilotage est intégré au tableau de bord des gestionnaires ; Présences et Statistiques existent pour les rôles de gestion mais restent masquées dans le menu. C'est une décision UX, pas un défaut de permission.

## DÉCISIONS HUMAINES RESTANTES

1. Seuil de publication des résultats de satisfaction (valeur actuelle : 5).
2. Audience des résultats de vote après clôture (actuellement : électeurs du scrutin).
3. Activation future de l'indexation publique.
4. Visibilité navigation de Pilotage, Présences et Statistiques.
5. Obligation MFA pour les rôles sensibles, au-delà de l'enrôlement volontaire actuel.
6. Sort de `rebuild/.env.before-recipe` suivi par Git et politique de secrets.

## Nouveau verdict

**READY FOR PREPROD**, sous réserve d'injecter les secrets hors Git, de configurer et recetter SMTP/ClamAV, puis de réaliser la recette humaine et le plan de sauvegarde automatisé. Ce verdict ne vaut **pas** autorisation de production.

## Hygiène Git avant mise à jour production

`rebuild/.env.before-recipe` était suivi par Git, n'est requis ni par le runtime ni par les tests et a été retiré de l'index tout en étant conservé localement. Il est désormais ignoré. `rebuild/.env.example` ne contient que des noms de variables et valeurs vides ; il reste versionné.

### SECRETS À ROTER EN PRODUCTION

- `DJANGO_SECRET_KEY`

La valeur historique n'est pas reproduite dans ce rapport. Aucun autre mot de passe, jeton ou clé privée n'a été détecté parmi les fichiers destinés au commit.
