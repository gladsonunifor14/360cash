"""Primitivas de segurança: hash de senha, OTP, tokens JWT e tokens opacos."""

import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from app.core.config import get_settings

_hasher = PasswordHasher()


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def validate_password_strength(password: str) -> list[str]:
    s = get_settings()
    problems = []
    if len(password) < s.password_min_length:
        problems.append(f"mínimo de {s.password_min_length} caracteres")
    if not any(c.isupper() for c in password):
        problems.append("ao menos uma letra maiúscula")
    if not any(c.islower() for c in password):
        problems.append("ao menos uma letra minúscula")
    if not any(c.isdigit() for c in password):
        problems.append("ao menos um número")
    if not any(not c.isalnum() for c in password):
        problems.append("ao menos um caractere especial")
    return problems


def generate_otp() -> str:
    n = get_settings().otp_length
    return "".join(secrets.choice("0123456789") for _ in range(n))


def hash_token(value: str) -> str:
    """Hash keyed (HMAC) para OTPs e tokens opacos guardados no banco."""
    key = get_settings().jwt_secret.encode()
    return hmac.new(key, value.encode(), hashlib.sha256).hexdigest()


def constant_time_equals(a: str, b: str) -> bool:
    return hmac.compare_digest(a, b)


def new_opaque_token() -> str:
    return secrets.token_urlsafe(48)


def create_jwt(subject: str, token_type: str, minutes: int, extra: dict[str, Any] | None = None) -> str:
    s = get_settings()
    now = datetime.now(UTC)
    payload = {
        "sub": subject,
        "typ": token_type,
        "iat": now,
        "exp": now + timedelta(minutes=minutes),
        "jti": secrets.token_hex(8),
        **(extra or {}),
    }
    return jwt.encode(payload, s.jwt_secret, algorithm=s.jwt_algorithm)


def decode_jwt(token: str, expected_type: str) -> dict[str, Any]:
    s = get_settings()
    payload = jwt.decode(token, s.jwt_secret, algorithms=[s.jwt_algorithm])
    if payload.get("typ") != expected_type:
        raise jwt.InvalidTokenError("tipo de token inválido")
    return payload
