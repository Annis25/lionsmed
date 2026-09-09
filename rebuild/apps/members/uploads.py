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

def photo_storage():
    return FileSystemStorage(location=settings.PRIVATE_MEDIA_ROOT, base_url=None,
        file_permissions_mode=0o600, directory_permissions_mode=0o700)


from apps.core.image_processing import encode_photo
