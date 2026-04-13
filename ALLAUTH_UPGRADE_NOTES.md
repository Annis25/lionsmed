# django-allauth — notes de mise à jour

**Version installée : 0.63.3. Dernière version : 65.x.**
**Statut : non mise à jour.** Le saut de version majeure renomme des réglages ;
la bascule doit être faite et testée à part.

---

## Pourquoi c'est urgent

`pip-audit` remonte **3 vulnérabilités** sur cette version (comptées deux fois par
l'outil, une fois par source d'avis) :

| Identifiant | Corrigé en |
|---|---|
| PYSEC-2025-110 | 65.13.0 |
| PYSEC-2025-111 | 65.13.0 |
| PYSEC-2026-56 | 65.14.1 |

Après la mise à jour de Django, Pillow, sqlparse et python-dotenv, `django-allauth`
est **la seule dépendance applicative encore vulnérable**.

---

## Élément décisif : le paquet n'est pas utilisé

Une recherche sur l'ensemble du code (`allauth`, `account_login`, `account_signup`,
`account_logout`, `socialaccount`, hors `settings.py`) ne remonte **aucune
occurrence**.

Concrètement :

- l'authentification passe par `accounts.views.login_view`, écrit à la main ;
- aucune URL d'allauth n'est branchée dans `lionsclub_platform/urls.py` ;
- aucun template d'allauth n'est surchargé ;
- aucun fournisseur social n'est configuré.

Ne subsistent que trois traces dans `settings.py` : les apps `allauth` et
`allauth.account`, le middleware `AccountMiddleware`, et le backend
`AuthenticationBackend`.

**Deux voies s'offrent donc, et le retrait est probablement la bonne.**

---

## Option A — Retirer allauth (recommandée)

Supprime les 3 vulnérabilités sans aucune migration de réglages.

### Étapes

1. Retirer de `INSTALLED_APPS` :
   ```python
   'allauth',
   'allauth.account',
   ```
2. Retirer de `MIDDLEWARE` :
   ```python
   'allauth.account.middleware.AccountMiddleware',
   ```
3. Retirer de `AUTHENTICATION_BACKENDS` :
   ```python
   'allauth.account.auth_backends.AuthenticationBackend',
   ```
4. Supprimer les réglages devenus inutiles :
   ```python
   ACCOUNT_EMAIL_REQUIRED = True
   ACCOUNT_USERNAME_REQUIRED = False
   ACCOUNT_AUTHENTICATION_METHOD = 'email'
   SITE_ID = 1                      # à conserver si django.contrib.sites reste utilisé
   ```
5. Retirer `django-allauth` de `requirements.txt`, puis `pip uninstall django-allauth`.

### Points de vigilance

- `django.contrib.sites` est listé dans `INSTALLED_APPS` : vérifier qu'aucun autre
  composant n'en dépend avant de retirer `SITE_ID`.
- Les tables `account_*` (`account_emailaddress`, `account_emailconfirmation`)
  restent en base, inertes. Les supprimer par une migration dédiée seulement
  après confirmation en production.
- Vérifier après retrait : connexion, déconnexion, approbation de candidature,
  et accès à `/admin/`.

### Si un jour la connexion Google ou Facebook est souhaitée

Réinstaller allauth **en version 65.x** à ce moment-là, avec les noms de réglages
actuels — sans traîner la dette de la 0.63.

---

## Option B — Monter en 65.x

À retenir seulement si l'usage d'allauth est prévu à court terme.

### Réglages actuels à renommer

Depuis la 65.x, les réglages `ACCOUNT_*` du projet sont **tous obsolètes** :

| Réglage actuel (`settings.py`) | Remplacement en 65.x |
|---|---|
| `ACCOUNT_EMAIL_REQUIRED = True` | `ACCOUNT_SIGNUP_FIELDS = ['email*', 'password1*', 'password2*']` |
| `ACCOUNT_USERNAME_REQUIRED = False` | idem — l'absence de `'username*'` dans `ACCOUNT_SIGNUP_FIELDS` suffit |
| `ACCOUNT_AUTHENTICATION_METHOD = 'email'` | `ACCOUNT_LOGIN_METHODS = {'email'}` |

Autres changements notables entre 0.63 et 65.x :

- `ACCOUNT_EMAIL_VERIFICATION` conserve son nom mais change de comportement par
  défaut sur certains parcours ;
- le middleware `allauth.account.middleware.AccountMiddleware` est devenu
  **obligatoire** (déjà présent ici) ;
- les gabarits ont été réorganisés : toute surcharge de template allauth serait à
  reprendre (sans objet ici, aucune n'existe) ;
- des migrations de base de données sont livrées : `python manage.py migrate`
  après la mise à jour.

### Procédure

```bash
pip install --upgrade "django-allauth>=65.14.1"
python manage.py migrate
python manage.py check
```

Puis reprendre les trois réglages du tableau ci-dessus et vérifier que la
connexion maison (`/connexion/`) fonctionne toujours — elle n'utilise pas
allauth, mais le backend et le middleware restent dans la chaîne de traitement.

---

## Recommandation

Partir sur l'**option A**. Retirer un paquet inutilisé supprime trois
vulnérabilités, allège la chaîne d'authentification et évite une migration de
réglages sans contrepartie. Le seul argument pour l'option B serait un projet
d'ouverture de la connexion par Google ou Facebook — auquel cas autant installer
la 65.x le moment venu.

Dans les deux cas, l'action reste à décider : rien n'a été modifié.
