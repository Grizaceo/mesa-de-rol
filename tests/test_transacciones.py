"""Un solo escritor por partida, y transacciones que sobreviven a un corte.

Reprodujeron el defecto (código anterior): dos lecturas de la misma revisión se
pisaban en silencio (`caja=7` quedó), doce hilos concurrentes dejaban 3 seqs
únicos de 12, y ocho procesos `recurso --sumar 1` sobrevivían 7 de 8. Ahora la
revisión vieja recibe `Conflicto`, el candado serializa hilos y procesos, y el
diario (`.transaccion.json`) rehace una transacción cortada sin duplicar eventos
ni dejar medio turno.

La idempotencia general (`command_id` repetido = un solo efecto) sigue pendiente:
se habilitará antes de los reintentos automáticos, conectores o web, como dice el
plan; aquí solo se garantiza orden único por transacción y rechazo sin mutación.
"""

from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from contextlib import contextmanager, redirect_stderr
from pathlib import Path
from unittest import mock

from mesa import bloqueo, cli, estado

from apoyo import REPO

ESPERA = 30  # si un test se cuelga esperando el candado, que falle por timeout del proceso


@contextmanager
def raiz_temporal():
    """Una raíz de datos de mentira con la partida «neva», para tests y subprocesos."""
    original = estado.RAIZ
    with tempfile.TemporaryDirectory() as tmp:
        raiz = Path(tmp)
        (raiz / "partidas").mkdir()
        shutil.copytree(REPO / "partidas" / "_plantilla", raiz / "partidas" / "neva")
        datos = json.loads((raiz / "partidas" / "neva" / "partida.json").read_text(encoding="utf-8"))
        datos["slug"] = "neva"
        (raiz / "partidas" / "neva" / "partida.json").write_text(json.dumps(datos, ensure_ascii=False), encoding="utf-8")
        (raiz / "partidas" / "neva" / "eventos.jsonl").write_text("", encoding="utf-8")
        (raiz / "lecciones").mkdir()
        (raiz / ".mesa-activa").write_text("neva\n", encoding="utf-8")
        estado.RAIZ = raiz
        try:
            yield raiz
        finally:
            estado.RAIZ = original


def entorno(raiz: Path) -> dict:
    return dict(os.environ, MESA_RAIZ=str(raiz), PYTHONPATH=str(REPO), HERMES_HOME=str(raiz / "hermes"))


def correr(raiz: Path, *args: str, espera_candado: float | None = None) -> subprocess.CompletedProcess:
    entorno_ = entorno(raiz)
    if espera_candado is not None:
        entorno_["MESA_ESPERA_CANDADO"] = str(espera_candado)
    return subprocess.run([sys.executable, "-m", "mesa", *args], cwd=REPO, env=entorno_,
                          capture_output=True, text=True, timeout=60)


def huella(*rutas: Path) -> list[bytes]:
    return [r.read_bytes() if r.exists() else b"" for r in rutas]


class TestSinPerdidas(unittest.TestCase):
    def test_una_revision_vieja_no_pisa_en_silencio(self):
        with raiz_temporal():
            a = estado.cargar("neva")
            b = estado.cargar("neva")
            b.setdefault("recursos", {})["caja"] = 1
            estado.guardar("neva", b)
            a.setdefault("recursos", {})["caja"] = 7
            with self.assertRaises(estado.Conflicto) as capturado:
                estado.guardar("neva", a)
            self.assertIn("versión", str(capturado.exception))
            self.assertEqual(estado.cargar("neva")["recursos"]["caja"], 1, "la escritura rechazada no muta")
            self.assertEqual(estado.leer_eventos("neva"), [], "el rechazo tampoco toca la bitácora")

    def test_hilos_concurrentes_asignan_seq_unico(self):
        with raiz_temporal():
            barrera = threading.Barrier(12)
            resultados: list[dict] = []
            def escribir(i: int) -> None:
                barrera.wait()
                resultados.append(estado.registrar("neva", {"tipo": "nota", "texto": f"n{i}"}))
            hilos = [threading.Thread(target=escribir, args=(i,)) for i in range(12)]
            for h in hilos:
                h.start()
            for h in hilos:
                h.join()
            self.assertEqual(sorted(r["seq"] for r in resultados), list(range(1, 13)))
            seqs = [e["seq"] for e in estado.leer_eventos("neva")]
            self.assertEqual(sorted(seqs), list(range(1, 13)), "ni duplicados ni huecos")

    def test_procesos_concurrentes_no_pierden_sumas(self):
        with raiz_temporal() as raiz:
            ya = raiz / "ya"
            guion = (
                "import os, sys, time\n"
                "from mesa import cli\n"
                "while not os.path.exists(os.environ['ESPERA']): time.sleep(0.005)\n"
                "sys.exit(cli.main(['recurso', 'caja', '--sumar', '1']))\n"
            )
            procesos = []
            for _ in range(8):
                entorno_ = dict(entorno(raiz), ESPERA=str(ya))
                procesos.append(subprocess.Popen([sys.executable, "-c", guion], cwd=REPO, env=entorno_,
                                                 stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True))
            ya.write_text("ya\n", encoding="utf-8")
            errores = [p.communicate(timeout=ESPERA)[1] for p in procesos]
            self.assertEqual([p.returncode for p in procesos], [0] * 8, errores)
            self.assertEqual(estado.cargar("neva")["recursos"]["caja"], 8)
            eventos = estado.leer_eventos("neva")
            self.assertEqual(len(eventos), 8)
            self.assertEqual(sorted(e["seq"] for e in eventos), list(range(1, 9)))


class TestCandado(unittest.TestCase):
    @contextmanager
    def _candado_tomado(self, raiz: Path):
        guion = (
            "import time\n"
            "from mesa import bloqueo, estado\n"
            "with bloqueo.candado(estado.ruta_candado('neva'), 5):\n"
            "    print('tomado', flush=True)\n"
            "    time.sleep(2)\n"
        )
        p = subprocess.Popen([sys.executable, "-c", guion], cwd=REPO, env=entorno(raiz),
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.assertEqual(p.stdout.readline().strip(), "tomado")
        p.stdout.close()
        try:
            yield p
        finally:
            p.wait(timeout=ESPERA)
            p.stderr.close()

    def test_el_segundo_escritor_es_rechazado_sin_mutar(self):
        with raiz_temporal() as raiz:
            archivos = (raiz / "partidas" / "neva" / "partida.json", raiz / "partidas" / "neva" / "eventos.jsonl")
            antes = huella(*archivos)
            with self._candado_tomado(raiz):
                r = correr(raiz, "nota", "no debería escribirse", espera_candado=0)
            self.assertEqual(r.returncode, 1)
            self.assertIn("escribiendo", r.stderr)
            self.assertEqual(huella(*archivos), antes, "el rechazado no mutó nada")

    def test_leer_no_espera_al_candado(self):
        with raiz_temporal() as raiz:
            with self._candado_tomado(raiz):
                r = correr(raiz, "estado", "--breve", espera_candado=0)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("Personaje 1", r.stdout)

    def test_reentrante_en_el_mismo_hilo(self):
        with raiz_temporal():
            with bloqueo.candado(estado.ruta_candado("neva")):
                with bloqueo.candado(estado.ruta_candado("neva")):
                    estado.registrar("neva", {"tipo": "nota", "texto": "dentro"})
            self.assertEqual([e["seq"] for e in estado.leer_eventos("neva")], [1])

    def test_un_proceso_muerto_no_deja_la_partida_bloqueada(self):
        with raiz_temporal() as raiz:
            with self._candado_tomado(raiz) as p:
                p.kill()
            r = correr(raiz, "nota", "después del cadáver", espera_candado=0)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual([e["seq"] for e in estado.leer_eventos("neva")], [1])


class TestRecuperacion(unittest.TestCase):
    def _partida_cortada(self, raiz: Path) -> None:
        """Deja un diario pendiente como si el proceso hubiera muerto antes de aplicar."""
        datos = estado.cargar("neva")
        datos.setdefault("recursos", {})["caja"] = 3
        with mock.patch.object(estado, "_aplicar", side_effect=OSError("corte a mitad")):
            with self.assertRaises(OSError):
                estado.escribir("neva", datos, [{"tipo": "recurso", "clave": "caja", "valor": 3}])

    def test_antes_del_diario_no_se_escribio_nada(self):
        with raiz_temporal() as raiz:
            datos = estado.cargar("neva")
            datos.setdefault("recursos", {})["caja"] = 3
            with mock.patch.object(estado, "_escribir_texto", side_effect=OSError("corte antes del diario")):
                with self.assertRaises(OSError):
                    estado.escribir("neva", datos, [{"tipo": "recurso", "clave": "caja", "valor": 3}])
            self.assertFalse(estado.ruta_diario("neva").exists())
            en_disco = json.loads((raiz / "partidas" / "neva" / "partida.json").read_text(encoding="utf-8"))
            self.assertEqual(en_disco["version"], 0)
            self.assertEqual((raiz / "partidas" / "neva" / "eventos.jsonl").read_text(encoding="utf-8"), "")

    def test_un_diario_a_medias_se_rehace_al_leer(self):
        with raiz_temporal() as raiz:
            self._partida_cortada(raiz)
            self.assertTrue(estado.ruta_diario("neva").exists())
            datos = estado.cargar("neva")
            self.assertEqual(datos["recursos"]["caja"], 3)
            self.assertEqual(datos["version"], 1, "la versión sube una sola vez")
            self.assertFalse(estado.ruta_diario("neva").exists(), "el diario se borra al terminar")
            self.assertEqual([e["seq"] for e in estado.leer_eventos("neva")], [1])

    def test_una_escritura_posterior_tambien_recupera(self):
        with raiz_temporal() as raiz:
            self._partida_cortada(raiz)
            evento = estado.registrar("neva", {"tipo": "nota", "texto": "siguiente"})
            self.assertEqual(evento["seq"], 2, "el diario se aplicó antes de numerar")
            self.assertEqual(estado.cargar("neva")["recursos"]["caja"], 3)
            self.assertEqual([e["seq"] for e in estado.leer_eventos("neva")], [1, 2])

    def test_una_cola_a_medias_se_recorta_y_no_duplica(self):
        with raiz_temporal() as raiz:
            datos = estado.cargar("neva")
            datos.setdefault("recursos", {})["caja"] = 3
            eventos = [{"tipo": "recurso", "clave": "caja", "valor": 3}, {"tipo": "nota", "texto": "dos"}]

            def cortar(slug, completos):
                ruta = estado._ruta_eventos(slug)
                with ruta.open("a", encoding="utf-8") as f:  # línea a medias, sin \n
                    f.write(json.dumps(completos[0], ensure_ascii=False)[:25])
                raise OSError("corte escribiendo la bitácora")

            with mock.patch.object(estado, "_unir_eventos", side_effect=cortar):
                with self.assertRaises(OSError):
                    estado.escribir("neva", datos, eventos)
            leidos = estado.leer_eventos("neva")
            self.assertEqual([e["seq"] for e in leidos], [1, 2])
            self.assertEqual([e["tipo"] for e in leidos], ["recurso", "nota"])
            for linea in (raiz / "partidas" / "neva" / "eventos.jsonl").read_text(encoding="utf-8").splitlines():
                json.loads(linea)  # no queda ninguna línea rota
            self.assertEqual(len(estado.leer_eventos("neva")), 2, "la recuperación no duplica")

    def test_si_ya_se_aplico_todo_no_se_repite(self):
        with raiz_temporal() as raiz:
            datos = estado.cargar("neva")
            datos.setdefault("recursos", {})["caja"] = 3
            diario = estado.ruta_diario("neva")
            original = Path.unlink

            def fallar(self, *args, **kwargs):
                if self == diario:
                    raise OSError("corte justo antes de borrar el diario")
                return original(self, *args, **kwargs)

            with mock.patch.object(Path, "unlink", fallar):
                with self.assertRaises(OSError):
                    estado.escribir("neva", datos, [{"tipo": "recurso", "clave": "caja", "valor": 3}])
            self.assertTrue(diario.exists())
            datos = estado.cargar("neva")
            self.assertEqual(datos["version"], 1)
            self.assertEqual([e["seq"] for e in estado.leer_eventos("neva")], [1])
            self.assertFalse(diario.exists())

    def test_un_turno_completo_o_nada(self):
        with raiz_temporal() as raiz:
            with mock.patch.object(estado, "_aplicar", side_effect=OSError("corte a mitad del turno")):
                with redirect_stderr(io.StringIO()) as salida:
                    codigo = cli.main(["turno", "--resumen", "empujan la puerta", "--accion", "Ana=empuja",
                                       "--cambio", "recurso caja 3"])
            self.assertEqual(codigo, 1, "el corte se reporta con un error legible")
            self.assertIn("corte a mitad del turno", salida.getvalue())
            # Antes de recuperar no hay medio turno: ni estado ni bitácora cambiaron.
            en_disco = json.loads((raiz / "partidas" / "neva" / "partida.json").read_text(encoding="utf-8"))
            self.assertEqual(en_disco["version"], 0)
            self.assertEqual((raiz / "partidas" / "neva" / "eventos.jsonl").read_text(encoding="utf-8"), "")
            # La siguiente lectura rehace el turno entero, con sus dos eventos en orden.
            datos = estado.cargar("neva")
            self.assertEqual(datos["recursos"]["caja"], 3)
            self.assertEqual([e["tipo"] for e in estado.leer_eventos("neva")], ["recurso", "turno"])
            self.assertEqual(datos["version"], 1)

    def test_una_linea_rota_en_medio_no_se_pierde_en_silencio(self):
        with raiz_temporal() as raiz:
            ruta = raiz / "partidas" / "neva" / "eventos.jsonl"
            ruta.write_text(
                json.dumps({"seq": 1, "tipo": "nota"}, ensure_ascii=False) + "\n{rota\n"
                + json.dumps({"seq": 3, "tipo": "nota"}, ensure_ascii=False) + "\n", encoding="utf-8")
            self.assertEqual([e["seq"] for e in estado.leer_eventos("neva")], [1, 3])  # leer no truena
            datos = estado.cargar("neva")
            datos["recursos"] = {"caja": 1}
            with self.assertRaises(estado.Conflicto):
                estado.escribir("neva", datos, [{"tipo": "recurso", "clave": "caja", "valor": 1}])
            self.assertIn("{rota", ruta.read_text(encoding="utf-8"), "no se recorta una línea del medio")
            self.assertEqual(json.loads((raiz / "partidas" / "neva" / "partida.json").read_text(encoding="utf-8"))["version"], 0,
                             "el aviso llega antes de aplicar nada")
            self.assertFalse(estado.ruta_diario("neva").exists(), "la transacción ni siquiera empezó")

    def test_un_diario_corrupto_avisa_en_vez_de_pisar(self):
        with raiz_temporal() as raiz:
            estado.ruta_diario("neva").write_text("{esto no es json", encoding="utf-8")
            with self.assertRaises(estado.Conflicto) as capturado:
                estado.cargar("neva")
            self.assertIn("diario", str(capturado.exception))
            self.assertEqual(json.loads((raiz / "partidas" / "neva" / "partida.json").read_text(encoding="utf-8"))["version"], 0)


if __name__ == "__main__":
    unittest.main()
