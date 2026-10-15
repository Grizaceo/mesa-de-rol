import io
import json
import shutil
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from mesa import cli, estado, imagenes, informes, lecciones

from apoyo import dados_fijos, repo_temporal


def correr(*args):
    salida, errores = io.StringIO(), io.StringIO()
    with redirect_stdout(salida), redirect_stderr(errores):
        codigo = cli.main(list(args))
    return codigo, salida.getvalue(), errores.getvalue()


class TestEstado(unittest.TestCase):
    def test_guardar_sube_version_y_registrar_numera(self):
        with repo_temporal():
            datos = estado.cargar("neva")
            version = datos.get("version", 0)
            estado.guardar("neva", datos)
            self.assertEqual(estado.cargar("neva")["version"], version + 1)
            ultimo = estado.leer_eventos("neva")[-1]["seq"]
            e = estado.registrar("neva", {"tipo": "nota", "texto": "hola"})
            self.assertEqual(e["seq"], ultimo + 1)
            self.assertEqual([x["seq"] for x in estado.leer_eventos("neva", desde=ultimo)], [ultimo + 1])

    def test_buscar_por_prefijo_y_errores(self):
        with repo_temporal():
            datos = estado.cargar("neva")
            self.assertEqual(estado.buscar(datos, "crisl")[1]["nombre"], "Crisljin")
            self.assertEqual(estado.buscar(datos, "JUALJIN")[1]["nombre"], "Jualjin")
            with self.assertRaises(ValueError):
                estado.buscar(datos, "Gúsev")

    def test_slug_invalido(self):
        with repo_temporal(), self.assertRaises(ValueError):
            estado.dir_partida("../etc")

    def test_nueva_partida_desde_plantilla(self):
        with repo_temporal():
            ruta = estado.nueva_partida("la-isla", "La isla")
            datos = estado.cargar("la-isla")
            self.assertEqual(datos["titulo"], "La isla")
            self.assertEqual(estado.leer_eventos("la-isla")[0]["tipo"], "partida_creada")
            self.assertTrue((ruta / "biblia.md").exists())
            with self.assertRaises(FileExistsError):
                estado.nueva_partida("la-isla", "otra vez")

    def test_partida_nueva_sin_carpetas_vacias_de_git(self):
        with repo_temporal() as raiz:
            for carpeta in ("imagenes", "guardados"):
                shutil.rmtree(raiz / "partidas" / "_plantilla" / carpeta, ignore_errors=True)
            estado.nueva_partida("clon", "Clon limpio")
            shutil.rmtree(raiz / "partidas" / "clon" / "imagenes")
            self.assertTrue((raiz / "partidas" / "clon" / "imagenes" / imagenes.tarjeta_svg("clon")["archivo"]).exists())
            self.assertTrue((raiz / informes.guardado("clon")[1]).exists())


class TestCli(unittest.TestCase):
    def test_prueba_registra_evento_y_actualiza_estado(self):
        with repo_temporal(), dados_fijos(12):
            codigo, salida, _ = correr("prueba", "Jualjin", "atletismo", "--cd", "media", "--etiqueta", "remar")
            self.assertEqual(codigo, 0)
            self.assertIn("12 +3 Fuerza = 15", salida.replace("1d20 (12)", "12"))
            ultimo = estado.leer_eventos("neva")[-1]
            self.assertEqual((ultimo["tipo"], ultimo["habilidad"], ultimo["exito"]), ("prueba", "Atletismo", True))

    def test_error_legible_y_codigo_1(self):
        with repo_temporal():
            codigo, _, errores = correr("prueba", "Nadie", "fuerza")
            self.assertEqual(codigo, 1)
            self.assertIn("no encuentro", errores)

    def test_escena_nueva_recarga_habilidades_por_escena(self):
        with repo_temporal(), dados_fijos(10):
            correr("prueba", "Crisljin", "ingenio", "--usar", "tengo una idea")
            correr("escena", "nueva", "--titulo", "Casa", "--lugar", "Calle arriba")
            datos = estado.cargar("neva")
            self.assertEqual(datos["escena"]["numero"], 3)
            crisljin = estado.buscar(datos, "Crisljin")[1]
            self.assertTrue(crisljin["habilidades"][0]["disponible"])

    def test_nivel_respeta_maximo(self):
        with repo_temporal():
            for _ in range(1):
                self.assertEqual(correr("nivel", "Jualjin", "--atributo", "fuerza")[0], 0)
            codigo, _, errores = correr("nivel", "Jualjin", "--atributo", "fuerza")
            self.assertEqual(codigo, 1)
            self.assertIn("máximo", errores)


class TestInformesYLecciones(unittest.TestCase):
    def test_contexto_incluye_lecciones_y_reglas_de_la_casa(self):
        with repo_temporal():
            texto = informes.contexto("neva")
            self.assertIn("L001", texto)
            self.assertIn("R6", texto)
            self.assertIn("ambientacion:historica", texto)

    def test_lecciones_por_alcance(self):
        with repo_temporal():
            fantasia = {"ambientacion": {"etiquetas": ["fantasia"]}}
            alcances = {i["alcance"] for i in lecciones.aplicables(fantasia)}
            self.assertNotIn("ambientacion:historica", alcances)
            nueva = lecciones.agregar("Prueba", "ambientacion:fantasia", "tono", "test")
            self.assertIn(nueva["id"], [i["id"] for i in lecciones.aplicables(fantasia)])
            lecciones.retirar(nueva["id"], "era una prueba")
            self.assertNotIn(nueva["id"], [i["id"] for i in lecciones.aplicables(fantasia)])
            with self.assertRaises(ValueError):
                lecciones.agregar("x", "cualquiera", "tono", "test")

    def test_guardado_escribe_archivo(self):
        with repo_temporal() as raiz:
            texto, ruta = informes.guardado("neva")
            self.assertIn("Jualjin", texto)
            self.assertTrue((raiz / ruta).exists())


class TestImagenes(unittest.TestCase):
    def test_tarjeta_local(self):
        with repo_temporal() as raiz:
            e = imagenes.tarjeta_svg("neva")
            self.assertTrue((raiz / "partidas" / "neva" / "imagenes" / e["archivo"]).exists())
            self.assertEqual(estado.cargar("neva")["escena"]["imagen"], e["archivo"])

    def test_elegir_desde_biblioteca_y_ruta(self):
        with repo_temporal() as raiz:
            origen = raiz / "muelle.svg"
            origen.write_text("<svg xmlns='http://www.w3.org/2000/svg'/>", encoding="utf-8")
            item = imagenes.agregar_biblioteca(str(origen), ["muelle", "niebla"], "Muelle en la niebla", "propia", "CC0")
            self.assertEqual(imagenes.buscar("niebla en el muelle")[0]["id"], item["id"])
            e = imagenes.elegir("neva", item["id"])
            self.assertIn("biblioteca:muelle", e["origen"])
            e2 = imagenes.elegir("neva", str(origen))
            self.assertEqual(e2["modo"], "elegir")
            with self.assertRaises(ValueError):
                imagenes.elegir("neva", str(raiz / "no-existe.png"))

    def test_generar_simulado_no_usa_red(self):
        with repo_temporal():
            r = imagenes.generar("neva", simular=True)
            self.assertTrue(r["simulado"])
            self.assertIn("sin texto", r["prompt"])
            self.assertIn("Bajo el Muelle Torcido", r["prompt"])


if __name__ == "__main__":
    unittest.main()
