"""
Docker Secrets injection utility.

Reads secrets from /run/secrets/ (Docker) with fallbacks to env vars and defaults.
All secret values are wrapped in a SecretStr that prevents accidental logging/printing.

Usage:
    from secrets_util import read_secret

    broker = read_secret("redpanda_broker", default="localhost:9092")
    print(broker)          # → "******" (masked)
    broker.get()           # → "redpanda:9092" (actual value)
    str(broker)            # → "******" (masked)
    f"broker={broker}"     # → "broker=******" (masked)
    broker == "redpanda:9092"  # → True (comparison works)
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

SECRETS_DIR = Path("/run/secrets")


class SecretStr:
    """A string wrapper that masks its value in logs, print, repr, and f-strings."""

    __slots__ = ("_value",)

    def __init__(self, value: str) -> None:
        object.__setattr__(self, "_value", value)

    def get(self) -> str:
        """Return the actual secret value. Use intentionally."""
        return self._value

    def __str__(self) -> str:
        return "******"

    def __repr__(self) -> str:
        return "SecretStr('******')"

    def __format__(self, format_spec: str) -> str:
        return "******"

    def __eq__(self, other: object) -> bool:
        if isinstance(other, SecretStr):
            return self._value == other._value
        if isinstance(other, str):
            return self._value == other
        return NotImplemented

    def __hash__(self) -> int:
        return hash(self._value)

    def __bool__(self) -> bool:
        return bool(self._value)

    def __len__(self) -> int:
        return len(self._value)

    def __contains__(self, item: str) -> bool:
        return item in self._value

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError("SecretStr is immutable")

    def __delattr__(self, name: str) -> None:
        raise AttributeError("SecretStr is immutable")

    def split(self, sep: str | None = None) -> list[str]:
        """Split the secret value. Returns plain strings (use for non-sensitive lists like symbols)."""
        return self._value.split(sep)


def read_secret(name: str, *, default: str = "") -> SecretStr:
    """
    Read a secret by name with 3-layer fallback:

    1. /run/secrets/<name>   (Docker secret — production)
    2. <NAME> env var        (local dev without Docker)
    3. default value         (hardcoded fallback)

    Returns a SecretStr that masks the value in print/logs/repr.
    Call .get() to access the raw value when you actually need it.
    """
    # 1. Docker secret file
    secret_path = SECRETS_DIR / name
    if secret_path.is_file():
        value = secret_path.read_text().strip()
        if value:
            logger.debug("Secret '%s' loaded from Docker secret", name)
            return SecretStr(value)

    # 2. Environment variable (uppercase)
    env_value = os.getenv(name.upper(), "")
    if env_value:
        logger.debug("Secret '%s' loaded from env var", name)
        return SecretStr(env_value)

    # 3. Default
    if default:
        logger.debug("Secret '%s' using default value", name)
    else:
        logger.warning("Secret '%s' not found in Docker secrets, env, or defaults", name)

    return SecretStr(default)


def read_secret_raw(name: str, *, default: str = "") -> str:
    """
    Same lookup as read_secret() but returns a plain string.
    Use only for non-sensitive config like log_level or stream_type.
    """
    return read_secret(name, default=default).get()
