"""Utilidades de test: dados predecibles y una raíz de repo temporal."""

from __future__ import annotations

import json
import shutil
import tempfile
from contextlib import contextmanager
from pathlib import Path

from mesa import dados, estado

REPO = Path(__file__).resolve().parent.parent


class DadosFijos:
    """Sustituto de SystemRandom: devuelve los valores en orden."""

    def __init__(self, valores):
        self.valores = list(valores)

    def randint(self, a, b):
        valor = self.valores.pop(0)
        assert a <= valor <= b, f"valor {valor} fuera de [{a}, {b}]"
        return valor


@contextmanager
def dados_fijos(*valores):
    original = dados._rng
    dados._rng = DadosFijos(valores)
    try:
        yield
    finally:
        dados._rng = original


@contextmanager
def repo_temporal():
    """Copia plantilla, partida de ejemplo y visor a un directorio temporal y apunta estado.RAIZ ahí."""
    original = estado.RAIZ
    with tempfile.TemporaryDirectory() as tmp:
        raiz = Path(tmp)
        shutil.copytree(REPO / "partidas" / "_plantilla", raiz / "partidas" / "_plantilla")
        shutil.copytree(REPO / "partidas" / "los-hermanos-del-neva", raiz / "partidas" / "neva")
        datos = json.loads((raiz / "partidas" / "neva" / "partida.json").read_text(encoding="utf-8"))
        datos["slug"] = "neva"
        (raiz / "partidas" / "neva" / "partida.json").write_text(json.dumps(datos, ensure_ascii=False), encoding="utf-8")
        (raiz / "lecciones").mkdir()
        shutil.copy2(REPO / "lecciones" / "lecciones.jsonl", raiz / "lecciones" / "lecciones.jsonl")
        (raiz / "biblioteca" / "imagenes").mkdir(parents=True)
        (raiz / "biblioteca" / "imagenes" / "indice.json").write_text("[]", encoding="utf-8")
        (raiz / ".mesa-activa").write_text("neva\n", encoding="utf-8")
        estado.RAIZ = raiz
        try:
            yield raiz
        finally:
            estado.RAIZ = original
