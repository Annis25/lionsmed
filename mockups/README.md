# Maquettes Lions Club Sfax-Méditerranée

Référence : commit `8e63540`, skill `.claude/skills/lionsmed-design/SKILL.md`.
Travail statique exclusivement dans `mockups/`. Aucun backend, envoi, authentification,
paiement ou stockage de formulaire n’est implémenté.

## Parcours de validation

- Ouvrir `accueil.html`, puis `plan-du-site.html` pour toutes les pages publiques.
- Ouvrir `espace/tableau-de-bord.html` pour l’espace privé. Le sélecteur de rôle permet
  de vérifier les sept rôles sur le même ensemble de composants. Le paramètre `role`
  est conservé dans les liens privés ; il représente un état de maquette, pas une
  autorisation réelle.
- Les pages Votes et Satisfaction proposent un sélecteur d’états explicitement
  statiques. Les formulaires ne transforment jamais une saisie en faux succès.
- `emails/index.html` donne accès aux neuf messages de démonstration.
- `home.html` et `aaa.html` sont des points d’entrée de compatibilité vers l’accueil.
  Les archives préexistantes de `_backup/` sont des pièces historiques non navigables.

## Structure

`assets/css/lions.css` : jetons, composants publics et privés partagés.
`assets/js/lions.js` : interactions publiques et privées partagées.
`accueil.css`, `accueil.js`, `rejoindre.css` : spécifique à ces pages.
`prive.css` et `prive.js` : petits repères de compatibilité/documentation, sans duplication.
`IMAGES.md` : fichiers attendus, contexte photographique et droits à confirmer.
`validation/` : rapports mesurés et captures des maquettes ; exclure de l’intégration.

## Vérifications reproductibles

Depuis la racine du dépôt, démarrer un serveur local limité à ce dossier :

```sh
python3 -m http.server 8876 --bind 127.0.0.1 --directory mockups
python3 mockups/outils/audit-statique.py
node mockups/outils/test-maquettes.cjs
node mockups/outils/test-interactions.cjs
node mockups/outils/test-qualite.cjs
```

Les scripts navigateur utilisent le Playwright déjà fourni par l’environnement Codex
et Chrome installé. Aucune dépendance n’a été ajoutée au projet. Les tests responsive
emploient des viewports Chromium exacts : 1440, 1280, 1024, 768, 430 et 375 px.

Les formulaires ont `action="#"`, `data-maquette` et un blocage partagé. Leurs exemples
d’erreur, succès et attente restent commentés pour l’intégration, conformément au skill.
Le changement d’état d’un vote ou d’une satisfaction est une prévisualisation explicite,
sans persistance. Le fichier ICS décrit un événement marqué DEMONSTRATION.

Les e-mails sont des aperçus HTML de la charte. L’intégration du CSS au moteur d’envoi,
les jetons personnels et les essais Outlook/Gmail/Apple Mail seront effectués lors de
l’intégration. Aucun système d’envoi n’est branché.
