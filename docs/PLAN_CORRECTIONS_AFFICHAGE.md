# Plan de correction de l'affichage — octobre 2026

Ce plan traite tous les constats des deux audits d'affichage :

- audit des écrans Communication (5 octobre 2026) : 8 points ;
- audit de tout le site (6 octobre 2026) : 18 points, sur 87 pages et 8 profils, ordinateur et
  mobile, thèmes clair et sombre.

État au 6 octobre 2026 : **les six lots sont appliqués et vérifiés** (voir « Résultat » en fin de
document). Rien n'est commité ni mis en ligne. Aucune correction ne touche aux permissions, aux
modèles ni aux migrations : il s'agit de styles (`rebuild/static/css/`), de gabarits
(`rebuild/templates/`) et de trois vues d'affichage.

## Comment lire ce plan

- Les lots sont à faire **dans l'ordre**. Chacun est livrable et déployable seul.
- Les trois premiers lots ne changent pas l'apparence voulue du site : ils corrigent des défauts.
- Le lot 4 change l'apparence : il attend une décision (voir « Décisions à prendre »).
- « Taille » donne l'ordre de grandeur du travail, pas une durée.

| Lot | Contenu | Taille | Risque | Décision requise |
|---|---|---|---|---|
| 0 | Effet de bord du 5 octobre à retirer | 1 règle | Très faible | Non |
| 1 | Corrections globales (styles partagés, menu) | ~40 lignes de style, 1 gabarit | Faible | Une (longueur des titres) |
| 2 | Pages à reprendre une par une | ~12 gabarits, 1 vue | Faible | Non |
| 3 | Mobile, accessibilité, finitions Communication | ~40 lignes de style, 3 gabarits | Faible | Non |
| 4 | Évolutions d'apparence | 3 à 4 écrans | Moyen | Oui, pour chaque point |
| 5 | Outillage et audit complémentaire | Scripts de contrôle, doc | Nul pour le site | Non |

---

## Lot 0 — Retirer un effet de bord introduit le 5 octobre

Une règle de style ajoutée pour la page Communication n'est pas limitée à cette page. Elle
s'applique à toutes les pages privées et supprime l'espace sous les notes d'introduction des
cartes : le texte se retrouve collé au contenu qui suit (Créer un vote, Messages de contact,
Suivi de participation). Elle est en production depuis le déploiement du 5 octobre.

- [x] `static/css/prive.css` : limiter `.prive-dense .app-shell .workspace-panel > .app-note` aux
      écrans Communication (préfixe `.communication-layout`).

Vérification : l'espace de 8 px revient sous les notes des trois pages citées.

---

## Lot 1 — Corrections globales

Un correctif par cause : chaque ligne répare toutes les pages concernées d'un coup.

### 1.1 Boutons au style « navigateur par défaut »

Le site ne remet pas à zéro l'apparence des boutons ; cinq composants oublient de le faire et
gardent un fond gris et une bordure en relief.

- Touchés : calendrier (événements de la grille `.cal-chip`, liste « À venir » `.cal-aside__link`,
  « Synchroniser » `.cal-icon-btn`, croix des fenêtres `.cal-dialog__close`), onglets des votes
  `.vote-tabs__btn`, croix des messages `.alert__dismiss` (même cause, non vue à l'écran).
- [x] `static/css/lions.css` (règle `button`, ligne 185) : ajouter `background: none; border: 0;`.
      Les boutons stylés (`.btn`, pagination, menu) définissent déjà leur fond et leur bordure.
- Vérification : détecteur « bouton à l'apparence navigateur » à 0 ; calendrier clair et sombre,
  votes ; aucun changement sur les boutons `.btn`.

### 1.2 Menu latéral

- [x] `templates/components/private/nav_icon.html` : ajouter une icône pour « Communication » et
      pour « Contenu public ».
- [x] Même fichier : corriger le tracé de la cloche « Notifications »
      (`…H4s2-1a6 6 0 0 0 2-6Z` → `…H4s2-1 2-6Z`).
- [x] Même fichier : prévoir une icône par défaut, pour qu'une future entrée ne soit jamais nue.
- Vérification : 0 entrée sans icône ; 0 erreur console (272 pages concernées aujourd'hui).

### 1.3 Champs de recherche à loupe

Le retrait prévu pour la loupe est écrasé par une règle plus forte ; le texte commence sous
l'icône. Pages : Documents, Gestion des documents, Votes.

- [x] `static/css/prive.css` (lignes 864-866) : préfixer les règles `.icon-search input` et
      `.vote-search input` par `.prive-dense`.
- [x] Même fichier : espace au-dessus de `.doc-search-row` (le champ touche la ligne de filtres).
- Vérification : 0 « icône sur le texte d'un champ » ; 0 « contrôles collés » sur Documents.

### 1.4 Badges étirés

- Touchés : annuaire (rôle), en-tête du profil, carte Cotisation du tableau de bord.
- [x] `static/css/lions.css` (`.badge`) : `width: fit-content; max-width: 100%;`.
- Vérification : les trois pages ; badges inchangés dans les tableaux et les en-têtes de carte.

### 1.5 Traits de séparation coupés ou orphelins

Les notes de bas de bloc (`.app-note`) portent un trait au-dessus, coupé à 62 caractères par la
règle générale des paragraphes ; utilisées en tête de carte, elles dessinent un trait sans rien
au-dessus.

- Touchés : tableau de bord (Votes ouverts, Documents récents, Satisfaction), Créer un vote,
  Messages de contact et Candidatures, Suivi de participation, Feuille de présence, Gestion de
  la satisfaction, formulaire d'action, « Autres votes ».
- [x] `static/css/prive.css` : `.app-note` en pleine largeur dans tout l'espace privé.
- [x] Même fichier : une note placée en premier dans une carte n'a ni trait ni retrait au-dessus.
- Vérification : les dix pages citées.

### 1.6 Titres de page

- [x] `static/css/prive.css` (ligne 13) : porter la largeur maximale des titres privés de 13 à
      28 caractères. Une trentaine de titres ne seront plus coupés (« Traiter une / demande »).
      **Décision D1.**
- [x] `static/css/lions.css` (ligne 2220) : retirer la règle qui met le titre en Inter sur 15
      pages (Contenu public, Candidatures, Messages de contact). Tous les titres en Playfair.
- Vérification : rapport des titres — une seule police, plus de coupure hors titres très longs.

### 1.7 Textes d'exemple trop pâles

- [x] `static/css/lions.css` (ligne 1014) : retirer `opacity: .85` de `.champ__input::placeholder`
      (3,94:1 → 5,4:1). Vaut aussi pour les pages publiques Contact et Candidature.
- Vérification : 0 constat de contraste sur les placeholders.

---

## Lot 2 — Pages à reprendre

### 2.1 Détail d'une demande (contact et candidature)

- [x] `templates/espace/request_detail.html` : informations en liste libellé / valeur
      (`.paire-liste`), champ « État du suivi » dans un bloc `.champ`, bouton dans `.lot2-actions`.
- Vérification : plus de contrôles collés ; ordinateur et mobile.

### 2.2 Liens qui ressemblent à du texte

- [x] `templates/espace/profile.html` : « Changement d'email », « Mot de passe », « Gérer mon
      parcours » avec les classes de lien déjà utilisées dans l'annuaire (`btn btn--ghost btn--sm`).
- [x] `templates/espace/dues_management.html` : idem pour « Historique des corrections ».
- [x] `static/css/prive.css` (ligne 198) : couleur de lien pour les liens des tableaux (noms dans
      Candidatures et Messages de contact). Contrôler les autres tableaux du site.

### 2.3 Tableau de bord

- [x] `templates/components/private/dashboard_club_life.html` : n'afficher « Voir le calendrier »
      qu'aux profils autorisés (un invité arrive aujourd'hui sur une page interdite).
- [x] Carte Notifications : ne plus l'étirer à la hauteur de l'agenda (60 % de vide).
- Vérification : tableau de bord des 7 profils connectés ; 0 lien en erreur.

### 2.4 Statistiques

- [x] `apps/governance/views.py` (vue `statistics`) et `templates/espace/statistics.html` :
      afficher le libellé de la catégorie (« District », « Général ») au lieu du code.
- [x] Test ciblé sur la vue.

### 2.5 Gestion d'un document

- [x] `templates/espace/document_manage_detail.html` : « Danger zone » → « Zone de danger » ;
      espace sous les sous-titres « Accès actuels » et « Accorder un accès ».

### 2.6 Suivi de participation d'un vote

- [x] Espace entre « Clôturer le scrutin » et le tableau (à revérifier après les lots 0 et 1.5).

### 2.7 Hiérarchie des titres

- [x] `templates/espace/documents.html`, `templates/components/private/vote_card.html` : titres
      de carte en `h2` (aujourd'hui `h1` puis `h3`). Reprendre les styles qui visent `h3`.

### 2.8 Glyphes et action destructive

- [x] Remplacer les flèches « ← » tapées au clavier par l'icône dessinée (5 gabarits :
      `management_detail`, `mandate_form`, `management_member_add`, `mandates`, `action_form`).
- [x] Remplacer le « + » de « Ajouter un choix » et de « Nouvel événement » par l'icône dessinée
      (`vote_creation`, `calendrier`).
- [x] `templates/espace/mandates.html` : « Supprimer » un mandat en style d'action destructive.

### 2.9 Feuille de présence (minimum)

- [x] `templates/espace/presence_sheet.html` : étiquette pour le champ « Motif ».

Vérification du lot : tests ciblés des applications touchées (members, governance, documents,
voting, agenda, communications), puis parcours complet.

---

## Lot 3 — Mobile, accessibilité, finitions Communication

### 3.1 Zones trop petites pour le doigt (mobile)

- [x] `static/css/prive.css` : 44 px minimum pour les flèches (32 px) et les vues (33 px) du
      calendrier, les onglets de vote (37 px), les liens « Retour à… » (16 à 22 px) et les
      sélecteurs de fichier (13 px).
- Vérification : 0 cible sous 44 px sur mobile, hors liens dans un paragraphe.

### 3.2 Communication

- [x] Liste des membres entre 1081 et 1250 px : rôle affiché sous l'adresse, comme sur mobile.
- [x] Résumé collant du suivi (626 px) : non collant quand la fenêtre fait moins de 760 px de haut.
- [x] Pastilles d'étapes dimensionnées en proportion du texte (texte agrandi à 200 %).
- [x] Marge du bloc « Version texte » ramenée à l'échelle de la charte.

### 3.3 Contrastes restants

- [x] Contour des champs sur fond teinté (formulaires de Contenu public) : 2,92:1 → 3:1 minimum.
- [x] Mois des pastilles de date du tableau de bord en thème sombre : 4,1:1 → 4,5:1 minimum.

Vérification du lot : parcours complet, mobile et sombre.

---

## Lot 4 — Évolutions d'apparence (après décision)

| # | Évolution | Pourquoi | Décision |
|---|---|---|---|
| 4.1 | Anneau de focus clavier renforcé en thème clair | L'anneau doré fait 1,4 à 1,6:1 sur fond clair | D2 |
| 4.2 | Feuille de présence compacte (une ligne par membre) | Environ 5 800 px pour 24 membres aujourd'hui | D3 |
| 4.3 | Historique des communications plus compact | 20 campagnes ≈ 4 800 px sur ordinateur | D4 |
| 4.4 | Carte Notifications : afficher les 3 dernières | La carte ne montre qu'un compteur | D5 |

---

## Lot 5 — Outillage et audit complémentaire

- [x] Verser dans le dépôt l'outil de parcours utilisé pour l'audit, en contrôle optionnel comme
      les contrôles navigateur existants, pour rejouer les mesures après chaque lot.
- [x] Corriger deux anciens scripts de contrôle : étape sans JavaScript instable
      (`tools/browser_members.cjs`, `tools/browser_public.cjs`) et page supprimée encore visitée
      (`/espace/pilotage/`).
- [x] Auditer ce que le parcours n'a pas couvert : messages d'erreur (14 formulaires) et de succès,
      fenêtres du calendrier ouvertes, réinitialisation de mot de passe par lien, vues Semaine et
      Jour du calendrier, étape de vérification de la double authentification.
- [x] `docs/DEPLOY_REBUILD.md` : chemins et nom de service réels, rappel sur `collectstatic`.

---

## Décisions à prendre

| # | Question | Recommandation |
|---|---|---|
| D1 | Titres des pages privées : passer de 13 à 28 caractères par ligne ? | Oui — appliqué |
| D2 | Renforcer l'anneau de focus en thème clair (la charte fixe « or, 3 px ») ? | Oui, or + liseré foncé — appliqué |
| D3 | Refaire la feuille de présence en tableau compact ? | Oui — appliqué |
| D4 | Compacter l'historique des communications ? | Oui — appliqué |
| D5 | Afficher les 3 dernières notifications sur le tableau de bord ? | Oui — appliqué |

Les cinq recommandations ont été appliquées telles quelles le 6 octobre ; chacune peut être annulée
séparément. Hors affichage, reste à trancher : 14 des 28 membres proposés dans Communication en production
sont des comptes « Test … » ; « Tout sélectionner » leur écrit.

---

## Vérification de chaque lot

1. `python manage.py check`.
2. Tests ciblés des applications dont un gabarit ou une vue change.
3. Parcours complet du site (87 pages, 8 profils, ordinateur et mobile, clair et sombre) : les
   compteurs du lot doivent être à zéro et aucun nouveau constat ne doit apparaître.
4. Relecture des captures des pages touchées.

## Mise en ligne de chaque lot

Sur le serveur, depuis `/var/www/lionsmed/rebuild`, après avoir récupéré le code :

```bash
python manage.py collectstatic --noinput --settings=config.settings.production
```

```bash
sudo systemctl restart lionsmed
```

Sans `--settings=config.settings.production`, les fichiers de style ne sont pas régénérés et le
site garde l'ancien affichage (cas rencontré le 5 octobre).

## Suivi

| Lot | État | Date |
|---|---|---|
| 0 | Fait, vérifié | 6 octobre 2026 |
| 1 | Fait, vérifié | 6 octobre 2026 |
| 2 | Fait, vérifié | 6 octobre 2026 |
| 3 | Fait, vérifié | 6 octobre 2026 |
| 4 | Fait, vérifié (D1 à D5 = recommandations) | 6 octobre 2026 |
| 5 | Fait, vérifié | 6 octobre 2026 |

Mise en ligne : **à faire** (après commit).

## Résultat (6 octobre 2026)

Parcours complet après corrections : 506 visites, 89 pages, 8 profils, **0 constat bloquant**.
Avant corrections, sur les mêmes pages : 272 pages avec une erreur console, 2 entrées de menu sans
icône, 5 composants au style navigateur par défaut, 15 constats de contraste de texte, 4 sauts de
niveau de titre, 2 champs de recherche à icône chevauchante, 15 pages avec une autre police de titre.

Tests : suite Django complète, 600 exécutés, 593 verts, 7 ignorés (les six contrôles navigateur
optionnels et un test de lecture de QR code dont la bibliothèque est absente du poste). Les six
contrôles navigateur, lancés à part, passent tous.

### Corrigé en plus du plan

- Fenêtre « Nouvel événement » du calendrier : quatre champs de 88 px côte à côte, repassés sur
  deux colonnes (trouvé par l'audit complémentaire du lot 5).
- Cases à cocher des formulaires privés : à gauche de leur libellé au lieu d'être étirées seules
  sur une ligne (formulaires de Contenu public).
- Liens « Annuler » et « Retour » des rangées d'actions : couleur de lien.
- Détail d'une candidature : libellé de l'origine au lieu de son code.
- Compteur des onglets de vote (3,13:1) et contour des champs sur fond teinté (2,92:1) : au seuil.
- Calendrier : période affichée en français (« October 2026 », « Tuesday 06 October 2026 »
  auparavant) et majuscule seulement en début de date (« Mardi 6 octobre »).
- Statistiques : cartes à la hauteur de leur contenu.
- Mobile : titres cliquables des cartes et des listes, croix des messages, fil d'Ariane des pages
  publiques à 44 px.

### Écarts par rapport au plan

- 2.9 (étiquette du champ « Motif ») est traité dans 4.2 : chaque champ de la nouvelle feuille de
  présence a son étiquette.
- 2.3 (carte Notifications étirée) est traité par 4.4 et par l'alignement des cartes en haut.

### Reste connu, non corrigé

- Calendrier, vue Semaine : deux événements simultanés se partagent une colonne étroite, leurs titres
  sont réduits à quelques lettres (le titre complet est dans la liste « À venir » et dans la fenêtre
  de l'événement). Titres des pastilles tronqués dans la grille du mois : voulu.
- Cases à cocher isolées : 24 px, leur libellé voisin est cliquable.
- Site public : liens à l'intérieur d'un texte ou d'une liste (16 à 21 px de haut sur mobile).
- Données, hors affichage : comptes « Test … » proposés dans la liste des membres en production.

Vérifié puis écarté : l'espacement signalé dans la gestion des cotisations sur mobile concernait un
bloc replié, donc invisible ; ce n'était pas un défaut.

## Parcours « créer une action et la publier » (6 octobre 2026)

Audit du parcours complet dans le navigateur, avec de vraies images, puis correction le même jour.

### Défauts sérieux — corrigés

- [x] Images cassées dans l'espace de gestion tant que l'action est en brouillon (page de
  modification et carte de la liste) : aperçu privé réservé aux gestionnaires de contenu.
- [x] Page publique : au-delà de cinq photos, les suivantes s'affichaient sous la mosaïque alors que la
  cinquième annonçait « +N ». Elles ne s'ouvrent plus que dans la visionneuse.
- [x] Photo de plus de 5 Mo : page brute « Bad Request (400) ». Avertissement dans le formulaire avant
  l'envoi ; sans JavaScript, page lisible « Fichier trop lourd » avec retour au formulaire.
- [x] « Publier » refusé à la création : un brouillon caché était créé et le second essai répondait
  « Ce slug est déjà utilisé ». On arrive maintenant sur l'action enregistrée, avec la raison du refus.
- [x] Retirer une image d'une action publiée la repassait en brouillon sans rien dire (page publique
  introuvable). L'action reste publiée et un message le confirme.
- [x] « Supprimer » sans confirmation : case à cocher obligatoire, vérifiée aussi côté serveur.
- [x] Trouvé pendant la vérification : « Remettre en brouillon » provoquait une erreur serveur.

### Finitions — corrigées

- [x] Encadré d'erreurs sur toute la largeur (tous les formulaires privés à deux colonnes).
- [x] Aperçu des images choisies (vignette, nom, poids) et rubrique « Images » réagencée.
- [x] Zone « Récit » plus haute (280 px).
- [x] Titres « Nouvelle action » et « Modifier l'action », état de publication en tête de page, lien
  « Voir la page publique », pastilles d'état colorées, messages qui disent ce qui s'est passé.
- [x] Page publique : titre d'action sur deux lignes au lieu de quatre, « Avec nos partenaires » aéré.
- [x] Liste vide : un seul bouton de création.

### Reste à décider ou à vérifier

- Documents : le formulaire annonce 50 Mo, mais tout fichier de plus de 5 Mo est refusé à l'envoi (le
  filtre prévu pour les photos s'applique à tous les fichiers).
- [x] Serveur : la limite d'envoi de Nginx pour lionsmed était de 20 Mo (quatre ou cinq photos de
  téléphone par enregistrement). Passée à 60 Mo le 6 octobre 2026, pour lionsmed uniquement.
