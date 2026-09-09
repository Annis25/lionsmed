from django.conf import settings
from django.core.files.storage import FileSystemStorage


def document_storage():
    return FileSystemStorage(location=settings.PRIVATE_MEDIA_ROOT / "documents", base_url=None,
        file_permissions_mode=0o600, directory_permissions_mode=0o700)
