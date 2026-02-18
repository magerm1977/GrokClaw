"""
Simple encryption for sensitive data (API keys, tokens).
"""

import os
from pathlib import Path

from cryptography.fernet import Fernet

KEY_FILE = Path.home() / ".grok-harness" / ".key"


def _get_or_create_key() -> bytes:
    """Get or create encryption key."""
    if KEY_FILE.exists():
        with open(KEY_FILE, "rb") as f:
            return f.read()
    key = Fernet.generate_key()
    KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(KEY_FILE, "wb") as f:
        f.write(key)
    try:
        os.chmod(KEY_FILE, 0o600)
    except OSError:
        pass
    return key


def encrypt_value(value: str) -> str:
    """Encrypt a string value."""
    key = _get_or_create_key()
    f = Fernet(key)
    encrypted = f.encrypt(value.encode())
    return encrypted.decode()


def decrypt_value(encrypted_value: str) -> str:
    """Decrypt a string value."""
    key = _get_or_create_key()
    f = Fernet(key)
    decrypted = f.decrypt(encrypted_value.encode())
    return decrypted.decode()
