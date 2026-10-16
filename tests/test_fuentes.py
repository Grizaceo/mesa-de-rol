"""Catálogo externo (P1.2): adaptador Open5e con caché, procedencia y política de consultas.

Antes de este cambio no había forma de traer reglas de 2024 sin transcribirlas a mano,
ni de saber de dónde salió un dato. Ahora `fuentes.actualizar` copia un objeto del
documento `srd-2024` a `biblioteca/fuentes/open5e/` con licencia, URL y fecha, y el
resto del motor lo lee sin tocar la red: si falta, se avisa; nunca se inventa.

Estos tests no salen a internet: el lector HTTP se inyecta o se parchea.
"""

from __future__ import annotations

import io
import json
import unittest
import urllib.error
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

from mesa import cli, fuentes

from apoyo import repo_temporal

CONJURO = {
    "key": "srd-2024_bola-de-prueba",
    "document": {"name": "System Reference Document 5.2", "key": "srd-2024"},
    "name": "Bola de prueba",
    "level": 3,
    "school": {"name": "Evocation", "key": "evocation"},
    "casting_time": "action",
    "range_text": "150 feet",
    "range": 150,
    "range_unit": "feet",
    "verbal": True,
    "somatic": True,
    "material": True,
    "material_specified": "una bolita",
    "material_consumed": False,
    "duration": "instantaneous",
    "concentration": False,
    "ritual": False,
    "desc": "Una bola de prueba estalla.",
    "higher_level": "El daño sube 1d6 por nivel.",
    "attack_roll": False,
    "saving_throw_ability": "dexterity",
    "damage_roll": "8d6",
    "damage_types": ["fire"],
    "target_type": "point",
    "target_count": None,
    "shape_type": "sphere",
    "shape_size": 20,
    "shape_size_unit": "feet",
    "classes": [{"name": "Wizard", "key": "srd-2024_wizard"}],
    "casting_options": [],
}

CONDICION = {
    "key": "srd-2024_derribado-de-prueba",
    "document": {"name": "System Reference Document 5.2", "key": "srd-2024"},
    "name": "Derribado de prueba",
    "icon": None,
    "descriptions": [{"desc": "Texto de prueba.", "document": "srd-2024", "gamesystem": "5e-2024"}],
}

DOCUMENTO = {
    "key": "srd-2024",
    "name": "System Reference Document 5.2",
    "licenses": [{"name": "Creative Commons Attribution 4.0", "key": "cc-by-40"}],
    "publisher": {"name": "Wizards of the Coast"},
    "gamesystem": {"name": "5th Edition 2024"},
    "permalink": "https://dnd.wizards.com/resources/systems-reference-document",
    "desc": "The System Reference Document (SRD) contains guidelines for publishing content under Creative Commons.",
    "publication_date": "2024-01-01T00:00:00",
}


def correr(*args):
    salida, errores = io.StringIO(), io.StringIO()
    with redirect_stdout(salida), redirect_stderr(errores):
        codigo = cli.main(list(args))
    return codigo, salida.getvalue(), errores.getvalue()


def lector_de(objeto: dict, documento: dict | None = None):
    """Lector HTTP de mentira: documento en /documents/ y el objeto en su endpoint."""
    def lector(url: str) -> dict:
        if "/documents/" in url:
            return documento if documento is not None else DOCUMENTO
        return {"count": 1, "results": [objeto]}
    return lector


class TestActualizar(unittest.TestCase):
    def test_copia_con_procedencia_y_mapea_al_esquema_interno(self):
        with repo_temporal():
            entrada = fuentes.actualizar("conjuro", CONJURO["key"], lector=lector_de(CONJURO))
            fuente = entrada["fuente"]
            self.assertEqual(fuente["documento"], "srd-2024")
            self.assertEqual(fuente["licencia"], "Creative Commons Attribution 4.0")
            self.assertEqual(fuente["permalink"], DOCUMENTO["permalink"])
            self.assertIn("api.open5e.com", fuente["url"])
            self.assertTrue(fuente["descargado"])
            datos = entrada["datos"]
            self.assertEqual(datos["nombre"], "Bola de prueba")
            self.assertEqual(datos["nivel"], 3)
            self.assertEqual(datos["escuela"], "evocation")
            self.assertEqual(datos["componentes"]["material_especificado"], "una bolita")
            self.assertEqual(datos["dano"], {"expresion": "8d6", "tipos": ["fire"]})
            self.assertEqual(datos["salvacion"], "dexterity")
            self.assertEqual(datos["clases"], ["srd-2024_wizard"])
            # En disco y legible sin red:
            self.assertEqual(fuentes.obtener("conjuro", CONJURO["key"])["nombre"], "Bola de prueba")
            # El documento queda cacheado con su licencia:
            self.assertEqual(fuentes.documento_local()["datos"]["licencia"], "Creative Commons Attribution 4.0")

    def test_condicion_mapea_sus_descripciones(self):
        with repo_temporal():
            fuentes.actualizar("condicion", CONDICION["key"], lector=lector_de(CONDICION))
            datos = fuentes.obtener("condicion", CONDICION["key"])
            self.assertEqual(datos["nombre"], "Derribado de prueba")
            self.assertEqual(datos["descripciones"][0]["texto"], "Texto de prueba.")

    def test_fuente_equivocada_se_rechaza_sin_escribir(self):
        with repo_temporal():
            ajeno = dict(CONJURO, document={"name": "Adventurer's Guide", "key": "a5e-ag"})
            with self.assertRaises(ValueError) as e:
                fuentes.actualizar("conjuro", "a5e-ag_bola", lector=lector_de(ajeno))
            self.assertIn("fuente equivocada", str(e.exception))
            self.assertFalse(fuentes.ruta_entrada("conjuro", "a5e-ag_bola").exists())
            self.assertEqual(fuentes.listar(), [])

    def test_una_regla_sin_documento_anidado_tambien_se_verifica(self):
        with repo_temporal():
            regla = {"key": "srd-2024_regla", "name": "Regla", "desc": "d", "document": "a5e-ag"}
            with self.assertRaises(ValueError):
                fuentes.actualizar("regla", "srd-2024_regla", lector=lector_de(regla))

    def test_no_esta_en_el_documento_avisa_y_sugiere_buscar(self):
        with repo_temporal():
            lector = lambda url: DOCUMENTO if "/documents/" in url else {"count": 0, "results": []}
            with self.assertRaises(ValueError) as e:
                fuentes.actualizar("conjuro", "srd-2024_nada", lector=lector)
            self.assertIn("fuentes buscar", str(e.exception))

    def test_tipo_desconocido(self):
        with repo_temporal(), self.assertRaises(ValueError):
            fuentes.actualizar("pocion", "x", lector=lector_de(CONJURO))


class TestOffline(unittest.TestCase):
    """El motor no sale a la red: la caché manda y lo que falta se avisa."""

    def test_sin_cache_avisa_y_no_inventa(self):
        with repo_temporal():
            with mock.patch.object(fuentes, "_leer_json", side_effect=AssertionError("no debe tocar la red")):
                with self.assertRaises(ValueError) as e:
                    fuentes.obtener("conjuro", "srd-2024_nada")
            self.assertIn("fuentes actualizar", str(e.exception))

    def test_con_cache_lee_sin_tocar_la_red(self):
        with repo_temporal():
            fuentes.actualizar("conjuro", CONJURO["key"], lector=lector_de(CONJURO))
            with mock.patch.object(fuentes, "_leer_json", side_effect=AssertionError("no debe tocar la red")):
                self.assertEqual(fuentes.obtener("conjuro", CONJURO["key"])["nivel"], 3)

    def test_cache_de_otra_version_o_fuente_equivocada_se_rechaza(self):
        with repo_temporal():
            fuentes.actualizar("conjuro", CONJURO["key"], lector=lector_de(CONJURO))
            ruta = fuentes.ruta_entrada("conjuro", CONJURO["key"])
            entrada = json.loads(ruta.read_text(encoding="utf-8"))
            entrada["cache"] = 99
            ruta.write_text(json.dumps(entrada), encoding="utf-8")
            with self.assertRaises(ValueError) as e:
                fuentes.obtener("conjuro", CONJURO["key"])
            self.assertIn("otra versión", str(e.exception))
            entrada["cache"] = fuentes.CACHE
            entrada["fuente"]["documento"] = "a5e-ag"
            ruta.write_text(json.dumps(entrada), encoding="utf-8")
            with self.assertRaises(ValueError) as e:
                fuentes.obtener("conjuro", CONJURO["key"])
            self.assertIn("fuente equivocada", str(e.exception))

    def test_cache_corrupta_avisa(self):
        with repo_temporal():
            ruta = fuentes.ruta_entrada("conjuro", "srd-2024_rota")
            ruta.parent.mkdir(parents=True, exist_ok=True)
            ruta.write_text("{no es json", encoding="utf-8")
            with self.assertRaises(ValueError) as e:
                fuentes.obtener("conjuro", "srd-2024_rota")
            self.assertIn("corrupto", str(e.exception))

    def test_listar_muestra_la_procedencia(self):
        with repo_temporal():
            fuentes.actualizar("conjuro", CONJURO["key"], lector=lector_de(CONJURO))
            entradas = fuentes.listar()
            self.assertEqual(len(entradas), 1)
            self.assertEqual(entradas[0]["tipo"], "conjuro")
            self.assertEqual(entradas[0]["nombre"], "Bola de prueba")
            self.assertEqual(entradas[0]["licencia"], "Creative Commons Attribution 4.0")
            self.assertTrue(entradas[0]["descargado"])


class TestPolitica(unittest.TestCase):
    """Reintentos acotados; un error HTTP no mejora esperando."""

    def _respuesta(self, cuerpo: dict):
        class Respuesta:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return json.dumps(cuerpo).encode("utf-8")

        return Respuesta()

    def test_reintenta_hasta_lograr(self):
        fallo = urllib.error.URLError("sin red")
        with mock.patch.object(fuentes, "ESPERA", 0), mock.patch(
            "urllib.request.urlopen", side_effect=[fallo, fallo, self._respuesta({"ok": True})]
        ) as abrir:
            self.assertEqual(fuentes._leer_json("https://api.open5e.com/v2/spells/?x"), {"ok": True})
            self.assertEqual(abrir.call_count, 3)
            peticion = abrir.call_args[0][0]
            self.assertIn("mesa-de-rol", peticion.get_header("User-agent"))

    def test_se_rinde_con_mensaje_legible(self):
        with mock.patch.object(fuentes, "ESPERA", 0), mock.patch(
            "urllib.request.urlopen", side_effect=urllib.error.URLError("sin red")
        ) as abrir:
            with self.assertRaises(RuntimeError) as e:
                fuentes._leer_json("https://api.open5e.com/v2/spells/?x")
            self.assertEqual(abrir.call_count, fuentes.INTENTOS)
            self.assertIn("intentos", str(e.exception))

    def test_un_error_http_no_se_reintenta(self):
        error = urllib.error.HTTPError("https://api.open5e.com/v2/spells/?x", 404, "Not Found", {}, None)
        with mock.patch("urllib.request.urlopen", side_effect=error) as abrir:
            with self.assertRaises(RuntimeError) as e:
                fuentes._leer_json("https://api.open5e.com/v2/spells/?x")
            self.assertEqual(abrir.call_count, 1)
            self.assertIn("HTTP 404", str(e.exception))

    def test_buscar_pide_una_sola_pagina_del_documento(self):
        urls = []

        def lector(url: str) -> dict:
            urls.append(url)
            return {"results": [{"key": "srd-2024_fireball", "name": "Fireball"}]}

        with repo_temporal():
            resultados = fuentes.buscar("conjuro", "fuego", lector=lector)
        self.assertEqual(resultados, [{"key": "srd-2024_fireball", "nombre": "Fireball"}])
        self.assertEqual(len(urls), 1)
        self.assertIn("document__key=srd-2024", urls[0])
        self.assertIn("limit=", urls[0])


class TestCli(unittest.TestCase):
    def test_flujo_actualizar_ver_listar(self):
        with repo_temporal():
            with mock.patch.object(fuentes, "_leer_json", side_effect=lector_de(CONJURO)):
                codigo, salida, _ = correr("fuentes", "actualizar", "conjuro", CONJURO["key"])
                self.assertEqual(codigo, 0)
                self.assertIn("Creative Commons Attribution 4.0", salida)
                codigo, salida, _ = correr("fuentes", "ver", "conjuro", CONJURO["key"])
                self.assertEqual(codigo, 0)
                self.assertEqual(json.loads(salida)["nombre"], "Bola de prueba")
                codigo, salida, _ = correr("fuentes", "listar")
                self.assertEqual(codigo, 0)
                self.assertIn(CONJURO["key"], salida)
                self.assertIn("srd-2024", salida)

    def test_ver_sin_cache_es_error_legible(self):
        with repo_temporal():
            codigo, _, errores = correr("fuentes", "ver", "conjuro", "srd-2024_nada")
            self.assertEqual(codigo, 1)
            self.assertIn("fuentes actualizar", errores)

    def test_buscar_por_cli_imprime_keys(self):
        with repo_temporal():
            with mock.patch.object(fuentes, "_leer_json", side_effect=lambda url: {"results": [{"key": "srd-2024_fireball", "name": "Fireball"}]}):
                codigo, salida, _ = correr("fuentes", "buscar", "conjuro", "fire")
            self.assertEqual(codigo, 0)
            self.assertIn("srd-2024_fireball", salida)
            self.assertIn("Fireball", salida)


if __name__ == "__main__":
    unittest.main()
