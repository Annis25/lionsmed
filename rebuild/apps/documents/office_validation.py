"""Validations structurelles réalistes au-delà de l'extension/MIME déclarés.

Pas d'analyseur artisanal complexe : bibliothèque standard `zipfile` pour DOCX/XLSX
(structures ZIP), vérification de signature et repérage heuristique de contenu actif
pour PDF. Défense en profondeur avant l'analyse antivirus, pas un remplacement.
"""
import zipfile
from io import BytesIO
from django.core.exceptions import ValidationError

MAGIC = {
    ".pdf": b"%PDF-",
    ".docx": b"PK\x03\x04",
    ".xlsx": b"PK\x03\x04",
    ".png": b"\x89PNG\r\n\x1a\n",
    ".jpg": b"\xff\xd8\xff",
    ".jpeg": b"\xff\xd8\xff",
}

MAX_ZIP_ENTRIES = 2000
MAX_UNCOMPRESSED_TOTAL = 100 * 1024 * 1024
MAX_COMPRESSION_RATIO = 100
REQUIRED_ENTRY = {".docx": "word/document.xml", ".xlsx": "xl/workbook.xml"}
FORBIDDEN_ENTRY_TOKENS = ("vbaProject.bin", "..", "macros/")


def check_signature(raw, suffix):
    magic = MAGIC.get(suffix)
    if not magic or not raw.startswith(magic):
        raise ValidationError("Signature de fichier incohérente avec son extension.")


def validate_office_zip(raw, suffix):
    try:
        archive = zipfile.ZipFile(BytesIO(raw))
    except zipfile.BadZipFile:
        raise ValidationError("Archive du document illisible ou corrompue.")
    infos = archive.infolist()
    if len(infos) > MAX_ZIP_ENTRIES:
        raise ValidationError("Document rejeté : nombre de fichiers internes excessif.")
    names, total_uncompressed = set(), 0
    for info in infos:
        name = info.filename
        names.add(name)
        if name.startswith("/") or ".." in name:
            raise ValidationError("Document rejeté : chemin interne suspect.")
        if any(token in name for token in FORBIDDEN_ENTRY_TOKENS):
            raise ValidationError("Document rejeté : contenu actif (macro) non autorisé.")
        total_uncompressed += info.file_size
        if info.compress_size and info.file_size / max(info.compress_size, 1) > MAX_COMPRESSION_RATIO:
            raise ValidationError("Document rejeté : taux de compression suspect.")
        if total_uncompressed > MAX_UNCOMPRESSED_TOTAL:
            raise ValidationError("Document rejeté : taille décompressée excessive.")
    required = REQUIRED_ENTRY.get(suffix)
    if required and required not in names:
        raise ValidationError("Structure de document Office invalide pour son extension.")
    if archive.testzip():
        raise ValidationError("Archive corrompue.")


def validate_pdf(raw):
    if not raw.startswith(b"%PDF-"):
        raise ValidationError("Signature PDF invalide.")
    for token in (b"/JavaScript", b"/JS", b"/OpenAction", b"/Launch"):
        if token in raw:
            raise ValidationError("PDF rejeté : contenu actif détecté (JavaScript ou action automatique).")


def validate_structure(raw, suffix):
    check_signature(raw, suffix)
    if suffix in (".docx", ".xlsx"):
        validate_office_zip(raw, suffix)
    elif suffix == ".pdf":
        validate_pdf(raw)
