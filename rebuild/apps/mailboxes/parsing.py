"""Lecture d'un message brut (RFC 822) en données prêtes à stocker.

Tout ce qui vient du message est traité comme hostile : en-têtes bornés et débarrassés des
caractères de contrôle, corps HTML réécrit par le nettoyeur, pièces jointes réduites à leur
nom, type et taille. Un message mal formé ne doit jamais interrompre la synchronisation.
"""
import hashlib
import re
from dataclasses import dataclass, field
from email import message_from_bytes, policy
from email.utils import getaddresses
from .sanitizer import clean_html, clean_text, html_to_text

# Marques des avis envoyés par Lionsmed à l'adresse personnelle d'un titulaire. Elles
# servent à ne jamais reprendre un de ces avis comme nouveau message institutionnel.
NOTICE_HEADER = "X-Lionsmed-Notification"
NOTICE_DOMAIN = "lionsmed-avis.invalid"
NOTICE_SUBJECT = "[Nouveau message Lionsmed]"

_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_MAX_ADDRESSES = 50


@dataclass
class Parsed:
    fingerprint: str
    message_id: str = ""
    references: str = ""
    sender_name: str = ""
    sender_address: str = ""
    reply_to: str = ""
    recipients: list = field(default_factory=list)
    copies: list = field(default_factory=list)
    subject: str = ""
    body_text: str = ""
    body_html: str = ""
    preview: str = ""
    attachments: list = field(default_factory=list)
    # Avis Lionsmed revenu vers une boîte : à ne pas importer.
    own_notice: bool = False
    # Réponse automatique, avis de non-remise, réponse ou transfert d'un avis Lionsmed :
    # importé, mais sans notification par e-mail (voir services.notify_holders).
    automatic: bool = False


def _line(value, limit):
    return " ".join(_CONTROL.sub(" ", str(value or "")).split())[:limit]


def _header(message, name, limit=998):
    try:
        return _line(message.get(name, ""), limit)
    except Exception:
        return ""


def _addresses(message, name):
    try:
        values = [str(value) for value in message.get_all(name, [])]
    except Exception:
        values = []
    result, seen = [], set()
    for display, address in getaddresses(values):
        address = _line(address, 254)
        if "@" not in address or address.lower() in seen:
            continue
        seen.add(address.lower())
        result.append({"name": _line(display, 200), "address": address})
        if len(result) >= _MAX_ADDRESSES:
            break
    return result


def _content(part):
    if part is None:
        return ""
    try:
        return str(part.get_content())
    except Exception:
        try:
            return (part.get_payload(decode=True) or b"").decode("utf-8", "replace")
        except Exception:
            return ""


def _body_part(message, kind):
    try:
        return message.get_body(preferencelist=(kind,))
    except Exception:
        return None


def _attachments(message, bodies):
    found = []
    try:
        parts = list(message.walk())
    except Exception:
        return found
    for part in parts:
        if part.is_multipart() or any(part is body for body in bodies):
            continue
        try:
            name = _line(part.get_filename() or "", 150)
            disposition = part.get_content_disposition()
            kind = _line(part.get_content_type(), 80)
            payload = part.get_payload(decode=True) or b""
        except Exception:
            continue
        # Image intégrée au corps du message (logo de signature…) : ce n'est pas une pièce jointe.
        if disposition != "attachment" and (not name or (kind.startswith("image/") and part.get("Content-ID"))):
            continue
        found.append({"name": name or "Pièce jointe sans nom", "type": kind, "size": len(payload)})
        if len(found) >= 30:
            break
    return found


def _automatic(message, sender_address, subject, references):
    auto = _header(message, "Auto-Submitted", 60).split(";")[0].strip().lower()
    local = sender_address.split("@")[0].lower()
    try:
        report = message.get_content_type() == "multipart/report"
    except Exception:
        report = False
    return bool(
        auto in {"auto-replied", "auto-notified"}
        or _header(message, "X-Autoreply", 20) or _header(message, "X-Autorespond", 20)
        or _header(message, "Precedence", 30).lower() == "auto_reply"
        or _header(message, "Return-Path", 300).replace(" ", "") == "<>"
        or report or local in {"mailer-daemon", "postmaster"}
        or NOTICE_DOMAIN in references
        or NOTICE_SUBJECT.lower() in subject.lower())


def parse(raw):
    message = message_from_bytes(raw, policy=policy.default)
    message_id = _header(message, "Message-ID", 255)
    references = _line(" ".join([_header(message, "References", 4000), _header(message, "In-Reply-To", 500)]), 4000)
    sender = (_addresses(message, "From") or [{"name": "", "address": ""}])[0]
    reply_to = (_addresses(message, "Reply-To") or [{"address": ""}])[0]["address"]
    subject = _line(_header(message, "Subject"), 255)
    plain, rich = _body_part(message, "plain"), _body_part(message, "html")
    body_html = clean_html(_content(rich)) if rich is not None else ""
    body_text = clean_text(_content(plain)) if plain is not None else ""
    if not body_text and rich is not None:
        body_text = html_to_text(_content(rich))
    # Même message = même Message-ID ; à défaut, même contenu à l'octet près.
    identity = ("mid:" + message_id.lower()).encode() if message_id else b"raw:" + raw
    return Parsed(
        fingerprint=hashlib.sha256(identity).hexdigest(),
        message_id=message_id, references=references,
        sender_name=sender["name"], sender_address=sender["address"],
        reply_to="" if reply_to.lower() == sender["address"].lower() else reply_to,
        recipients=_addresses(message, "To"), copies=_addresses(message, "Cc"),
        subject=subject, body_text=body_text, body_html=body_html,
        preview=" ".join(body_text.split())[:200],
        attachments=_attachments(message, [part for part in (plain, rich) if part is not None]),
        own_notice=bool(_header(message, NOTICE_HEADER, 40)) or message_id.lower().endswith("@" + NOTICE_DOMAIN + ">"),
        automatic=_automatic(message, sender["address"], subject, references),
    )
