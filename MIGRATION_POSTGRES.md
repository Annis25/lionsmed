# Migration SQLite → PostgreSQL

**Statut : procédure validée par une migration de test réussie (20 août 2026).**
La bascule en production n'a pas été faite — elle reste une décision
d'exploitation. Ce document décrit la procédure telle qu'elle a été
**réellement exécutée et corrigée**, et non plus telle qu'imaginée.

> Les sections marquées **⚑ Corrigé après essai** signalent les endroits où la
> procédure initiale était inexacte. Voir aussi §Résultats de la migration test
> en fin de document.

---

## Pourquoi migrer

SQLite verrouille la base entière à chaque écriture. Tant que le site ne fait que
servir des pages publiques, cela ne se voit pas. Les écritures concurrentes de
l'espace membre changent la donne :

- **Votes** — plusieurs membres votant dans la même minute lors d'une assemblée ;
- **Inscriptions aux événements** — pic à l'ouverture des inscriptions ;
- **Notifications en masse** — `bulk_create` sur l'ensemble des membres ;
- **Cache en base** — `DatabaseCache` ajoute des écritures à chaque requête soumise
  au rate limiting.

Le symptôme est une erreur `database is locked` renvoyée à l'utilisateur : le
vote n'est pas enregistré.

**⚑ Corrigé après essai — mesures réelles.** Un test de 40 membres votant
simultanément sur le même scrutin a donné :

| Configuration | Votes enregistrés | « database is locked » | Durée |
|---|---|---|---|
| PostgreSQL 16.2 | 40 / 40 | 0 | **33 ms** |
| SQLite, `timeout=20 s` (config actuelle) | 40 / 40 | 0 | **1 171 ms** |
| SQLite, `timeout=0,5 s` | 35 / 40 | 5 | 560 ms |
| SQLite, `timeout=0,05 s` | 18 / 40 | 22 | 108 ms |

Deux enseignements, plus nuancés que ce que ce document affirmait :

1. **Le `timeout=20 s` posé au lot I7 tient mieux que prévu.** À 40 votants
   simultanés, SQLite ne perd aucun vote — il met simplement les écritures en
   file d'attente. Le danger n'est donc pas immédiat.
2. **Mais il est 35× plus lent, et la marge est un délai, pas une capacité.**
   Les écritures se sérialisent : matériel plus lent, transactions plus longues
   ou davantage de votants rapprochent du seuil. Les deux dernières lignes du
   tableau montrent ce qui se passe une fois ce seuil franchi — des votes
   perdus, silencieusement du point de vue du club.

Ordre de grandeur : avec 45 membres, SQLite tiendra. La migration reste
justifiée pour supprimer la question plutôt que de la surveiller, mais
**l'urgence est moindre que ce qui était supposé**.

---

## Prérequis

- PostgreSQL 14 ou supérieur accessible depuis le serveur applicatif
- `psycopg2-binary` déjà présent dans `requirements.txt`
- Une fenêtre de maintenance : le site doit être arrêté pendant la copie

---

## Configuration

Le fichier `settings.py` choisit le moteur dans cet ordre :

1. `DATABASE_URL` présent → PostgreSQL
2. sinon `DB_NAME` présent → PostgreSQL (variables `DB_*`)
3. sinon → SQLite

**⚑ Corrigé après essai — `DATABASE_URL` ne gère pas les sockets Unix.**
Le parseur de `settings.py` s'appuie sur `urlparse`, qui ne sait pas placer un
chemin de socket (`/run/postgresql`) dans le champ hôte : le chemin est absorbé
dans le nom de base et l'hôte retombe sur `localhost`. Sans effet en production
si PostgreSQL est joint en TCP — mais **pour une connexion par socket Unix,
utiliser impérativement la forme `DB_*`**.

Renseigner **l'une** des deux formes dans le `.env` de production :

```bash
# Forme 1 — URL unique (les caractères spéciaux du mot de passe doivent être
# encodés : @ devient %40, : devient %3A, etc.)
DATABASE_URL=postgresql://lions_user:mot%40de%3Apasse@localhost:5432/lionsdb

# Forme 2 — variables séparées (pas d'encodage nécessaire)
DB_NAME=lionsdb
DB_USER=lions_user
DB_PASSWORD=mot@de:passe
DB_HOST=localhost
DB_PORT=5432
```

`DB_CONN_MAX_AGE` (60 s par défaut) contrôle la réutilisation des connexions.

**⚑ Corrigé après essai — protéger les valeurs contenant des caractères
spéciaux.** Lors du test, un `SECRET_KEY` contenant `(`, `$` et `^` a rendu le
fichier d'environnement invalide ; le shell a échoué silencieusement et Django
est **retombé sur SQLite** sans le signaler. Encadrer toute valeur contenant des
métacaractères par des apostrophes simples :

```bash
DB_PASSWORD='mot@de:passe$avec(caracteres)'
```

Et vérifier systématiquement le moteur réellement actif avant toute opération
d'écriture :

```bash
python manage.py shell -c "from django.db import connection; print(connection.settings_dict['ENGINE'], connection.settings_dict['NAME'])"
```

---

## Procédure

### 1. Créer la base

```sql
CREATE DATABASE lionsdb ENCODING 'UTF8' LC_COLLATE 'fr_FR.UTF-8' LC_CTYPE 'fr_FR.UTF-8' TEMPLATE template0;
CREATE USER lions_user WITH PASSWORD '<mot de passe>';
GRANT ALL PRIVILEGES ON DATABASE lionsdb TO lions_user;
ALTER DATABASE lionsdb OWNER TO lions_user;
```

### 2. Sauvegarder l'existant

```bash
cp db.sqlite3 db.sqlite3.avant-migration
tar czf media-avant-migration.tar.gz media/ private_media/
```

### 3. Exporter les données depuis SQLite

Le site doit être arrêté à partir d'ici.

```bash
python manage.py dumpdata \
  --natural-foreign --natural-primary \
  --exclude contenttypes --exclude auth.permission \
  --exclude sessions.session --exclude admin.logentry \
  --exclude axes \
  --indent 2 --output dump_lionsmed.json
```

Les exclusions comptent :

- `contenttypes` et `auth.permission` sont recréés par les migrations ; les
  réimporter provoque des collisions de clés ;
- `sessions.session` : les sessions en cours n'ont pas à être transférées ;
- `admin.logentry` et `axes` : historiques, sans valeur après bascule.

### 4. Créer le schéma sur PostgreSQL

Renseigner `DATABASE_URL` dans le `.env`, puis :

```bash
python manage.py migrate
python manage.py createcachetable
```

### 5. Vider les tables pré-remplies par les migrations

```bash
python manage.py shell -c "
from django.contrib.contenttypes.models import ContentType
from django.contrib.auth.models import Permission
Permission.objects.all().delete()
ContentType.objects.all().delete()
"
```

### 6. Importer

```bash
python manage.py loaddata dump_lionsmed.json
```

### 7. Vérifier avant de rouvrir

```bash
python manage.py shell -c "
from django.contrib.auth import get_user_model
from events.models import Event
from news.models import Article
from members.models import Document, Cotisation
from voting.models import Vote, UserVote
from sitecontent.models import DomainAction, BureauMember
U = get_user_model()
for label, qs in [('utilisateurs', U.objects.all()), ('événements', Event.objects.all()),
                  ('articles', Article.objects.all()), ('documents', Document.objects.all()),
                  ('cotisations', Cotisation.objects.all()), ('votes', Vote.objects.all()),
                  ('bulletins', UserVote.objects.all()), ('domaines', DomainAction.objects.all()),
                  ('bureau', BureauMember.objects.all())]:
    print(f'{label:15} {qs.count()}')
"
```

Comparer ces nombres avec ceux relevés sur SQLite **avant** la migration
(même commande, en repassant `DATABASE_URL` en commentaire).

Puis contrôler manuellement :

- connexion d'un membre ;
- téléchargement d'un document confidentiel selon le rôle ;
- soumission d'un vote ;
- affichage de la page d'accueil (événements et actualités).

### 8. Séquences d'auto-incrément — **⚑ étape inutile, à ne pas exécuter**

Ce document affirmait qu'il fallait rejouer `sqlsequencereset`, en présentant
cette étape comme « la plus souvent oubliée ». **C'était faux pour ce projet.**

Depuis Django 4.1, `loaddata` repositionne lui-même les séquences des modèles
qu'il a chargés. Vérification faite après import, sur les 16 tables portant une
séquence :

```
table                                   max(id)  séquence   état
accounts_user                                11        11   ✓
events_event                                  5         5   ✓
news_article                                  5         5   ✓
members_cotisation                           10        10   ✓
voting_vote                                   2         2   ✓
sitecontent_domainaction                      6         6   ✓
… (16 tables au total)
Séquences en retard : 0
```

Une création d'objet immédiatement après l'import a réussi, sans erreur de clé
dupliquée. **Ne pas exécuter `sqlsequencereset`** : la commande est sans effet
utile ici et son résultat, redirigé vers `dbshell`, ajoute un risque inutile.

Contrôle rapide si l'on veut tout de même s'en assurer :

```bash
python manage.py shell -c "
from django.db import connection
from django.apps import apps
with connection.cursor() as c:
    c.execute(\"SELECT sequencename, last_value FROM pg_sequences WHERE schemaname='public'\")
    seqs = dict(c.fetchall())
for m in apps.get_models():
    if not m._meta.managed or m._meta.pk.name != 'id':
        continue
    seq = f'{m._meta.db_table}_id_seq'
    if seq not in seqs or not m.objects.exists():
        continue
    with connection.cursor() as c:
        c.execute(f'SELECT MAX(id) FROM \\\"{m._meta.db_table}\\\"')
        mx = c.fetchone()[0]
    if seqs[seq] < mx:
        print('RETARD', m._meta.db_table, seqs[seq], '<', mx)
print('contrôle terminé')
"
```

---

## Retour arrière

Tant que `db.sqlite3.avant-migration` est conservé, le retour est immédiat :
retirer `DATABASE_URL` du `.env`, restaurer le fichier, redémarrer. Garder cette
copie au moins une semaine après la bascule.

---

## Alternative : pgloader

`pgloader` copie SQLite vers PostgreSQL sans passer par un export JSON, ce qui
est plus rapide sur de gros volumes. Pour ce projet, `dumpdata`/`loaddata` est
préférable : le volume est faible et l'export JSON reste lisible et vérifiable à
l'œil, ce qui n'est pas le cas d'une copie binaire.

---

## Après la migration

- Retirer le cache en base au profit de Redis si le trafic le justifie
  (`CACHES` dans `settings.py`) ;
- Adapter la sauvegarde : `django-dbbackup` bascule automatiquement sur
  `pg_dump` une fois le moteur PostgreSQL actif (voir `SAUVEGARDES.md`) ;
- Vérifier que la sauvegarde tourne bien sous le nouveau moteur avant de
  supprimer l'ancienne base SQLite.

---

## Résultats de la migration test (20 août 2026)

Migration complète exécutée sur PostgreSQL 16.2, base `lionsdb`, utilisateur
`lions_user`, encodage UTF8 / collation `fr_FR.UTF-8`. La base SQLite du projet
est restée **strictement intacte** (empreinte MD5 identique avant et après).

### Comptages avant / après

| Modèle | SQLite | PostgreSQL |
|---|---|---|
| accounts.user | 11 | 11 |
| accounts.membershiprequest | 3 | 3 |
| events.event | 5 | 5 |
| news.article | 5 | 5 |
| news.category | 5 | 5 |
| members.cotisation | 10 | 10 |
| notifications.notification | 10 | 10 |
| voting.vote | 2 | 2 |
| sitecontent.siteconfig | 1 | 1 |
| sitecontent.domainaction | 6 | 6 |
| sitecontent.clubvalue | 6 | 6 |
| sitecontent.bureaumember | 5 | 5 |
| sitecontent.membershipbenefit | 4 | 4 |
| sitecontent.historicalmilestone | 2 | 2 |
| sitecontent.clubstats | 1 | 1 |
| **Total métier** | **76** | **76** |

Le dump contient 77 objets : les 76 ci-dessus plus `sites.site`, créé par les
migrations de `django.contrib.sites`. `loaddata` l'écrase sans conflit.

Modèles vides des deux côtés : `events.eventregistration`, `voting.uservote`,
`members.document`, `gallery.album`, `gallery.photo`,
`notifications.emailreminder`.

### Champs sensibles

| Contrôle | Résultat |
|---|---|
| Hachages de mots de passe | **11 / 11 identiques** au bit près (`pbkdf2_sha256`) |
| Connexion réelle avec un hachage migré | **réussie** (compte `mehdi.trabelsi`, HTTP 302 → `/espace-membre/`) |
| Dates `date_joined` | identiques, **aucun décalage de fuseau** |
| Dates `date_start` des événements | identiques |
| Accents (`Méditerranée`, `Éducation`, `—`) | intacts |
| `FileField` / `ImageField` | **aucun fichier en base** : mécanisme validé par un aller-retour de sérialisation (chemin relatif préservé), pas sur données réelles |

### Tests fonctionnels

| Test | Résultat |
|---|---|
| 23 pages (8 publiques, 6 membre, 9 admin) | toutes **200** |
| Pages de détail événement et article (slugs migrés) | 200 |
| Vote via `/espace-membre/votes/` | enregistré, second vote du même membre refusé |
| Contrainte `unique_together` (vote, membre) | **appliquée par la base** (`IntegrityError`) |
| Inscription à un événement | créée, doublon refusé par la base |
| CRUD admin événements (créer / éditer / supprimer) | fonctionnel |
| CRUD admin articles + bascule publication | fonctionnel, `published_at` posé |

### Concurrence

40 membres votant simultanément sur le même scrutin, via 40 fils d'exécution
partant d'une barrière commune :

- **PostgreSQL** : 40 / 40 enregistrés, 0 verrou, **33 ms** ;
- 20 fils tentant de voter pour **le même membre** : 1 succès, 19 rejets
  d'unicité, 1 seul bulletin en base — intégrité respectée sous contention.

Le comparatif avec SQLite figure en tête de document.

---

## Différences de comportement PostgreSQL vs SQLite

Trois écarts constatés, à connaître avant la bascule.

### 1. Les longueurs maximales deviennent contraignantes

SQLite ignore `max_length` sur les `CharField` ; PostgreSQL le fait respecter.
Une insertion de 250 caractères dans un champ déclaré à 100 lève `DataError`.

Sans conséquence ici — l'import des 76 objets est passé sans erreur, aucune
donnée existante ne dépassait sa limite. Mais si un import échoue un jour sur
`value too long for type character varying(n)`, la cause est là : une donnée
tolérée par SQLite et refusée par PostgreSQL.

### 2. Le tri alphabétique change avec les accents

Avec la collation `fr_FR.UTF-8` :

```
SQLite     : ['Environnement', 'Programme Vision', 'Santé', 'Vie du Club', 'Éducation']
PostgreSQL : ['Éducation', 'Environnement', 'Programme Vision', 'Santé', 'Vie du Club']
```

SQLite compare les octets bruts, ce qui rejette les mots accentués en fin de
liste. PostgreSQL applique l'ordre alphabétique français.

**C'est une amélioration**, mais visible pour les utilisateurs : catégories,
noms de membres et titres accentués changeront de position dans les listes
triées. À signaler au bureau plutôt qu'à laisser découvrir.

### 3. La casse des emails reste distinctive

`User.objects.filter(email=...)` est sensible à la casse sur les deux moteurs :
une saisie `ADMIN@LIONSMED.TN` ne retrouve pas `admin@lionsmed.tn`.

Le comportement est **inchangé** par la migration — ce n'est donc pas un risque
de bascule. Mais `login_view` filtre sur `email` exact : un membre saisissant
son adresse en majuscules ne peut pas se connecter. À traiter séparément
(`email__iexact`), indépendamment de PostgreSQL.

---

## Rejeu en production : ce qui change

La procédure ci-dessus a été validée de bout en bout. Pour la production :

1. §1 Créer la base — **inchangé**, a fonctionné tel quel ;
2. §2 Sauvegarder — **inchangé** (`python manage.py backup_all`) ;
3. §3 `dumpdata` — **inchangé**, les exclusions listées sont les bonnes ;
4. §4 `migrate` + `createcachetable` — **inchangé** ;
5. §5 Vider `contenttypes` / `auth.permission` — **inchangé**, nécessaire ;
6. §6 `loaddata` — **inchangé** ;
7. §7 Vérifier — **inchangé** ;
8. §8 `sqlsequencereset` — **à supprimer de la procédure** (voir ci-dessus).

Deux précautions ajoutées : protéger les valeurs du `.env` contenant des
caractères spéciaux, et vérifier le moteur actif avant toute écriture.

Un point n'a **pas** pu être validé faute de données : la migration de fichiers
médias réels. Si des documents ou images existent au moment de la bascule,
vérifier après import qu'un document se télécharge bien depuis l'espace membre.
