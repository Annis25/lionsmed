# Déploiement — lionsmed rebuild

Procédure opérationnelle. Aucun secret réel ci-dessous ; `.env.example` liste les variables à renseigner.

## 1. Installation

```sh
sudo apt install postgresql-16 clamav-daemon nginx
python3 -m venv rebuild/.venv
rebuild/.venv/bin/pip install -r rebuild/requirements.txt
cp rebuild/.env.example rebuild/.env && chmod 600 rebuild/.env
# Renseigner rebuild/.env : DJANGO_SECRET_KEY (≥50 car.), DB_*, DJANGO_ALLOWED_HOSTS,
# DJANGO_SITE_ORIGIN=https://lionsmed.tn, LIONSMED_CLAMD_SOCKET, LIONSMED_SATISFACTION_HOUR,
# LIONSMED_SMTP_ENABLED + EMAIL_*, LIONSMED_CONTACT_RECIPIENT.
```

Créer la base PostgreSQL dédiée (jamais la base legacy) :

```sh
sudo -u postgres psql -c "CREATE ROLE lionsmed_rebuild LOGIN PASSWORD '...';"
sudo -u postgres psql -c "CREATE DATABASE lionsmed_rebuild_prod OWNER lionsmed_rebuild;"
sudo -u postgres psql -d lionsmed_rebuild_prod -c "CREATE EXTENSION IF NOT EXISTS btree_gist;"
```

`DB_NAME` doit commencer par `lionsmed_rebuild_` ; la commande `migrate` refuse toute base
portant une table legacy connue (`apps/core/management/commands/migrate.py`).

## 2. Antivirus (ClamAV) — obligatoire avant d'ouvrir les documents privés

```sh
sudo systemctl enable --now clamav-daemon
sudo systemctl status clamav-daemon
```

Renseigner `LIONSMED_CLAMD_SOCKET=/var/run/clamav/clamd.ctl` (ou `LIONSMED_CLAMD_HOST`/`_PORT`
si TCP). **Sans cette configuration, `apps.documents.services.upload_document` refuse tout
dépôt** (échec fermé volontaire, voir `apps/documents/scanning.py`). Vérifier après
démarrage :

```sh
echo "test" | nc -U /var/run/clamav/clamd.ctl  # ou PING via zINSTREAM applicatif
```

## 3. Migrations, statiques, comptes

```sh
rebuild/.venv/bin/python rebuild/manage.py check --deploy --settings=config.settings.production
rebuild/.venv/bin/python rebuild/manage.py migrate --settings=config.settings.production
rebuild/.venv/bin/python rebuild/manage.py collectstatic --noinput --settings=config.settings.production
rebuild/.venv/bin/python rebuild/manage.py createsuperuser --settings=config.settings.production
```

Créer les comptes personnels réels puis attribuer les rôles (jamais via l'admin) :

```sh
rebuild/.venv/bin/python rebuild/manage.py grant_role --actor <UUID_technique> --user <UUID_personnel> --role PRESIDENT
```

Activer le MFA pour SUPER_ADMIN/PRESIDENT/SECRETAIRE dès la première connexion :
`/espace/authentification-forte/` (TOTP + 10 codes de récupération à conserver hors ligne).

## 4. Répertoires privés

```sh
sudo mkdir -p /srv/lionsmed/private_media /srv/lionsmed/public_images
sudo chown www-data:www-data /srv/lionsmed/private_media /srv/lionsmed/public_images
sudo chmod 700 /srv/lionsmed/private_media
```

Pointer `PRIVATE_MEDIA_ROOT`/`PUBLIC_IMAGE_ROOT` (variables d'environnement ou surcharge de
`config/settings/production.py`) vers ces chemins. **Jamais servis par Nginx directement** :
tout accès passe par les vues Django (`documents:download`, `members:photo`, `editorial:image`).

## 5. Serveur applicatif (Gunicorn) — exemple systemd

`/etc/systemd/system/lionsmed-rebuild.service` :

```ini
[Unit]
Description=lionsmed rebuild (gunicorn)
After=network.target postgresql.service clamav-daemon.service

[Service]
User=www-data
WorkingDirectory=/srv/lionsmed/rebuild
EnvironmentFile=/srv/lionsmed/rebuild/.env
ExecStart=/srv/lionsmed/rebuild/.venv/bin/gunicorn config.wsgi:application \
    --bind unix:/run/lionsmed/gunicorn.sock --workers 3 --timeout 30
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

## 6. Reverse proxy (Nginx) — HTTPS obligatoire

```nginx
server {
    listen 443 ssl http2;
    server_name lionsmed.tn;
    ssl_certificate     /etc/letsencrypt/live/lionsmed.tn/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/lionsmed.tn/privkey.pem;

    location /static/ { alias /srv/lionsmed/rebuild/runtime/staticfiles/; }
    location / {
        proxy_pass http://unix:/run/lionsmed/gunicorn.sock;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
server { listen 80; server_name lionsmed.tn; return 301 https://$host$request_uri; }
```

`SECURE_PROXY_SSL_HEADER` n'est **pas** activé dans `config/settings/production.py` tant que
ce proxy exact n'est pas en place : l'activer sans un proxy qui garantit `X-Forwarded-Proto`
fiable permettrait une usurpation HTTPS. À activer explicitement (`("HTTP_X_FORWARDED_PROTO", "https")`)
une fois Nginx confirmé en frontal unique.

Journaux Nginx : exclure `/reinitialiser/` et `/espace/documents/*/telecharger/` d'un logging
verbeux (query string) si un module de log étendu est ajouté — les URLs elles-mêmes ne
portent pas de secret ici, mais éviter tout ajout futur qui journaliserait un corps de requête.

## 7. Scheduler outbox / rappels (systemd timers — pas de Celery)

Un seul mécanisme d'envoi (`OutboxMessage`/`deliver_outbox`), déjà en place. **Sans ces
timers actifs, les messages restent indéfiniment `PENDING`** (incident déjà rencontré en
production : outbox alimentée normalement, mais jamais livrée faute de worker planifié).

Unités versionnées dans `rebuild/deploy/systemd/` (`lionsmed-outbox.service/.timer`,
`lionsmed-event-reminders.service/.timer`) — voir `rebuild/deploy/systemd/README.md`
pour l'installation, la vérification et la fréquence de chacune. Adapter `User`,
`Group`, `WorkingDirectory` et `EnvironmentFile` au chemin réel du serveur avant copie.

```sh
sudo cp rebuild/deploy/systemd/lionsmed-*.service rebuild/deploy/systemd/lionsmed-*.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now lionsmed-outbox.timer lionsmed-event-reminders.timer
systemctl list-timers lionsmed-*
journalctl -u lionsmed-outbox.service -n 50
```

`select_for_update(skip_locked)` dans `deliver_batch` rend un chevauchement de deux exécutions
inoffensif (pas de verrou externe nécessaire). Superviser via
`rebuild/.venv/bin/python manage.py outbox_status --settings=config.settings.production`
(compteurs par état, âge du plus ancien `PENDING`, jamais de destinataire ni de contenu) :
messages `FAILED` en hausse, `PENDING` anormalement ancien, ou timer `inactive`/absent de
`systemctl list-timers`.

## 8. Sauvegardes / restauration

```sh
# Sauvegarde (à planifier, ex. systemd timer quotidien)
pg_dump -Fc -h <host> -U lionsmed_rebuild -d lionsmed_rebuild_prod -f /srv/backups/db-$(date +%F).pgcustom
tar czf /srv/backups/private_media-$(date +%F).tar.gz -C /srv/lionsmed private_media
tar czf /srv/backups/public_images-$(date +%F).tar.gz -C /srv/lionsmed public_images
# Conserver .env séparément, chiffré, hors du dépôt de sauvegardes courant.
```

Restauration (**testée** sur cet environnement de développement, voir BUILD_PROGRESS.md
Phase C — comptages `django_migrations` identiques avant/après) :

```sh
createdb -O lionsmed_rebuild -h <host> -U lionsmed_rebuild lionsmed_rebuild_restore
pg_restore -h <host> -U lionsmed_rebuild -d lionsmed_rebuild_restore --no-owner db-<date>.pgcustom
tar xzf private_media-<date>.tar.gz -C /chemin/restauration
rebuild/.venv/bin/python manage.py migrate --check --settings=config.settings.production  # doit être propre
```

Tester la restauration **avant** d'en avoir besoin, sur un environnement séparé — un backup
non restauré au moins une fois n'est pas fiable par simple existence.

## 9. Indexation publique

Ne pas définir `LIONSMED_PUBLIC_INDEXING=true` tant que : textes légaux validés, contenu
institutionnel confirmé, domaine et certificat en place. Activation :

```sh
# Dans rebuild/.env, une fois tout validé :
LIONSMED_PUBLIC_INDEXING=true
sudo systemctl restart lionsmed-rebuild
```

Vérifier ensuite `/robots.txt` (`Allow: /`) et `/sitemap.xml` (uniquement contenus publiés).

## 10. Rollback

- Application : `systemctl stop lionsmed-rebuild`, redéployer la révision précédente, `migrate` n'est pas automatiquement réversible pour toutes les migrations — vérifier au cas par cas avant `migrate <app> <migration_précédente>`.
- Base : restaurer le dump précédent (procédure §8) sur une base neuve, basculer `DB_NAME`, ne jamais écraser une base contenant des écritures plus récentes sans plan de réconciliation.
- Legacy : reste en lecture seule pendant toute bascule (voir `MIGRATE_LEGACY_TO_REBUILD.md` §6) ; aucune suppression du legacy prévue à ce stade.
