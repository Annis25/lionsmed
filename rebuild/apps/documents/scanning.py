"""Analyse antivirus des documents privés avant disponibilité.

Parle directement le protocole INSTREAM de clamd (pas de dépendance tierce) sur un socket
Unix ou TCP configuré en exploitation. Toute indisponibilité, timeout ou réponse
inattendue échoue fermé : `ScannerUnavailable` — jamais un document rendu disponible
faute de scanner joignable. Ne simule jamais un antivirus qui aurait réussi.
"""
import socket
import struct
from django.conf import settings

CHUNK_SIZE = 8192


class ScannerUnavailable(Exception):
    pass


class ScanResult:
    def __init__(self, clean, detail=""):
        self.clean = clean
        self.detail = detail


def _connect(host, port, unix_socket, timeout):
    if unix_socket:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.connect(unix_socket)
        return sock
    return socket.create_connection((host, int(port)), timeout=timeout)


def scan_bytes(data, *, host=None, port=None, unix_socket=None, timeout=10):
    unix_socket = unix_socket or getattr(settings, "CLAMD_SOCKET", None) or None
    host = host or getattr(settings, "CLAMD_HOST", None) or None
    port = port or getattr(settings, "CLAMD_PORT", None) or None
    if not unix_socket and not (host and port):
        raise ScannerUnavailable("Scanner antivirus non configuré.")
    try:
        with _connect(host, port, unix_socket, timeout) as sock:
            sock.sendall(b"zINSTREAM\0")
            for offset in range(0, len(data), CHUNK_SIZE):
                chunk = data[offset:offset + CHUNK_SIZE]
                sock.sendall(struct.pack("!L", len(chunk)) + chunk)
            sock.sendall(struct.pack("!L", 0))
            response = b""
            while b"\0" not in response:
                part = sock.recv(4096)
                if not part:
                    break
                response += part
    except (OSError, socket.timeout) as error:
        raise ScannerUnavailable(str(error)) from error
    text = response.decode("utf-8", "replace").strip("\x00").strip()
    if text.endswith("OK"):
        return ScanResult(clean=True, detail=text)
    if "FOUND" in text:
        return ScanResult(clean=False, detail=text)
    raise ScannerUnavailable(f"Réponse antivirus inattendue : {text!r}")
