---
name: lionsmed-design
description: Système de design et règles de production des maquettes du site Lions Club Sfax-Méditerranée (dossier /mockups/). À charger avant de créer ou modifier une page, une feuille de style ou un composant de la maquette — palette, typographie, signature graphique, navigation partagée, règles de contenu, images, accessibilité et checklist de livraison.
---

# Lions Club Sfax-Méditerranée — système de design

Référence unique pour toute page de `/mockups/`. Ce qui figure ici est **validé** et ne
se rediscute pas à chaque page.

---

## 0. Cadre non négociable

**Lions Club Sfax-Méditerranée** — Sfax, Tunisie, District 414 Tunisie. Membre de Lions Clubs
International. Devise : « Nous servons ». Domaine : `lionsmed.tn`.
Le nom institutionnel complet est employé dans tous les textes, titres, SEO et JSON-LD.
Le logo conserve son wording propre (« Lions Sfax Med »).

- On travaille **uniquement** dans `/mockups/`.
- **Aucun fichier Django** n'est modifié : ni `models.py`, `views.py`, `urls.py`,
  `settings.py`, ni template, migration ou base de données. La base `db.sqlite3` peut
  être **lue** pour récupérer les contenus officiels, jamais écrite.
- **Aucun commit, aucun push.**
- **Aucune dépendance externe** : pas de Tailwind, Bootstrap, framework JS ni librairie
  d'animation. CSS écrit à la main, JavaScript vanilla.
- **Aucune image téléchargée depuis Internet.**
- Aucun CSS ni JS en ligne dans le HTML, **sauf le JSON-LD**.
- `assets/css/lions.css` porte les **jetons et tous les composants partagés**. Une
  feuille de page ne contient que le strictement spécifique et ne redéfinit **aucune
  variable**.
- `assets/js/lions.js` porte les **comportements partagés** — menu mobile, sous-menu,
  révélation au scroll, compteurs, retour en haut, année courante, blocage des
  formulaires de maquette, bascule d'affichage du mot de passe, repère d'emplacement
  d'image manquante. Un fichier JS de page ne contient que le spécifique et **ne duplique
  jamais** `lions.js`.
- Un composant susceptible de servir à une seconde page va dans `lions.css`, jamais dans
  une feuille de page.

---

## 1. Jetons

Tous portés par `assets/css/lions.css`. **Une feuille de page ne redéfinit jamais une
variable** — elle consomme.

### Palette — verrouillée

```css
--navy:       #0E2E5E   /* bandeaux sombres, hero */
--navy-fonce: #0A2349   /* pied de page */
--bleu:       #184898   /* bleu Lions officiel — boutons, liens */
--or:         #F8C800   /* jaune Lions officiel — accents, CTA */
--encre:      #12294D   /* texte principal */
--gris:       #5A6B85   /* texte secondaire */
--gris-clair: #8494AC   /* métadonnées décoratives uniquement — voir §10 */
--fond:       #F6F9FD   /* fond de section clair */
--fond-2:     #E9F1FA   /* fond de bande secondaire */
--bord:       #E1E9F4   /* bordures de cartes */
```

Le jaune est un **accent**, jamais une couleur de fond large.

### Typographie

- **Playfair Display 600** : `h1`, `h2`, grands nombres, titres d'actualités.
- **Inter 400/500/600/700** : tout le reste.
- Chargement Google Fonts avec `preconnect` et `display=swap`.

```css
--t-display: clamp(2.75rem, 6vw, 5rem);
--t-h2:      clamp(2rem, 3.6vw, 3.25rem);
--t-h3:      1.3125rem;
--t-lede:    clamp(1.05rem, 1.4vw, 1.35rem);
--t-body:    1.0625rem;
--t-meta:    0.8125rem;
```

Règles fermes :

- `h1` — `line-height: 1.02`, `letter-spacing: -.03em`, **`max-width: 13ch`**.
- `h2` — `line-height: 1.08`, `letter-spacing: -.02em`, `max-width: 18ch`.
- Corps — `line-height: 1.75`, `max-width: 62ch`, jamais au-delà.
- Chiffres de statistiques — `font-variant-numeric: tabular-nums`.
- **Zéro capitale intégrale**, sauf les sur-titres (`.eyebrow`) et « WE SERVE ».
  Deux exceptions, pas trois.

### Formes et ombres

```css
--r-carte:  10px;
--r-pilule: 999px;
--r-arche:  220px 220px 3px 3px;

--ombre:        0 14px 34px rgba(14,46,94,.12);
--ombre-survol: 0 16px 40px rgba(14,46,94,.13);
```

Toutes les ombres sont **bleutées**. Jamais de gris neutre.

### Espace

Échelle : `4 8 12 16 24 32 48 64 96 128 160` px, exposée en `--e1` … `--e11`.
**Aucune valeur d'espacement hors de cette échelle.**

```css
--section-y: clamp(80px, 8vw, 120px);   /* plafonné à 120 px */
--head-gap:  clamp(32px, 4vw, 56px);
--gouttiere: clamp(20px, 5vw, 56px);
--conteneur: 1200px;
```

**Règle du vide** — aucune section ne se termine sur plus de **80 px** d'espace vide
au-delà de son padding, et deux colonnes voisines ne doivent pas différer de plus de
~80 px en hauteur de contenu. Se mesure, ne s'estime pas (voir §13).

---

## 2. Signature graphique — l'arc

Elle vient du sceau Lions. **Trois emplois, et trois seulement.**

| Échelle | Emploi | Où |
|---|---|---|
| **Monumentale** | 6 à 8 cercles concentriques SVG, trait 1 à 1,2 px, or et bleu clair alternés, opacité ~0,55, débordant à droite, **centre hors écran** | hero d'accueil ; version réduite dans `.page-hero` |
| **Structurelle** | l'**arche**, `--r-arche` | un seul bloc visuel majeur par page |
| **De détail** | **filet or de 56 × 2 px** au-dessus de chaque titre de section principale | `.section-head::before` |

**Interdit** : arcs semés au hasard, arcs derrière chaque carte, arcs en fond de section.

L'absence du filet or (`.section-head--secondaire`) est ce qui **marque une section
secondaire**. C'est un signal, pas un oubli.

La forme de l'arche est portée par `.media--arche` dans `lions.css` — un seul bloc visuel
majeur par page, jamais deux.

### Exception : l'espace privé n'a pas la signature de l'arc

`/mockups/espace/` partage la charte du site public — mêmes couleurs, mêmes typographies,
mêmes rayons, mêmes ombres — mais **aucun des trois emplois de l'arc** : ni arcs
concentriques, ni arche, ni filet or au-dessus des titres. C'est un **outil de travail**,
pas une vitrine.

S'y ajoutent trois écarts assumés, consignés en tête de `assets/css/prive.css` :

- **Playfair est réservé au `h1` et aux grands chiffres.** Tout le reste en Inter : dans
  un outil, la lisibilité prime sur l'effet. Les titres de bloc sont des `h2`/`h3` en
  Inter 600, pas des titres de section publics.
- **`--section-y` ne s'applique pas.** L'espacement vient directement de l'échelle
  `--e*`, plus serré : la densité d'information est assumée.
- **L'or ne sert qu'à ce qui attend une action du membre** — `.carte-action--urgent`,
  et rien d'autre. Le bleu reste la couleur d'action, le fond de l'application est
  `--fond`, les contenus sont des cartes blanches bordées `--bord`.

---

## 3. Navigation

### Barre principale

Dans cet ordre, sans exception :

**Accueil · Notre Club · Nos Actions · Nous rejoindre · Contact**

puis le bouton pilule bleu **« Se connecter »**.

- **Événements** et **Actualités** ne figurent **pas** dans la barre. Elles restent
  atteignables par les sections de l'accueil, les liens contextuels et le pied de page.
- **« Notre Club » est un lien simple.** Aucun sous-menu tant que la page
  `notre-club.html` n'est pas construite et ses sections arrêtées.
- Le **menu mobile reprend la même liste, dans le même ordre**.
- **Pas de recherche dans la barre.** La loupe sera réintroduite quand une page de
  recherche existera réellement. Voir §15.

### État actif

Le lien courant porte **`class="… actif"` et `aria-current="page"`**, les deux.
`aria-current` porte la sémantique, `.actif` sert de crochet de style à l'intégration
Django. L'état actif n'est **jamais** signalé par la seule couleur : un soulignement or
de 2,5 px l'accompagne.

### Bascule mobile

Sous **1080 px** : burger, panneau plein écran glissant depuis la droite. Le burger
porte `aria-expanded` et `aria-controls`.

---

## 4. En-tête et pied de page partagés

Le balisage de l'en-tête et du pied de page est **rigoureusement identique d'une page à
l'autre, au caractère près**, à la seule exception de `actif` / `aria-current="page"`
sur le lien courant.

Les deux blocs sont encadrés par :

```html
<!-- ══ EN-TÊTE PARTAGÉ — deviendra un include Django, garder identique sur toutes les pages ══ -->
<!-- ══ FIN EN-TÊTE PARTAGÉ ══ -->

<!-- ══ PIED DE PAGE PARTAGÉ — deviendra un include Django, garder identique sur toutes les pages ══ -->
<!-- ══ FIN PIED DE PAGE PARTAGÉ ══ -->
```

**Jamais injectés en JavaScript** : le contenu doit être dans le HTML.

Le pied de page compte quatre colonnes — marque, **Liens rapides** (qui liste bien
Événements et Actualités), **Notre club**, **Contact** — et une barre basse.

Après toute modification, vérifier l'identité par hachage (§13).

---

## 5. Rythme des sections

**Une page doit être convaincante sans aucune photographie.** Si elle ne tient qu'une
fois les images déposées, la direction artistique a échoué.

La qualité est portée, dans cet ordre : la **typographie** (échelle, contraste de
graisses, longueur de ligne), l'**espace**, le **rythme** des traitements de section,
les **détails** (filets, alignements optiques, micro-transitions), puis le **mouvement**.
La couleur et les images renforcent, elles ne sauvent pas.

Deux sections voisines ne partagent **jamais** le même fond **et** la même structure.
Chaque section a **un élément dominant**, pas quatre éléments égaux.

Traitements disponibles : champ sombre asymétrique · fond blanc à deux colonnes
déséquilibrées · grille de cartes sur fond clair · bande basse discrète · bandeau navy
pleine largeur · deux colonnes de densités différentes · split visuel/navy.

---

## 6. Écriture

- **Première personne du pluriel** : « nous », « notre club », « nos membres ».
  Jamais « le club » à la troisième personne dans le corps de page.
- **Verbes concrets.** « Nous dépistons », pas « nous œuvrons dans le cadre d'une
  démarche de prévention ».
- Un chiffre est toujours accompagné d'un mot humain et d'une **période de référence**.
- **Aucune phrase creuse.** Si une ligne peut figurer sur le site de n'importe quelle
  association, elle est supprimée.

---

## 7. Les quatre axes

Le club a **exactement quatre axes prioritaires** :
**Diabète · Environnement · Humanitaire · Jeunesse**.

**Santé oculaire**, **cancer infantile**, **malnutrition**, **aide aux victimes de
catastrophes** et **santé mentale et bien-être** sont des **grandes causes portées par
Lions Clubs International**. Elles se présentent dans une bande distincte, volontairement
plus discrète, et **ne concurrencent jamais** les quatre axes : titre plus petit, pas de
filet or, espacement réduit.

Le texte officiel transmis par le club énumère cinq éléments sous l'intitulé « quatre
axes », en y ajoutant la santé oculaire, qui n'a pas de paragraphe descriptif. Traité
comme une coquille, en attente de confirmation du bureau. **Si le bureau confirme cinq
axes, cette règle est à reprendre entièrement.**

Le texte officiel complet de chaque axe est conservé en commentaire au-dessus de sa
carte, pour les futures pages de détail.

---

## 8. Contenu : ne jamais inventer

Les contenus officiels existent dans la base : table `sitecontent` (axes, mission,
historique, statistiques, coordonnées), `events_event`, `news_article`. **Les lire plutôt
que d'inventer.** Lecture seule.

N'inventer sous aucun prétexte : chiffres officiels, coordonnées, noms de membres,
partenaires, dates historiques.

Marqueurs obligatoires dans le code :

```html
<!-- CONTENU DE DÉMONSTRATION -->
<!-- DONNÉE À VALIDER PAR LE CLUB -->
```

**Une photographie authentique porte la même exigence qu'un texte.** Une vraie photo
du club placée sous un contenu de démonstration affirme que la scène a eu lieu : elle
reçoit sa propre réserve, et son `alt` décrit **strictement ce que montre l'image**,
jamais le contenu auquel elle est rattachée.

Ne pas rendre une association douteuse plus plausible qu'elle ne l'est : un écart visible
entre l'image et le titre est le signal, pas le défaut.

### Droit à l'image

**Ne jamais attribuer un nom, une fonction ou un rôle à une personne figurant sur une
photographie.**

Les personnes reconnaissables sur les photos du club n'ont pas donné d'accord de
publication vérifié. Toute page affichant des visages identifiables porte le rappel
correspondant dans la liste de validation destinée au bureau.

---

## 9. Images

- Nomenclature : **`<emplacement>-<largeur>.webp`**, minuscules, sans accent, tirets.
- Chaque `<img>` référence dès l'écriture son **nom de fichier définitif**. Déposer le
  fichier doit suffire — **aucune modification de code**, hormis l'`alt`, signalé par
  `<!-- ALT À RÉÉCRIRE APRÈS DÉPÔT DE LA PHOTO -->`.
- Variantes servies en `srcset` + `sizes`. `width`/`height` en dur, ratio porté par le
  conteneur `.media` : **la hauteur est réservée, aucun décalage au chargement.**
- `loading="lazy"` partout sauf le hero, qui prend `fetchpriority="high"`.
- Toute image temporaire est préfixée **`tmp-`** et précédée de
  `<!-- IMAGE GÉNÉRÉE — MAQUETTE UNIQUEMENT — À REMPLACER AVANT MISE EN LIGNE -->`.
- Emplacement sans fichier : **repère technique** `.media--vide` — fond `#EDF1F7`,
  bordure pointillée `#C3D0E2`, texte 12 px `#8494AC` donnant nom, ratio et dimensions
  minimales. Ni dégradé, ni couleur de charte, ni icône : il doit se lire « emplacement
  à remplir », jamais comme un parti pris graphique.
- Les originaux vivent dans `assets/sources/` avec leur `README.md`. **Trois d'entre eux
  portent une orientation EXIF non appliquée** : toujours `-auto-orient` avant tout
  recadrage ou `-strip`.
- Tout emplacement est décrit dans **`mockups/IMAGES.md`**, qui fait foi.

---

## 10. Accessibilité

- Lien d'évitement « Aller au contenu principal » en début de page.
- **Un seul `<h1>` par page**, hiérarchie `h2`/`h3` cohérente.
- `:focus-visible` partout : contour **or de 3 px**.
- Contrastes **AA**, y compris le texte blanc sur photo — le dégradé doit le garantir,
  et **se mesurer par échantillonnage de pixels sur le rendu réel**, pas s'estimer.
- `--gris-clair` (#8494AC) tombe à 3,0:1 sur blanc : **interdit pour du contenu**
  (dates, lieux, légendes). Utiliser `--gris`. Il reste réservé au repère technique,
  qui est un échafaudage de développement, pas du contenu.
- Aucune information transmise par la **couleur seule**.
- Icônes décoratives en `aria-hidden="true"`, images décoratives en `alt=""`.
- Chaque élément focusable a un nom accessible — et **fait réellement quelque chose**.
  Un bouton inerte est un défaut au même titre qu'un lien mort.

### Formulaires

- `<label>` **visible**, relié par `for`/`id`. Le `placeholder` ne remplace jamais le label.
- Focus visible et **distinct** du survol.
- Erreur reliée par `aria-describedby`, jamais signalée par la seule couleur.
- Champ obligatoire marqué par un **texte**, pas seulement un astérisque.
- `autocomplete` pertinent, `inputmode` adapté, zone de saisie **≥ 44 px**.
- Maquette : `action="#"`, soumission empêchée en JS, et au-dessus de chaque formulaire
  `<!-- MAQUETTE : formulaire non fonctionnel, sera branché à l'intégration Django -->`.
  Les états visuels se montrent en **exemples statiques commentés**, jamais via une
  validation JavaScript inventée.

---

## 11. Mouvement

Un seul moment orchestré par page ; le reste est discret.

- **Ouverture du hero** : sur-titre, `h1`, paragraphe, boutons, colonne de valeurs en
  fondu montant — décalage **90 ms**, translation **24 px**, durée **850 ms**,
  `cubic-bezier(.22,.7,.3,1)`. Les arcs se déploient en `clip-path`, 1,1 s, léger retard.
- **Reveal au scroll** : opacité + **16 px maximum**, sur les **grands blocs uniquement**,
  jamais carte par carte.
- **Micro-interactions** : 200 ms. Élévation de carte 4 px, flèches qui glissent de 4 px.
- **Compteurs** : `easeOutCubic`, 1,4 s, déclenchés par `IntersectionObserver`.
- Uniquement `transform` et `opacity` (le `clip-path` des arcs est la seule dérogation).
- `IntersectionObserver` avec **`unobserve`** après déclenchement.
- **L'état final est porté par la règle CSS, pas par le remplissage de l'animation** :
  utiliser `backwards`, jamais `both`. Si l'animation ne se déclenche pas, le contenu
  doit être visible, pas bloqué à `opacity: 0`.
- `prefers-reduced-motion: reduce` **neutralise tout** — animations, transitions,
  `scroll-behavior` — et affiche immédiatement l'état final.

---

## 12. Responsive et SEO

Points de rupture testés réellement : **1440 · 1280 · 1024 · 768 · 430 · 375 px**.
**Aucun débordement horizontal à aucune largeur.** Le mobile n'est pas une version
desktop compressée.

Seuils : ≤ 1080 px burger et colonnes empilées · ≤ 760 px hero vertical couvrant,
chiffres en 2 colonnes · ≤ 520 px cartes en 1 colonne.

SEO, sur chaque page : `title` unique, `meta description`, `canonical`, Open Graph
complet, Twitter Card, et **`noindex, follow`** tant que la maquette n'est pas validée,
avec un commentaire indiquant de le retirer. JSON-LD `Organization`/`NGO` sur l'accueil,
`BreadcrumbList` sur les pages intérieures éditoriales. Le contenu important est dans le
HTML, jamais généré par JavaScript.

### Phrase factuelle de référence

Elle figure **en clair dans le HTML** de chaque page qui présente le club — pour Google
comme pour les moteurs de réponse et les assistants IA. Reprise **telle quelle, sans
reformulation** :

> Le Lions Club Sfax-Méditerranée est un club Lions basé à Sfax, en Tunisie, rattaché au
> District 414 Tunisie. Ses quatre axes prioritaires sont le diabète, l'environnement,
> l'humanitaire et la jeunesse.

**Ancrage local** — le contenu doit permettre de comprendre naturellement, sans bourrage
de mots-clés, que le club agit à **Sfax**, en **Tunisie**, au sein du **District 414 Tunisie**.

**Aucun lien mort.** Un lien sans cible pointe vers `#` avec un commentaire
`<!-- LIEN À CRÉER -->`.

---

## 13. Vérifications avant toute livraison

Rien n'est livré sans ces contrôles, **mesurés**, pas estimés.

```sh
# Les six largeurs : débordement horizontal, erreurs console
# (Chrome headless plafonne à 500 px : passer par une iframe à largeur exacte
#  pour 430 et 375 px)

grep -c "ALT À RÉÉCRIRE" mockups/<page>.html   # → 0 à la mise en ligne
grep -c "tmp-"           mockups/<page>.html   # → 0 à la mise en ligne
grep -c "noindex"        mockups/<page>.html   # → 0 à la mise en ligne
```

À contrôler également : un seul `<h1>` · aucun élément focusable sans nom accessible ·
aucune image sans attribut `alt` · navigation clavier complète · `prefers-reduced-motion`
neutralise bien tout · en-têtes et pieds de page identiques d'une page à l'autre
(comparaison par hachage, `actif`/`aria-current` neutralisés).

### Les trois questions

À répondre explicitement dans chaque résumé de livraison :

1. **En niveaux de gris, sans le logo, la page reste-t-elle reconnaissable ?**
   Si non, la signature graphique est trop faible.
2. **Peux-tu nommer l'élément dominant de chaque section ?**
   Si une section n'en a pas, elle est plate.
3. **Cette page pourrait-elle appartenir à une autre association sans changer autre
   chose que le nom ?** Si oui, c'est raté.

---

## 14. Interdits

Quelle que soit la justification :

- gradients multicolores ou saturés, arrière-plans animés
- glassmorphism, effets de verre, flous décoratifs
- **glyphes typographiques en guise d'icônes** (`→` `↗` `⌄` `◆` `♥` `●` `+`) —
  uniquement du SVG dessiné, trait fin
- emoji
- ombres grises neutres
- quatre rangées de cartes construites à l'identique
- tout centrer — le centrage est réservé aux titres de section et aux rangées d'icônes
- carrousels à défilement automatique
- parallaxe au-delà de 32 px
- sections purement décoratives, sans contenu utile
- grands espaces vides qui n'apportent rien
- jaune en fond large
- copie d'un bloc de `lionsclubs.org` : on s'inspire de la hiérarchie et du souffle,
  jamais de la forme

---

## 15. Fonctionnalités différées

Registre de ce qui est **volontairement absent**. Sans lui, ces décisions se reperdent
d'une session à l'autre et reviennent par mégarde.

- **Recherche** — pas de loupe dans la barre tant qu'aucune page de recherche n'existe.
- **Sous-menu « Notre Club »** — lien simple tant que les sections de `notre-club.html`
  ne sont pas arrêtées.
- **Commissions** — fonctionnalité explicitement reportée par le propriétaire du projet.
  Ne créer ni modèle, ni page, ni rôle, ni tableau de bord sans nouvelle demande.
- **Carte cartographique** — aucune sur `contact.html` : coût de performance et traceurs
  tiers, pour aucun bénéfice tant que l'adresse précise n'est pas validée.
