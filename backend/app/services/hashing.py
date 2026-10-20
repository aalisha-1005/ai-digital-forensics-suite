"""SHA-256 hashing helpers (read-only access to evidence)."""
import hashlib
from pathlib import Path

CHUNK = 1024 * 1024


def sha256_file(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:  # read-only
        for chunk in iter(lambda: fh.read(CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def verify_file(path, expected: str) -> tuple[bool, str]:
    """Return (matches, actual_hash). Missing files count as a mismatch."""
    p = Path(path)
    if not p.exists():
        return False, "MISSING"
    actual = sha256_file(p)
    return actual == expected, actual
