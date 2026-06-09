import os
import hashlib
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

CHUNK = 64 * 1024  # 64 KB read chunks


def _derive_key(key_str: str) -> bytes:
    return hashlib.sha256(key_str.encode()).digest()


def encrypt_file(src: str, dst: str, key_str: str) -> None:
    """AES-256-CTR encrypt src → dst. Prepends 16-byte random IV."""
    key = _derive_key(key_str)
    iv = os.urandom(16)
    cipher = Cipher(algorithms.AES(key), modes.CTR(iv))
    enc = cipher.encryptor()
    with open(src, "rb") as fin, open(dst, "wb") as fout:
        fout.write(iv)
        while chunk := fin.read(CHUNK):
            fout.write(enc.update(chunk))
        fout.write(enc.finalize())


def decrypt_file(src: str, dst: str, key_str: str) -> None:
    """AES-256-CTR decrypt src → dst. Reads 16-byte IV from file head."""
    key = _derive_key(key_str)
    with open(src, "rb") as fin, open(dst, "wb") as fout:
        iv = fin.read(16)
        cipher = Cipher(algorithms.AES(key), modes.CTR(iv))
        dec = cipher.decryptor()
        while chunk := fin.read(CHUNK):
            fout.write(dec.update(chunk))
        fout.write(dec.finalize())


def get_encryption_key() -> str | None:
    return os.getenv("BACKUP_ENCRYPTION_KEY")
