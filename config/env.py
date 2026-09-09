"""Small, explicit environment-variable parsing helpers.

Every helper reads ``os.environ`` (already populated from ``.env`` by
``config.settings``' ``load_dotenv``). Invalid values raise
``ImproperlyConfigured`` with a clear message rather than being silently
coerced -- ``DJANGO_DEBUG=maybe`` is an error, not ``True``.

``parse_database_url`` understands ``sqlite://`` and
``postgres://`` / ``postgresql://`` URLs and returns a Django ``DATABASES``
entry. It does not need a live database to run, so it is fully unit-testable.
"""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import unquote, urlparse

from django.core.exceptions import ImproperlyConfigured

_TRUE = {"1", "true", "yes", "on", "y", "t"}
_FALSE = {"0", "false", "no", "off", "n", "f", ""}


def get(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name)
    if value is None:
        return default
    return value


def get_str(name: str, default: str = "") -> str:
    value = os.environ.get(name)
    return default if value is None else value.strip()


def get_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    token = raw.strip().lower()
    if token in _TRUE:
        return True
    if token in _FALSE:
        return False
    raise ImproperlyConfigured(
        f"Environment variable {name}={raw!r} is not a valid boolean. "
        f"Use one of: {sorted(_TRUE | _FALSE - {''})}."
    )


def get_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw.strip())
    except ValueError:
        raise ImproperlyConfigured(
            f"Environment variable {name}={raw!r} is not a valid integer."
        )


def get_list(name: str, default: list[str] | None = None) -> list[str]:
    raw = os.environ.get(name)
    if raw is None:
        return list(default or [])
    return [item.strip() for item in raw.split(",") if item.strip()]


def parse_database_url(url: str, *, base_dir: Path, conn_max_age: int = 0) -> dict:
    """Return one Django ``DATABASES['default']`` dict for ``url``.

    Supported schemes:
      * ``sqlite:///relative/path.db`` or ``sqlite:////abs/path.db``
      * ``sqlite://:memory:``
      * ``postgres://user:pass@host:port/name?sslmode=require``
      * ``postgresql://...`` (alias of ``postgres``)

    Query parameters ``sslmode`` and ``conn_max_age`` are honoured; any other
    query parameter is passed through to the backend ``OPTIONS`` untouched.
    """

    if not url or not url.strip():
        raise ImproperlyConfigured("DATABASE_URL is empty.")

    parsed = urlparse(url.strip())
    scheme = parsed.scheme.lower()

    if scheme == "sqlite":
        # sqlite://:memory:  ->  netloc == ':memory:'
        if parsed.netloc in (":memory:", "") and parsed.path in ("", "/:memory:", ":memory:"):
            name: str | Path = ":memory:"
        else:
            raw_path = (parsed.netloc + parsed.path) if parsed.netloc else parsed.path
            raw_path = raw_path.lstrip("/") if not raw_path.startswith("//") else raw_path
            candidate = Path(unquote(raw_path or "db.sqlite3"))
            name = candidate if candidate.is_absolute() else (base_dir / candidate)
        return {"ENGINE": "django.db.backends.sqlite3", "NAME": str(name)}

    if scheme in ("postgres", "postgresql", "postgis"):
        if not parsed.hostname or not parsed.path.lstrip("/"):
            raise ImproperlyConfigured(
                f"DATABASE_URL {url!r} is missing a host or database name."
            )
        options: dict[str, str] = {}
        max_age = conn_max_age
        for pair in parsed.query.split("&"):
            if not pair or "=" not in pair:
                continue
            key, _, raw_value = pair.partition("=")
            value = unquote(raw_value)
            if key == "sslmode":
                options["sslmode"] = value
            elif key == "conn_max_age":
                try:
                    max_age = int(value)
                except ValueError:
                    raise ImproperlyConfigured(
                        f"DATABASE_URL conn_max_age={value!r} is not an integer."
                    )
            else:
                options[key] = value
        config = {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": unquote(parsed.path.lstrip("/")),
            "USER": unquote(parsed.username or ""),
            "PASSWORD": unquote(parsed.password or ""),
            "HOST": parsed.hostname or "",
            "PORT": str(parsed.port or ""),
            "CONN_MAX_AGE": max_age,
            "CONN_HEALTH_CHECKS": True,
        }
        if options:
            config["OPTIONS"] = options
        return config

    raise ImproperlyConfigured(
        f"DATABASE_URL scheme {scheme!r} is not supported "
        f"(expected 'sqlite', 'postgres', or 'postgresql')."
    )
