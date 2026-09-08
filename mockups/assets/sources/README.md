# Photographies sources — Lions Club Sfax-Méditerranée

Copies **fidèles aux originaux**, conservées ici pour que les recadrages de la page
d'accueil puissent être refaits sans dépendre d'un fichier extérieur au dépôt.

**Ne pas modifier ces fichiers.** Ce sont les masters. Toutes les images servies par la
page sont dérivées d'eux et vivent dans `../images/`.

---

## ⚠️ Orientation EXIF — à lire avant tout recadrage

Trois fichiers portent une orientation EXIF **non appliquée aux pixels**. Un outil qui
supprime les métadonnées (`-strip`, export « sans métadonnées ») sans redresser d'abord
produit une image **retournée**.

**Toujours appliquer `-auto-orient` (ImageMagick) ou l'équivalent avant tout recadrage,
redimensionnement ou `-strip`.**

| Fichier | Orientation EXIF | Effet si ignorée |
|---|---|---|
| `club-bloc-medical-original.jpg` | `RightTop` | Image couchée à 90° |
| `club-distribution-original.jpg` | `BottomLeft` | Image retournée |
| `club-soiree-original.jpg` | `BottomLeft` | Image retournée |

`club-tablee-original.jpg` est un cas différent : **aucune donnée EXIF**, mais les pixels
sont couchés. Elle exige un `-rotate -90` explicite (sens antihoraire).

---

## Inventaire

| Fichier | Dimensions natives | Ce que montre la photo | Utilisée pour |
|---|---|---|---|
| `club-exterieur-original.jpg` | 1600×1200 | Grande photo de groupe en extérieur devant un bâtiment aux façades colorées, ~28 personnes en gilets Lions tenant des certificats, bannière « Lions Sfax Med — WE SERVE », plantes en pot au premier plan | `hero-principal-*`, `og-accueil.jpg` |
| `club-distribution-original.jpg` | 4032×3024 | Selfie de 8 membres en gilets Lions, en extérieur, cartons empilés à l'arrière-plan | `rejoindre-*` |
| `club-tablee-original.jpg` | 727×1320 *(couchée)* | Grande tablée en salle de réception, éclairage chaud, une trentaine de personnes en tenue de soirée | `evenement-1-*` |
| `club-plage-original.jpg` | 4032×2268 | Groupe en gilets Lions sur la plage, de nuit, avec la bannière du club et une tente | `evenement-2-*` |
| `club-remise-materiel-original.jpg` | 4096×3072 | Groupe posé en salle de réunion, blouses blanches et gilets Lions, matériel médical sur la table | `evenement-3-*` |
| `club-rencontre-original.jpg` | 1600×1200 | Présentation de matériel médical en salle de réunion, un médecin désigne des couveuses posées sur une table vitrée | `actualite-1-*` |
| `club-bloc-medical-original.jpg` | 4032×3024 *(EXIF)* | Six personnes en casaques et charlottes chirurgicales devant un écran médical | `actualite-2-*` |
| `club-soiree-original.jpg` | 4032×3024 *(EXIF)* | Groupe de membres attablés au café, le soir, sous une pergola | `actualite-3-*` |
| `club-collectif-original.jpg` | 1280×960 | Photo de groupe en intérieur, ~20 personnes derrière une table à nappe fleurie, salle blanche | *aucune — réserve* |

---

## Recadrages appliqués

Reproductibles à l'identique. `Q` vaut `-quality 82 -define webp:method=6 -strip`.

```sh
A="-auto-orient"

# hero-principal — 16/9 desktop, 4/3 mobile
convert club-exterieur-original.jpg $A -crop 1600x900+0+200 +repage -resize 1600x900 $Q ../images/hero-principal-1600.webp
convert club-exterieur-original.jpg $A -crop 1600x900+0+200 +repage -resize 1100x619 $Q ../images/hero-principal-1100.webp
convert club-exterieur-original.jpg $A                      -resize 640x480          $Q ../images/hero-principal-640.webp

# rejoindre — 3/2
convert club-distribution-original.jpg $A -crop 4032x2688+0+300 +repage -resize 1600x1067 $Q ../images/rejoindre-1600.webp

# événements — 16/10
convert club-tablee-original.jpg          $A -rotate -90 -crop 1163x727+80+0 +repage -resize 1100x688 $Q ../images/evenement-1-1100.webp
convert club-plage-original.jpg           $A -crop 3629x2268+200+0 +repage -resize 1100x688 $Q ../images/evenement-2-1100.webp
convert club-remise-materiel-original.jpg $A -crop 4096x2560+0+300 +repage -resize 1100x688 $Q ../images/evenement-3-1100.webp

# actualités — 1/1
convert club-rencontre-original.jpg    $A -crop 560x560+560+330 +repage -resize 480x480 $Q ../images/actualite-1-480.webp
convert club-bloc-medical-original.jpg $A -crop 3024x3024+0+560 +repage -resize 480x480 $Q ../images/actualite-2-480.webp
convert club-soiree-original.jpg       $A -crop 3024x3024+500+0 +repage -resize 480x480 $Q ../images/actualite-3-480.webp

# partage social — 1200×630
convert club-exterieur-original.jpg $A -crop 1600x840+0+180 +repage -resize 1200x630 -quality 86 -strip ../images/og-accueil.jpg
```

---

## Droit à l'image

Ces photographies montrent des personnes identifiables. **Avant toute mise en ligne, le
bureau doit s'assurer que chaque personne reconnaissable a consenti à la publication.**
Cette vérification n'a pas été faite dans le cadre de la maquette.
