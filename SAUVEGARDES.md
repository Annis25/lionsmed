# Sauvegardes

## Ce qui est sauvegardé

| Volet | Contenu | Outil |
|---|---|---|
| Base de données | Tout le contenu du site et des comptes | `dbbackup` |
| `media/` | Images d'événements, d'articles, photos de profil | `mediabackup` |
| `private_media/` | Documents internes (PV, rapports, règlements) | archive `tar.gz` dédiée |

Le troisième volet mérite une explication : depuis la correction B1, les documents
confidentiels sont stockés hors de `MEDIA_ROOT`. `mediabackup` ne les voit donc
pas. La commande `backup_all` ajoute cette archive — c'est la raison d'être de
cette commande plutôt qu'un simple appel à `dbbackup && mediabackup`.

## Lancer une sauvegarde

```bash
python manage.py backup_all
```

Options :

- `--quiet` — sortie réduite, pour les tâches planifiées
- `--no-cleanup` — conserve tout, sans appliquer la rétention

## Destination

Par défaut `../lionsmed_backups/`, soit **hors du dépôt Git**. À changer par
variable d'environnement :

```bash
BACKUP_ROOT=/mnt/sauvegardes/lionsmed
```

> **Une sauvegarde sur le même disque que la base ne protège pas d'une panne
> disque.** Le dossier par défaut convient au développement ; en production,
> pointer vers un montage distant (NAS, stockage objet) ou synchroniser le
> dossier vers un hébergement tiers après chaque sauvegarde.

## Rétention

| Variable | Défaut | Effet |
|---|---|---|
| `BACKUP_KEEP` | 30 | sauvegardes de base conservées |
| `BACKUP_KEEP_MEDIA` | 10 | archives média et documents privés conservées |

À 30 sauvegardes quotidiennes, la fenêtre de récupération est d'un mois.

## Tâche planifiée

`crontab -e` sous l'utilisateur qui fait tourner l'application :

```cron
# Sauvegarde quotidienne à 3h15
15 3 * * * cd /chemin/vers/lionsmed && /chemin/vers/venv/bin/python manage.py backup_all --quiet >> /var/log/lionsmed-backup.log 2>&1
```

Le `cd` est indispensable : `manage.py` résout les chemins relativement au
répertoire courant. Penser aussi à faire tourner `/var/log/lionsmed-backup.log`
via logrotate.

Alternative systemd (préférable si le serveur utilise déjà des timers) :

```ini
# /etc/systemd/system/lionsmed-backup.service
[Unit]
Description=Sauvegarde Lions Club Sfax-Méditerranée

[Service]
Type=oneshot
User=lionsmed
WorkingDirectory=/chemin/vers/lionsmed
ExecStart=/chemin/vers/venv/bin/python manage.py backup_all --quiet
```

```ini
# /etc/systemd/system/lionsmed-backup.timer
[Unit]
Description=Sauvegarde quotidienne Lions Club

[Timer]
OnCalendar=*-*-* 03:15:00
Persistent=true

[Install]
WantedBy=timers.target
```

```bash
systemctl enable --now lionsmed-backup.timer
```

`Persistent=true` rattrape une exécution manquée si le serveur était éteint.

## Restauration

### Base de données

```bash
python manage.py dbrestore
```

Sans argument, la dernière sauvegarde est proposée. Pour choisir un fichier
précis :

```bash
python manage.py dbrestore -i lionsmed-20260820-131422.sqlite3
```

En SQLite, une restauration à chaud est aussi possible : arrêter le site,
remplacer `db.sqlite3` par le fichier de sauvegarde, redémarrer.

### Médias publics

```bash
python manage.py mediarestore
```

### Documents privés

```bash
tar xzf ../lionsmed_backups/lionsmed-private-<horodatage>.tar.gz -C /chemin/vers/lionsmed/
```

L'archive contient le dossier `private_media/` à sa racine : l'extraire depuis la
racine du projet le remet à sa place.

## Vérifier que les sauvegardes fonctionnent

Une sauvegarde jamais restaurée n'est pas une sauvegarde. À contrôler
**trimestriellement** :

1. Copier la dernière sauvegarde vers un dossier de travail séparé ;
2. Restaurer dans une base de test (ne jamais tester sur la production) ;
3. Compter les enregistrements principaux et les comparer à la production :

```bash
python manage.py shell -c "
from django.contrib.auth import get_user_model
from events.models import Event
from news.models import Article
from members.models import Document
print('utilisateurs', get_user_model().objects.count())
print('événements  ', Event.objects.count())
print('articles    ', Article.objects.count())
print('documents   ', Document.objects.count())
"
```

4. Vérifier qu'un document confidentiel restauré s'ouvre correctement.

Consigner la date de chaque test réussi : en cas d'incident, savoir quand la
restauration a été validée pour la dernière fois change la façon de réagir.

## Surveillance

Le cron ci-dessus écrit dans un journal mais ne prévient personne en cas
d'échec. Tant qu'aucune alerte n'est en place, **relire le journal
périodiquement** — une sauvegarde silencieusement cassée depuis trois semaines
est le scénario classique.

Piste : faire suivre la commande d'un appel à un service de surveillance de
tâches planifiées, qui alerte lorsqu'un signal attendu n'arrive pas.

## Après le passage à PostgreSQL

`django-dbbackup` détecte le moteur actif et bascule seul sur `pg_dump` /
`pg_restore`. Aucun changement de configuration n'est nécessaire, mais
**relancer une sauvegarde et une restauration de test juste après la bascule**
pour confirmer que `pg_dump` est accessible dans le `PATH` du service.
