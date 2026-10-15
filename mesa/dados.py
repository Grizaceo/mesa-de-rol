"""Dados con azar del sistema operativo.

Toda tirada de la mesa pasa por aquí: nada de dados "mentales". El generador es
`random.SystemRandom` (os.urandom); los tests lo reemplazan por uno predecible.
"""

from __future__ import annotations

import random
import re

CARAS_VALIDAS = (2, 3, 4, 6, 8, 10, 12, 20, 100)
_TERMINO = re.compile(r"([+-]?)(?:(\d*)d(\d+|%)|(\d+))")

_rng: random.Random = random.SystemRandom()


def tirar_dado(caras: int) -> int:
    return _rng.randint(1, caras)


def analizar(expr: str) -> list[tuple[int, int, int]]:
    """'2d6+1d4-1' -> [(1, 2, 6), (1, 1, 4), (-1, 1, 0)].

    Cada término es (signo, cantidad, caras); caras == 0 marca una constante.
    """
    s = expr.replace(" ", "").lower()
    if not s:
        raise ValueError("expresión de dados vacía")
    terminos: list[tuple[int, int, int]] = []
    pos = 0
    while pos < len(s):
        m = _TERMINO.match(s, pos)
        if not m or m.end() == pos:
            raise ValueError(f"expresión de dados inválida: {expr!r}")
        signo_txt = m.group(1)
        if terminos and not signo_txt:
            raise ValueError(f"falta + o - entre términos en {expr!r}")
        signo = -1 if signo_txt == "-" else 1
        if m.group(3) is not None:
            caras = 100 if m.group(3) == "%" else int(m.group(3))
            cantidad = int(m.group(2) or 1)
            if caras not in CARAS_VALIDAS:
                validas = ", ".join(f"d{c}" for c in CARAS_VALIDAS)
                raise ValueError(f"d{caras} no existe en esta mesa (válidos: {validas})")
            if not 1 <= cantidad <= 50:
                raise ValueError("entre 1 y 50 dados por término")
            terminos.append((signo, cantidad, caras))
        else:
            terminos.append((signo, int(m.group(4)), 0))
        pos = m.end()
    return terminos


def tirar(expr: str, critico: bool = False) -> dict:
    """Tira una expresión. Con crítico se duplican los dados, no el modificador (SRD 5.2)."""
    dados, modificador, suma = [], 0, 0
    for signo, cantidad, caras in analizar(expr):
        if caras == 0:
            modificador += signo * cantidad
            continue
        n = cantidad * 2 if critico else cantidad
        valores = [tirar_dado(caras) for _ in range(n)]
        dados.append({"dado": f"d{caras}", "signo": signo, "valores": valores})
        suma += signo * sum(valores)
    return {
        "expr": expr,
        "critico": critico,
        "dados": dados,
        "modificador": modificador,
        "total": suma + modificador,
    }


def resolver_modo(ventajas: list[str], desventajas: list[str]) -> str:
    """Ventaja y desventaja no se acumulan; si hay de ambas, se anulan (SRD 5.2)."""
    if ventajas and desventajas:
        return "normal"
    if ventajas:
        return "ventaja"
    if desventajas:
        return "desventaja"
    return "normal"


def prueba_d20(
    modificador: int,
    cd: int | None = None,
    modo: str = "normal",
    naturales: bool = True,
) -> dict:
    """Prueba d20. Con `naturales`, el 20 siempre acierta y el 1 siempre falla (regla de la casa)."""
    if modo not in ("normal", "ventaja", "desventaja"):
        raise ValueError(f"modo desconocido: {modo}")
    valores = [tirar_dado(20) for _ in range(1 if modo == "normal" else 2)]
    if modo == "ventaja":
        elegido = max(valores)
    elif modo == "desventaja":
        elegido = min(valores)
    else:
        elegido = valores[0]
    total = elegido + modificador
    nat20, nat1 = elegido == 20, elegido == 1

    if cd is None:
        exito = None
    elif naturales and nat20:
        exito = True
    elif naturales and nat1:
        exito = False
    else:
        exito = total >= cd

    if naturales and nat20:
        resultado = "critico"
    elif naturales and nat1:
        resultado = "uno_natural"
    elif exito is None:
        resultado = "sin_cd"
    else:
        resultado = "exito" if exito else "fallo"

    return {
        "valores": valores,
        "elegido": elegido,
        "modo": modo,
        "modificador": modificador,
        "total": total,
        "cd": cd,
        "exito": exito,
        "resultado": resultado,
        "natural_20": nat20,
        "natural_1": nat1,
        "margen": None if cd is None else total - cd,
    }
