"""Reglas d20-simple: cuatro atributos, pruebas d20, ventaja, críticos y combate ligero.

Basado en el SRD 5.2.1 (CC-BY-4.0), simplificado para principiantes; las
desviaciones están documentadas en reglas/d20-simple.md y guias/fuente-srd.md.
"""

from __future__ import annotations

from . import dados
from .texto import con_signo, norm

ATRIBUTOS = ("fuerza", "agilidad", "ingenio", "corazon")
NOMBRE_ATRIBUTO = {"fuerza": "Fuerza", "agilidad": "Agilidad", "ingenio": "Ingenio", "corazon": "Corazón"}
_ALIAS_ATRIBUTO = {
    "fue": "fuerza", "str": "fuerza", "fuer": "fuerza",
    "agi": "agilidad", "dex": "agilidad", "des": "agilidad",
    "ing": "ingenio", "int": "ingenio", "wis": "ingenio", "sab": "ingenio",
    "cor": "corazon", "cha": "corazon", "car": "corazon",
}

# Las 18 habilidades del SRD 5.2 y el atributo de esta mesa que las cubre.
# (nombre en español, atributo, nombre SRD)
HABILIDADES = [
    ("Acrobacias", "agilidad", "Acrobatics"),
    ("Trato con animales", "corazon", "Animal Handling"),
    ("Arcanos", "ingenio", "Arcana"),
    ("Atletismo", "fuerza", "Athletics"),
    ("Engaño", "ingenio", "Deception"),
    ("Historia", "ingenio", "History"),
    ("Perspicacia", "corazon", "Insight"),
    ("Intimidación", "fuerza", "Intimidation"),
    ("Investigación", "ingenio", "Investigation"),
    ("Medicina", "ingenio", "Medicine"),
    ("Naturaleza", "ingenio", "Nature"),
    ("Percepción", "ingenio", "Perception"),
    ("Interpretación", "corazon", "Performance"),
    ("Persuasión", "corazon", "Persuasion"),
    ("Religión", "ingenio", "Religion"),
    ("Juego de manos", "agilidad", "Sleight of Hand"),
    ("Sigilo", "agilidad", "Stealth"),
    ("Supervivencia", "ingenio", "Survival"),
]
_HABILIDAD_POR_CLAVE = {}
for _es, _attr, _en in HABILIDADES:
    _HABILIDAD_POR_CLAVE[norm(_es)] = (_attr, _es)
    _HABILIDAD_POR_CLAVE[norm(_en)] = (_attr, _es)

DIFICULTADES = {
    "muy facil": 5,
    "facil": 10, "sencilla": 10,
    "media": 15, "exigente": 15,
    "dificil": 20,
    "muy dificil": 25,
    "casi imposible": 30,
}

# Condiciones del SRD 5.2 adaptadas (las mágicas quedan fuera) + propias de la mesa.
# desventaja: atributos afectados, "todo" o "ataques"; ventaja_contra: los ataques contra
# quien la sufre tienen ventaja; penalizador_por_nivel: resta a toda prueba d20.
CONDICIONES = {
    "agarrado": {"nombre": "Agarrado", "efecto": "No puede moverse; desventaja al atacar a otro que no sea quien lo agarra.", "desventaja": ["ataques"]},
    "apresado": {"nombre": "Apresado", "efecto": "No puede moverse; sus ataques tienen desventaja y los ataques contra él, ventaja.", "desventaja": ["ataques", "agilidad"], "ventaja_contra": True},
    "asustado": {"nombre": "Asustado", "efecto": "Desventaja en pruebas y ataques mientras vea la fuente del miedo; no puede acercarse a ella.", "desventaja": ["todo"]},
    "aturdido": {"nombre": "Aturdido", "efecto": "Incapacitado; los ataques contra él tienen ventaja.", "ventaja_contra": True},
    "cegado": {"nombre": "Cegado", "efecto": "Falla lo que requiera vista; ataca con desventaja y lo atacan con ventaja.", "desventaja": ["ataques"], "ventaja_contra": True},
    "derribado": {"nombre": "Derribado", "efecto": "En el suelo: ataca con desventaja; cuerpo a cuerpo lo atacan con ventaja. Levantarse cuesta medio movimiento.", "desventaja": ["ataques"], "ventaja_contra": True},
    "empapado": {"nombre": "Empapado", "efecto": "Ropa mojada y frío: desventaja en Agilidad hasta secarse o cambiarse.", "desventaja": ["agilidad"]},
    "ensordecido": {"nombre": "Ensordecido", "efecto": "No oye; falla lo que requiera oído."},
    "envenenado": {"nombre": "Envenenado", "efecto": "Desventaja en pruebas y ataques.", "desventaja": ["todo"]},
    "incapacitado": {"nombre": "Incapacitado", "efecto": "No puede actuar ni hablar."},
    "inconsciente": {"nombre": "Inconsciente", "efecto": "Incapacitado y derribado; suelta lo que tenga. Los ataques contra él tienen ventaja.", "ventaja_contra": True},
    "oculto": {"nombre": "Oculto", "efecto": "Escondido (SRD: Hide). Lo encuentra quien iguale su tirada de Sigilo con Percepción. Se pierde al hacer ruido o atacar."},
    "agotamiento": {"nombre": "Agotamiento", "efecto": "-2 por nivel a toda prueba d20. Un descanso largo quita un nivel. En el nivel 6, fuera de combate.", "penalizador_por_nivel": 2, "niveles": 1},
    "fuera de combate": {"nombre": "Fuera de combate", "efecto": "Vida en 0: no actúa. Un aliado puede estabilizarlo con una acción si llega a su lado. No muere salvo modo letal acordado.", "ventaja_contra": True},
}

# Amenazas de referencia (vida, defensa, ataque, daño, protección), escaladas al d20.
# Comparables con el SRD 5.2: Mastiff CA12/5 PG, Bandit CA12/11 PG, Guard CA16/11 PG.
PLANTILLAS_ENEMIGO = {
    "rata": {"nombre": "Rata grande", "vida": 3, "defensa": 10, "ataque": 0, "dano": "1d2", "proteccion": 0},
    "perro": {"nombre": "Perro asustado", "vida": 5, "defensa": 12, "ataque": 1, "dano": "1d4", "proteccion": 0},
    "maton": {"nombre": "Matón de muelle", "vida": 8, "defensa": 12, "ataque": 1, "dano": "1d6", "proteccion": 0},
    "guardia": {"nombre": "Guardia armado", "vida": 10, "defensa": 14, "ataque": 2, "dano": "1d6", "proteccion": 1,
                "armas": [{"nombre": "Porra", "dano": "1d6"}, {"nombre": "Rifle", "dano": "1d12", "distancia": True}]},
}

COBERTURA = {"media": 2, "tres-cuartos": 5, "tres cuartos": 5}

# Condiciones con las que no se puede atacar.
_NO_ACTUA = {"fuera de combate", "inconsciente", "incapacitado", "aturdido"}


def resolver_atributo(nombre: str) -> tuple[str, str | None]:
    """'percepción' -> ('ingenio', 'Percepción'); 'Fuerza' -> ('fuerza', None)."""
    clave = norm(nombre)
    clave = _ALIAS_ATRIBUTO.get(clave, clave)
    if clave in ATRIBUTOS:
        return clave, None
    if clave in _HABILIDAD_POR_CLAVE:
        return _HABILIDAD_POR_CLAVE[clave]
    opciones = ", ".join(NOMBRE_ATRIBUTO.values())
    raise ValueError(f"{nombre!r} no es atributo ni habilidad conocida (atributos: {opciones}; habilidades: ver guias/habilidades.md)")


def resolver_cd(cd: str | int | None) -> int | None:
    if cd is None or cd == "":
        return None
    if isinstance(cd, int):
        return cd
    texto = norm(str(cd)).replace("-", " ").replace("_", " ")
    if texto.lstrip("-").isdigit():
        return int(texto)
    if texto in DIFICULTADES:
        return DIFICULTADES[texto]
    raise ValueError(f"dificultad desconocida: {cd!r} (usa un número o: {', '.join(sorted(set(DIFICULTADES)))})")


def condicion_de_catalogo(nombre: str) -> dict | None:
    base = CONDICIONES.get(norm(nombre))
    return dict(base) if base else None


def _efectos(ficha: dict, ambito: str) -> tuple[list[str], list[str], int]:
    """Ventajas, desventajas y penalizador fijo que imponen las condiciones de la ficha.

    `ambito` es un atributo ('agilidad') o 'ataques'.
    """
    ventajas, desventajas, penalizador = [], [], 0
    for c in ficha.get("condiciones", []):
        afectados = {norm(a) for a in c.get("desventaja", [])}
        if "todo" in afectados or ambito in afectados:
            desventajas.append(c["nombre"])
        favorecidos = {norm(a) for a in c.get("ventaja", [])}
        if "todo" in favorecidos or ambito in favorecidos:
            ventajas.append(c["nombre"])
        if c.get("penalizador_por_nivel"):
            penalizador -= int(c["penalizador_por_nivel"]) * int(c.get("niveles", 1))
    return ventajas, desventajas, penalizador


def buscar_habilidad(ficha: dict, nombre: str) -> dict:
    clave = norm(nombre).strip("¡!¿?«» ")
    for h in ficha.get("habilidades", []):
        if clave and norm(h["nombre"]).strip("¡!¿?«» ").startswith(clave):
            return h
    raise ValueError(f"{ficha['nombre']} no tiene la habilidad {nombre!r}")


def buscar_arma(ficha: dict, nombre: str | None) -> dict:
    armas = ficha.get("equipo", []) if ficha.get("atributos") else ficha.get("armas", [])
    armas = [a for a in armas if a.get("dano")]
    if not armas:
        if ficha.get("dano"):
            return {"nombre": "Ataque", "dano": ficha["dano"]}
        raise ValueError(f"{ficha['nombre']} no tiene armas con daño")
    if nombre is None:
        return armas[0]
    clave = norm(nombre)
    for a in armas:
        if norm(a["nombre"]).startswith(clave) or clave in norm(a["nombre"]):
            return a
    raise ValueError(f"{ficha['nombre']} no lleva {nombre!r} (lleva: {', '.join(a['nombre'] for a in armas)})")


def _motivos(declarada: bool | str, extra: list[str]) -> list[str]:
    motivos = list(extra)
    if declarada:
        motivos.insert(0, declarada if isinstance(declarada, str) else "declarada")
    return motivos


def prueba(
    partida: dict,
    ficha: dict,
    atributo: str,
    cd: str | int | None = None,
    ventaja: bool | str = False,
    desventaja: bool | str = False,
    bonos: list[tuple[int, str]] | None = None,
    oficio: bool = False,
    usar: str | None = None,
    etiqueta: str = "",
) -> dict:
    """Prueba de atributo o habilidad. Muta la ficha si se gasta una habilidad."""
    reglas = partida.get("reglas", {})
    attr, habilidad = resolver_atributo(atributo)
    partes = [{"fuente": NOMBRE_ATRIBUTO[attr], "valor": int(ficha.get("atributos", {}).get(attr, 0))}]
    if oficio:
        partes.append({"fuente": "Oficio", "valor": int(reglas.get("bono_oficio", 2))})
    if usar:
        hab = buscar_habilidad(ficha, usar)
        if not hab.get("disponible", True):
            raise ValueError(f"«{hab['nombre']}» ya está gastada ({hab.get('recarga', 'sin recarga')})")
        if hab.get("bono"):
            partes.append({"fuente": hab["nombre"], "valor": int(hab["bono"])})
        hab["disponible"] = False
    for valor, fuente in bonos or []:
        partes.append({"fuente": fuente or "bono", "valor": valor})

    v_cond, d_cond, penalizador = _efectos(ficha, attr)
    if penalizador:
        partes.append({"fuente": "Agotamiento", "valor": penalizador})
    ventajas = _motivos(ventaja, v_cond)
    desventajas = _motivos(desventaja, d_cond)
    modo = dados.resolver_modo(ventajas, desventajas)
    modificador = sum(p["valor"] for p in partes)
    r = dados.prueba_d20(modificador, resolver_cd(cd), modo, naturales=reglas.get("naturales", True))
    return {
        "tipo": "prueba",
        "quien": ficha["nombre"],
        "atributo": attr,
        "habilidad": habilidad,
        "etiqueta": etiqueta,
        "partes": partes,
        "ventajas": ventajas,
        "desventajas": desventajas,
        "habilidad_usada": usar,
        **r,
    }


def aplicar_vida(ficha: dict, delta: int) -> dict:
    """Suma o resta vida dentro de [0, máximo] y gestiona 'Fuera de combate'."""
    maximo = int(ficha.get("vida_max", ficha.get("vida", 0)))
    antes = int(ficha.get("vida", 0))
    ficha["vida"] = max(0, min(maximo, antes + delta))
    nombres = {norm(c["nombre"]) for c in ficha.get("condiciones", [])}
    if ficha["vida"] == 0 and "fuera de combate" not in nombres:
        ficha.setdefault("condiciones", []).append(condicion_de_catalogo("fuera de combate"))
    if ficha["vida"] > 0 and "fuera de combate" in nombres:
        ficha["condiciones"] = [c for c in ficha["condiciones"] if norm(c["nombre"]) != "fuera de combate"]
    return {"antes": antes, "despues": ficha["vida"], "maximo": maximo}


def dano(
    partida: dict,
    expr: str,
    objetivo: dict | None = None,
    critico: bool = False,
) -> dict:
    """Tira daño; si hay objetivo, resta su protección (mínimo 1 si así lo dice la partida) y aplica."""
    reglas = partida.get("reglas", {})
    tirada = dados.tirar(expr, critico=critico and reglas.get("critico_dobla_dados", True))
    resultado = {"tirada": tirada, "bruto": tirada["total"]}
    if objetivo is not None:
        proteccion = int(objetivo.get("proteccion", 0))
        minimo = int(reglas.get("dano_minimo", 1))
        final = max(minimo, tirada["total"] - proteccion)
        resultado.update(
            {"objetivo": objetivo["nombre"], "proteccion": proteccion, "final": final, "vida": aplicar_vida(objetivo, -final)}
        )
    return resultado


def ataque(
    partida: dict,
    atacante: dict,
    objetivo: dict,
    arma: str | None = None,
    ventaja: bool | str = False,
    desventaja: bool | str = False,
    bonos: list[tuple[int, str]] | None = None,
    oficio: bool = False,
    cobertura: str | None = None,
    atributo: str | None = None,
    etiqueta: str = "",
) -> dict:
    """Tirada de ataque contra la Defensa del objetivo y, si acierta, daño aplicado."""
    reglas = partida.get("reglas", {})
    if int(atacante.get("vida", 1)) <= 0:
        raise ValueError(f"{atacante['nombre']} está en 0 de vida: no puede atacar")
    impide = next((c["nombre"] for c in atacante.get("condiciones", []) if norm(c["nombre"]) in _NO_ACTUA), None)
    if impide:
        raise ValueError(f"{atacante['nombre']} no puede atacar: está {impide}")
    elegida = buscar_arma(atacante, arma)
    if atacante.get("atributos"):
        attr = resolver_atributo(atributo)[0] if atributo else ("agilidad" if elegida.get("distancia") else "fuerza")
        partes = [{"fuente": NOMBRE_ATRIBUTO[attr], "valor": int(atacante["atributos"].get(attr, 0))}]
    else:
        attr = None
        partes = [{"fuente": "Ataque", "valor": int(atacante.get("ataque", 0))}]
    if oficio:
        partes.append({"fuente": "Oficio", "valor": int(reglas.get("bono_oficio", 2))})
    for valor, fuente in bonos or []:
        partes.append({"fuente": fuente or "bono", "valor": valor})

    v_cond, d_cond, penalizador = _efectos(atacante, "ataques")
    if attr:
        v_attr, d_attr, _ = _efectos(atacante, attr)
        v_cond += [m for m in v_attr if m not in v_cond]
        d_cond += [m for m in d_attr if m not in d_cond]
    if penalizador:
        partes.append({"fuente": "Agotamiento", "valor": penalizador})
    ventajas = _motivos(ventaja, v_cond)
    ventajas += [f"{c['nombre']} (objetivo)" for c in objetivo.get("condiciones", []) if c.get("ventaja_contra")]
    desventajas = _motivos(desventaja, d_cond)

    defensa = int(objetivo.get("defensa", 10))
    extra = COBERTURA.get(norm(cobertura or ""), 0)
    modo = dados.resolver_modo(ventajas, desventajas)
    r = dados.prueba_d20(sum(p["valor"] for p in partes), defensa + extra, modo, naturales=reglas.get("naturales", True))
    evento = {
        "tipo": "ataque",
        "quien": atacante["nombre"],
        "objetivo": objetivo["nombre"],
        "arma": elegida["nombre"],
        "etiqueta": etiqueta,
        "partes": partes,
        "ventajas": ventajas,
        "desventajas": desventajas,
        "cobertura": extra,
        **r,
    }
    if r["exito"]:
        evento["dano"] = dano(partida, elegida["dano"], objetivo, critico=r["resultado"] == "critico")
    return evento


def describir_prueba(e: dict) -> str:
    """Línea legible para el chat: lo que el director pega en RESULTADO."""
    quien = e.get("quien", "")
    que = e.get("habilidad") or NOMBRE_ATRIBUTO.get(e.get("atributo") or "", "")
    if e["tipo"] == "ataque":
        que = f"ataca a {e['objetivo']}" if e["arma"] == "Ataque" else f"ataque con {e['arma']} a {e['objetivo']}"
    cabeza = " · ".join(x for x in (quien, que, e.get("etiqueta")) if x)
    if e["modo"] == "normal":
        dado = f"1d20 ({e['elegido']})"
    else:
        dado = f"2d20 con {e['modo']} ({' y '.join(map(str, e['valores']))}, vale el {e['elegido']})"
    mods = " ".join(f"{con_signo(p['valor'])} {p['fuente']}" for p in e["partes"] if p["valor"] or p["fuente"])
    cuerpo = f"{dado} {mods} = {e['total']}"
    if e.get("cd") is not None:
        cuerpo += f" contra {'Defensa' if e['tipo'] == 'ataque' else 'dificultad'} {e['cd']}"
    etiquetas = {
        "critico": "¡CRÍTICO! (20 natural)",
        "uno_natural": "fallo (1 natural)",
        "exito": "éxito",
        "fallo": "fallo",
        "sin_cd": "",
    }
    salida = f"{cabeza}: {cuerpo}"
    if etiquetas[e["resultado"]]:
        salida += f" → {etiquetas[e['resultado']]}"
    if e["modo"] == "ventaja":
        salida += f" [ventaja: {', '.join(e['ventajas'])}]"
    elif e["modo"] == "desventaja":
        salida += f" [desventaja: {', '.join(e['desventajas'])}]"
    elif e.get("ventajas") and e.get("desventajas"):
        salida += f" [se anulan ventaja ({', '.join(e['ventajas'])}) y desventaja ({', '.join(e['desventajas'])})]"
    if e.get("dano"):
        d = e["dano"]
        valores = " + ".join(str(v) for t in d["tirada"]["dados"] for v in t["valores"])
        salida += (
            f"\n  daño {d['tirada']['expr']}{' (crítico: dados dobles)' if d['tirada']['critico'] else ''}: "
            f"{valores} = {d['bruto']} − protección {d['proteccion']} = {d['final']}"
            f" → {d['objetivo']} {d['vida']['despues']}/{d['vida']['maximo']}"
        )
    return salida
