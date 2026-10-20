import hashlib
import hmac
import os
import re
import secrets
import time
from collections import defaultdict, deque

from . import config

_N, _R, _P = 2 ** 14, 8, 1


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P, dklen=32)
    return f"scrypt${_N}${_R}${_P}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, n, r, p, salt, dk = stored.split("$")
        calc = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=int(n), r=int(r), p=int(p), dklen=32)
        return hmac.compare_digest(calc.hex(), dk)
    except Exception:
        return False


def validate_password_strength(pw: str) -> str | None:
    if len(pw) < 12:
        return "Password must be at least 12 characters."
    if not (re.search(r"[a-z]", pw) and re.search(r"[A-Z]", pw) and re.search(r"\d", pw)):
        return "Password must mix upper case, lower case and digits."
    return None


def new_token() -> str:
    return secrets.token_urlsafe(32)


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class RateLimiter:
    """In-memory sliding window (single process). Keyed by client IP + username."""

    def __init__(self, max_attempts: int, window: int):
        self.max, self.window, self.hits = max_attempts, window, defaultdict(deque)

    def _prune(self, key):
        q, now = self.hits[key], time.monotonic()
        while q and now - q[0] > self.window:
            q.popleft()
        return q

    def blocked(self, key) -> bool:
        return len(self._prune(key)) >= self.max

    def record_failure(self, key):
        self._prune(key).append(time.monotonic())

    def reset(self, key):
        self.hits.pop(key, None)


login_limiter = RateLimiter(config.LOGIN_MAX_ATTEMPTS, config.LOGIN_WINDOW_SECONDS)

_SAFE_NAME = re.compile(r"[^A-Za-z0-9._ -]")


def safe_display_name(name: str) -> str:
    """Original filename is stored as metadata only (never used as a path)."""
    base = os.path.basename(name.replace("\\", "/"))
    return _SAFE_NAME.sub("_", base)[:200] or "unnamed"
