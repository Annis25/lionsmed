# Audit final Lionsmed

## Verdict

**READY FOR PREPROD, pas pour production directe.** Le runtime audité est `rebuild/`. Les contrôles de code, de permissions, de migrations et les tests automatisés sont cohérents ; la configuration réelle de production reste à recetter.

## P0

Aucun défaut P0 démontré.

## P1

Aucun défaut P1 restant dans le code audité. Avant production, l’équipe doit toutefois fournir et tester les secrets, SMTP, ClamAV, sauvegardes PostgreSQL, restauration et HTTPS réel.

## P2

- Décider institutionnellement le seuil de publication des résultats de satisfaction.
- Confirmer l’audience des résultats de vote après clôture (actuellement : électeurs du scrutin).
- Valider l’activation de l’indexation publique et l’obligation MFA pour les rôles sensibles.
- Confirmer la visibilité de Pilotage, Présences et Statistiques dans la navigation privée.

## P3

Recette manuelle recommandée aux largeurs 1440, 1024, 768, 430 et 375 px sur les pages publiques, le menu mobile, le tableau de bord, l’annuaire, le calendrier et les e-mails reçus dans Gmail/Outlook.

## Sécurité

- Matrice centrale dans `rebuild/apps/core/permissions.py` ; un rôle actif ambigu est refusé.
- Vues et sélecteurs chargent les objets dans le périmètre autorisé ; les tests couvrent notamment documents, profils, votes, cotisations et agenda.
- Aucun SQL brut, `mark_safe`, filtre `safe`, `csrf_exempt` ni redirection `next` non contrôlée n’a été conservé dans le périmètre audité.
- Correction appliquée : les retours POST agenda et cotisations refusent les URL externes (`private_views.py`, `dues/views.py`), avec tests de non-régression.
- Fichiers privés, validation d’images, contrôle documentaire et ClamAV fail-closed restent en place.

## Permissions

Les rôles réels sont ceux de `Role` : SUPER_ADMIN, DIRECTEUR, PRESIDENT, VICE_PRESIDENT, SECRETAIRE, TRESORIER, BUREAU, GST, GMT, GLT, LCIF, MEMBRE et INVITE. La rubrique Communication est explicitement limitée à SUPER_ADMIN, PRESIDENT, VICE_PRESIDENT, SECRETAIRE, TRESORIER et BUREAU.

## SEO

Robots, sitemap, canonical, OpenGraph et JSON-LD reposent sur `SITE_ORIGIN`. L’indexation reste volontairement désactivée par défaut ; les routes privées ne sont pas ajoutées au sitemap. La production doit définir une origine HTTPS canonique.

## Performance

Les listes et sélecteurs critiques utilisent leurs périmètres ORM ; l’outbox est indexée sur l’état et la date de disponibilité, avec verrouillage `skip_locked`. Aucun N+1 évident et sûr à corriger n’a été trouvé pendant cette passe.

## PostgreSQL

Migrations synchronisées. Contraintes et index existent sur les flux prioritaires, notamment grants actifs, outbox et notifications. Aucun index supplémentaire à haut bénéfice/faible risque n’a été identifié sans mesure de charge.

## Responsive et accessibilité

Le menu de l’accueil mobile utilise maintenant une icône hamburger robuste sur le bouton afin d’éviter le rendu des trois traits à largeur nulle. Labels, titres, boutons nommés, `aria-expanded`, réduction des animations et navigation clavier des composants existants ont été vérifiés par lecture de code. Une recette écran/lecteur d’écran reste nécessaire.

## Emails

Chaque campagne est individualisée, sans CC/BCC ; aperçu, test, confirmation, idempotence et historique passent par les capacités et l’outbox. L’invitation initiale n’expose aucun mot de passe et propose à la personne de définir le sien avec un jeton Django.

## Exploitation

Avant production : injecter les secrets hors Git, configurer SMTP et ClamAV, exécuter le worker outbox/reminders sous supervision, collecter les statics, mettre en place backup PostgreSQL, tester une restauration et conserver un commit/tag de rollback. Ne pas annuler aveuglément les migrations en production.

## Tests

Les tests ciblés des retours sûrs agenda/cotisations passent. La suite complète Django a exécuté **348 tests**, avec **0 failure** et **0 error**. Les sorties 403/404/405/CSRF et rate-limit observées correspondent aux scénarios de refus attendus.

## Décisions humaines restantes

Les décisions P2 ci-dessus, la recette réelle SMTP/ClamAV, les politiques de sauvegarde/rétention et l’approbation de production restent sous responsabilité humaine.
