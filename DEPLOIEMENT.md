# Déploiement — lionsmed.tn

Ce document couvre ce que la configuration Django suppose du serveur. Plusieurs
protections mises en place dans le code **ne tiennent que si nginx est configuré
en conséquence** : ce ne sont pas des recommandations de confort.

Documents liés : `SAUVEGARDES.md`, `MIGRATION_POSTGRES.md`,
`ALLAUTH_UPGRADE_NOTES.md`, `.env.example`.

---

## 1. Le point critique : `X-Forwarded-Proto`

`settings.py` active en production :

```python
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
```

Django considère alors comme **sécurisée** toute requête portant l'en-tête
`X-Forwarded-Proto: https`. Cet en-tête vient du réseau : il n'est digne de
confiance que si le proxy le réécrit systématiquement.

### Ce qui se passe si nginx transmet l'en-tête au lieu de l'écraser

Un client envoie directement :

```
GET /espace-membre/ HTTP/1.1
Host: lionsmed.tn
X-Forwarded-Proto: https
```

sur une connexion **en clair**. Django croit la requête chiffrée. Conséquences :

- `SECURE_SSL_REDIRECT` ne redirige plus — le trafic reste en HTTP ;
- `request.is_secure()` renvoie `True` à tort ;
- les cookies de session et CSRF marqués `Secure` sont émis sur une connexion
  non chiffrée, donc interceptables.

La protection HTTPS entière repose sur cette seule ligne de configuration nginx.

### Configuration correcte

```nginx
proxy_set_header X-Forwarded-Proto $scheme;
```

`$scheme` est le protocole **réellement vu par nginx**. Cette directive écrase
toute valeur envoyée par le client. Ne jamais utiliser
`$http_x_forwarded_proto`, qui reprendrait la valeur du client.

### Vérification après déploiement

Depuis une machine extérieure :

```bash
curl -sS -o /dev/null -w '%{http_code} %{redirect_url}\n' \
  -H 'X-Forwarded-Proto: https' http://lionsmed.tn/contact/
```

Résultat attendu : **`301 https://lionsmed.tn/contact/`** — nginx a écrasé
l'en-tête, Django redirige malgré tout vers HTTPS.

Si la réponse est `200`, l'en-tête forgé a traversé : la configuration est
vulnérable, à corriger avant l'ouverture au public.

---

## 2. Configuration nginx de référence

```nginx
server {
    listen 80;
    server_name lionsmed.tn www.lionsmed.tn;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name lionsmed.tn www.lionsmed.tn;

    ssl_certificate     /etc/letsencrypt/live/lionsmed.tn/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/lionsmed.tn/privkey.pem;

    client_max_body_size 20M;   # cohérent avec les limites d'upload Django

    # ── Fichiers statiques (générés par collectstatic) ──
    location /static/ {
        alias /chemin/vers/lionsmed/staticfiles/;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    # ── Médias publics : images d'événements, d'articles, photos de profil ──
    location /media/ {
        alias /chemin/vers/lionsmed/media/;
        expires 7d;
        # Empêche l'interprétation d'un fichier envoyé par un utilisateur
        add_header X-Content-Type-Options nosniff;
    }

    # ── Documents internes : JAMAIS servis directement ──
    # Ils vivent dans private_media/, hors de MEDIA_ROOT. Aucune règle nginx ne
    # doit y donner accès : le téléchargement passe par une vue Django qui
    # contrôle le rôle du demandeur (voir §3).
    location /private_media/ {
        deny all;
        return 404;
    }

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host              $host;
        proxy_set_header X-Real-IP         $remote_addr;
        proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
        # ── Ligne critique, voir §1 ──
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

### `client_max_body_size`

Fixé à 20 Mo, au-dessus des limites applicatives (5 Mo par image, 15 Mo par
document). Une valeur trop basse produit une erreur nginx brute `413`, sans le
message d'erreur explicite du formulaire Django.

---

## 3. Documents internes — ne pas les exposer

Depuis la correction B1, `Document.file` est stocké dans `private_media/`,
**hors** de `MEDIA_ROOT`. L'accès passe uniquement par
`/espace-membre/documents/<id>/telecharger/`, qui vérifie le rôle avant de
renvoyer le fichier.

À ne jamais faire :

```nginx
# ✗ Réintroduirait la fuite corrigée en B1
location /private_media/ {
    alias /chemin/vers/lionsmed/private_media/;
}
```

### Vérification

```bash
curl -sS -o /dev/null -w '%{http_code}\n' https://lionsmed.tn/private_media/documents/
curl -sS -o /dev/null -w '%{http_code}\n' https://lionsmed.tn/media/documents/
```

Les deux doivent répondre `403` ou `404`, jamais `200` ni un index de
répertoire.

---

## 4. Variables d'environnement

Copier `.env.example` en `.env` sur le serveur et le renseigner. L'application
**refuse de démarrer** si `SECRET_KEY` ou `EMAIL_HOST` manquent — un oubli est
donc détecté au démarrage, pas en production silencieuse.

```bash
DEBUG=False
SECRET_KEY=<généré, jamais celui du poste de développement>
EMAIL_HOST=...
EMAIL_HOST_USER=...
EMAIL_HOST_PASSWORD=...
DEFAULT_FROM_EMAIL=secretariat@lionsmed.tn
BACKUP_ROOT=/mnt/sauvegardes/lionsmed
LOG_DIR=/var/log/lionsmed          # optionnel, défaut : logs/ dans le projet
```

Générer la clé :

```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

Permissions : `chmod 600 .env`, propriétaire = utilisateur applicatif.

---

## 5. Procédure de déploiement

```bash
git pull
pip install -r requirements.txt
python manage.py migrate
python manage.py collectstatic --noinput     # ← indispensable
python manage.py createcachetable            # première installation seulement
python manage.py check --deploy              # doit signaler 0 problème
systemctl restart lionsmed
```

### `collectstatic` n'est pas optionnel — à lancer à CHAQUE déploiement

Deux raisons cumulées le rendent obligatoire :

1. **`staticfiles/` n'est plus versionné.** Le dossier a été retiré du suivi Git
   (c'est du contenu généré, source de conflits et de fichiers périmés). Un
   `git clone` ou un `git pull` ne le fournit donc plus : seul `collectstatic`
   le produit.
2. **Le stockage utilise un manifeste.** `STORAGES['staticfiles']` s'appuie sur
   `CompressedManifestStaticFilesStorage`, qui exige le fichier
   `staticfiles/staticfiles.json`. En son absence, **toutes les pages
   échouent** — pas seulement les images — avec :
   ```
   ValueError: Missing staticfiles manifest entry for 'css/main.css'
   ```

L'ordre importe : lancer `collectstatic` **avant le premier accès au site**,
donc avant le redémarrage du service, jamais après.

À intégrer au script de déploiement, sans condition ni raccourci « seulement si
les fichiers statiques ont changé » : le manifeste doit refléter l'état courant
à chaque mise en production.

Contrôle après déploiement :

```bash
test -f staticfiles/staticfiles.json && echo "manifeste présent" || echo "MANIFESTE ABSENT — le site va échouer"
```

---

## 6. HSTS — montée progressive

`SECURE_HSTS_SECONDS` est volontairement à **300 secondes** (5 minutes).

HSTS demande aux navigateurs de refuser toute connexion HTTP au domaine pendant
la durée annoncée. La consigne est mémorisée côté client et **ne peut pas être
révoquée à distance** : en cas de problème de certificat, le site devient
inaccessible pour tous les visiteurs déjà venus, jusqu'à expiration.

Palier recommandé :

| Étape | Valeur | Quand |
|---|---|---|
| 1 | `300` (actuel) | mise en ligne |
| 2 | `86400` (1 jour) | après une semaine sans incident TLS |
| 3 | `31536000` (1 an) | après un mois, renouvellement automatique confirmé |

Ne passer à l'étape 3 qu'après avoir vu le certificat se renouveler seul au
moins une fois.

---

## 7. Vérifications post-déploiement obligatoires

**À exécuter depuis une machine extérieure au serveur**, une fois le site en
ligne. Aucune de ces vérifications n'a pu être faite en local : elles dépendent
toutes de la configuration nginx réelle.

Tant que les contrôles 1 à 3 ne sont pas passés, **considérer le site comme non
sécurisé** et ne pas communiquer son adresse aux membres.

---

### 7.1 — La ligne nginx dont tout dépend

`settings.py` active `SECURE_PROXY_SSL_HEADER`, ce qui fait confiance à un
en-tête HTTP. Cette confiance n'est légitime que si nginx **écrase** l'en-tête
reçu au lieu de le transmettre.

La ligne exacte attendue dans le bloc `location / { … }` :

```nginx
proxy_set_header X-Forwarded-Proto $scheme;
```

`$scheme` vaut le protocole réellement vu par nginx. Il écrase toute valeur
envoyée par le client.

**Jamais** `$http_x_forwarded_proto` : cette variable reprend la valeur fournie
par le client, ce qui revient à ne rien vérifier du tout.

Vérifier la présence de la ligne :

```bash
sudo grep -rn 'X-Forwarded-Proto' /etc/nginx/
```

Attendu : au moins une ligne `proxy_set_header X-Forwarded-Proto $scheme;`.
Si la commande ne renvoie rien, ou renvoie `$http_x_forwarded_proto`, corriger
avant d'aller plus loin.

---

### 7.2 — La redirection HTTPS fonctionne sans boucler

```bash
curl -sSI http://lionsmed.tn/ | head -5
```

**Attendu** — une seule redirection vers HTTPS :

```
HTTP/1.1 301 Moved Permanently
Location: https://lionsmed.tn/
```

Puis confirmer que la cible répond bien, sans redirection supplémentaire :

```bash
curl -sS -o /dev/null -w 'code=%{http_code} redirections=%{num_redirects}
' \
  -L --max-redirs 5 http://lionsmed.tn/
```

**Attendu** : `code=200 redirections=1`

| Résultat | Interprétation |
|---|---|
| `code=200 redirections=1` | correct |
| `code=200 redirections=0` | HTTP n'est pas redirigé — vérifier le bloc `listen 80` |
| erreur `Maximum (5) redirects followed` | **boucle de redirection** : nginx transmet HTTPS à Django en HTTP. La ligne du §7.1 est absente ou incorrecte |

---

### 7.3 — Un en-tête forgé ne doit pas usurper le HTTPS

C'est le contrôle le plus important, et le seul qui teste réellement §7.1.

On envoie une requête **en clair** en prétendant venir de HTTPS :

```bash
curl -sSI -H 'X-Forwarded-Proto: https' http://lionsmed.tn/ | head -3
```

| Réponse | Signification |
|---|---|
| **`301` + `Location: https://…`** | **correct** — nginx a écrasé l'en-tête, Django redirige quand même |
| **`200`** | **faille** — l'en-tête forgé a traversé : la redirection HTTPS se contourne, `request.is_secure()` ment, et les cookies marqués `Secure` sont émis en clair. Corriger §7.1 immédiatement |

Même contrôle sur une page authentifiée, où l'enjeu est le cookie de session :

```bash
curl -sSI -H 'X-Forwarded-Proto: https' http://lionsmed.tn/espace-membre/ | head -3
```

Attendu : `301` vers HTTPS. Un `302` vers `/connexion/` signifie que Django a
traité la requête comme sécurisée — même conclusion que ci-dessus.

---

### 7.4 — Les documents internes restent inaccessibles

```bash
curl -sS -o /dev/null -w '%{http_code}\n' https://lionsmed.tn/private_media/
curl -sS -o /dev/null -w '%{http_code}\n' https://lionsmed.tn/private_media/documents/
curl -sS -o /dev/null -w '%{http_code}\n' https://lionsmed.tn/media/documents/
```

**Attendu** : `403` ou `404` pour les trois. Un `200`, ou pire un index de
répertoire, signifie que la fuite corrigée en B1 a été réintroduite par la
configuration nginx.

---

### 7.5 — En-têtes de sécurité et mode debug

```bash
curl -sSI https://lionsmed.tn/ | grep -iE 'strict-transport|x-frame|x-content-type'
```

**Attendu** : les trois en-têtes présents, dont
`Strict-Transport-Security: max-age=300; includeSubDomains; preload`
(voir §6 pour la montée progressive de cette valeur).

```bash
curl -sS https://lionsmed.tn/page-inexistante-test | grep -ci -e traceback -e 'DEBUG = True'
```

**Attendu** : `0`. Toute autre valeur signifie que `DEBUG` est resté actif.

---

### 7.6 — Fichiers statiques servis

```bash
curl -sS -o /dev/null -w '%{http_code}\n' https://lionsmed.tn/
```

**Attendu** : `200`. Un `500` sur la page d'accueil indique presque toujours un
manifeste absent — `collectstatic` n'a pas été exécuté (voir §5).

---

### 7.7 — Contrôles manuels dans un navigateur

- connexion d'un membre, y compris **avec l'adresse saisie en majuscules** ;
- téléchargement d'un document selon le rôle : un membre simple ne doit pas voir
  les documents réservés au bureau, et l'URL directe du fichier doit échouer ;
- envoi du formulaire de contact, puis vérification de la **réception effective**
  du message (le backend SMTP ne masque plus les échecs depuis la correction B8) ;
- 5 tentatives de connexion erronées : la 5ᵉ doit afficher la page de
  verrouillage ;
- lancement d'une sauvegarde : `python manage.py backup_all`.

---

### Récapitulatif

| # | Contrôle | Attendu | Si échec |
|---|---|---|---|
| 7.1 | `proxy_set_header X-Forwarded-Proto $scheme;` présent | ligne trouvée | corriger nginx, tout le reste en dépend |
| 7.2 | `curl -I http://lionsmed.tn/` | `301` → https, 1 seule redirection | boucle = §7.1 manquant |
| 7.3 | En-tête forgé sur HTTP | `301` vers https | `200` = **faille ouverte** |
| 7.4 | `/private_media/`, `/media/documents/` | `403`/`404` | fuite de documents |
| 7.5 | En-têtes de sécurité, absence de traceback | présents, `0` | `DEBUG` actif ou HSTS absent |
| 7.6 | Page d'accueil | `200` | `collectstatic` non lancé |

---

## 8. Journalisation

Les journaux applicatifs sont écrits dans `LOG_DIR` (défaut : `logs/` à la
racine du projet), en rotation sur 5 fichiers de 5 Mo.

- `lionsmed.log` — journal général, niveau INFO et au-dessus
- `securite.log` — connexions échouées, verrouillages, actions d'administration

Le dossier doit être **accessible en écriture par l'utilisateur applicatif** :

```bash
mkdir -p /var/log/lionsmed
chown lionsmed:lionsmed /var/log/lionsmed
```

Prévoir une rotation système (logrotate) si `LOG_DIR` pointe vers `/var/log`,
en complément de la rotation applicative.
