# IMAGES — Page d'accueil Lions Club Sfax-Méditerranée

> Manifeste des emplacements photographiques de `accueil.html`.
> Chaque emplacement porte déjà son **nom de fichier définitif**.
> **Déposer un fichier au bon nom suffit à l'activer. Aucune ligne de code à modifier.**

---

## Chiffres clés

| | |
|---|---|
| **Emplacements photographiques** | **13** — 12 dans la page + 1 image de partage |
| **Servis par une photo réelle du club** | **9** |
| **En attente d'une image** | **4** — les quatre cartes d'axes |
| **Fichiers `tmp-` réellement déposés** | **0** |
| **Fichiers déposés / attendus** | **19 / 27** |

Les quatre cartes d'axes affichent le **repère technique** décrit plus bas, et non une
photo. C'est délibéré : aucune des neuf photographies disponibles ne documente le
diabète, l'environnement ou la jeunesse de façon vérifiable. Y placer une photo du club
affirmerait un rattachement que le bureau n'a jamais confirmé.

---

## Procédure de dépôt

1. Recadrer au ratio demandé. **Ne jamais agrandir** au-delà de la résolution native.
2. Exporter en **WebP**, qualité 82.
3. Nommer strictement `<emplacement>-<largeur>.webp` — minuscules, sans accent, tirets.
4. Déposer dans `mockups/assets/images/`.
5. Recharger : le repère technique disparaît de lui-même.
6. **Recopier la colonne `alt`** de ce tableau dans la balise correspondante, et
   supprimer le commentaire `<!-- ALT À RÉÉCRIRE APRÈS DÉPÔT DE LA PHOTO -->`.

La colonne `alt` se remplit **au moment où la photo est choisie**, pas au dépôt. Le dépôt
devient alors mécanique : copier le fichier, recopier le texte alternatif.

### Budget de poids

| Variante | Visé | Plafond |
|---|---|---|
| `-240` / `-480` | ≤ 25 Ko | 40 Ko |
| `-640` | ≤ 70 Ko | 90 Ko |
| `-1100` | ≤ 150 Ko | 190 Ko |
| `-1600` | ≤ 270 Ko | 330 Ko |

---

## Tableau des emplacements

Dans l'ordre d'apparition.

### 1 — Hero ✅ servi

| | |
|---|---|
| **Nom de base** | `hero-principal` |
| **Variantes** | `-640` `-1100` `-1600` |
| **Ratio** | **16/9** pour `-1100` et `-1600` · **4/3** pour `-640` (recadrage mobile distinct, servi par `<source media>`) |
| **Dimensions minimales** | `1600×900` · `1100×619` · `640×480` |
| **Cadrage** | Le tiers gauche est recouvert d'un aplat navy opaque : **aucun visage à gauche**, sujet dans la moitié droite. De l'air en haut et en bas, la bande est rognée entre 500 et 640 px. |
| **`alt`** | Membres du Lions Club Sfax-Méditerranée réunis en extérieur, en gilets jaunes, autour de la bannière du club. |
| **Priorité** | Haute |
| **Photo en place** | `club-exterieur-original.jpg` — groupe extérieur, bannière « Lions Sfax Med », certificats |

### 2 à 5 — Cartes des 4 axes ⛔ en attente

Quatre cartes sur une même rangée. Les quatre photos doivent **se répondre** : même
température de lumière, même distance au sujet. Sinon la rangée se désagrège.

| | |
|---|---|
| **Variantes** | `-640` `-1100` |
| **Ratio** | **16/10** |
| **Dimensions minimales** | `1100×688` |
| **Cadrage commun** | Plan moyen horizontal. **Une pastille ronde de 52 px déborde sur le bas-gauche** : laisser cette zone libre de visage. Photo pas trop sombre. |
| **Priorité** | **Haute** — c'est le bloc qui porte la démonstration de la page |

| # | Nom de base | Sujet attendu | `alt` à rédiger |
|---|---|---|---|
| 2 | `tmp-axe-diabete` | Dépistage ou sensibilisation au diabète : table de dépistage, glucomètre, prise de tension, échange avec un soignant. | *(à rédiger au choix de la photo)* |
| 3 | `tmp-axe-environnement` | Plantation d'arbres, nettoyage de plage ou d'espace public, distribution de plants. Extérieur, lumière du jour. | *(à rédiger)* |
| 4 | `tmp-axe-humanitaire` | Remise de dons ou d'équipement : cartons, matériel médical, colis alimentaires. | *(à rédiger)* |
| 5 | `tmp-axe-jeunesse` | Action auprès de jeunes : atelier scolaire, remise de fournitures, Leo Club. | *(à rédiger)* |

### 6 à 8 — Cartes événements ✅ servies

| | |
|---|---|
| **Variantes** | `-640` `-1100` · **Ratio** 16/10 · **Minimum** `1100×688` |
| **Cadrage commun** | **Un badge date navy occupe le coin haut-gauche** : zone à laisser libre. Photo plutôt lumineuse, le badge est sombre. |
| **Priorité** | Moyenne |

| # | Nom de base | `alt` en place | Photo en place |
|---|---|---|---|
| 6 | `evenement-1` | Membres du club réunis autour d'une table lors d'une soirée en salle de réception. | `club-tablee-original.jpg` |
| 7 | `evenement-2` | Membres du club en gilets jaunes sur la plage, le soir, avec la bannière Lions Sfax Med. | `club-plage-original.jpg` |
| 8 | `evenement-3` | Groupe en blouses blanches et gilets Lions réuni en salle de réunion autour de matériel médical. | `club-remise-materiel-original.jpg` |

### 9 à 11 — Vignettes actualités ✅ servies

Vignettes carrées de **112 px** de côté (84 px sous 520 px). Un plan large y devient
illisible : **cadrage serré obligatoire**.

| | |
|---|---|
| **Variantes** | `-240` `-480` · **Ratio** 1/1 · **Minimum** `480×480` |
| **Cadrage commun** | Plan rapproché, **un seul sujet lisible**, parfaitement centré, contraste élevé. |
| **Priorité** | Basse |

| # | Nom de base | `alt` en place | Photo en place |
|---|---|---|---|
| 9 | `actualite-1` | Matériel médical présenté sur une table lors d'une remise d'équipement. | `club-rencontre-original.jpg` |
| 10 | `actualite-2` | Six personnes en casaques et charlottes chirurgicales devant un écran médical. | `club-bloc-medical-original.jpg` |
| 11 | `actualite-3` | Membres du club réunis autour d'une table le soir, sous une pergola. | `club-soiree-original.jpg` |

### 12 — Bloc « Nous rejoindre » ✅ servi

| | |
|---|---|
| **Nom de base** | `rejoindre` · **Variantes** `-640` `-1100` `-1600` · **Ratio** 3/2 · **Minimum** `1600×1067` |
| **Cadrage** | Affiché dans une **arche** (`220px 220px 3px 3px`), rapport 3/4 à l'écran : le sujet doit tenir dans la moitié haute. Le bord droit se fond dans le navy : rien de signifiant dans les 25 % de droite. |
| **`alt`** | Huit membres du club en gilets Lions, souriants, réunis en extérieur devant des cartons de dons. |
| **Priorité** | Haute |
| **Photo en place** | `club-distribution-original.jpg` |

### 13 — Image de partage ✅ servie

| | |
|---|---|
| **Nom de base** | `og-accueil.jpg` — **JPEG**, pas WebP (compatibilité des robots sociaux) |
| **Dimensions** | **1200×630 exactement** (ratio 1.91/1) |
| **Cadrage** | Sujet centré, marge de sécurité de 60 px sur les quatre bords : les plateformes rognent différemment. La bannière du club doit rester lisible. |
| **Priorité** | Moyenne |
| **Photo en place** | `club-exterieur-original.jpg`, recadrée pour garder la bannière dans le cadre |

---

## Annexe technique

Attributs déjà écrits dans `accueil.html`. Pour vérification à l'intégration.

| Emplacement | `sizes` | Chargement |
|---|---|---|
| `hero-principal` | `100vw` | `fetchpriority="high"`, `<source media="(max-width:760px)">` vers `-640` |
| `tmp-axe-*` | `(max-width:520px) 100vw, (max-width:1080px) 50vw, 282px` | `lazy` |
| `evenement-*` | `(max-width:760px) 100vw, (max-width:1080px) 50vw, 210px` | `lazy` |
| `actualite-*` | `(max-width:520px) 84px, 112px` | `lazy` |
| `rejoindre` | `(max-width:1080px) 100vw, 38vw` | `lazy` |

Chaque `<img>` porte `width` et `height` en dur, et son conteneur `.media` porte le ratio
en CSS : **la hauteur est réservée avant le chargement, aucun décalage de mise en page à
l'arrivée des images.**

---

## Repère d'emplacement vide

Tant qu'un fichier manque, le conteneur `.media` affiche un repère **technique** :

- fond `#EDF1F7` uni, bordure intérieure pointillée `1px` en `#C3D0E2` ;
- au centre, Inter 12 px en `#8494AC` : `nom-de-base · ratio · min L×H`.

Ni dégradé, ni couleur de charte, ni icône, ni emblème : il doit se lire « emplacement à
remplir », jamais comme un parti pris graphique.

**Mécanique** — le texte vient de l'attribut `data-attendu` du conteneur, rendu par
`::after`. Le style ne s'active que si la classe `.media--vide` est posée, ce que fait le
gestionnaire `onerror` de `accueil.js`. Fichier déposé → l'image charge → aucune erreur →
classe jamais posée : **le repère ne coûte rien une fois les photos en place.**

> Le contraste du repère (2,6:1) est sous le seuil AA. C'est assumé : ce n'est pas du
> contenu, c'est un échafaudage de développement qui disparaît en production, et les
> couleurs sont imposées par le cahier des charges.

---

## Images temporaires en place

**Aucune. 0 fichier `tmp-`.**

Les quatre emplacements d'axes **référencent** leurs noms `tmp-` définitifs
(`tmp-axe-diabete-640.webp`, `-1100`, et de même pour les trois autres — 8 fichiers), mais
**aucun fichier n'a été produit** : cet environnement ne dispose d'aucun outil de
génération d'images, et le téléchargement depuis Internet est exclu par le cadre de
travail. Les quatre cartes affichent donc le repère technique.

Le câblage est complet. Déposer les 8 fichiers suffit à activer les quatre cartes,
**sans toucher au code** — hormis les quatre `alt`, signalés par
`<!-- ALT À RÉÉCRIRE APRÈS DÉPÔT DE LA PHOTO -->`.

### Consignes de génération — bloc de style commun

**À reproduire mot pour mot en tête de chacune des quatre consignes ci-dessous.**

> Photographie documentaire, format horizontal 16/10, lumière naturelle de jour,
> Méditerranée, couleurs sobres et légèrement désaturées, profondeur de champ modérée.
> Cadrage plan moyen, sujet centré ou légèrement à droite, **coin bas-gauche dégagé**.
> **Aucun visage reconnaissable de face** : privilégier les gros plans, les mains, les
> objets, les silhouettes, les plans de dos, les cadrages larges sans identité lisible.
> Aucun logo, aucun texte, aucune marque, aucune blouse blanche.
> Pas de mise en scène qui pourrait se lire comme une action documentée d'un club réel.
> Aucun visage ne doit pouvoir être présenté comme celui d'un membre ou d'un bénéficiaire.

| Fichier | Consigne, à la suite du bloc commun |
|---|---|
| `tmp-axe-diabete` | *…Sur une table, un lecteur de glycémie, une bandelette et un brassard de tension. Deux mains adultes, de trois quarts, manipulent l'appareil. Arrière-plan neutre et flou.* |
| `tmp-axe-environnement` | *…Des mains gantées déposent un jeune plant dans une terre sableuse. Au second plan flou, des pots et un arrosoir. Littoral méditerranéen suggéré, sans horizon reconnaissable.* |
| `tmp-axe-humanitaire` | *…Une pile de cartons de dons fermés, de trois quarts, dans une lumière rasante. Une silhouette de dos, floue, en soulève un. Aucun visage.* |
| `tmp-axe-jeunesse` | *…Une table d'écolier vue de dessus : cahiers, crayons, cartable ouvert. Des mains d'enfant écrivent. Le cadre s'arrête aux poignets, aucun visage.* |

Toute image générée doit être précédée dans le HTML de
`<!-- IMAGE GÉNÉRÉE — MAQUETTE UNIQUEMENT — À REMPLACER AVANT MISE EN LIGNE -->`
— ce commentaire est **déjà en place** sur les quatre cartes.

---

## À vérifier avant intégration Django

Ces deux commandes doivent **toutes deux renvoyer `0`**. Tant que ce n'est pas le cas, la
page n'est pas prête pour la production.

```sh
grep -c "ALT À RÉÉCRIRE" mockups/accueil.html   # → doit renvoyer 0
grep -c "tmp-"           mockups/accueil.html   # → doit renvoyer 0
```

Compléter par :

```sh
grep -c "noindex"        mockups/accueil.html   # → doit renvoyer 0 à la mise en ligne
ls mockups/assets/images/tmp-*                  # → aucun fichier ne doit subsister
```

**État à ce jour :**

| Commande | Résultat | Attendu en production |
|---|---|---|
| `grep -c "ALT À RÉÉCRIRE"` | **4** — un par carte d'axe | 0 |
| `grep -c "tmp-"` | **16** — par axe : 1 `data-attendu`, 1 `src`, 2 entrées `srcset` | 0 |
| `grep -c "noindex"` | **1** — volontaire, maquette de validation | 0 |
| `ls assets/images/tmp-*` | aucun fichier | aucun fichier |

---

## Photos réelles à demander au club

*Section rédigée pour être transmise telle quelle au bureau.*

Bonjour,

Les neuf photographies que vous nous avez transmises sont en place sur la nouvelle page
d'accueil : la photo d'ouverture, les trois événements, les trois actualités et le bloc
d'adhésion. Merci.

Il nous manque **quatre photographies**, et ce sont les plus visibles de la page : celles
des quatre axes prioritaires. En attendant, ces quatre emplacements affichent un cadre
gris de repérage.

### Les quatre photos manquantes

Une par axe. Elles doivent se ressembler : même type de lumière, même distance au sujet.

1. **Diabète** — une action de dépistage : table de dépistage, glucomètre, prise de
   tension, échange avec un professionnel de santé.
2. **Environnement** — une plantation d'arbres, un nettoyage de plage, une distribution
   de plants. En extérieur, de jour.
3. **Humanitaire** — une remise de dons ou d'équipement : cartons, matériel médical,
   colis alimentaires.
4. **Jeunesse** — une action auprès de jeunes : atelier scolaire, remise de fournitures,
   Leo Club.

**Format** : photo **horizontale**, au moins **1100 pixels de large**. Cadrage moyen,
plusieurs personnes, gilets Lions visibles. **Laisser le coin bas-gauche dégagé** : un
pictogramme rond s'y superpose.

### Trois améliorations possibles

- **Vignettes d'actualités** : elles s'affichent en **petit carré de 112 pixels**. À cette
  taille, on doit voir **un visage ou un objet**, pas une salle entière. Si vous avez des
  **plans serrés** — un portrait, deux mains qui échangent quelque chose, un détail
  d'action — ils remplaceraient avantageusement les recadrages actuels.
- **Photo d'ouverture** : la photo de groupe extérieure convient très bien. Si vous en
  avez une version **plus large que 1600 pixels**, elle serait bienvenue.
- **Photos d'événements** : les trois photos utilisées sont des scènes de vie du club.
  Dès que vous aurez des photos correspondant aux **événements réellement programmés**,
  elles les remplaceront.

### Consignes générales

- **Fichiers d'origine**, non compressés par WhatsApp ou Messenger — la compression
  détruit la qualité de façon irréversible.
- Photos **horizontales**, sauf les vignettes d'actualités.
- Privilégier la **lumière du jour** et les visages nets.
- **Droit à l'image** : s'assurer que chaque personne reconnaissable accepte la
  publication sur le site. Cette vérification n'a pas été faite pour les neuf photos
  déjà en place.

Merci.

---

## Assets de marque — déjà en place

Aucun à fournir.

| Fichier | Dimensions | Usage |
|---|---|---|
| `emblem-256.png` | 256×243 | Emblème de la barre de navigation (42 px), du pied de page, filigrane du bandeau chiffres, favicon |
| `emblem.png` | 583×553 | Réserve haute définition |
| `logomed.png` | 1006×557 | Logo complet, réserve |
| `logomed-nav.png` | 420×233 | Logo complet, utilisé par les autres pages |

Le filigrane du bandeau chiffres est obtenu par filtre CSS
(`brightness(0) invert(1)` + `opacity: .17`) : **aucun fichier blanc à produire.**

---

## Photothèque source

`mockups/assets/sources/` conserve les **neuf originaux** en pleine résolution, avec un
`README.md` documentant l'inventaire, les recadrages appliqués et — point important —
**trois fichiers portant une orientation EXIF non appliquée**, qui produisent une image
retournée si on les traite sans `-auto-orient`.

Ne pas modifier ces fichiers : tout ce que sert la page en dérive.

---

## Récapitulatif des fichiers

| Nom de base | Fichiers attendus | État |
|---|---|---|
| `hero-principal` | `-640` `-1100` `-1600` | ✅ 3/3 |
| `tmp-axe-diabete` | `-640` `-1100` | ⛔ 0/2 |
| `tmp-axe-environnement` | `-640` `-1100` | ⛔ 0/2 |
| `tmp-axe-humanitaire` | `-640` `-1100` | ⛔ 0/2 |
| `tmp-axe-jeunesse` | `-640` `-1100` | ⛔ 0/2 |
| `evenement-1` | `-640` `-1100` | ✅ 2/2 |
| `evenement-2` | `-640` `-1100` | ✅ 2/2 |
| `evenement-3` | `-640` `-1100` | ✅ 2/2 |
| `actualite-1` | `-240` `-480` | ✅ 2/2 |
| `actualite-2` | `-240` `-480` | ✅ 2/2 |
| `actualite-3` | `-240` `-480` | ✅ 2/2 |
| `rejoindre` | `-640` `-1100` `-1600` | ✅ 3/3 |
| `og-accueil` | `og-accueil.jpg` 1200×630 | ✅ 1/1 |

**19 fichiers déposés sur 27.** Les 8 manquants correspondent aux 4 cartes d'axes.
