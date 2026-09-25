"""Fonctions du bureau — catalogue institutionnel du club.

Une fonction du bureau n'est ni un rôle applicatif ni une permission : « 1er Vice-Président »
et « 2e Vice-Président » peuvent relever du même rôle VICE_PRESIDENT, « Protocole » n'a aucun
rôle. Ce catalogue ne vit donc pas dans apps.core.permissions.

`Mandate.function` reste un libellé (aucune migration) : la saisie passe par ce catalogue, qui
impose un libellé canonique pour les sept fonctions du bureau et refuse leurs variantes
libres (« Premier vice président », « 1ère VP »…). Une fonction hors catalogue (« Responsable
d'une commission ») reste possible et s'affiche après les sept fonctions. Les variantes déjà
enregistrées ne sont ni réécrites ni perdues : elles restent reconnues pour l'ordre public.
"""
import re
import unicodedata
from django.core.exceptions import ValidationError

# (clé, libellé, forme féminine, variantes masculines, variantes féminines) — variantes
# reconnues après normalisation. L'ordre de cette liste est l'ordre public de « Notre bureau ».
BUREAU_FUNCTIONS = (
    ("PAST_PRESIDENT", "Past President", "Past President",
     {"past president", "immediate past president", "immediat past president", "ipp", "president sortant",
      "ancien president"},
     {"past presidente", "presidente sortante", "ancienne presidente"}),
    ("PRESIDENT", "Président", "Présidente",
     {"president", "president du club"},
     {"presidente", "presidente du club"}),
    ("VICE_PRESIDENT_1", "1er Vice-Président", "1re Vice-Présidente",
     {"1er vice president", "1er vp", "premier vice president", "first vice president", "1st vice president"},
     {"1re vice presidente", "1ere vice presidente", "1re vp", "1ere vp", "premiere vice presidente"}),
    # « Vice-Président » sans rang : reconnu pour l'ordre des données existantes, jamais promu
    # 1er ou 2e, et refusé à la saisie (le rang doit être précisé).
    ("VICE_PRESIDENT", "Vice-Président", "Vice-Présidente",
     {"vice president", "vp"},
     {"vice presidente"}),
    ("VICE_PRESIDENT_2", "2e Vice-Président", "2e Vice-Présidente",
     {"2e vice president", "2eme vice president", "2e vp", "2eme vp", "deuxieme vice president", "second vice president",
      "2nd vice president"},
     {"2e vice presidente", "2eme vice presidente", "deuxieme vice presidente", "seconde vice presidente"}),
    ("SECRETAIRE", "Secrétaire", "Secrétaire",
     {"secretaire", "secretaire du club", "secretaire general"},
     {"secretaire generale"}),
    ("TRESORIER", "Trésorier", "Trésorière",
     {"tresorier", "tresorier du club"},
     {"tresoriere", "tresoriere du club"}),
    ("PROTOCOLE", "Protocole", "Protocole",
     {"protocole", "chef du protocole", "chef de protocole", "responsable du protocole", "responsable protocole",
      "maitre du protocole"},
     {"cheffe du protocole"}),
)
UNRANKED = len(BUREAU_FUNCTIONS)
NOT_SELECTABLE = {"VICE_PRESIDENT"}
# alias normalisé → (rang, clé, libellé canonique correspondant au genre de la saisie)
_BY_ALIAS = {}
for _rank, (_key, _masculine, _feminine, _masc_aliases, _fem_aliases) in enumerate(BUREAU_FUNCTIONS):
    _BY_ALIAS.update({alias: (_rank, _key, _masculine) for alias in _masc_aliases})
    _BY_ALIAS.update({alias: (_rank, _key, _feminine) for alias in _fem_aliases})
_LABELS = {key: {masculine, feminine} for key, masculine, feminine, _, _ in BUREAU_FUNCTIONS}


def normalize_function(label):
    """« 1er Vice-Président » → « 1er vice president » ; « Trésorière » → « tresoriere »."""
    text = unicodedata.normalize("NFKD", label or "").encode("ascii", "ignore").decode("ascii").lower()
    text = re.sub(r"[^a-z0-9]+", " ", text).strip()
    return re.sub(r"\b(\d+)\s+(er|re|ere|e|eme|nd|st)\b", r"\1\2", text)  # « 1 er » → « 1er »


def _match(label):
    return _BY_ALIAS.get(normalize_function(label))


def function_key(label):
    match = _match(label)
    return match[1] if match else None


def function_rank(label):
    match = _match(label)
    return match[0] if match else UNRANKED


def canonical_label(label):
    """Libellé du catalogue correspondant à une saisie reconnue (forme féminine conservée),
    ou None pour une fonction hors catalogue."""
    match = _match(label)
    return match[2] if match else None


def selectable_labels():
    """Libellés proposés à la saisie, dans l'ordre du bureau, formes masculine puis féminine."""
    labels = []
    for key, masculine, feminine, _, _ in BUREAU_FUNCTIONS:
        if key in NOT_SELECTABLE:
            continue
        labels.append(masculine)
        if feminine != masculine:
            labels.append(feminine)
    return labels


def validate_function(label):
    """Seule porte d'entrée d'une fonction enregistrée par le service de mandat."""
    label = " ".join((label or "").split())
    if not label:
        raise ValidationError("La fonction est obligatoire.")
    if len(label) > 150:
        raise ValidationError("La fonction ne peut pas dépasser 150 caractères.")
    key = function_key(label)
    if key in NOT_SELECTABLE:
        raise ValidationError("Précisez le rang : « 1er Vice-Président » ou « 2e Vice-Président ».")
    if key and label not in _LABELS[key]:
        raise ValidationError(f"Cette fonction figure dans la liste : choisissez « {canonical_label(label)} ».")
    return label
