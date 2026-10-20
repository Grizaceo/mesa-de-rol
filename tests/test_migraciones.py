"""Diagnóstico dry-run (P1.4) y migración en copia validada (P1.5) de legacy a D&D 2024.

Reglas del contrato (plan §2 y P1.4–P1.5):
- No se convierten 4 atributos (`fuerza`, `agilidad`, `ingenio`, `corazon`) en 6 por heurística.
- El diagnóstico es dry-run: enumera campos faltantes y decisiones humanas sin tocar la partida.
- La migración solo escribe en una copia nueva (otro slug u otra raíz scratch), exige las 6
  características acordadas por personaje, conserva intacta la partida original y no reescribe
  los eventos históricos previos.
"""

from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from mesa import capacidades, cli, esquemas, estado, migraciones

from apoyo import REPO, repo_temporal

HISTORICA = REPO / "partidas" / "los-hermanos-del-neva" / "partida.json"
EVENTOS_HISTORICA = REPO / "partidas" / "los-hermanos-del-neva" / "eventos.jsonl"


def correr(*args, perfil: str = capacidades.CLI):
    salida, errores = io.StringIO(), io.StringIO()
    with redirect_stdout(salida), redirect_stderr(errores):
        codigo = cli.main(list(args), perfil=perfil)
    return codigo, salida.getvalue(), errores.getvalue()


FICHAS_NEVA_ACORDADAS = {
    "jualjin": {
        "clase": "Guerrero",
        "especie": "Humano",
        "trasfondo": "Marinero",
        "defensa": 14,
        "atributos": {
            "fuerza": 16,
            "destreza": 12,
            "constitucion": 14,
            "inteligencia": 10,
            "sabiduria": 11,
            "carisma": 13,
        },
        "competencias": {
            "habilidades": ["Atletismo", "Percepción"],
            "salvaciones": ["fuerza", "constitucion"],
        },
    },
    "crisljin": {
        "clase": "Pícaro",
        "especie": "Humano",
        "trasfondo": "Marinero",
        "defensa": 14,
        "atributos": {
            "fuerza": 10,
            "destreza": 14,
            "constitucion": 12,
            "inteligencia": 16,
            "sabiduria": 13,
            "carisma": 12,
        },
        "competencias": {
            "habilidades": ["Investigación", "Sigilo", "Percepción"],
            "salvaciones": ["destreza", "inteligencia"],
        },
    },
}


class TestDiagnosticoDryRun(unittest.TestCase):
    def test_diagnostico_no_muta_la_partida_ni_los_eventos(self):
        with repo_temporal() as raiz:
            ruta_json = raiz / "partidas" / "neva" / "partida.json"
            ruta_ev = raiz / "partidas" / "neva" / "eventos.jsonl"
            antes_json = ruta_json.read_bytes()
            antes_ev = ruta_ev.read_bytes()

            informe = migraciones.diagnosticar(estado.cargar("neva"), "neva")

            self.assertEqual(ruta_json.read_bytes(), antes_json)
            self.assertEqual(ruta_ev.read_bytes(), antes_ev)
            self.assertEqual(informe["version_actual"], esquemas.VERSION_LEGACY)
            self.assertEqual(informe["version_objetivo"], esquemas.VERSION_2024)
            self.assertFalse(informe["listo_para_migrar"])

    def test_diagnostico_enumera_campos_faltantes_y_decisiones_humanas(self):
        with repo_temporal():
            datos = estado.cargar("neva")
            informe = migraciones.diagnosticar(datos, "neva")
            nombres = [p["nombre"] for p in informe["personajes"]]
            self.assertEqual(nombres, ["Jualjin", "Crisljin"])

            jualjin = informe["personajes"][0]
            self.assertEqual(
                jualjin["caracteristicas_faltantes"],
                list(esquemas.IDS_2024),
                "no convierte las 4 claves legacy en puntuaciones 2024 ni asume que 'fuerza: 3' sea puntuación",
            )
            self.assertEqual(jualjin["atributos_legacy"], {"fuerza": 3, "agilidad": 1, "ingenio": 1, "corazon": 2})
            self.assertTrue(jualjin["tiene_oficio_legacy"])
            self.assertEqual(jualjin["proteccion_plana_legacy"], 1)
            self.assertIn("¡A mi hermano no!", jualjin["habilidades_recarga_legacy"])

            texto = migraciones.formatear_diagnostico(informe)
            self.assertIn("no convierte", texto.lower())
            self.assertIn("Jualjin", texto)
            self.assertIn("Crisljin", texto)
            self.assertIn("fuerza, destreza, constitucion, inteligencia, sabiduria, carisma", texto)

    def test_partida_ya_2024_no_pide_migracion(self):
        with repo_temporal():
            correr("nueva", "mesa-2024", "--titulo", "Ya es 2024")
            informe = migraciones.diagnosticar(estado.cargar("mesa-2024"), "mesa-2024")
            self.assertTrue(informe["ya_es_2024"])
            self.assertTrue(informe["listo_para_migrar"])
            self.assertEqual(informe["acciones_humanas"], [])

    def test_cli_migrar_dry_run_imprime_diagnostico_y_json(self):
        with repo_temporal() as raiz:
            antes = (raiz / "partidas" / "neva" / "partida.json").read_bytes()
            codigo, salida, errores = correr("-p", "neva", "migrar", "--dry-run")
            self.assertEqual(codigo, 0, errores)
            self.assertIn("Diagnóstico de migración", salida)
            self.assertIn("Jualjin", salida)

            codigo_j, salida_j, errores_j = correr("-p", "neva", "--json", "migrar")
            self.assertEqual(codigo_j, 0, errores_j)
            doc = json.loads(salida_j)
            self.assertFalse(doc["listo_para_migrar"])
            self.assertEqual((raiz / "partidas" / "neva" / "partida.json").read_bytes(), antes)


class TestMigracionEnCopia(unittest.TestCase):
    def test_rechaza_migrar_sin_fichas_2024_acordadas(self):
        with repo_temporal():
            with self.assertRaises(ValueError) as ctx:
                migraciones.migrar_copia("neva", "neva-2024", fichas_2024={})
            self.assertIn("Jualjin", str(ctx.exception))
            self.assertFalse((estado.dir_partidas() / "neva-2024").exists())

    def test_rechaza_heuristica_o_caracteristicas_incompletas(self):
        with repo_temporal():
            incompleta = {
                "jualjin": {"atributos": {"fuerza": 16, "destreza": 12}},
                "crisljin": FICHAS_NEVA_ACORDADAS["crisljin"],
            }
            with self.assertRaises(ValueError) as ctx:
                migraciones.migrar_copia("neva", "neva-2024", fichas_2024=incompleta)
            self.assertIn("constitucion", str(ctx.exception))
            self.assertFalse((estado.dir_partidas() / "neva-2024").exists())

    def test_rechaza_sobreescribir_la_partida_original(self):
        with repo_temporal():
            with self.assertRaises(ValueError) as ctx:
                migraciones.migrar_copia("neva", "neva", fichas_2024=FICHAS_NEVA_ACORDADAS)
            self.assertIn("copia", str(ctx.exception).lower())

    def test_migra_en_copia_scratch_conserva_original_y_eventos_historicos(self):
        with repo_temporal() as raiz, tempfile.TemporaryDirectory() as scratch_tmp:
            scratch = Path(scratch_tmp)
            orig_json = (raiz / "partidas" / "neva" / "partida.json").read_bytes()
            orig_ev = (raiz / "partidas" / "neva" / "eventos.jsonl").read_bytes()
            lineas_orig = orig_ev.decode("utf-8").splitlines()

            resultado = migraciones.migrar_copia(
                "neva",
                "neva-2024",
                fichas_2024=FICHAS_NEVA_ACORDADAS,
                raiz_destino=scratch,
            )

            # 1. El original sigue intacto byte a byte (rollback = seguir usando el original).
            self.assertEqual((raiz / "partidas" / "neva" / "partida.json").read_bytes(), orig_json)
            self.assertEqual((raiz / "partidas" / "neva" / "eventos.jsonl").read_bytes(), orig_ev)

            # 2. La copia existe solo en scratch, pasa validación 2024 y guarda el resumen.
            dir_copia = Path(resultado["ruta"])
            self.assertEqual(dir_copia, scratch / "partidas" / "neva-2024")
            self.assertTrue((dir_copia / "migracion-2024.md").is_file())
            datos_copia = json.loads((dir_copia / "partida.json").read_text(encoding="utf-8"))
            esquemas.validar(datos_copia, "neva-2024")
            self.assertEqual(datos_copia["schema_version"], esquemas.VERSION_2024)
            self.assertEqual(datos_copia["reglamento"], "dnd-2024")
            self.assertEqual(datos_copia["migrada_desde"]["slug"], "neva")

            jualjin = datos_copia["personajes"][0]
            self.assertEqual(jualjin["atributos"]["fuerza"], 16)
            self.assertEqual(jualjin["atributos"]["sabiduria"], 11)
            self.assertEqual(jualjin["clase"], "Guerrero")
            self.assertEqual(jualjin["proteccion"], 0)
            self.assertNotIn("oficio", jualjin)
            self.assertEqual(jualjin["legado_d20_simple"]["atributos"], {"fuerza": 3, "agilidad": 1, "ingenio": 1, "corazon": 2})

            # 3. Los eventos históricos previos son idénticos línea por línea; solo se añade el evento final.
            lineas_copia = (dir_copia / "eventos.jsonl").read_text(encoding="utf-8").splitlines()
            self.assertEqual(lineas_copia[:-1], lineas_orig)
            ultimo = json.loads(lineas_copia[-1])
            self.assertEqual(ultimo["tipo"], "partida_migrada")
            self.assertEqual(ultimo["origen"], "neva")
            self.assertEqual(ultimo["seq"], len(lineas_orig) + 1)

    def test_cli_migrar_copiar_con_archivo_fichas_y_bloqueo_mcp(self):
        with repo_temporal() as raiz, tempfile.TemporaryDirectory() as scratch_tmp:
            scratch = Path(scratch_tmp)
            archivo_fichas = scratch / "fichas.json"
            archivo_fichas.write_text(json.dumps(FICHAS_NEVA_ACORDADAS, ensure_ascii=False), encoding="utf-8")

            # El MCP de juego no puede ejecutar `migrar` (administración deliberada de la CLI).
            codigo_mcp, _, err_mcp = correr("-p", "neva", "migrar", "--dry-run", perfil=capacidades.JUEGO)
            self.assertEqual(codigo_mcp, 1)
            self.assertIn("no es una acción de juego", err_mcp)

            # Por CLI deliberada sí migra la copia en scratch sin tocar el original.
            orig_bytes = (raiz / "partidas" / "neva" / "partida.json").read_bytes()
            codigo, salida, errores = correr(
                "-p", "neva", "migrar", "copiar", "neva-2024",
                "--fichas", str(archivo_fichas),
                "--raiz-destino", str(scratch),
            )
            self.assertEqual(codigo, 0, errores)
            self.assertIn("neva-2024", salida)
            self.assertIn("migracion-2024.md", salida)
            self.assertEqual((raiz / "partidas" / "neva" / "partida.json").read_bytes(), orig_bytes)
            self.assertTrue((scratch / "partidas" / "neva-2024" / "partida.json").is_file())


if __name__ == "__main__":
    unittest.main()
