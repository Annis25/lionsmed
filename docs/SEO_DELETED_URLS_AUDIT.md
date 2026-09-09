# Audit SEO — URLs supprimées

Date : 10 septembre 2026  
Périmètre : `rebuild/` (routes publiques, sitemap, robots, redirections et accès privé).  
État d'indexation audité : `LIONSMED_PUBLIC_INDEXING=false` — aucune activation effectuée.

## Constats

- Le routeur ne déclare aucune route `actualites` ou `news`.
- Les anciennes URLs Actualités testées retournent bien une 404, sans redirection vers l'accueil.
- Le registre `editorial.Redirect` de l'environnement local contient **0** entrée. Lorsqu'un slug d'action ou d'événement est modifié, le code ne permet qu'une redirection permanente interne vers la ressource publique finale exacte ; les boucles, chaînes, URL externes et redirections génériques sont refusées.
- La fonction historique d'import `actualites` subsiste dans `apps/core/legacy_pipeline.py`, mais elle est explicitement non exécutée et marque les données comme rejetées : ce n'est pas une route active ni une anomalie SEO.
- Aucune référence active à une page Actualités n'a été trouvée dans la navbar, le footer, les breadcrumbs, JSON-LD, OpenGraph, canonical, les e-mails publics ou le sitemap. Aucun schéma `NewsArticle` n'est présent.
- Le sitemap ne contient que les pages publiques actuelles et les actions/événements/profils publics actifs. Quand l'indexation est désactivée, il ne contient aucune balise `<url>`.
- Toutes les surfaces privées reçoivent `X-Robots-Tag: noindex, nofollow` via le middleware global ; les ICS ajoutent également `noindex`/`noindex, nofollow` et les jetons invalides renvoient 404.

## Inventaire des URLs supprimées et échantillon HTTP

| Ancienne URL | Statut actuel | Attendu | Présente sitemap ? | Lien interne ? | Action nécessaire |
|---|---:|---|---|---|---|
| `/actualites/` | 404 | 404/410, sans soft-404 | Non | Non | Aucune |
| `/actualites/inconnu/` | 404 | 404/410, sans soft-404 | Non | Non | Aucune |
| `/news/` | Absente du routeur (404 attendue) | 404/410 | Non | Non | Aucune |
| `/news/inconnu/` | Absente du routeur (404 attendue) | 404/410 | Non | Non | Aucune |
| Ancien slug action/événement enregistré | Aucun enregistrement local | 301 seulement vers la nouvelle URL exacte | Non | Non | À contrôler lors d'un futur changement de slug |
| `/nos-actions/inconnu/` | 404 attendue | 404, sans renvoi accueil | Non | Non | Aucune |
| `/evenements/inconnu/` | 404 attendue | 404, sans renvoi accueil | Non | Non | Aucune |
| `/espace/` et sous-pages privées | Authentification/403 selon droit | Jamais indexable | Non | Non public | Aucune |
| `/espace/calendrier/abonnement/<jeton>.ics` invalide | 404 | 404 et noindex | Non | Non | Aucune |

## Robots et sitemap

Configuration actuelle : `PUBLIC_INDEXING_ENABLED=False`.

- `robots.txt` : `User-agent: *` puis `Disallow: /`.
- `sitemap.xml` : vide (aucune URL publiée).
- À l'activation future, le sitemap reste filtré aux seuls contenus publics publiés et validés ; les formulaires, l'espace membre, les brouillons et les pages filtrées restent exclus/noindex.

## Vérifications exécutées

- Recherche statique sur `actualites`, `news`, `redirect`, `canonical`, `sitemap`, `robots` et `NewsArticle`.
- Inspection des routes, sitemaps, middleware `X-Robots-Tag`, génération des métadonnées et registre de redirections.
- Registre local : 0 redirection active.
- Tests réussis :
  - `PublicationTests` et `SeoTests` : **15 tests**, 0 échec ; couvrent notamment `/actualites/`, son détail inexistant, sitemap, robots, canonical et politique noindex.
  - `AuthTests` et `CalendarIcsTests` : **28 tests**, 0 échec ; couvrent les accès privés, les en-têtes noindex et les ICS invalides.

Une exécution plus large de 118 tests a révélé un échec isolé hors périmètre SEO dans `SubmissionTests.test_state_change_permissions_and_audit` (droits de changement d'état d'une candidature). Il n'affecte ni les routes supprimées, ni sitemap/robots, ni l'indexabilité ; il devra toutefois être corrigé avant une validation globale de production.

## Verdict

**READY WITH CONDITIONS**

Le périmètre URL supprimées / indexation est prêt : aucune ancienne URL Actualités active, aucun lien interne ou sitemap obsolète, aucune soft-404 vers l'accueil et les zones privées sont noindex.

Conditions avant activation :

1. Corriger puis rejouer le test de permissions de candidature hors périmètre SEO.
2. Après déploiement, vérifier en HTTP réel sur le domaine public les statuts listés ci-dessus et tout futur 301 ajouté au registre de redirections.
3. N'activer `LIONSMED_PUBLIC_INDEXING=true` qu'après ces vérifications.
