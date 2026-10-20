"""Diagnóstico dry-run (P1.4) y migración en copia validada (P1.5) de legacy a D&D 2024.

Principios:
- No se convierten los cuatro bonos de `d20-simple` (`fuerza`, `agilidad`, `ingenio`,
  `corazon`) en las seis puntuaciones de D&D 2024 por heurística, ni se inventan clases,
  especies, conjuros o competencias por analogía.
- `diagnosticar` es de solo lectura (dry-run): inspecciona la partida y enumera qué falta
  y qué deben acordar los jugadores.
- `migrar_copia` nunca modifica la partida original ni reescribe los eventos históricos:
  crea una copia en un slug nuevo (o en una raíz scratch), exige las seis características
  acordadas para cada personaje, añade un único evento `partida_migrada` al final y deja
  un resumen en `migracion-2024.md` con instrucciones de rollback.
"""

from __future__ import annotations

import copy
import json
import shutil
from pathlib import Path

from . import esquemas, estado
from .texto import norm, slug_valido

_CLAVES_REGLAS_LEGACY = ("bono_oficio", "atributo_maximo", "dano_minimo", "critico_dobla_dados")
_CAMPOS_OPCIONALES_FICHA = (
    "nivel", "vida", "vida_max", "defensa", "clase", "subclase", "especie",
    "trasfondo", "competencias", "rasgos", "habilidades", "equipo",
)


def _buscar_ficha_acordada(fichas_2024: dict | None, personaje: dict) -> dict | None:
    if not fichas_2024:
        return None
    claves = {norm(personaje.get("id", "")), norm(personaje.get("nombre", ""))} - {""}
    for k, valor in fichas_2024.items():
        if norm(str(k)) in claves and isinstance(valor, dict):
            return valor
    return None


def _diagnosticar_atributos_acordados(ficha_acordada: dict | None) -> tuple[list[str], list[str]]:
    """Devuelve (caracteristicas_faltantes, errores_atributos) respecto del esquema 2024."""
    if not ficha_acordada or not isinstance(ficha_acordada.get("atributos"), dict):
        return list(esquemas.IDS_2024), []
    attrs = ficha_acordada["atributos"]
    resueltos: dict[str, object] = {}
    errores: list[str] = []
    for k, v in attrs.items():
        canon = esquemas.resolver_atributo_2024(str(k))
        if canon is None:
            errores.append(f"característica desconocida {k!r}")
        else:
            resueltos[canon] = v
    faltantes = [i for i in esquemas.IDS_2024 if i not in resueltos]
    for clave in esquemas.IDS_2024:
        if clave in resueltos:
            valor = resueltos[clave]
            if not isinstance(valor, int) or isinstance(valor, bool) or not (
                esquemas.PUNTUACION_MINIMA <= valor <= esquemas.PUNTUACION_MAXIMA
            ):
                errores.append(
                    f"{esquemas.NOMBRES_2024[clave]} debe ser entero de "
                    f"{esquemas.PUNTUACION_MINIMA} a {esquemas.PUNTUACION_MAXIMA} (dice {valor!r})"
                )
    return faltantes, errores


def diagnosticar(datos: dict, slug: str = "", fichas_2024: dict | None = None) -> dict:
    """Inspecciona una partida sin modificarla y devuelve qué requiere una migración a 2024."""
    esquemas.validar(datos, slug)
    version = esquemas.version_de(datos)
    ident = slug or datos.get("slug", "")
    if version == esquemas.VERSION_2024:
        return {
            "slug": ident,
            "titulo": datos.get("titulo", ident),
            "ya_es_2024": True,
            "version_actual": esquemas.VERSION_2024,
            "reglamento_actual": datos.get("reglamento", esquemas.REGLAMENTO_2024),
            "version_objetivo": esquemas.VERSION_2024,
            "reglamento_objetivo": esquemas.REGLAMENTO_2024,
            "listo_para_migrar": True,
            "campos_partida": [],
            "personajes": [],
            "acciones_humanas": [],
        }

    reglas_actuales = datos.get("reglas") or {}
    claves_legacy = [k for k in _CLAVES_REGLAS_LEGACY if k in reglas_actuales]
    campos_partida = [
        {"campo": "schema_version", "actual": datos.get("schema_version"), "objetivo": esquemas.VERSION_2024},
        {"campo": "reglamento", "actual": datos.get("reglamento", esquemas.REGLAMENTO_LEGACY), "objetivo": esquemas.REGLAMENTO_2024},
    ]
    if claves_legacy:
        campos_partida.append({
            "campo": "reglas",
            "claves_legacy": claves_legacy,
            "nota": "En D&D 2024 el bonificador de competencia deriva del nivel y no hay tope +4 ni resta plana de protección.",
        })

    informes_pj = []
    acciones_humanas = []
    todos_listos = True

    for p in datos.get("personajes", []):
        nombre = p["nombre"]
        acordada = _buscar_ficha_acordada(fichas_2024, p)
        faltantes, errores = _diagnosticar_atributos_acordados(acordada)
        if faltantes or errores:
            todos_listos = False
        attrs_legacy = dict(p.get("atributos") or {})
        tiene_oficio = bool(p.get("oficio"))
        proteccion = int(p.get("proteccion", 0))
        habs_legacy = [
            h["nombre"] for h in p.get("habilidades", [])
            if h.get("recarga") in ("escena", "combate")
        ]
        armas = [e["nombre"] for e in p.get("equipo", []) if e.get("dano")]

        decisiones_pj = []
        if faltantes:
            decisiones_pj.append(
                f"Acordar las 6 puntuaciones 2024 (1–30) de {nombre}: {', '.join(faltantes)} "
                f"(hoy tiene bonos d20-simple {attrs_legacy}; no se convierten por heurística)."
            )
        for err in errores:
            decisiones_pj.append(f"Corregir en {nombre}: {err}.")
        if tiene_oficio:
            aplica = (p.get("oficio") or {}).get("aplica", "")
            decisiones_pj.append(
                f"Decidir competencias de habilidades/salvaciones/herramientas de {nombre} "
                f"para sustituir su Oficio legacy ({aplica!r})."
            )
        if proteccion > 0:
            decisiones_pj.append(
                f"Revisar CA (`defensa`, hoy {p.get('defensa', 10)}) de {nombre}: "
                f"en 2024 no se resta `proteccion` plana ({proteccion})."
            )
        if habs_legacy:
            decisiones_pj.append(
                f"Revisar habilidades con recarga por escena/combate de {nombre} ({', '.join(habs_legacy)}): "
                "decidir si quedan como rasgos de casa o pasan a recarga por descanso corto/largo."
            )
        acciones_humanas.extend(decisiones_pj)
        informes_pj.append({
            "id": p.get("id", norm(nombre)),
            "nombre": nombre,
            "nivel": int(p.get("nivel", 1)),
            "atributos_legacy": attrs_legacy,
            "caracteristicas_faltantes": faltantes,
            "errores_atributos": errores,
            "tiene_oficio_legacy": tiene_oficio,
            "proteccion_plana_legacy": proteccion,
            "habilidades_recarga_legacy": habs_legacy,
            "armas_actuales": armas,
            "listo": not faltantes and not errores,
            "decisiones": decisiones_pj,
        })

    return {
        "slug": ident,
        "titulo": datos.get("titulo", ident),
        "ya_es_2024": False,
        "version_actual": version,
        "reglamento_actual": datos.get("reglamento", esquemas.REGLAMENTO_LEGACY),
        "version_objetivo": esquemas.VERSION_2024,
        "reglamento_objetivo": esquemas.REGLAMENTO_2024,
        "listo_para_migrar": todos_listos and bool( datos.get("personajes") ),
        "campos_partida": campos_partida,
        "personajes": informes_pj,
        "acciones_humanas": acciones_humanas,
    }


def formatear_diagnostico(informe: dict) -> str:
    """Resumen legible para la terminal del diagnóstico dry-run."""
    slug = informe.get("slug") or "(partida)"
    titulo = informe.get("titulo") or slug
    if informe.get("ya_es_2024"):
        return (
            f"# Diagnóstico de migración — {titulo} ({slug})\n\n"
            "La partida ya usa el esquema 2 (`dnd-2024`). No requiere migración."
        )
    lineas = [
        f"# Diagnóstico de migración (dry-run) — {titulo} ({slug})",
        "",
        f"- Esquema actual: `{informe['version_actual']}` (`{informe['reglamento_actual']}`)",
        f"- Esquema objetivo: `{informe['version_objetivo']}` (`{informe['reglamento_objetivo']}`)",
        f"- Listo para migrar: **{'sí' if informe['listo_para_migrar'] else 'no (requiere ficha acordada)'}**",
        "",
        "> Nota: esta herramienta **no convierte** los 4 atributos de `d20-simple` en las 6",
        "> características de D&D 2024 por heurística, ni inventa clases, equipo o conjuros.",
        "> La partida original nunca se modifica en el sitio.",
        "",
        "## Personajes",
    ]
    for pj in informe.get("personajes", []):
        estado_pj = "listo" if pj["listo"] else f"faltan: {', '.join(pj['caracteristicas_faltantes']) or 'corregir rangos'}"
        lineas.append(f"- **{pj['nombre']}** (id `{pj['id']}`, nivel {pj['nivel']}) — {estado_pj}")
        lineas.append(f"  - Bonos legacy actuales: `{json.dumps(pj['atributos_legacy'], ensure_ascii=False)}`")
        for dec in pj.get("decisiones", []):
            lineas.append(f"  - Acción humana: {dec}")
    lineas += [
        "",
        "## Cómo ejecutar la migración en copia cuando estén acordadas las fichas",
        f"`bin/mesa -p {slug} migrar copiar {slug}-2024 --fichas fichas-2024.json`",
    ]
    return "\n".join(lineas)


def parsear_atributos_inline(items: list[str] | None) -> dict[str, dict]:
    """Convierte `--atributos 'Jualjin=fuerza:16,destreza:12,...'` en diccionario de fichas."""
    salida: dict[str, dict] = {}
    for item in items or []:
        quien, sep, resto = item.partition("=")
        if not sep or not quien.strip() or not resto.strip():
            raise ValueError(
                f"formato inválido en --atributos {item!r}: "
                "usa 'Nombre=fuerza:16,destreza:12,constitucion:14,inteligencia:10,sabiduria:11,carisma:13'"
            )
        attrs: dict[str, int] = {}
        for par in resto.split(","):
            k, sep_kv, v = par.strip().partition(":")
            if not sep_kv:
                raise ValueError(f"par atributo:valor inválido {par!r} en {item!r}")
            canon = esquemas.resolver_atributo_2024(k.strip())
            if canon is None:
                raise ValueError(f"característica 2024 desconocida: {k.strip()!r}")
            try:
                attrs[canon] = int(v.strip())
            except ValueError as e:
                raise ValueError(f"puntuación no entera para {canon}: {v.strip()!r}") from e
        salida[norm(quien.strip())] = {"atributos": attrs}
    return salida


def cargar_fichas_2024(ruta_o_json: str | None = None, inline: list[str] | None = None) -> dict:
    """Combina un archivo/JSON de fichas 2024 con definiciones `--atributos` de la CLI."""
    fichas: dict = {}
    if ruta_o_json:
        candidato = Path(ruta_o_json).expanduser()
        texto = candidato.read_text(encoding="utf-8") if candidato.is_file() else ruta_o_json
        try:
            cargado = json.loads(texto)
        except json.JSONDecodeError as e:
            raise ValueError(f"no se pudo leer --fichas {ruta_o_json!r} como archivo ni como JSON ({e})") from e
        if not isinstance(cargado, dict):
            raise ValueError("el archivo de --fichas debe ser un objeto JSON indexado por id o nombre de personaje")
        fichas.update(cargado)
    for k, v in parsear_atributos_inline(inline).items():
        actual = _buscar_ficha_acordada(fichas, {"id": k, "nombre": k})
        if actual is not None:
            actual.setdefault("atributos", {}).update(v["atributos"])
        else:
            fichas[k] = v
    return fichas


def _normalizar_atributos_2024(attrs: dict) -> dict[str, int]:
    salida: dict[str, int] = {}
    for k, v in attrs.items():
        canon = esquemas.resolver_atributo_2024(str(k))
        if canon is None:
            raise ValueError(f"característica desconocida: {k!r}")
        salida[canon] = int(v)
    return {clave: salida[clave] for clave in esquemas.IDS_2024}


def _resumen_migracion_md(
    slug_origen: str,
    slug_destino: str,
    datos_origen: dict,
    datos_nuevos: dict,
    cambios_pj: list[dict],
) -> str:
    lineas = [
        f"# Migración a D&D 2024 — {datos_nuevos.get('titulo', slug_destino)}",
        "",
        f"- **Partida original (intacta):** `{slug_origen}` (versión {datos_origen.get('version', 0)}, `{datos_origen.get('reglamento', 'd20-simple')}`)",
        f"- **Copia migrada:** `{slug_destino}` (`schema_version: 2`, `reglamento: dnd-2024`)",
        f"- **Fecha:** `{datos_nuevos['migrada_desde']['fecha']}`",
        "",
        "## Cambios por personaje",
    ]
    for c in cambios_pj:
        mods = ", ".join(
            f"{esquemas.NOMBRES_2024[k]} {v} ({esquemas.modificador(v):+d})"
            for k, v in c["atributos_2024"].items()
        )
        lineas.append(f"- **{c['nombre']}** (nivel {c['nivel']}, competencia +{esquemas.competencia(c['nivel'])}):")
        lineas.append(f"  - Antes (`d20-simple`): `{json.dumps(c['atributos_legacy'], ensure_ascii=False)}`")
        lineas.append(f"  - Ahora (`dnd-2024`): {mods}")
        if c.get("extras"):
            lineas.append(f"  - Campos acordados: {', '.join(c['extras'])}")
    lineas += [
        "",
        "## Garantías y rollback",
        f"- La partida original `{slug_origen}` y su `eventos.jsonl` no se modificaron.",
        "- Los eventos históricos de la copia se conservaron íntegros y solo se añadió al final el evento `partida_migrada`.",
        f"- **Rollback:** vuelve a la partida original con `bin/mesa usar {slug_origen}` y borra la carpeta de la copia `{slug_destino}`.",
        "",
    ]
    return "\n".join(lineas)


def migrar_copia(
    slug: str,
    destino: str,
    fichas_2024: dict,
    *,
    raiz_destino: Path | None = None,
) -> dict:
    """Crea una copia migrada a D&D 2024 validando las fichas acordadas, sin tocar el original."""
    if not slug_valido(destino):
        raise ValueError("el slug de destino va en minúsculas, con guiones: p. ej. 'neva-2024'")
    dir_origen = estado.dir_partida(slug)
    base_partidas = (Path(raiz_destino).expanduser() / "partidas") if raiz_destino is not None else estado.dir_partidas()
    dir_destino = base_partidas / destino
    if dir_destino.resolve() == dir_origen.resolve():
        raise ValueError(
            "no se migra la partida original en el sitio: elige otro slug para la copia "
            f"(p. ej. `{slug}-2024`) o indica `--raiz-destino`"
        )
    if dir_destino.exists():
        raise FileExistsError(f"ya existe la copia de destino: {dir_destino}")

    datos_origen = estado.cargar(slug)
    informe = diagnosticar(datos_origen, slug, fichas_2024=fichas_2024)
    if not informe["listo_para_migrar"]:
        pendientes = []
        for pj in informe["personajes"]:
            if not pj["listo"]:
                detalle = ", ".join(pj["caracteristicas_faltantes"] + pj["errores_atributos"])
                pendientes.append(f"{pj['nombre']} ({detalle})")
        raise ValueError(
            "no se puede migrar sin las 6 características 2024 acordadas por personaje "
            f"(no se convierten por heurística): {'; '.join(pendientes)}"
        )

    datos_nuevos = copy.deepcopy(datos_origen)
    fecha = estado.ahora()
    reglas_previas = dict(datos_nuevos.get("reglas") or {})
    reglas_legacy_guardadas = {k: reglas_previas.pop(k) for k in _CLAVES_REGLAS_LEGACY if k in reglas_previas}
    datos_nuevos["slug"] = destino
    datos_nuevos["schema_version"] = esquemas.VERSION_2024
    datos_nuevos["reglamento"] = esquemas.REGLAMENTO_2024
    datos_nuevos["reglas"] = reglas_previas
    datos_nuevos["migrada_desde"] = {
        "slug": slug,
        "schema_version": esquemas.version_de(datos_origen),
        "reglamento": datos_origen.get("reglamento", esquemas.REGLAMENTO_LEGACY),
        "version": datos_origen.get("version", 0),
        "fecha": fecha,
        "reglas_legado_d20_simple": reglas_legacy_guardadas,
    }

    cambios_pj = []
    for p in datos_nuevos.get("personajes", []):
        acordada = _buscar_ficha_acordada(fichas_2024, p)
        assert acordada is not None
        attrs_legacy = dict(p.get("atributos") or {})
        legado_pj: dict = {"atributos": attrs_legacy}
        if "oficio" in p:
            legado_pj["oficio"] = p.pop("oficio")
        if p.get("proteccion"):
            legado_pj["proteccion"] = p["proteccion"]
        p["legado_d20_simple"] = legado_pj
        p["atributos"] = _normalizar_atributos_2024(acordada["atributos"])
        p["proteccion"] = int(acordada.get("proteccion", 0))
        extras_aplicados = []
        for campo in _CAMPOS_OPCIONALES_FICHA:
            if campo in acordada:
                p[campo] = copy.deepcopy(acordada[campo])
                extras_aplicados.append(campo)
        cambios_pj.append({
            "nombre": p["nombre"],
            "nivel": int(p.get("nivel", 1)),
            "atributos_legacy": attrs_legacy,
            "atributos_2024": dict(p["atributos"]),
            "extras": extras_aplicados,
        })

    datos_nuevos["version"] = int(datos_origen.get("version", 0)) + 1
    datos_nuevos["actualizado"] = fecha
    esquemas.validar(datos_nuevos, destino)

    base_partidas.mkdir(parents=True, exist_ok=True)
    shutil.copytree(
        dir_origen,
        dir_destino,
        ignore=shutil.ignore_patterns(estado.CANDADO, f"{estado.DIARIO}*"),
    )

    ruta_eventos_destino = dir_destino / "eventos.jsonl"
    ultimo_seq = estado._reparar_eventos(ruta_eventos_destino)
    evento_migracion = {
        "seq": ultimo_seq + 1,
        "ts": fecha,
        "tipo": "partida_migrada",
        "origen": slug,
        "destino": destino,
        "schema_version": esquemas.VERSION_2024,
        "reglamento": esquemas.REGLAMENTO_2024,
        "personajes": [c["nombre"] for c in cambios_pj],
    }
    estado._escribir_texto(
        dir_destino / "partida.json",
        json.dumps(datos_nuevos, ensure_ascii=False, indent=2) + "\n",
    )
    with ruta_eventos_destino.open("a", encoding="utf-8") as f:
        f.write(json.dumps(evento_migracion, ensure_ascii=False) + "\n")

    resumen_md = _resumen_migracion_md(slug, destino, datos_origen, datos_nuevos, cambios_pj)
    ruta_resumen = dir_destino / "migracion-2024.md"
    estado._escribir_texto(ruta_resumen, resumen_md)

    return {
        "origen": slug,
        "destino": destino,
        "ruta": str(dir_destino),
        "resumen_archivo": str(ruta_resumen),
        "schema_version": esquemas.VERSION_2024,
        "reglamento": esquemas.REGLAMENTO_2024,
        "version": datos_nuevos["version"],
        "evento": evento_migracion,
        "cambios_personajes": cambios_pj,
    }
