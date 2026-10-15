import json
import os
import subprocess
import tomllib
import unittest
from unittest import mock

from mesa import estado, harness, informes, sesion

from apoyo import REPO, repo_temporal


class TestAdaptadores(unittest.TestCase):
    def test_los_adaptadores_del_repo_estan_en_sincronia(self):
        self.assertEqual(estado.RAIZ, REPO)
        self.assertEqual(harness.diferencias(), [], "corre `bin/mesa harness sync` y commitea")

    def test_los_generados_son_validos(self):
        for ruta, contenido in harness.archivos().items():
            with self.subTest(ruta=ruta):
                if ruta.endswith(".json"):
                    json.loads(contenido)
                elif ruta.endswith(".toml"):
                    tomllib.loads(contenido)

    def test_todos_apuntan_al_mismo_servidor_mcp(self):
        a = harness.archivos()
        self.assertEqual(json.loads(a[".mcp.json"])["mcpServers"]["mesa"]["command"], harness.MCP)
        self.assertEqual(json.loads(a[".cursor/mcp.json"])["mcpServers"]["mesa"]["command"], harness.MCP)
        self.assertEqual(json.loads(a[".gemini/settings.json"])["mcpServers"]["mesa"]["command"], harness.MCP)
        self.assertEqual(json.loads(a[".opencode/opencode.json"])["mcp"]["servers"]["mesa"]["command"], [harness.MCP])
        self.assertEqual(tomllib.loads(a[".codex/config.toml"])["mcp_servers"]["mesa"]["command"], harness.MCP)

    def test_sin_opencode_json_en_la_raiz(self):
        # La CLI de Devin lo leería con el formato v1 y crearía un servidor «servers» roto.
        self.assertFalse((REPO / "opencode.json").exists())
        self.assertNotIn("opencode.json", harness.archivos())

    def test_los_comandos_existen_en_cada_formato(self):
        a = harness.archivos()
        for nombre in ("retomar", "pausar", "nueva-historia"):
            self.assertIn("$ARGUMENTS", a[f".claude/commands/{nombre}.md"])
            self.assertIn("$ARGUMENTS", a[f".opencode/commands/{nombre}.md"])
            self.assertIn("{{args}}", tomllib.loads(a[f".gemini/commands/{nombre}.toml"])["prompt"])

    def test_claude_y_gemini_importan_agents(self):
        a = harness.archivos()
        self.assertIn("@AGENTS.md", a["CLAUDE.md"])
        self.assertIn("@./AGENTS.md", a["GEMINI.md"])

    def test_instrucciones_para_cada_harness(self):
        for h in harness.HARNESSES:
            self.assertTrue(harness.instrucciones(h["id"]))
        with self.assertRaises(ValueError):
            harness.instrucciones("teletipo")


class TestSesiones(unittest.TestCase):
    def test_retomar_registra_narrador_en_cada_evento(self):
        with repo_temporal():
            texto = sesion.retomar("neva", "codex/gpt-5.5")
            self.assertIn("codex/gpt-5.5", texto)
            estado.registrar("neva", {"tipo": "nota", "texto": "hola"})
            self.assertEqual(estado.leer_eventos("neva")[-1]["narrador"], "codex/gpt-5.5")

    def test_traspaso_entre_narradores(self):
        with repo_temporal():
            sesion.retomar("neva", "claude-code/opus")
            sesion.pausar("neva", "Stepán espera preguntas")
            self.assertIn("Retomar aquí", informes.contexto("neva"))
            texto = sesion.retomar("neva", "hermes/kimi-k3")
            self.assertIn("Stepán espera preguntas", texto)
            self.assertIn("antes: claude-code/opus", texto)
            import io
            from contextlib import redirect_stdout
            from mesa import cli
            with redirect_stdout(io.StringIO()):
                cli.main(["turno", "--accion", "Jualjin=¿Quién te persigue?", "--resumen", "Stepán responde"])
            self.assertNotIn("pausa", estado.cargar("neva"))
            self.assertNotIn("Retomar aquí", informes.contexto("neva"))

    def test_retomar_sin_narrador_no_hereda_el_anterior(self):
        with repo_temporal(), mock.patch.dict(os.environ, {"MESA_NARRADOR": ""}):
            sesion.retomar("neva", "claude-code/opus")
            sesion.pausar("neva", "Stepán espera preguntas")
            datos = estado.cargar("neva")
            self.assertNotIn("sesion", datos)
            self.assertEqual(datos["pausa"]["narrador"], "claude-code/opus")
            self.assertEqual(estado.leer_eventos("neva")[-1]["narrador"], "claude-code/opus")
            texto = sesion.retomar("neva")
            self.assertIn("Narra ahora: **sin identificar** (antes: claude-code/opus)", texto)
            self.assertIn("Identifícate", texto)

    def test_retomar_trae_el_borrador_de_anteriormente(self):
        with repo_temporal():
            texto = sesion.retomar("neva", "hermes/kimi-k3")
            self.assertIn("## Anteriormente", texto)
            self.assertIn("- Turno 11:", texto)
            self.assertLess(texto.index("## Anteriormente"), texto.index("## Retomar aquí"))

    def test_pausar_con_commit(self):
        with repo_temporal() as raiz:
            git = lambda *a: subprocess.run(["git", "-C", str(raiz), *a], capture_output=True, text=True, check=True)
            git("init", "-q", "-b", "main")
            git("config", "user.name", "Test")
            git("config", "user.email", "test@example.com")
            git("add", "-A")
            git("commit", "-q", "-m", "inicio")
            salida = sesion.pausar("neva", "Pendiente de prueba", commit=True)
            self.assertIn("Commit", salida)
            self.assertIn("pausa(neva): Pendiente de prueba", git("log", "-1", "--format=%s").stdout)
            self.assertIn("Sin cambios", sesion._commit("neva", "otra", None))


if __name__ == "__main__":
    unittest.main()
