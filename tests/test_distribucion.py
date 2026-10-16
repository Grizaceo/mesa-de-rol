"""Recursos inmutables: la copia empaquetada y el wheel instalado de verdad.

Dos garantías separadas:

  * `mesa/recursos/` es una copia byte a byte de `visor/`, `partidas/_plantilla/` y
    `adaptadores/`, y sigue siéndolo (`test_sync_*`, guarda contra ediciones a mano).
  * el wheel funciona instalado fuera del checkout: crea partidas con la plantilla
    empaquetada, sirve el visor empaquetado y escribe los datos solo bajo la raíz
    explícita (`MESA_RAIZ`, o el directorio del usuario si no la hay).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

from mesa import cli, distribucion

from apoyo import REPO

CONTENIDO_FALSO = {
    "visor/index.html": "<html>visor</html>",
    "visor/app.js": "console.log(1)\n",
    "partidas/_plantilla/partida.json": '{"slug": "_plantilla"}',
}


@contextmanager
def origen_falso(contenido: dict[str, str]):
    """Un repositorio de mentira con su copia empaquetada, ambos en un temporal."""
    with tempfile.TemporaryDirectory() as tmp:
        raiz, copias = Path(tmp) / "repo", Path(tmp) / "recursos"
        for relativo, texto in contenido.items():
            ruta = raiz / relativo
            ruta.parent.mkdir(parents=True, exist_ok=True)
            ruta.write_text(texto, encoding="utf-8")
        copias.mkdir()
        with mock.patch.object(distribucion, "raiz_checkout", return_value=raiz), \
             mock.patch.object(distribucion, "COPIAS", copias):
            yield raiz, copias


class TestCopiaEmpaquetada(unittest.TestCase):
    def test_copia_en_sincronia_con_el_repositorio(self):
        pendientes = distribucion.diferencias()
        self.assertEqual(pendientes, [], "corre `bin/mesa recursos sync` y commitea mesa/recursos/")

    def test_sync_copia_actualiza_y_borra(self):
        with origen_falso(CONTENIDO_FALSO) as (raiz, copias):
            self.assertEqual(sorted(distribucion.diferencias()), sorted(CONTENIDO_FALSO))
            self.assertFalse((copias / "visor").exists())
            cambiadas = distribucion.sincronizar()
            self.assertEqual(sorted(cambiadas), sorted(CONTENIDO_FALSO))
            self.assertEqual(distribucion.diferencias(), [])
            self.assertEqual((copias / "visor" / "app.js").read_bytes(), b"console.log(1)\n")

            # El original cambia: la copia vieja se detecta y `sync` la actualiza.
            (raiz / "visor" / "app.js").write_text("console.log(2)\n", encoding="utf-8")
            self.assertEqual(distribucion.diferencias(), ["visor/app.js"])
            distribucion.sincronizar()
            self.assertEqual((copias / "visor" / "app.js").read_bytes(), b"console.log(2)\n")

            # El original se borra: la copia también, o el wheel llevaría un recurso muerto.
            (raiz / "visor" / "app.js").unlink()
            self.assertIn("visor/app.js", distribucion.diferencias())
            distribucion.sincronizar()
            self.assertFalse((copias / "visor" / "app.js").exists())
            self.assertEqual(distribucion.diferencias(), [])

    def test_verificar_describe_los_tres_estados(self):
        with origen_falso(CONTENIDO_FALSO) as (_, __):
            self.assertEqual(distribucion.verificar()[0], "fallo")
            distribucion.sincronizar()
            self.assertEqual(distribucion.verificar()[0], "ok")
        with mock.patch.object(distribucion, "raiz_checkout", return_value=None):
            self.assertEqual(distribucion.verificar()[0], "omitido")

    def test_inmutable_prefiere_el_checkout_y_cae_a_la_copia(self):
        with origen_falso(CONTENIDO_FALSO) as (raiz, copias):
            self.assertEqual(distribucion.visor(), raiz / "visor")
            # Un recurso que no está en el checkout (caso raro) sale de la copia empaquetada.
            self.assertEqual(distribucion.adaptadores(), copias / "adaptadores")

    def test_comando_recursos(self):
        self.assertEqual(cli.main(["recursos", "verificar"]), 0)
        self.assertEqual(cli.main(["recursos", "sync"]), 0)


class TestWheelInstalado(unittest.TestCase):
    """El wheel de verdad: `pip wheel`, instalado en un venv, corrido desde fuera del checkout."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.base = Path(cls._tmp.name)
        cls.venv = cls.base / "venv"
        creado = subprocess.run([sys.executable, "-m", "venv", "--system-site-packages", str(cls.venv)],
                                capture_output=True, text=True)
        if creado.returncode != 0:
            raise unittest.SkipTest(f"no se pudo crear el venv: {creado.stderr[-300:]}")
        cls.python = cls.venv / "bin" / "python"
        cls.mesa = cls.venv / "bin" / "mesa"
        cls.trabajo = cls.base / "trabajo"
        cls.trabajo.mkdir()
        version = subprocess.run(
            [str(cls.python), "-c", "import setuptools; print(setuptools.__version__)"], capture_output=True, text=True)
        try:
            moderna = int(version.stdout.strip().split(".")[0]) >= 68
        except ValueError:
            moderna = False
        if version.returncode != 0 or not moderna:
            raise unittest.SkipTest("sin setuptools>=68 en el intérprete: no se puede construir sin red")
        cls.dist = cls.base / "dist"
        # Se construye desde una copia con señuelos, no desde el checkout: el wheel no debe
        # llevarse partidas, lecciones ni archivos de harness, y el repo queda limpio.
        cls.fuente = cls.base / "fuente"
        shutil.copytree(REPO / "mesa", cls.fuente / "mesa", ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copy2(REPO / "pyproject.toml", cls.fuente / "pyproject.toml")
        shutil.copy2(REPO / "README.md", cls.fuente / "README.md")
        for relativo in ("partidas/secreta/partida.json", "lecciones/lecciones.jsonl",
                         ".hermes/config.yaml", "visor/index.html"):
            senuelo = cls.fuente / relativo
            senuelo.parent.mkdir(parents=True, exist_ok=True)
            senuelo.write_text("no debe viajar\n", encoding="utf-8")
        construido = subprocess.run(
            [str(cls.python), "-m", "pip", "wheel", "--no-build-isolation", "--no-deps",
             "--wheel-dir", str(cls.dist), str(cls.fuente)], capture_output=True, text=True)
        if construido.returncode != 0:
            raise AssertionError(f"pip wheel falló:\n{construido.stdout[-1500:]}\n{construido.stderr[-1500:]}")
        cls.rueda, = cls.dist.glob("mesa_de_rol-*.whl")
        instalado = subprocess.run([str(cls.python), "-m", "pip", "install", "--no-deps", "--quiet", str(cls.rueda)],
                                   capture_output=True, text=True)
        if instalado.returncode != 0:
            raise AssertionError(f"pip install falló:\n{instalado.stderr[-1500:]}")

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def entorno(self, datos: Path, sin: tuple[str, ...] = ()) -> dict:
        entorno = {
            "PATH": f"{self.venv / 'bin'}:/usr/bin:/bin",
            "HOME": str(self.base / "casa"),
            "XDG_DATA_HOME": str(self.base / "xdg"),
            "HERMES_HOME": str(self.base / "hermes"),
            "MESA_RAIZ": str(datos),
            "LANG": "C.UTF-8",
        }
        for clave in sin:
            entorno.pop(clave, None)
        return entorno

    def correr(self, *args, datos: Path, sin: tuple[str, ...] = ()) -> subprocess.CompletedProcess:
        return subprocess.run([str(self.mesa), *args], capture_output=True, text=True,
                              env=self.entorno(datos, sin), cwd=self.trabajo)

    def test_la_rueda_lleva_los_recursos_y_nada_de_las_partidas(self):
        with zipfile.ZipFile(self.rueda) as z:
            nombres = z.namelist()
        for esperado in ("mesa/recursos/visor/index.html", "mesa/recursos/visor/app.js",
                         "mesa/recursos/partidas/_plantilla/partida.json",
                         "mesa/recursos/adaptadores/hermes/mesa-de-rol/SKILL.md",
                         "mesa/recursos/adaptadores/comandos/retomar.md"):
            self.assertIn(esperado, nombres)
        # Fuera del paquete no viaja nada (solo la metadata del wheel), y los señuelos de la
        # fuente (partidas, lecciones, .hermes, visor/ y adaptadores/ de raíz) se quedan fuera.
        fuera = [n for n in nombres if ".dist-info" not in n and not n.startswith("mesa/")]
        self.assertEqual(fuera, [], "los recursos van bajo mesa/recursos/")
        self.assertEqual([n for n in nombres if "secreta" in n or ".hermes" in n], [])
        self.assertEqual([n for n in nombres if n.startswith(("visor/", "partidas/", "adaptadores/", "lecciones/", "biblioteca/"))], [])
        self.assertFalse([n for n in nombres if n.startswith(("visor/", "partidas/", "adaptadores/"))],
                         "los recursos van bajo mesa/recursos/, no en la raíz del wheel")

    def test_instalado_funciona_fuera_del_checkout(self):
        datos = self.base / "datos-minimo"
        nueva = self.correr("nueva", "campana", "--titulo", "Prueba del wheel", datos=datos)
        self.assertEqual(nueva.returncode, 0, nueva.stderr)
        partida = datos / "partidas" / "campana"
        self.assertEqual(json.loads((partida / "partida.json").read_text(encoding="utf-8"))["slug"], "campana")
        # Las plantillas que copia son las empaquetadas (el checkout no está al lado).
        self.assertTrue((partida / "director.md").is_file())
        self.assertTrue((partida / "biblia.md").is_file())

        self.assertEqual(self.correr("usar", "campana", datos=datos).returncode, 0)
        breve = self.correr("estado", "--breve", datos=datos)
        self.assertEqual(breve.returncode, 0, breve.stderr)
        self.assertIn("Personaje 1", breve.stdout)

        tarjeta = self.correr("imagen", "ninguna", datos=datos)
        self.assertEqual(tarjeta.returncode, 0, tarjeta.stderr)
        imagenes = list((partida / "imagenes").glob("*"))
        self.assertEqual([i.suffix for i in imagenes], [".svg"], tarjeta.stdout + tarjeta.stderr)

        # El visor empaquetado se sirve y la API lee la partida de la raíz pedida.
        salida = self._sondear_visor(datos, imagenes[0].name)
        self.assertEqual(salida["index"], 200)
        self.assertTrue(salida["index_lleva_app"], salida)
        self.assertEqual(salida["app"], 200)
        self.assertEqual(salida["estado"], 200)
        self.assertEqual(salida["slug"], "campana")
        self.assertEqual(salida["media"], 200)
        self.assertEqual(salida["travesia"], 404)

        # Nada se escribió fuera: ni en el directorio de trabajo, ni en el venv, ni en el repo.
        self.assertEqual(list(self.trabajo.iterdir()), [])
        self.assertEqual([p for p in self.venv.rglob("campana")], [], "la partida se escribió dentro del venv")
        self.assertFalse((REPO / "partidas" / "campana").exists())
        self.assertFalse((self.base / "casa" / ".local" / "share" / "mesa-de-rol" / "partidas" / "campana").exists())

    def test_sin_mesa_raiz_los_datos_van_al_directorio_del_usuario(self):
        xdg = self.base / "xdg"
        nueva = self.correr("nueva", "sin-raiz", "--titulo", "Sin MESA_RAIZ", datos=xdg / "mesa-de-rol", sin=("MESA_RAIZ",))
        self.assertEqual(nueva.returncode, 0, nueva.stderr)
        self.assertTrue((xdg / "mesa-de-rol" / "partidas" / "sin-raiz" / "partida.json").is_file())
        self.assertFalse((REPO / "partidas" / "sin-raiz").exists())
        self.assertFalse((self.trabajo / "partidas").exists())

    def _sondear_visor(self, datos: Path, archivo: str) -> dict:
        codigo = (
            "import json, sys, threading, urllib.error, urllib.request\n"
            "from mesa import servidor\n"
            "srv = servidor.crear('127.0.0.1', 0)\n"
            "puerto = srv.server_address[1]\n"
            "threading.Thread(target=srv.serve_forever, daemon=True).start()\n"
            "def obtener(ruta):\n"
            "    try:\n"
            "        with urllib.request.urlopen(f'http://127.0.0.1:{puerto}{ruta}', timeout=5) as r:\n"
            "            return r.status, r.read()\n"
            "    except urllib.error.HTTPError as e:\n"
            "        return e.code, e.read()\n"
            "salida = {}\n"
            "codigo, cuerpo = obtener('/')\n"
            "salida['index'] = codigo\n"
            "salida['index_lleva_app'] = b'app.js' in cuerpo\n"
            "salida['app'] = obtener('/visor/app.js')[0]\n"
            "codigo, cuerpo = obtener('/api/estado')\n"
            "salida['estado'] = codigo\n"
            "salida['slug'] = json.loads(cuerpo)['slug']\n"
            "salida['media'] = obtener(f'/media/{salida[\"slug\"]}/{sys.argv[1]}')[0]\n"
            "salida['travesia'] = obtener('/visor/..%2F..%2Fpartidas%2Fcampana%2Fdirector.md')[0]\n"
            "srv.shutdown()\n"
            "print(json.dumps(salida))\n"
        )
        r = subprocess.run([str(self.python), "-c", codigo, archivo], capture_output=True, text=True,
                           env=self.entorno(datos), cwd=self.trabajo)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)


if __name__ == "__main__":
    unittest.main()
