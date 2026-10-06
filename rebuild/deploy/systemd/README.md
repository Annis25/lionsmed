# Timers systemd — outbox e-mail et rappels

Unités versionnées ici, à copier telles quelles sur le serveur (adapter `User`,
`Group`, `WorkingDirectory` et `EnvironmentFile` si le chemin de déploiement diffère
de `/var/www/lionsmed/rebuild`, `User=ubuntu` / `Group=www-data`).

## Installation

```sh
sudo cp deploy/systemd/lionsmed-outbox.service deploy/systemd/lionsmed-outbox.timer \
        deploy/systemd/lionsmed-event-reminders.service deploy/systemd/lionsmed-event-reminders.timer \
        /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now lionsmed-outbox.timer
sudo systemctl enable --now lionsmed-event-reminders.timer
```

Relève des boîtes e-mail institutionnelles (Messagerie) — à n'installer qu'une fois les mots de
passe des boîtes ajoutés au fichier `.env` (voir `docs/DEPLOY_REBUILD.md`, « Boîtes e-mail
institutionnelles ») :

```sh
sudo cp deploy/systemd/lionsmed-mailboxes.service deploy/systemd/lionsmed-mailboxes.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now lionsmed-mailboxes.timer
```

## Vérification

```sh
systemctl status lionsmed-outbox.timer          # doit afficher "active (waiting)"
systemctl list-timers --all | grep lionsmed
journalctl -u lionsmed-outbox.service -n 50
```

`inactive (dead)` est **normal** pour `lionsmed-outbox.service` et
`lionsmed-event-reminders.service` : ce sont des unités `Type=oneshot`, elles ne
tournent pas en continu — seul le `.timer` correspondant doit être `active (waiting)`.

## Fréquences

- `lionsmed-outbox.timer` : toutes les minutes (`deliver_outbox --limit 20`). Deux
  exécutions qui se chevauchent ne posent pas de problème : `deliver_batch()` utilise
  `select_for_update(skip_locked=True)`, donc un message n'est jamais pris deux fois.
- `lionsmed-event-reminders.timer` : une fois par jour à 07:00 (`send_event_reminders`).
  Idempotent par construction (`event_key` inclut la date de version de l'événement) :
  exécuter la commande plusieurs fois le même jour ne crée pas de doublon.

- `lionsmed-mailboxes.timer` : toutes les deux minutes (`sync_mailboxes`). Lecture seule sur le
  serveur de messagerie, une boîte après l'autre. Sans doublon par construction (UID et empreinte
  du message uniques) ; deux exécutions qui se chevauchent ne traitent pas la même boîte (bail en
  base). Une boîte en panne est réessayée de plus en plus rarement — jusqu'à 30 minutes pour une
  coupure, 6 heures pour un mot de passe refusé — afin de ne pas faire bannir le serveur par
  l'hébergeur de messagerie. Passer à une minute est possible (`OnUnitActiveSec=1min`) si
  l'hébergeur ne limite pas le nombre de connexions.

## Surveillance opérationnelle

Pas de supervision externe complexe — un administrateur vérifie périodiquement :

```sh
rebuild/.venv/bin/python manage.py outbox_status --settings=config.settings.production
```

Signaux à surveiller :
- `FAILED` élevé ou en hausse continue → SMTP indisponible ou mal configuré ;
- « Plus ancien PENDING » anormalement grand (plusieurs dizaines de minutes) → le timer
  ne tourne plus (`systemctl status lionsmed-outbox.timer`) ou le SMTP est bloqué ;
- timer `inactive`/absent de `systemctl list-timers` → le service n'a pas été activé
  ou a été désactivé par erreur.

`outbox_status` n'affiche jamais destinataire, sujet, contenu ni jeton — uniquement des
compteurs par état.

Pour les boîtes institutionnelles :

```sh
rebuild/.venv/bin/python manage.py mailbox_status --settings=config.settings.production
journalctl -u lionsmed-mailboxes.service -n 50
```

`mailbox_status` indique, par boîte, si elle est reliée, quand elle a été relevée pour la
dernière fois, le nombre de titulaires actuels et de messages. Codes d'erreur possibles :
`auth_failed` (mot de passe refusé : corriger `.env`), `unreachable` (serveur injoignable),
`tls_error` (certificat du serveur refusé), `protocol_error`, `unexpected`. Ni cette commande
ni le journal n'affichent de mot de passe, d'expéditeur, d'objet ou de contenu.
