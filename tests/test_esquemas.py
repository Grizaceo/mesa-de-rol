"""Esquema de partida (P1.1): versión declarada, seis características 2024 y catálogo.

Antes de este cambio no había forma de distinguir legacy de 2024: la plantilla no
declaraba esquema, nada validaba las seis características con sus valores derivados,
y el motor d20-simple habría leído puntuaciones (10) como bonos (+10) sin avisar.
La partida histórica (sin `schema_version`) se lee como legacy y no se toca.
"""

from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stderr, redirect_stdout

from mesa import cli, esquemas, estado, informes, reglas

from apoyo import REPO, repo_temporal

PLANTILLA = REPO / "partidas" / "_plantilla" / "partida.json"
HISTORICA = REPO / "partidas" / "los-hermanos-del-neva" / "partida.json"


def correr(*args):
    salida, errores = io.StringIO(), io.StringIO()
    with redirect_stdout(salida), redirect_stderr(errores):
        codigo = cli.main(list(args))
    return codigo, salida.getvalue(), errores.getvalue()


def partida_2024() -> dict:
    return json.loads(PLANTILLA.read_text(encoding="utf-8"))


class TestVersion(unittest.TestCase):
    def test_la_plantilla_declara_el_esquema_2024(self):
        datos = partida_2024()
        self.assertEqual(datos["schema_version"], esquemas.VERSION_2024)
        self.assertEqual(datos["reglamento"], "dnd-2024")
        self.assertEqual(esquemas.version_de(datos), esquemas.VERSION_2024)
        esquemas.validar(datos, "_plantilla")

    def test_la_historica_es_legacy_y_abre_sin_alterarse(self):
        antes = HISTORICA.read_bytes()
        with repo_temporal():
            datos = estado.cargar("neva")
            self.assertEqual(esquemas.version_de(datos), esquemas.VERSION_LEGACY)
            self.assertEqual(datos["reglamento"], "d20-simple")
        self.assertEqual(HISTORICA.read_bytes(), antes, "leer la histórica no la reescribe")

    def test_sin_schema_version_manda_el_reglamento(self):
        self.assertEqual(esquemas.version_de({"reglamento": "dnd-2024"}), esquemas.VERSION_2024)
        self.assertEqual(esquemas.version_de({"reglamento": "d20-simple"}), esquemas.VERSION_LEGACY)
        self.assertEqual(esquemas.version_de({}), esquemas.VERSION_LEGACY,
                         "los archivos de antes de los esquemas son legacy")

    def test_esquema_o_reglamento_desconocidos_son_error(self):
        with self.assertRaises(ValueError):
            esquemas.version_de({"schema_version": 99})
        with self.assertRaises(ValueError) as e:
            esquemas.validar({"reglamento": "cyberpunk", "personajes": []}, "x")
        self.assertIn("cyberpunk", str(e.exception))

    def test_esquema_y_reglamento_no_pueden_contradecirse(self):
        with self.assertRaises(ValueError) as e:
            esquemas.validar({"schema_version": 2, "reglamento": "d20-simple", "personajes": []}, "x")
        self.assertIn("d20-simple", str(e.exception))


class TestValidacion2024(unittest.TestCase):
    def test_falta_una_caracteristica_y_se_dice_cual(self):
        datos = partida_2024()
        del datos["personajes"][0]["atributos"]["carisma"]
        with self.assertRaises(ValueError) as e:
            esquemas.validar(datos, "x")
        self.assertIn("carisma", str(e.exception))

    def test_caracteristica_desconocida(self):
        datos = partida_2024()
        datos["personajes"][0]["atributos"]["suerte"] = 10
        with self.assertRaises(ValueError) as e:
            esquemas.validar(datos, "x")
        self.assertIn("suerte", str(e.exception))

    def test_puntuacion_fuera_de_rango_o_no_entera(self):
        for valor in (0, 31, "diez", True, 10.5):
            with self.subTest(valor=valor):
                datos = partida_2024()
                datos["personajes"][0]["atributos"]["fuerza"] = valor
                with self.assertRaises(ValueError):
                    esquemas.validar(datos, "x")

    def test_nivel_fuera_de_rango(self):
        for valor in (0, 21, "uno"):
            with self.subTest(valor=valor):
                datos = partida_2024()
                datos["personajes"][0]["nivel"] = valor
                with self.assertRaises(ValueError):
                    esquemas.validar(datos, "x")

    def test_personaje_sin_nombre(self):
        datos = partida_2024()
        datos["personajes"][0]["nombre"] = "  "
        with self.assertRaises(ValueError):
            esquemas.validar(datos, "x")

    def test_la_historica_pasa_la_validacion_legacy(self):
        datos = json.loads(HISTORICA.read_text(encoding="utf-8"))
        esquemas.validar(datos, "los-hermanos-del-neva")

    def test_una_partida_que_no_es_objeto(self):
        with self.assertRaises(ValueError):
            esquemas.validar([], "x")


class TestDerivados(unittest.TestCase):
    def test_modificador(self):
        tabla = {1: -5, 2: -4, 3: -4, 8: -1, 9: -1, 10: 0, 11: 0, 12: 1, 13: 1, 18: 4, 20: 5, 30: 10}
        for puntuacion, esperado in tabla.items():
            with self.subTest(puntuacion=puntuacion):
                self.assertEqual(esquemas.modificador(puntuacion), esperado)

    def test_competencia_por_nivel(self):
        tabla = {1: 2, 4: 2, 5: 3, 8: 3, 9: 4, 12: 4, 13: 5, 16: 5, 17: 6, 20: 6}
        for nivel, esperado in tabla.items():
            with self.subTest(nivel=nivel):
                self.assertEqual(esquemas.competencia(nivel), esperado)


class TestCatalogo(unittest.TestCase):
    def test_seis_ids_estables_con_nombre_es_y_en(self):
        self.assertEqual([a["id"] for a in esquemas.ATRIBUTOS_2024],
                         ["fuerza", "destreza", "constitucion", "inteligencia", "sabiduria", "carisma"])
        self.assertEqual(esquemas.NOMBRES_2024["sabiduria"], "Sabiduría")
        self.assertEqual(esquemas.NOMBRES_EN_2024["sabiduria"], "Wisdom")

    def test_alias_espanol_e_ingles(self):
        casos = {
            "fue": "fuerza", "Fuerza": "fuerza", "str": "fuerza", "Strength": "fuerza",
            "des": "destreza", "Dex": "destreza", "dexterity": "destreza",
            "Constitución": "constitucion", "con": "constitucion",
            "int": "inteligencia", "wis": "sabiduria", "sab": "sabiduria",
            "car": "carisma", "cha": "carisma", "Charisma": "carisma",
        }
        for alias, esperado in casos.items():
            with self.subTest(alias=alias):
                self.assertEqual(esquemas.resolver_atributo_2024(alias), esperado)
        self.assertIsNone(esquemas.resolver_atributo_2024("magia"))

    def test_nombre_para_presentacion_cubre_legacy_y_2024(self):
        self.assertEqual(esquemas.nombre_atributo("corazon"), "Corazón")
        self.assertEqual(esquemas.nombre_atributo("destreza"), "Destreza")
        self.assertEqual(esquemas.nombre_atributo("raro"), "raro")


class TestNuevaPartida(unittest.TestCase):
    def test_nueva_partida_es_2024_y_el_estado_la_lee(self):
        with repo_temporal():
            codigo, _, _ = correr("nueva", "mesa-2024", "--titulo", "Mesa nueva")
            self.assertEqual(codigo, 0)
            datos = estado.cargar("mesa-2024")
            self.assertEqual(esquemas.version_de(datos), esquemas.VERSION_2024)
            self.assertEqual(sorted(datos["personajes"][0]["atributos"]), sorted(esquemas.IDS_2024))
            codigo, salida, _ = correr("estado", "--breve")
            self.assertEqual(codigo, 0)
            self.assertIn("Personaje 1", salida)

    def test_el_resumen_muestra_puntuacion_y_modificador(self):
        with repo_temporal():
            correr("nueva", "mesa-2024", "--titulo", "Mesa nueva")
            codigo, salida, _ = correr("estado")
            self.assertEqual(codigo, 0)
            self.assertIn("Fuerza 10 (+0)", salida)
            self.assertIn("Sabiduría 10 (+0)", salida)

    def test_el_motor_legacy_se_niega_en_2024_sin_mutar(self):
        with repo_temporal():
            correr("nueva", "mesa-2024", "--titulo", "Mesa nueva")
            antes = estado.cargar("mesa-2024")["version"]
            codigo, _, errores = correr("prueba", "Personaje 1", "fuerza")
            self.assertEqual(codigo, 1)
            self.assertIn("dnd-2024", errores)
            self.assertIn("motor", errores)
            codigo, _, errores = correr("nivel", "Personaje 1", "--atributo", "fuerza")
            self.assertEqual(codigo, 1)
            self.assertIn("motor", errores)
            self.assertEqual(estado.cargar("mesa-2024")["version"], antes)
            self.assertEqual([e["tipo"] for e in estado.leer_eventos("mesa-2024")], ["partida_creada"])

    def test_el_contexto_no_manda_al_reglamento_equivocado(self):
        with repo_temporal() as raiz:
            (raiz / "reglas").mkdir()
            (raiz / "reglas" / "d20-simple.md").write_text("# Reglamento\n", encoding="utf-8")
            correr("nueva", "mesa-2024", "--titulo", "Mesa nueva")
            texto = informes.contexto("mesa-2024")
            self.assertIn("biblia.md", texto)
            self.assertNotIn("d20-simple.md", texto, "una partida 2024 no se juega con el reglamento legacy")
            self.assertIn("d20-simple.md", informes.contexto("neva"), "la histórica sí lo menciona")


class TestMotorSoloLegacy(unittest.TestCase):
    def test_prueba_y_ataque_se_niegan_con_partida_2024(self):
        datos = partida_2024()
        ficha = datos["personajes"][0]
        for intento in (lambda: reglas.prueba(datos, ficha, "fuerza"),
                        lambda: reglas.ataque(datos, ficha, dict(ficha, nombre="Otro"))):
            with self.subTest(intento=intento):
                with self.assertRaises(ValueError) as e:
                    intento()
                self.assertIn("dnd-2024", str(e.exception))


if __name__ == "__main__":
    unittest.main()
