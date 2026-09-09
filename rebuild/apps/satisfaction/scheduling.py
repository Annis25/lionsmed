from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo
from django.conf import settings

TUNIS = ZoneInfo("Africa/Tunis")
FRIDAY = 4  # date.weekday() : lundi=0 … vendredi=4


def nth_weekday(year, month, weekday, n):
    """n-ième occurrence d'un jour de semaine donné dans le mois (n=1 : la première)."""
    first = date(year, month, 1)
    first_occurrence = first + timedelta(days=(weekday - first.weekday()) % 7)
    return first_occurrence + timedelta(days=7 * (n - 1))


def second_friday(year, month):
    return nth_weekday(year, month, FRIDAY, 2)


def third_friday(year, month):
    return nth_weekday(year, month, FRIDAY, 3)


def compute_auto_window(year, month):
    """Activation automatique (décision confirmée par le club) : ouverture le deuxième
    vendredi du mois, fermeture le troisième vendredi, à l'heure de référence configurée.
    Retourne (None, None) si l'heure n'est pas configurée : aucune heure n'est présentée
    comme officielle par défaut."""
    reference = getattr(settings, "SATISFACTION_REFERENCE_HOUR", None)
    if not reference:
        return None, None
    hour, minute = (int(part) for part in reference.split(":"))
    opens_local = datetime.combine(second_friday(year, month), time(hour, minute), tzinfo=TUNIS)
    closes_local = datetime.combine(third_friday(year, month), time(hour, minute), tzinfo=TUNIS)
    return opens_local.astimezone(ZoneInfo("UTC")), closes_local.astimezone(ZoneInfo("UTC"))
