from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo
from django.conf import settings

TUNIS = ZoneInfo("Africa/Tunis")


def third_saturday(year, month):
    """Règle connue : le troisième samedi du mois. weekday() : lundi=0 ... samedi=5."""
    first = date(year, month, 1)
    first_saturday = first + timedelta(days=(5 - first.weekday()) % 7)
    return first_saturday + timedelta(days=14)


def compute_window(year, month):
    """Ouverture le 1er du mois, fermeture 24 h avant le troisième samedi, à l'heure de
    référence configurée. Retourne (None, None) si l'heure n'est pas configurée : aucune
    heure de production n'est présentée comme officielle par défaut (À CONFIRMER HUMAINEMENT)."""
    reference = getattr(settings, "SATISFACTION_REFERENCE_HOUR", None)
    if not reference:
        return None, None
    hour, minute = (int(part) for part in reference.split(":"))
    opens_local = datetime.combine(date(year, month, 1), time(hour, minute), tzinfo=TUNIS)
    saturday = third_saturday(year, month)
    closes_local = datetime.combine(saturday - timedelta(days=1), time(hour, minute), tzinfo=TUNIS)
    return opens_local.astimezone(ZoneInfo("UTC")), closes_local.astimezone(ZoneInfo("UTC"))
