"""Password hashing and opaque token helpers.

Passwords are hashed with Argon2id. Session and reset tokens are random,
URL-safe strings; only an HMAC-SHA256 digest (keyed with SECRET_KEY) is stored,
so a database leak does not reveal usable tokens.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import unicodedata

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.core.config import get_settings

_hasher = PasswordHasher()
# A real hash used to equalise timing when the user does not exist.
_DUMMY_HASH = _hasher.hash("smartpos-dummy-password")

MIN_PASSWORD_LENGTH = 8


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    try:
        return _hasher.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    try:
        return _hasher.check_needs_rehash(password_hash)
    except InvalidHashError:
        return True


def validate_password_strength(password: str) -> list[str]:
    problems = []
    if len(password) < MIN_PASSWORD_LENGTH:
        problems.append(f"Password must be at least {MIN_PASSWORD_LENGTH} characters long.")
    if len(password) > 128:
        problems.append("Password must be at most 128 characters long.")
    # Letters include combining marks so that, e.g., a Thai word counts as letters only.
    letters_only = all(c.isalpha() or unicodedata.category(c).startswith("M") for c in password)
    if password.isdigit() or letters_only:
        problems.append("Password must contain both letters and numbers or symbols.")
    return problems


def generate_token(nbytes: int = 32) -> str:
    return secrets.token_urlsafe(nbytes)


def hash_token(token: str) -> str:
    key = get_settings().secret_key.encode()
    return hmac.new(key, token.encode(), hashlib.sha256).hexdigest()


def tokens_match(token: str, token_hash: str) -> bool:
    return hmac.compare_digest(hash_token(token), token_hash)
