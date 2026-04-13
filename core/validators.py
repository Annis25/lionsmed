"""Validateurs partagés pour les fichiers envoyés par les utilisateurs."""

from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
from django.template.defaultfilters import filesizeformat
from django.utils.deconstruct import deconstructible

IMAGE_EXTENSIONS = ['jpg', 'jpeg', 'png', 'webp']
DOCUMENT_EXTENSIONS = ['pdf', 'docx']

MAX_IMAGE_SIZE = 5 * 1024 * 1024    # 5 Mo
MAX_DOCUMENT_SIZE = 15 * 1024 * 1024  # 15 Mo

validate_image_extension = FileExtensionValidator(
    allowed_extensions=IMAGE_EXTENSIONS,
    message="Format d'image non accepté. Extensions autorisées : %(allowed_extensions)s.",
)
validate_document_extension = FileExtensionValidator(
    allowed_extensions=DOCUMENT_EXTENSIONS,
    message="Format de document non accepté. Extensions autorisées : %(allowed_extensions)s.",
)


@deconstructible
class MaxFileSizeValidator:
    """Refuse un fichier dépassant la taille indiquée (en octets)."""

    def __init__(self, max_bytes):
        self.max_bytes = max_bytes

    def __call__(self, value):
        size = getattr(value, 'size', None)
        if size is None:
            return
        if size > self.max_bytes:
            raise ValidationError(
                "Fichier trop volumineux (%(size)s). Taille maximale autorisée : %(max)s.",
                code='file_too_large',
                params={
                    'size': filesizeformat(size),
                    'max': filesizeformat(self.max_bytes),
                },
            )

    def __eq__(self, other):
        return isinstance(other, MaxFileSizeValidator) and self.max_bytes == other.max_bytes


@deconstructible
class ImageContentValidator:
    """Vérifie que le fichier est réellement une image, pas seulement bien nommé.

    Une extension .jpg ne prouve rien : on ouvre le fichier avec Pillow et on
    contrôle que le format décodé fait partie des formats autorisés. Cela bloque
    un script renommé en image, ainsi que les fichiers corrompus.
    """

    # Correspondance extension → format Pillow
    ALLOWED_FORMATS = {'JPEG', 'PNG', 'WEBP'}

    def __call__(self, value):
        from PIL import Image, UnidentifiedImageError

        file_obj = getattr(value, 'file', value)
        try:
            position = file_obj.tell()
        except (AttributeError, OSError):
            position = None
        try:
            file_obj.seek(0)
            with Image.open(file_obj) as image:
                # verify() détecte les fichiers tronqués ou non conformes.
                image.verify()
                image_format = image.format
        except UnidentifiedImageError:
            raise ValidationError(
                "Ce fichier n'est pas une image valide.", code='invalid_image'
            )
        except ValidationError:
            raise
        except Exception:
            raise ValidationError(
                "Ce fichier n'est pas une image valide ou est corrompu.",
                code='invalid_image',
            )
        finally:
            try:
                file_obj.seek(position if position is not None else 0)
            except (AttributeError, OSError):
                pass

        if image_format not in self.ALLOWED_FORMATS:
            raise ValidationError(
                "Format d'image non accepté (%(found)s). Formats autorisés : %(allowed)s.",
                code='invalid_image_format',
                params={
                    'found': image_format,
                    'allowed': ', '.join(sorted(self.ALLOWED_FORMATS)),
                },
            )

    def __eq__(self, other):
        return isinstance(other, ImageContentValidator)


@deconstructible
class DocumentContentValidator:
    """Contrôle la signature binaire d'un document.

    Symétrique d'ImageContentValidator : une extension .pdf ne prouve rien. On
    lit les premiers octets et on vérifie la signature attendue (%PDF- pour un
    PDF, l'en-tête ZIP PK\\x03\\x04 pour un .docx, qui est une archive).
    """

    SIGNATURES = {
        'pdf': [b'%PDF-'],
        'docx': [b'PK\x03\x04', b'PK\x05\x06', b'PK\x07\x08'],
    }

    def __call__(self, value):
        name = getattr(value, 'name', '') or ''
        extension = name.rsplit('.', 1)[-1].lower() if '.' in name else ''
        expected = self.SIGNATURES.get(extension)
        if not expected:
            return  # l'extension est déjà refusée par le validateur dédié

        file_obj = getattr(value, 'file', value)
        try:
            position = file_obj.tell()
        except (AttributeError, OSError):
            position = None
        try:
            file_obj.seek(0)
            header = file_obj.read(8)
        except Exception:
            raise ValidationError(
                "Fichier illisible.", code='unreadable_document'
            )
        finally:
            try:
                file_obj.seek(position if position is not None else 0)
            except (AttributeError, OSError):
                pass

        if not any(header.startswith(sig) for sig in expected):
            raise ValidationError(
                "Le contenu du fichier ne correspond pas à un %(ext)s valide.",
                code='invalid_document_content',
                params={'ext': extension.upper()},
            )

    def __eq__(self, other):
        return isinstance(other, DocumentContentValidator)


# Jeux de validateurs prêts à l'emploi
IMAGE_VALIDATORS = [
    validate_image_extension,
    MaxFileSizeValidator(MAX_IMAGE_SIZE),
    ImageContentValidator(),
]
DOCUMENT_VALIDATORS = [
    validate_document_extension,
    MaxFileSizeValidator(MAX_DOCUMENT_SIZE),
    DocumentContentValidator(),
]
