import base64
import hashlib

from cryptography.fernet import Fernet

from core.config.settings import settings

_PREFIX = "enc:"


def _fernet() -> Fernet:
    key = settings.mail_encryption_key or settings.jwt_secret or "omniaide-fallback"
    digest = hashlib.sha256(key.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_secret(plaintext: str) -> str:
    if not plaintext:
        return ""
    return _PREFIX + _fernet().encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_secret(stored: str) -> str:
    if not stored:
        return ""
    if stored.startswith(_PREFIX):
        try:
            return _fernet().decrypt(stored[len(_PREFIX):].encode("utf-8")).decode("utf-8")
        except Exception:
            return ""
    return stored
