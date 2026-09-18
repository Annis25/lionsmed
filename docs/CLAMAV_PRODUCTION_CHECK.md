# ClamAV — procédure de mise en service (à exécuter plus tard sur le serveur)

Ces commandes n’ont pas été exécutées en production. L’audit local du 15 septembre 2026
constate : paquet `clamav-daemon` absent, service inactif, `check_antivirus` en échec.
Les documents restent refusés tant que le scanner ne confirme pas leur innocuité.

## Installation et signatures (Debian/Ubuntu)

```sh
sudo apt update
sudo apt install clamav clamav-daemon
sudo systemctl stop clamav-freshclam
sudo freshclam
sudo systemctl enable --now clamav-freshclam
sudo systemctl enable --now clamav-daemon
sudo systemctl status clamav-daemon --no-pager
sudo journalctl -u clamav-daemon -n 40 --no-pager
```

Adapter les noms de services à la distribution. Vérifier les erreurs de chargement des
signatures avant de déclarer le service disponible.

## Socket et droits

Dans `/etc/clamav/clamd.conf`, vérifier `LocalSocket /run/clamav/clamd.ctl` et les droits
de ce socket. Le compte système exécutant Gunicorn et les commandes Django doit pouvoir
s’y connecter (groupe `clamav`, socket accessible à ce groupe). Ne pas rendre le socket
accessible à tous. Redémarrer les processus applicatifs après changement des groupes.

```sh
sudo stat /run/clamav/clamd.ctl
sudo systemctl restart clamav-daemon
```

Configurer dans l’environnement du runtime :

```text
LIONSMED_CLAMD_SOCKET=/run/clamav/clamd.ctl
```

Alternative TCP : `LIONSMED_CLAMD_HOST` et `LIONSMED_CLAMD_PORT`, sur une interface privée
protégée. Ne jamais exposer clamd sur Internet. Une configuration socket prime sur TCP.

Depuis le runtime et sous **le même utilisateur système** que l’application :

```sh
.venv/bin/python manage.py check_antivirus --settings=config.settings.production
```

Résultat attendu : PONG et version ClamAV ; code de sortie non nul si indisponible.
Cette commande ne transmet aucun fichier utilisateur. Le health check ne remplace pas
la recette INSTREAM ci-dessous.

## Recette de bout en bout et indisponibilité

Sur un environnement de recette, avec données synthétiques uniquement :

1. Soumettre un PDF synthétique valide : accepté après `stream: OK`.
2. Soumettre au scanner la chaîne de test officielle EICAR : résultat détecté,
   aucun document disponible. Ne jamais utiliser un malware réel.
3. Rendre le scanner indisponible dans cet environnement : health check en erreur,
   upload refusé, aucun fichier/document disponible.
4. Restaurer le scanner, vérifier à nouveau le health check et un dépôt sain.

Ne pas interrompre le scanner de production pour cette recette. Les tests Django
simulent aussi virus, timeout, réponse inattendue et exception : ils ne prouvent pas
que le service du serveur est installé ou que ses signatures sont à jour.

Surveiller `clamav-daemon`, `clamav-freshclam` et `check_antivirus`. Une défaillance
ne doit jamais entraîner un contournement de l’antivirus ni une acceptation silencieuse.
