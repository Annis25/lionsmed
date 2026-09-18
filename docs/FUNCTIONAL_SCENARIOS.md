# Scénarios fonctionnels automatisés

## Périmètre

Extension du lot satisfaction/documents/votes/téléphone/cotisations/événements.
14 nouveaux tests de parcours dans
`rebuild/apps/core/tests/test_functional_journeys.py`.

Ce sont des tests fonctionnels HTTP Django : formulaires et vraies vues, services,
base PostgreSQL isolée, permissions, redirections et résultats persistés. CSRF actif
sur tous les clients utilisés. Aucun email réel ; livraison testée via locmem.
Documents stockés dans un répertoire temporaire propre aux tests.

## Matrice des parcours

| Domaine | Scénarios automatisés | Résultat vérifié |
|---|---|---|
| Satisfaction | Secrétaire crée, président modifie les axes, membre répond, rejeu, modification après réponse, lecture résultats | Une réponse ; notes par axe enregistrées ; structure figée ; titre corrigé ; aucun commentaire/identité du membre dans les résultats |
| Satisfaction | Axe manquant puis fenêtre fermée | Erreur formulaire/période indisponible ; aucune réponse ni audit de réponse réussie |
| Satisfaction | Une réponse avec seuil de deux participants | Résultats masqués ; pas de graphique divulguant les notes |
| Documents | Dépôt sain, accès invité refusé, droit nominatif accordé, GET/HEAD téléchargement, révocation | Fichier disponible seulement après scan ; ACL réévaluée après révocation ; contenu PDF téléchargé |
| Documents | Virus, scanner indisponible, timeout et exception | Erreur liée au fichier ; aucun document/fichier disponible ; aucun audit de dépôt réussi |
| Votes | Création, double POST, écran de confirmation, vote, rejeu du bulletin, clôture, résultats | Un scrutin et un audit de création ; aucun bulletin avant confirmation ; un bulletin/participation ; scrutin fermé ; résultats accessibles |
| Votes | Jeton de création absent et choix inexistant | Aucune création invalide ; aucun bulletin ni participation |
| Téléphone profil | Numéro national avec espaces, puis lettres/mélanges/longueurs invalides | Stockage +216 normalisé ; erreurs HTTP liées au champ ; numéro déjà enregistré préservé |
| Contact/candidature | Téléphone invalide, correction, envoi, rejeu, ouverture de la demande par secrétaire/GMT | Une demande ; numéro normalisé ; une intention email ; demande visible au gestionnaire autorisé |
| Cotisations | Impayé → partiel → payé → correction ; filtre payé ; POST président refusé ; date invalide ; année inconnue | États attendus ; historique de trois corrections ; date retirée pour tranche non payée ; aucun paiement forgé ou incorrect |
| Événements | Ajout calendrier proche, double POST, désactivation d'un destinataire avant livraison | Un événement ; une intention par membre ; deux emails locmem ; destinataire devenu inactif en not_applicable sans envoi |
| Sécurité | POST membre forgé ; POST président sans CSRF | Refus 403 ; aucun objet ni audit de mutation réussi |
| Permissions | GET et POST sur gestion satisfaction, dépôt document et création vote, pour les 14 rôles | 84 vérifications route/méthode/rôle ; cohérence backend avec la matrice centrale ; aucune création à partir de formulaires invalides |
| Anonyme | GET et POST avec CSRF valide mais sans session sur les gestions privées | Redirection login ; aucune mutation |

Les tests antérieurs conservent la couverture des frontières événement 2/6/7/8 jours,
des comptes invités, des permissions trésorier/SUPER_ADMIN et des 21 contrôles navigateur
aux tailles 1440×900, 390×844 et 430×932.

## Commande ciblée

```sh
cd /home/besbes/Documents/lionsmed/rebuild
.venv/bin/python manage.py test apps.core.tests.test_functional_journeys --settings=config.settings.test --noinput
```

Résultat ciblé : **14 tests, 0 failure, 0 error**.

Suite complète après ajout : **404 tests en 41,676 s, 0 failure, 0 error, 5 skips**.
Check Django : 0 problème. Git diff --check : propre. Les cinq skips sont inchangés
(recettes navigateur opt-in et vérification QR conditionnelle) ; aucun nouveau scénario
HTTP n’est désactivé.

## Limites explicites

- Pas une couverture exhaustive de toutes les combinaisons de tout le site.
- Les parcours HTTP complètent les tests navigateur ; ils ne simulent pas des clics Chrome.
- Scanner mocké : sain/virus/timeout/exception testés, mais ClamAV réel reste à installer
  et recetter avec EICAR. SMTP et timers réels nécessitent une recette distincte.
- Rejeux séquentiels testés ; tests de charge et scénarios de concurrence simultanée
  approfondis restent distincts.
- La matrice des rôles contrôle la conformité des vues à permissions.py, pas une
  redéfinition de la politique métier. Aucune permission ni migration modifiée dans cette passe.

Aucun commit, push, déploiement ou traitement de données production.
