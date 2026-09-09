# Lionsmed — contexte final de projet

## Produit

Lionsmed est le nouveau portail du Lions Club Sfax-Méditerranée : site public éditorial et espace privé des membres. Le runtime actif est `rebuild/`; les mockups et le legacy ne sont pas le runtime de production.

## Architecture

- Django 5 / PostgreSQL, configuration par environnement.
- Applications : comptes, agenda, communications, core, documents, cotisations, éditorial, gouvernance, membres, satisfaction, actions de service et votes.
- Données privées stockées hors URL publique ; images de contenu public servies par la couche `PublicImage`.
- Migrations nouvelles de la phase courante : agenda, cotisations, gouvernance, membres, actions, votes.

## Règles d'autorisation

La source unique est `rebuild/apps/core/permissions.py`.

- Gestion générique : SUPER_ADMIN, PRESIDENT, SECRETAIRE.
- Contact : PRESIDENT et SECRETAIRE.
- Candidatures : PRESIDENT et GMT.
- Cotisations : modification SUPER_ADMIN/TRESORIER ; consultation bureau élargi.
- Membre : calendrier, vote, satisfaction, annuaire privé et informations personnelles selon statut.
- Invité : accès personnel limité, sans annuaire/vote/satisfaction.
- Un rôle actif unique est requis ; ambiguïté = refus d'accès.

## Fonctions livrées

- Site public : accueil, club, valeurs, actions, détail d'action avec galerie et lightbox, rejoindre et contact.
- Espace privé : tableau de bord, profils, parcours, annuaire, calendrier et flux ICS, présences, notifications, documents, votes, satisfaction, cotisations, contenus publics, membres/mandats, années Lions et MFA.
- Boîtes de traitement séparées : candidatures (PRESIDENT/GMT) et messages de contact (PRESIDENT/SECRETAIRE).
- Actions : brouillon/publication, image principale, galerie plafonnée, impact, bénéficiaires, heures, partenaires et lien Instagram.

## Garde-fous techniques

- CSRF, limitation de débit, MFA TOTP, mots de passe Django, audit des mutations.
- Transactions et verrous pour inscriptions d'événement, votes et cotisations.
- Documents privés, contrôle de format, structure et antivirus ClamAV en échec fermé.
- Migrations legacy bloquées dans la base rebuild ; import legacy explicite, traçable et non automatique.

## État de l'audit du 9 septembre 2026

**Statut : prêt pour la préproduction, pas pour la production.**

- Schéma Django : vérifié, migrations synchronisées, aucune migration manquante.
- Tests : 339 collectés ; 0 failure, 0 error après correction de la validation extension–MIME des portraits ; trois tests sont ignorés selon les dépendances/environnement de test.
- Upload portrait : MIME déclaré cohérent avec l'extension exigé avant le décodage et la normalisation JPEG ; PNG, JPEG, WebP et HEIC/HEIF légitimes restent supportés.
- Backup/restore local validé sur une base temporaire sans écraser la base de développement.
- Avant production : configurer secrets/SMTP/ClamAV/HTTPS, sauvegardes automatisées, recette des rôles et décisions humaines restantes.
- Hygiène Git : `rebuild/.env.before-recipe` est local et ignoré, jamais livré ; `DJANGO_SECRET_KEY` doit être renouvelée avant la mise à jour production.

## E-mails et communication membres

- Les e-mails transactionnels utilisent une base HTML Lionsmed commune, avec version texte, logo absolu depuis `SITE_ORIGIN` et salutation au prénom.
- Les rôles Bureau autorisés disposent de la capability `communication.send_member_broadcast` pour préparer, prévisualiser, tester et mettre en file une campagne individuelle via l’outbox.
- Les campagnes conservent un historique d’audit et des compteurs d’envoi, sans stocker de copie personnalisée par destinataire.

## Passe finale — 10 septembre 2026

- L’invitation d’un nouveau membre est mise dans l’outbox sans mot de passe connu : l’e-mail « Bienvenue parmi nous » porte un lien Django sécurisé permettant à la personne de choisir son propre mot de passe. Son renvoi exige une confirmation et reste idempotent sur une courte fenêtre.
- Les e-mails utilisent une base HTML et texte communs, avec logo absolu depuis `SITE_ORIGIN`, footer institutionnel, salutation au prénom et CTA jaune compatible clients e-mail.
- Les liens de retour POST du calendrier et des cotisations sont désormais limités à l’hôte courant : aucun `next` ou `Referer` externe n’est suivi.
- Les résultats de vote envoyés par e-mail restent strictement agrégés ; aucun électeur, bulletin ou choix individuel n’est fourni au modèle.
- Les décisions non techniques restent : seuil de satisfaction, audience finale des résultats de vote, activation de l’indexation publique, politique MFA obligatoire et préparation réelle SMTP/ClamAV/backup avant production.

Le détail, les priorités et la checklist sont dans `docs/AUDIT_FINAL_AVANT_PRODUCTION.md`.
