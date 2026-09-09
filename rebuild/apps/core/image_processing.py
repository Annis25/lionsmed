from io import BytesIO
from pathlib import Path
import os
import subprocess
import tempfile
import warnings
from PIL import Image, ImageOps, UnidentifiedImageError
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage
from django.conf import settings

MAX_BYTES = 5 * 1024 * 1024
MAX_PIXELS = 16_000_000
FORMATS = {".jpg": "JPEG", ".jpeg": "JPEG", ".png": "PNG", ".webp": "WEBP"}
HEIF_FORMATS = {".heic", ".heif"}


def _convert_heif(raw, suffix):
    input_path = output_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as source:
            source.write(raw)
            input_path = source.name
        output_path = input_path + ".jpg"
        subprocess.run(
            ["heif-convert", "--quiet", input_path, output_path],
            check=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            timeout=20,
        )
        return Path(output_path).read_bytes()
    except (FileNotFoundError, OSError, subprocess.SubprocessError) as error:
        raise ValidationError("Cette photo iPhone ne peut pas être convertie automatiquement.") from error
    finally:
        for path in (input_path, output_path):
            if path:
                try:
                    os.unlink(path)
                except FileNotFoundError:
                    pass

def encode_photo(upload):
    suffix = Path(upload.name).suffix.lower()
    expected = FORMATS.get(suffix)
    if not expected and suffix not in HEIF_FORMATS:
        raise ValidationError("Photo JPEG, PNG, WebP ou HEIC requise.")
    if upload.size > MAX_BYTES:
        raise ValidationError("La photo doit peser au maximum 5 Mo.")
    raw = upload.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValidationError("La photo doit peser au maximum 5 Mo.")
    if suffix in HEIF_FORMATS:
        raw = _convert_heif(raw, suffix)
        expected = "JPEG"
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(raw)) as check:
                if check.format != expected or check.width * check.height > MAX_PIXELS or max(check.size) > 8000:
                    raise ValidationError("Type ou dimensions de photo non autorisés (16 millions de pixels maximum).")
                if getattr(check, "n_frames", 1) != 1:
                    raise ValidationError("Choisissez une photo fixe.")
                check.verify()
            with Image.open(BytesIO(raw)) as source:
                source.load()
                oriented = ImageOps.exif_transpose(source).convert("RGB")
                oriented.thumbnail((1024, 1024))
                # Toile neuve : ni EXIF, ni commentaires, ni profil ICC d'origine.
                clean = Image.new("RGB", oriented.size)
                clean.paste(oriented)
                out = BytesIO(); clean.save(out, format="JPEG", quality=85)
                return ContentFile(out.getvalue())
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning) as error:
        raise ValidationError("Photo invalide ou dimensions excessives.") from error
