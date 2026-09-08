# Audit et corrections — Lions Club Sfax-Méditerranée

Référence : 8e63540. Intervention exclusivement dans mockups/.

## P0

- Anciennes pages Tailwind harmonisées avec le skill ; aucune dépendance ajoutée.
- Navigation publique identique, liens et ancres corrigés, pages de détail créées.
- Formulaires sans envoi, profil e-mail non modifiable, invités sans vote,
  Bureau sans publication, résultats de vote uniquement dans l’état clôturé.
- Membres fictifs retirés du site public, données privées anonymes et signalées.

## P1

- Coquille privée commune et 7 rôles, profil/parcours/mandats, annuaire, calendrier,
  documents, notifications, cotisations, présences, pilotage et audit exceptionnel.
- Votes unique/multiple/élection, blanc exclusif, confirmation et état verrouillé.
- Satisfaction émotionnelle 1–5 et états ouvert/confirmation/déjà répondu/fermé.
- Tableaux responsive, navigation clavier, focus, labels, reduced motion.
- Voile d’accueil renforcé après mesure réelle du contraste ; formulaire de
  candidature sans grand vide latéral.

## P2

- CSS et JS publics/privés mutualisés ; métadonnées, canoniques, OG, Twitter,
  JSON-LD et noindex harmonisés ; phrase factuelle explicite.
- Neuf maquettes e-mail et index ; export ICS local, liens Google/Outlook/Apple.
- IMAGES.md actualisé ; anciens prototypes remplacés par des entrées de compatibilité.

## Tests

- 49 pages × 6 largeurs = 294 rendus Chromium : aucun overflow, aucune exception JS.
- 15 scénarios d’interaction réussis ; 147 vérifications de rôles réussies.
- 16 formulaires marqués et bloqués, un H1 par page, aucun alt absent, aucun nom
  accessible manquant détecté, aucune ancre ni ressource HTML/CSS/JS locale cassée.
- Navbar/footer : un hash normalisé commun sur les 18 pages publiques.
- 2 385 contrôles de contraste calculé sans échec ; échantillonnage réel des textes
  sur photo aux six largeurs : minimum observé 5,18:1 (hors repères techniques).
- Quatre images d’axes manquent volontairement, soit huit variantes attendues.
  Le navigateur signale leurs 404 ; elles affichent les repères techniques prévus.
- Les résultats sont des contrôles Chromium, pas une certification WCAG complète
  ni des essais dans les clients de messagerie. Rapports JSON et captures dans validation/.

## Trois questions du skill

| Grandes pages | Niveaux de gris, sans logo | Élément dominant | Spécificité institutionnelle |
|---|---|---|---|
| Accueil | Typographie et arcs conservés | Hero, quatre axes, chiffres datés, agenda, arche | Sfax, quatre axes et District |
| Notre Club | Arcs et contraste typographique | Présentation, réseau, chronologie, valeurs, axes, bureau | Réseau Lions et histoire locale |
| Nos Actions | Numérotation et hiérarchie | Quatre axes puis liste filtrable | Priorités exactes de Sfax-Méditerranée |
| Listes et détails publics | Même signature de page | Titre et contenu éditorial | Textes officiels encore attendus ; ne pas valider leur contenu comme final |
| Rejoindre / candidature / contact | Charte et hiérarchie conservées | Parcours ou formulaire | Adhésion au club de Sfax et contact déclaré |
| Connexion / mot de passe | Typographie et cadre d’accès | Formulaire | Accès à l’espace Lions |
| Espace privé | Outil sans arcs, conformément à l’exception | Actions attendues puis suivi ; choix et graphiques sur les pages dédiées | Année Lions, mandats personnels, parcours Lions / LEO et rôles |
| E-mails | Hiérarchie simple | Objet et CTA unique | Messages du club, sans données officielles inventées |

## Validation humaine requise

- Bureau actuel, titulaires, périodes des mandats et archives institutionnelles.
- Textes et photos officiels des actions, actualités et événements ; statistiques
  et périodes de référence ; associations des six photos de l’accueil ; droit à l’image.
- Quatre photos d’axes, portraits de candidats si une élection est retenue.
- Coordonnées définitives, réseaux officiels, mentions juridiques et durées de conservation.
- Montant des cotisations, calendrier officiel, heure exacte de clôture de satisfaction,
  règles détaillées d’attribution des rôles et supervision du Directeur.

## Backend

Aucun fichier Django modifié. Aucune écriture DB. Aucun commit. Aucun push.

## Fichiers modifiés

- `mockups/IMAGES.md`
- `mockups/aaa.html`
- `mockups/accueil.html`
- `mockups/actualites.html`
- `mockups/assets/css/accueil.css`
- `mockups/assets/css/lions.css`
- `mockups/assets/css/prive.css`
- `mockups/assets/js/lions.js`
- `mockups/assets/js/prive.js`
- `mockups/candidature.html`
- `mockups/confidentialite.html`
- `mockups/connexion.html`
- `mockups/contact.html`
- `mockups/espace/tableau-de-bord.html`
- `mockups/evenements.html`
- `mockups/home.html`
- `mockups/mentions-legales.html`
- `mockups/mot-de-passe-oublie.html`
- `mockups/nos-actions.html`
- `mockups/notre-club.html`
- `mockups/plan-du-site.html`
- `mockups/rejoindre.html`
- `mockups/sitemap.xml`

## Fichiers créés

- `mockups/README.md`
- `mockups/action-detail.html`
- `mockups/article-detail.html`
- `mockups/assets/calendrier-demonstration.ics`
- `mockups/emails/candidature.html`
- `mockups/emails/document.html`
- `mockups/emails/importante.html`
- `mockups/emails/index.html`
- `mockups/emails/mot-de-passe.html`
- `mockups/emails/ouverture-vote.html`
- `mockups/emails/rappel-j1.html`
- `mockups/emails/rappel-j7.html`
- `mockups/emails/resultats-vote.html`
- `mockups/emails/satisfaction.html`
- `mockups/espace/annuaire.html`
- `mockups/espace/audit.html`
- `mockups/espace/calendrier.html`
- `mockups/espace/contenu-public.html`
- `mockups/espace/cotisations.html`
- `mockups/espace/document-detail.html`
- `mockups/espace/documents.html`
- `mockups/espace/membres.html`
- `mockups/espace/notifications.html`
- `mockups/espace/presences.html`
- `mockups/espace/profil-membre.html`
- `mockups/espace/profil.html`
- `mockups/espace/responsables.html`
- `mockups/espace/satisfaction-resultats.html`
- `mockups/espace/satisfaction.html`
- `mockups/espace/statistiques.html`
- `mockups/espace/vote-creation.html`
- `mockups/espace/vote-resultats.html`
- `mockups/espace/vote-suivi.html`
- `mockups/espace/votes.html`
- `mockups/evenement-detail.html`
- `mockups/outils/audit-statique.py`
- `mockups/outils/test-interactions.cjs`
- `mockups/outils/test-maquettes.cjs`
- `mockups/outils/test-qualite.cjs`
- `mockups/validation/` : rapports et captures des six largeurs.

Aucun fichier préexistant supprimé.
