"""Générateur iCalendar minimal (RFC 5545), sans dépendance tierce — le format est
assez simple pour ne pas justifier une bibliothèque de plus. Couvre uniquement ce dont
le calendrier interne a besoin : VEVENT avec dates, lieu, description, lien."""
import re
from datetime import timezone as dt_timezone
from django.conf import settings
from django.utils import timezone

_PRODID = "-//Lions Club Sfax-Mediterranee//Lionsmed Calendrier//FR"


def _escape(value):
    return re.sub(r"([,;\\])", r"\\\1", value or "").replace("\n", "\\n")


def _fold(line):
    # RFC 5545 : replier les lignes de plus de 75 octets, continuation par espace.
    encoded = line.encode("utf-8")
    if len(encoded) <= 75:
        return line
    parts, chunk = [], b""
    for byte in encoded:
        if len(chunk) >= 74:
            parts.append(chunk)
            chunk = b""
        chunk += bytes([byte])
    if chunk:
        parts.append(chunk)
    return ("\r\n ").join(part.decode("utf-8", errors="ignore") for part in parts)


def _dt(value):
    return timezone.localtime(value, timezone=dt_timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _date(value):
    return timezone.localtime(value).strftime("%Y%m%d")


def event_to_vevent(event):
    lines = ["BEGIN:VEVENT", f"UID:event-{event.pk}@lionsmed.tn", f"DTSTAMP:{_dt(event.updated_at)}"]
    if event.all_day and event.starts_at:
        lines.append(f"DTSTART;VALUE=DATE:{_date(event.starts_at)}")
        if event.ends_at:
            lines.append(f"DTEND;VALUE=DATE:{_date(event.ends_at)}")
    else:
        if event.starts_at:
            lines.append(f"DTSTART:{_dt(event.starts_at)}")
        if event.ends_at:
            lines.append(f"DTEND:{_dt(event.ends_at)}")
    lines.append(f"SUMMARY:{_escape(event.title)}")
    description = event.summary or event.body
    if event.meeting_link:
        description = (description + "\n\n" if description else "") + event.meeting_link
    if description:
        lines.append(f"DESCRIPTION:{_escape(description[:1000])}")
    if event.location:
        lines.append(f"LOCATION:{_escape(event.location)}")
    if event.meeting_link:
        lines.append(f"URL:{_escape(event.meeting_link)}")
    lines.append(f"LAST-MODIFIED:{_dt(event.updated_at)}")
    lines.append("END:VEVENT")
    return lines


def build_calendar(events, *, calendar_name="Lionsmed — Calendrier"):
    lines = [
        "BEGIN:VCALENDAR", "VERSION:2.0", f"PRODID:{_PRODID}", "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
        f"X-WR-CALNAME:{_escape(calendar_name)}", "X-PUBLISHED-TTL:PT1H",
    ]
    for event in events:
        lines += event_to_vevent(event)
    lines.append("END:VCALENDAR")
    return "\r\n".join(_fold(line) for line in lines) + "\r\n"
