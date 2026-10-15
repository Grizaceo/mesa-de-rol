"""Utilidades de texto compartidas."""

from __future__ import annotations

import re
import unicodedata


def norm(texto: str) -> str:
    """Minúsculas sin tildes ni espacios sobrantes: 'Corazón ' -> 'corazon'."""
    descompuesto = unicodedata.normalize("NFKD", texto)
    sin_tildes = "".join(c for c in descompuesto if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", sin_tildes).strip().lower()


def con_signo(n: int) -> str:
    return f"+{n}" if n >= 0 else str(n)


def slug_valido(slug: str) -> bool:
    return bool(re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", slug))
