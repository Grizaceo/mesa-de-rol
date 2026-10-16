import io
import json
import shutil
import unittest
import urllib.error
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from mesa import cli, estado, imagenes, informes, lecciones

from apoyo import dados_fijos, repo_temporal


def correr(*args):
    salida, errores = io.StringIO(), io.StringIO()
    with redirect_stdout(salida), redirect_stderr(errores):
        codigo = cli.main(list(args))
    return codigo, salida.getvalue(), errores.getvalue()


class TestSelectores(unittest.TestCase):
    """P0-01: un selector vacío o ambiguo no puede elegir a nadie por accidente."""

    def _datos(self):
        return {"personajes": [{"nombre": "Anabella", "vida": 5}, {"nombre": "Ana", "vida": 5}]}

    def test_selector_vacio_o_solo_espacios_es_error(self):
        for quien in ("", "   ", "\t", " \n "):
            with self.subTest(quien=quien), self.assertRaises(ValueError):
                estado.buscar(self._datos(), quien)

    def test_selector_vacio_no_muta_la_partida(self):
        with repo_temporal():
            antes = (estado.dir_partida("neva") / "partida.json").read_text(encoding="utf-8")
            codigo, _, errores = correr("vida", "", "-1")
            self.assertEqual(codigo, 1)
            self.assertIn("vacío", errores)
            self.assertEqual((estado.dir_partida("neva") / "partida.json").read_text(encoding="utf-8"), antes)
            self.assertEqual(estado.buscar(estado.cargar("neva"), "Jualjin")[1]["vida"], 14)

    def test_coincidencia_exacta_gana_al_prefijo(self):
        datos = self._datos()
        self.assertEqual(estado.buscar(datos, "Ana")[1]["nombre"], "Ana")
        self.assertEqual(estado.buscar(datos, "Anab")[1]["nombre"], "Anabella")

    def test_prefijo_ambiguo_es_error_inequivoco(self):
        with self.assertRaises(ValueError) as e:
            estado.buscar(self._datos(), "An")
        self.assertIn("ambiguo", str(e.exception))
        self.assertIn("Ana", str(e.exception))
        self.assertIn("Anabella", str(e.exception))

    def test_quitar_enemigo_sin_nombre_no_borra_al_primero(self):
        with repo_temporal():
            correr("enemigo", "agregar", "Rata", "--plantilla", "rata")
            codigo, _, _ = correr("enemigo", "quitar")
            self.assertEqual(codigo, 1)
            self.assertEqual(len(estado.cargar("neva")["enemigos"]), 1)


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


class TestTurnoEnUnPaso(unittest.TestCase):
    def test_turno_aplica_los_cambios_y_queda_ultimo(self):
        with repo_temporal():
            antes = estado.leer_eventos("neva")[-1]["seq"]
            codigo, salida, errores = correr(
                "turno", "--accion", "Jualjin=¿Quién te persigue?", "--accion", "Crisljin=Reviso el paquete",
                "--resumen", "Stepán habla de la patrulla",
                "--cambio", 'pista "La patrulla busca un bote de la Armada" --fuente Stepán',
                "--cambio", 'pnj Stepán --nota "Teme al Puente de Hierro"',
                "--cambio", 'escena posicion Crisljin "junto al pilote, a 1 m de Stepán"',
            )
            self.assertEqual(codigo, 0, errores)
            self.assertIn("Turno 12 registrado.", salida)
            self.assertIn("Para la DECISIÓN", salida)
            self.assertIn("«Tengo una idea» disponible (+4, una por escena)", salida)
            datos = estado.cargar("neva")
            self.assertEqual(datos["pistas"][-1]["fuente"], "Stepán")
            self.assertIn("Teme al Puente de Hierro", next(n for n in datos["pnj"] if n["nombre"] == "Stepán")["notas"])
            self.assertNotIn("pausa", datos)
            nuevos = [e["tipo"] for e in estado.leer_eventos("neva", desde=antes)]
            self.assertEqual(nuevos, ["pista", "pnj", "posicion", "turno"])

    def test_turno_es_todo_o_nada(self):
        with repo_temporal():
            version = estado.cargar("neva")["version"]
            antes = estado.leer_eventos("neva")[-1]["seq"]
            codigo, _, errores = correr("turno", "--accion", "Jualjin=x", "--resumen", "x",
                                        "--cambio", 'pista "No debería quedar"', "--cambio", "vida Nadie -2")
            self.assertEqual(codigo, 1)
            self.assertIn("no encuentro", errores)
            self.assertEqual(estado.cargar("neva")["version"], version)
            self.assertNotIn("No debería quedar", [p["texto"] for p in estado.cargar("neva")["pistas"]])
            self.assertEqual(estado.leer_eventos("neva", desde=antes), [])

    def test_turno_rechaza_comandos_que_no_son_cambios(self):
        with repo_temporal():
            for cambio in ("tirar 1d20", "servir", "pista"):
                codigo, _, errores = correr("turno", "--resumen", "x", "--cambio", cambio)
                self.assertEqual(codigo, 1, cambio)
                self.assertIn("cambio", errores)

    def test_turno_avisa_si_falta_la_accion_de_alguien(self):
        with repo_temporal():
            _, salida, _ = correr("turno", "--accion", "Jualjin=Le pregunto a Stepán", "--resumen", "x")
            self.assertIn("⚠ Sin acción de Crisljin", salida)
            self.assertNotIn("Sin acción de Jualjin", salida)

    def test_accion_sin_igual_y_posicion_sin_quien_son_errores(self):
        with repo_temporal():
            codigo, _, errores = correr("turno", "--accion", "Jualjin miro", "--resumen", "x")
            self.assertEqual(codigo, 1)
            self.assertIn("Nombre=lo que declaró", errores)
            codigo, _, errores = correr("escena", "posicion")
            self.assertEqual(codigo, 1)
            self.assertIn("uso: escena posicion", errores)


class TestRecargasYDescanso(unittest.TestCase):
    def test_fin_del_combate_recarga_lo_por_combate(self):
        with repo_temporal():
            self.assertEqual(correr("habilidad", "Jualjin", "a mi hermano", "--usar")[0], 0)
            self.assertIn("sigue gastada", " ".join(informes.revisar(estado.cargar("neva"))))
            correr("enemigo", "agregar", "Matón", "--plantilla", "maton")
            self.assertNotIn("sigue gastada", " ".join(informes.revisar(estado.cargar("neva"))))
            _, salida, _ = correr("enemigo", "limpiar")
            self.assertIn("Fin del combate", salida)
            jualjin = estado.buscar(estado.cargar("neva"), "Jualjin")[1]
            self.assertTrue(jualjin["habilidades"][0]["disponible"])

    def test_vendaje_una_vez_y_descanso_largo(self):
        with repo_temporal(), dados_fijos(10):
            correr("vida", "Jualjin", "-6")
            self.assertEqual(correr("vendaje", "Jualjin")[0], 0)
            self.assertEqual(estado.buscar(estado.cargar("neva"), "Jualjin")[1]["vida"], 11)
            codigo, _, errores = correr("vendaje", "Jualjin")
            self.assertEqual(codigo, 1)
            self.assertIn("ya usó", errores)
            correr("prueba", "Crisljin", "ingenio", "--usar", "tengo una idea")
            correr("condicion", "Jualjin", "agregar", "agotamiento", "--niveles", "2")
            _, salida, _ = correr("descanso", "largo")
            self.assertIn("Descanso largo", salida)
            datos = estado.cargar("neva")
            jualjin, crisljin = estado.buscar(datos, "Jualjin")[1], estado.buscar(datos, "Crisljin")[1]
            self.assertEqual(jualjin["vida"], 14)
            self.assertNotIn("vendaje_usado", jualjin)
            self.assertEqual(next(c for c in jualjin["condiciones"] if c["nombre"] == "Agotamiento")["niveles"], 1)
            self.assertTrue(crisljin["habilidades"][0]["disponible"])

    def test_no_hay_vendaje_con_amenazas_en_pie(self):
        with repo_temporal():
            correr("enemigo", "agregar", "Matón", "--plantilla", "maton")
            codigo, _, errores = correr("vendaje", "Crisljin")
            self.assertEqual(codigo, 1)
            self.assertIn("fuera de combate", errores)


class TestFichaBreveYDocumentos(unittest.TestCase):
    def test_estado_breve_una_linea_por_personaje(self):
        with repo_temporal():
            _, salida, _ = correr("estado", "--breve")
            lineas = salida.strip().splitlines()
            self.assertEqual(len(lineas), 2)
            self.assertTrue(lineas[1].startswith("Crisljin (11/11)"))
            self.assertIn("Empapado: desventaja en Agilidad", lineas[1])
            self.assertIn("Oficio +2", lineas[0])

    def test_documento_se_pega_en_el_chat_y_queda_en_el_estado(self):
        with repo_temporal():
            codigo, salida, _ = correr("documento", "agregar", "Para Misha", "--clase", "carta",
                                       "--texto", "Línea uno\\nLínea dos", "--fuente", "En el paquete")
            self.assertEqual(codigo, 0)
            self.assertIn("> **Carta · Para Misha**", salida)
            self.assertIn("> Línea dos", salida)
            self.assertIn("> _En el paquete_", salida)
            datos = estado.cargar("neva")
            self.assertEqual(datos["documentos"][0]["id"], "D1")
            self.assertEqual(datos["documentos"][0]["texto"], "Línea uno\nLínea dos")
            self.assertIn("## Documentos", informes.resumen(datos))
            self.assertIn("Para Misha", correr("documento", "ver", "D1")[1])
            self.assertEqual(estado.leer_eventos("neva")[-1]["tipo"], "documento")


class TestErrores(unittest.TestCase):
    def test_un_error_de_red_es_legible(self):
        with repo_temporal(), mock.patch.object(imagenes, "_descargar", side_effect=urllib.error.URLError("sin red")):
            codigo, _, errores = correr("imagen", "elegir", "http://127.0.0.1:9/x.png")
            self.assertEqual(codigo, 1)
            self.assertIn("error de sistema o de red", errores)

    def test_revisar_avisa_de_enemigos_en_cero(self):
        with repo_temporal(), dados_fijos(20, 6, 6):
            correr("enemigo", "agregar", "Rata", "--plantilla", "rata")
            correr("ataque", "Jualjin", "Rata", "--arma", "bichero")
            _, salida, _ = correr("revisar")
            self.assertIn("Rata está en 0 de vida", salida)


class TestInformesYLecciones(unittest.TestCase):
    def test_contexto_incluye_lecciones_y_reglas_de_la_casa(self):
        with repo_temporal():
            texto = informes.contexto("neva")
            self.assertIn("L003", texto)
            self.assertNotIn("**L001**", texto)  # incorporada en AGENTS.md
            self.assertNotIn("**L009**", texto)  # solo en la sesión cero
            self.assertIn("R6", texto)
            self.assertIn("ambientacion:historica", texto)

    def test_contexto_completo_no_imprime_los_secretos(self):
        with repo_temporal() as raiz:
            (raiz / "partidas" / "neva" / "director.md").write_text("SECRETO-DE-PRUEBA", encoding="utf-8")
            texto = informes.contexto("neva", completo=True)
            self.assertNotIn("SECRETO-DE-PRUEBA", texto)
            self.assertIn("herramienta de lectura de archivos", texto)
            self.assertIn("# Biblia — Los Hermanos del Neva", texto)

    def test_lecciones_incorporadas_y_de_sesion_cero(self):
        with repo_temporal():
            nueva = lecciones.agregar("Pregunta la crudeza", "global", "seguridad", "test", fase="sesion-cero")
            ids = lambda partida: [i["id"] for i in lecciones.aplicables(partida)]
            self.assertIn(nueva["id"], ids({"escenas_jugadas": 0}))
            self.assertNotIn(nueva["id"], ids({"escenas_jugadas": 2}))
            lecciones.fijar_fase(nueva["id"], "siempre")
            self.assertIn(nueva["id"], ids({"escenas_jugadas": 2}))
            lecciones.incorporar(nueva["id"], "AGENTS.md")
            self.assertNotIn(nueva["id"], ids({"escenas_jugadas": 0}))
            self.assertIn("incorporada en AGENTS.md", lecciones.como_markdown(lecciones.leer()))

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
