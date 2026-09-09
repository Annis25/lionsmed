from django.core.exceptions import RequestDataTooBig
from django.core.files.uploadhandler import FileUploadHandler
from .uploads import MAX_BYTES


class PhotoSizeLimitHandler(FileUploadHandler):
    """Arrête les fichiers trop lourds avant leur écriture complète sur disque."""
    def new_file(self, *args, **kwargs):
        super().new_file(*args, **kwargs)
        self.received = 0

    def receive_data_chunk(self, raw_data, start):
        self.received += len(raw_data)
        if self.received > MAX_BYTES:
            raise RequestDataTooBig("Limite de taille de photo dépassée.")
        return raw_data

    def file_complete(self, file_size):
        return None
