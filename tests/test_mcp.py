import json
import os
import subprocess
import sys
import unittest
from unittest import mock

from mesa import cli, estado, mcp

from apoyo import REPO, dados_fijos, repo_temporal


def llamar(nombre, argumentos):
    r = mcp.atender({"jsonrpc": "2.0", "id": 9, "method": "tools/call", "params": {"name": nombre, "arguments": argumentos}})
    return r["result"]["isError"], r["result"]["content"][0]["text"]


class TestProtocolo(unittest.TestCase):
    def test_initialize_negocia_version(self):
        r = mcp.atender({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-03-26"}})
        self.assertEqual(r["result"]["protocolVersion"], "2025-03-26")
        self.assertIn("tools", r["result"]["capabilities"])
        r = mcp.atender({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "1999-01-01"}})
        self.assertEqual(r["result"]["protocolVersion"], mcp.VERSIONES[0])

    def test_lista_de_herramientas_bien_formada(self):
        herramientas = mcp.atender({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})["result"]["tools"]
        self.assertEqual(len(herramientas), 10)
        for h in herramientas:
            self.assertEqual(h["inputSchema"]["type"], "object")
            self.assertTrue(h["description"])
            for requerido in h["inputSchema"].get("required", []):
                self.assertIn(requerido, h["inputSchema"]["properties"])

    def test_notificaciones_y_errores(self):
        self.assertIsNone(mcp.atender({"jsonrpc": "2.0", "method": "notifications/initialized"}))
        self.assertEqual(mcp.atender({"jsonrpc": "2.0", "id": 3, "method": "resources/list"})["error"]["code"], -32601)
        r = mcp.atender({"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "borrar_todo"}})
        self.assertEqual(r["error"]["code"], -32602)
        self.assertEqual(mcp.atender({"id": 5, "method": "ping"})["error"]["code"], -32600)

    def test_traduccion_a_cli(self):
        args = mcp.construir_argumentos("prueba", {
            "quien": "Crisljin", "atributo": "sigilo", "cd": 15, "ventaja": "Jualjin distrae",
            "desventaja": True, "oficio": True, "bonos": ["2:palanca"], "etiqueta": "colarse", "partida": "neva"})
        self.assertEqual(args, ["-p", "neva", "prueba", "Crisljin", "sigilo", "--cd", "15", "--etiqueta", "colarse",
                                "--ventaja", "Jualjin distrae", "--desventaja", "--oficio", "--bono", "2:palanca"])
        self.assertEqual(mcp.construir_argumentos("turno", {"resumen": "x", "acciones": {"Jualjin": "remo"}}),
                         ["turno", "--resumen", "x", "--accion", "Jualjin=remo"])


class TestHerramientas(unittest.TestCase):
    def test_prueba_por_mcp_usa_el_mismo_motor(self):
        with repo_temporal(), dados_fijos(12):
            error, texto = llamar("prueba", {"quien": "Jualjin", "atributo": "atletismo", "cd": "media"})
            self.assertFalse(error)
            self.assertIn("contra dificultad 15", texto)
            self.assertEqual(estado.leer_eventos("neva")[-1]["habilidad"], "Atletismo")

    def test_comando_generico_y_prohibidos(self):
        with repo_temporal():
            error, _ = llamar("comando", {"args": ["vida", "Jualjin", "-2"]})
            self.assertFalse(error)
            self.assertEqual(estado.buscar(estado.cargar("neva"), "Jualjin")[1]["vida"], 12)
            error, texto = llamar("comando", {"args": ["servir"]})
            self.assertTrue(error)
            error, texto = llamar("prueba", {"atributo": "fuerza"})
            self.assertTrue(error)
            self.assertIn("argumentos inválidos", texto)

    def test_prohibidos_aunque_vayan_detras_de_opciones(self):
        with repo_temporal():
            for args in (["--json", "servir"], ["-p", "neva", "servir"], ["--partida=neva", "servir"]):
                error, texto = llamar("comando", {"args": args})
                self.assertTrue(error, args)
                self.assertIn("no se puede usar", texto)

    def test_una_excepcion_inesperada_no_tumba_el_servidor(self):
        with repo_temporal(), mock.patch.object(cli, "c_estado", side_effect=AttributeError("se rompió")):
            error, texto = llamar("estado", {})
            self.assertTrue(error)
            self.assertIn("AttributeError", texto)

    def test_turno_con_cambios(self):
        args = mcp.construir_argumentos("turno", {
            "resumen": "x", "acciones": {"Jualjin": "remo"},
            "cambios": [["pista", "Huellas frescas", "--fuente", "Crisljin"], "vida Jualjin -1"]})
        self.assertEqual(args, ["turno", "--resumen", "x", "--accion", "Jualjin=remo",
                                "--cambio", "pista 'Huellas frescas' --fuente Crisljin", "--cambio", "vida Jualjin -1"])
        with repo_temporal():
            error, texto = llamar("turno", {"resumen": "x", "acciones": {"Jualjin": "remo", "Crisljin": "miro"},
                                            "cambios": [["pista", "Huellas «frescas» y 'raras'", "--fuente", "Crisljin"]]})
            self.assertFalse(error, texto)
            self.assertEqual(estado.cargar("neva")["pistas"][-1]["texto"], "Huellas «frescas» y 'raras'")
            self.assertEqual(estado.leer_eventos("neva")[-1]["tipo"], "turno")

    def test_estado_breve(self):
        with repo_temporal():
            error, texto = llamar("estado", {"breve": True})
            self.assertFalse(error)
            self.assertTrue(texto.startswith("Jualjin (14/14)"))

    def test_errores_de_la_cli_vuelven_como_isError(self):
        with repo_temporal():
            error, texto = llamar("prueba", {"quien": "Nadie", "atributo": "fuerza"})
            self.assertTrue(error)
            self.assertIn("no encuentro", texto)


class TestProcesoReal(unittest.TestCase):
    def test_stdio_de_punta_a_punta(self):
        """Como lo arranca un harness: stdout solo lleva JSON-RPC, una línea por mensaje."""
        with repo_temporal() as raiz:
            mensajes = [
                {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "test", "version": "0"}}},
                {"jsonrpc": "2.0", "method": "notifications/initialized"},
                {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "estado", "arguments": {}}},
                {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "tirar", "arguments": {"expr": "2d6+1"}}},
            ]
            entrada = "\n".join(json.dumps(m) for m in mensajes) + "\n"
            entorno = dict(os.environ, PYTHONPATH=str(REPO), MESA_RAIZ=str(raiz))
            r = subprocess.run([sys.executable, "-m", "mesa.mcp"], input=entrada, capture_output=True, text=True, timeout=30, env=entorno)
            lineas = [json.loads(l) for l in r.stdout.splitlines()]
            self.assertEqual([l["id"] for l in lineas], [1, 2, 3])
            self.assertIn("Los Hermanos del Neva", lineas[1]["result"]["content"][0]["text"])
            self.assertFalse(lineas[2]["result"]["isError"])
            self.assertEqual(estado.leer_eventos("neva")[-1]["expr"], "2d6+1")

    def test_un_error_de_red_no_tumba_el_proceso(self):
        """Antes, `imagen elegir` con la red caída mataba el servidor y el narrador se quedaba sin dados."""
        with repo_temporal() as raiz:
            mensajes = [
                {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "comando", "arguments": {"args": ["imagen", "elegir", "http://127.0.0.1:9/x.png"]}}},
                {"jsonrpc": "2.0", "id": 2, "method": "ping"},
            ]
            entrada = "\n".join(json.dumps(m) for m in mensajes) + "\n"
            entorno = dict(os.environ, PYTHONPATH=str(REPO), MESA_RAIZ=str(raiz))
            r = subprocess.run([sys.executable, "-m", "mesa.mcp"], input=entrada, capture_output=True, text=True, timeout=30, env=entorno)
            lineas = [json.loads(l) for l in r.stdout.splitlines()]
            self.assertEqual([l["id"] for l in lineas], [1, 2])
            self.assertTrue(lineas[0]["result"]["isError"])
            self.assertIn("error de sistema o de red", lineas[0]["result"]["content"][0]["text"])


if __name__ == "__main__":
    unittest.main()
