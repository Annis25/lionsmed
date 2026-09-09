from io import BytesIO
from uuid import uuid4
from PIL import Image
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage
from django.db import transaction
from django.utils import timezone
from apps.core.models import PublicImage
from apps.core.image_processing import encode_photo
from .publication import require,audit

def storage():return FileSystemStorage(location=settings.PUBLIC_IMAGE_ROOT,file_permissions_mode=0o600,directory_permissions_mode=0o700)

def upload_image(*,actor,upload,alt,source,approved):
    from django.core.exceptions import ValidationError
    require(actor,"image.manage")
    if not alt.strip() or not source.strip() or not approved:raise ValidationError("Description, source et autorisation explicite requises.")
    cleaned=encode_photo(upload);keys=[]
    try:
        with Image.open(cleaned) as image:
            width,height=image.size
            for size in (480,1024):
                resized=image.copy();resized.thumbnail((size,size));output=BytesIO();resized.save(output,format="WEBP",quality=85)
                keys.append(storage().save(uuid4().hex+".webp",ContentFile(output.getvalue())))
        with transaction.atomic(durable=True):
            from django.contrib.auth import get_user_model
            actor=get_user_model().objects.select_for_update().get(pk=actor.pk)
            require(actor,"image.manage")
            item=PublicImage(small_key=keys[0],large_key=keys[1],width=width,height=height,alt=alt,source=source,approved_at=timezone.now(),uploaded_by=actor)
            item.full_clean();item.save();audit(actor,"image.approved",item)
        return item
    except Exception:
        for key in keys:storage().delete(key)
        raise
