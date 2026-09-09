from io import BytesIO
from pathlib import Path
import warnings
from PIL import Image, ImageOps, UnidentifiedImageError
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage
from django.conf import settings

MAX_BYTES = 5 * 1024 * 1024
MAX_PIXELS = 16_000_000
FORMATS = {".jpg": ("JPEG", "image/jpeg"), ".jpeg": ("JPEG", "image/jpeg"), ".png": ("PNG", "image/png"), ".webp": ("WEBP", "image/webp")}

def encode_photo(upload):
    expected = FORMATS.get(Path(upload.name).suffix.lower())
    if not expected or upload.content_type != expected[1]:
        raise ValidationError("Photo JPEG, PNG ou WebP requise, avec un type cohérent.")
    if upload.size > MAX_BYTES:
        raise ValidationError("La photo doit peser au maximum 5 Mo.")
    raw = upload.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValidationError("La photo doit peser au maximum 5 Mo.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(raw)) as check:
                if check.format != expected[0] or check.width * check.height > MAX_PIXELS or max(check.size) > 8000:
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
