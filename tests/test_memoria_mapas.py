import io
import json
import unittest
from contextlib import redirect_stderr, redirect_stdout

from mesa import cli, estado, informes, mapas, mcp, memoria

from apoyo import repo_temporal


def correr(*args):
    salida, errores = io.StringIO(), io.StringIO()
    with redirect_stdout(salida), redirect_stderr(errores):
        codigo = cli.main(list(args))
    return codigo, salida.getvalue(), errores.getvalue()


def disco(slug="neva"):
    return (estado.dir_partida(slug) / "partida.json").read_text(encoding="utf-8")


ZONA = "##########\\n#..T.....#\\n#........+\\n#~~~.....#\\n##########"


class TestMemoria(unittest.TestCase):
    """Hechos clave, «Hasta ahora» y crónica: lo que el narrador lee en vez de toda la conversación."""

    def test_agregar_editar_fijar_y_archivar(self):
        with repo_temporal():
            self.assertEqual(correr("hecho", "agregar", "Anya debe 30 rublos", "--categoria", "promesa")[0], 0)
            self.assertEqual(correr("hecho", "agregar", "El paquete lleva un sello", "--fijar")[0], 0)
            self.assertEqual(correr("hecho", "editar", "h1", "Anya debe 40 rublos")[0], 0)
            self.assertEqual(correr("hecho", "archivar", "2")[0], 0)
            hechos = estado.cargar("neva")["memoria"]["hechos"]
            self.assertEqual([h["id"] for h in hechos], ["H1", "H2"])
            self.assertEqual((hechos[0]["texto"], hechos[0]["categoria"], hechos[0]["editado_por"]), ("Anya debe 40 rublos", "promesa", "narrador"))
            self.assertTrue(hechos[1]["fijado"] and hechos[1]["archivado"])
            eventos = [e for e in estado.leer_eventos("neva") if e["tipo"] == "hecho"]
            self.assertEqual([e["accion"] for e in eventos], ["agregar", "agregar", "editar", "archivar"])

    def test_rechaza_vacio_duplicado_largo_y_categoria_desconocida_sin_mutar(self):
        with repo_temporal():
            correr("hecho", "agregar", "Algo cierto")
            antes = disco()
            for args in (("hecho", "agregar", "   "), ("hecho", "agregar", "algo  CIERTO"), ("hecho", "agregar", "x" * 501),
                         ("hecho", "editar", "H9", "nada"), ("hecho", "fijar", "")):
                with self.subTest(args=args):
                    codigo, _, errores = correr(*args)
                    self.assertEqual(codigo, 1)
                    self.assertTrue(errores.startswith("error:"))
            self.assertEqual(disco(), antes)
            with self.assertRaises(ValueError):
                memoria.aplicar({}, "agregar", texto="x", categoria="inventada")

    def test_presupuesto_fijados_siempre_y_los_mas_recientes_primero(self):
        datos = {"memoria": {"presupuesto": 400}}
        for i in range(1, 9):
            memoria.aplicar(datos, "agregar", texto=f"Hecho número {i} " + "x" * 60, fijado=(i == 1))
        memoria.aplicar(datos, "archivar", ident="H8")
        dentro, fuera = memoria.en_contexto(datos)
        ids = [h["id"] for h in dentro]
        self.assertIn("H1", ids)  # fijado y el más viejo: entra igual
        self.assertNotIn("H8", ids + [h["id"] for h in fuera])  # archivado: ni dentro ni «fuera»
        self.assertIn("H7", ids)  # el más reciente vigente
        self.assertTrue(fuera and all(int(h["id"][1:]) < int(min(i for i in ids if i != "H1")[1:]) for h in fuera))
        self.assertEqual(ids, sorted(ids, key=lambda i: int(i[1:])))
        uso = memoria.uso(datos)
        self.assertLessEqual(uso["libres"], 400)
        self.assertTrue(any("fuera del contexto" in a for a in memoria.avisos(datos)))

    def test_contexto_lleva_la_memoria_y_deja_fuera_lo_archivado(self):
        with repo_temporal():
            correr("memoria", "hasta-ahora", "Los hermanos esconden a Stepán bajo el muelle.")
            correr("hecho", "agregar", "Belov manda en el Puente de Hierro", "--categoria", "pnj")
            correr("hecho", "agregar", "Rumor viejo que ya no importa")
            correr("hecho", "archivar", "H2")
            texto = informes.contexto("neva")
            self.assertIn("## Memoria de la historia", texto)
            self.assertIn("Los hermanos esconden a Stepán", texto)
            self.assertIn("H1 (pnj): Belov manda en el Puente de Hierro", texto)
            self.assertNotIn("Rumor viejo", texto)
            self.assertIn("Hasta ahora: Los hermanos esconden", informes.anteriormente("neva"))

    def test_turno_avisa_tras_cinco_turnos_sin_hechos(self):
        with repo_temporal():
            correr("hecho", "agregar", "Punto de partida")
            for i in range(4):
                _, salida, _ = correr("turno", "--accion", "Jualjin=espera", "--accion", "Crisljin=espera", "--resumen", f"pausa {i}")
                self.assertNotIn("sin hechos clave", salida)
            _, salida, _ = correr("turno", "--accion", "Jualjin=espera", "--accion", "Crisljin=espera", "--resumen", "pausa 5")
            self.assertIn("Van 5 turnos sin hechos clave", salida)
            _, salida, _ = correr("turno", "--accion", "Jualjin=habla", "--accion", "Crisljin=escucha", "--resumen", "Hablan",
                                  "--cambio", "hecho agregar 'Stepán sirvió en Kronstadt' --categoria pnj")
            self.assertIn("Hecho clave H2 (pnj)", salida)
            self.assertNotIn("sin hechos clave", salida)

    def test_turno_con_un_cambio_invalido_no_anota_el_hecho(self):
        with repo_temporal():
            antes = disco()
            codigo, _, _ = correr("turno", "--accion", "Jualjin=x", "--resumen", "nada",
                                  "--cambio", "hecho agregar 'Esto no debe quedar'", "--cambio", "vida Nadie -1")
            self.assertEqual(codigo, 1)
            self.assertEqual(disco(), antes)

    def test_cronica_al_cerrar_la_escena(self):
        with repo_temporal():
            numero = estado.cargar("neva")["escena"]["numero"]
            _, salida, _ = correr("escena", "nueva", "--titulo", "Calle arriba", "--cierre", "Escondieron a Stepán y despistaron a la patrulla")
            self.assertNotIn("sin resumen", salida)
            escenas = estado.cargar("neva")["memoria"]["escenas"]
            self.assertEqual(escenas[0]["numero"], numero)
            self.assertEqual(escenas[0]["resumen"], "Escondieron a Stepán y despistaron a la patrulla")
            _, salida, _ = correr("escena", "nueva", "--titulo", "La casa")
            self.assertIn(f"La escena {numero + 1} se cerró sin resumen", salida)
            self.assertEqual(correr("memoria", "escena", str(numero + 1), "Subieron a casa con el paquete")[0], 0)
            self.assertIn(f"Escena {numero + 1} · Calle arriba: Subieron a casa", memoria.markdown(estado.cargar("neva")))
            self.assertEqual(correr("escena", "editar", "--cierre", "no")[0], 1)

    def test_el_mcp_de_juego_puede_usar_memoria_y_mapas(self):
        with repo_temporal():
            for args in (["hecho", "agregar", "Desde el MCP"], ["memoria", "ver"], ["mapa", "zona", "--dibujo", "###\\n#.#\\n###"],
                         ["mundo", "lugar", "Petrogrado", "--x", "0", "--y", "0"]):
                with self.subTest(args=args):
                    ok, texto = mcp.ejecutar(args)
                    self.assertTrue(ok, texto)


class TestZona(unittest.TestCase):
    def test_dibujo_valido_y_errores_legibles(self):
        mapa = mapas.nueva_zona("###\n#.\n###", ["T=mesa"])
        self.assertEqual(mapa["filas"], ["###", "#. ", "###"])
        self.assertEqual(mapa["celda"], 1.5)
        self.assertEqual(mapa["leyenda"], {"#": "muro", ".": "suelo"})
        for dibujo, leyenda, pista in (("#1#", None, "dígitos"), ("#X#", None, "leyenda"), ("." * 27, None, "26"), ("", None, "vacío")):
            with self.subTest(dibujo=dibujo), self.assertRaisesRegex(ValueError, pista):
                mapas.nueva_zona(dibujo, leyenda)
        with self.assertRaisesRegex(ValueError, "fuera del mapa"):
            mapas.validar_celda(mapa, "C2")  # es un espacio
        with self.assertRaisesRegex(ValueError, "fuera del mapa"):
            mapas.validar_celda(mapa, "A9")
        self.assertEqual(mapas.validar_celda(mapa, " b2 "), "B2")
        self.assertEqual(mapas.distancia_casillas("C2", "F4"), 3)  # la diagonal vale una casilla

    def test_fichas_en_la_cuadricula_con_distancias_para_el_narrador(self):
        with repo_temporal():
            self.assertEqual(correr("mapa", "zona", "--dibujo", ZONA, "--leyenda", "T=mesa", "--nombre", "Muelle")[0], 0)
            correr("escena", "posicion", "Jualjin", "junto a la mesa", "--celda", "c2")
            correr("escena", "posicion", "Crisljin", "en la puerta", "--celda", "J3")
            correr("enemigo", "agregar", "Matón", "--plantilla", "maton")
            correr("escena", "posicion", "Matón", "--celda", "F4")
            texto = mapas.zona_texto(estado.cargar("neva"))
            self.assertIn("   2 # . 1 T . . . . . #", texto)
            self.assertIn("   4 # ~ ~ ~ . 3 . . . #", texto)
            self.assertIn("3 Matón (F4, amenaza)", texto)
            self.assertIn("Desde Jualjin: Crisljin 10,5 m · Matón 4,5 m", texto)
            _, salida, _ = correr("turno", "--accion", "Jualjin=mira", "--accion", "Crisljin=mira", "--resumen", "Se miran")
            self.assertIn("Mapa de la zona: Muelle", salida)
            self.assertIn("Stepán no tiene casilla en el mapa de zona", salida)

    def test_casilla_sin_mapa_o_fuera_no_muta(self):
        with repo_temporal():
            antes = disco()
            self.assertEqual(correr("escena", "posicion", "Jualjin", "aquí", "--celda", "B2")[0], 1)
            self.assertEqual(disco(), antes)
            correr("mapa", "zona", "--dibujo", "###\\n#.#\\n###")
            antes = disco()
            codigo, _, errores = correr("escena", "posicion", "Jualjin", "aquí", "--celda", "Z9")
            self.assertEqual(codigo, 1)
            self.assertIn("fuera del mapa", errores)
            self.assertEqual(disco(), antes)

    def test_redibujar_quita_casillas_que_quedan_fuera_y_escena_nueva_limpia(self):
        with repo_temporal():
            correr("mapa", "zona", "--dibujo", ZONA, "--leyenda", "T=mesa")
            correr("escena", "posicion", "Crisljin", "en la puerta", "--celda", "J3")
            _, salida, _ = correr("mapa", "zona", "--dibujo", "#####\\n#...#\\n#####")
            self.assertIn("Quedaron sin casilla (fuera del mapa nuevo): Crisljin", salida)
            self.assertNotIn("celda", next(p for p in estado.cargar("neva")["escena"]["posiciones"] if p["quien"] == "Crisljin"))
            correr("escena", "posicion", "Crisljin", "dentro", "--celda", "B2")
            correr("escena", "nueva", "--titulo", "Misma sala", "--conservar-mapa", "--cierre", "x")
            escena = estado.cargar("neva")["escena"]
            self.assertEqual(escena["mapa"]["filas"][1], "#...#")
            self.assertEqual(escena["posiciones"][-1]["celda"], "B2")
            correr("escena", "nueva", "--titulo", "Otra parte", "--cierre", "y")
            self.assertNotIn("mapa", estado.cargar("neva")["escena"])

    def test_semantica_vision_cobertura_camino_luz_y_areas_srd(self):
        dibujo = (
            "#########\n"
            "#...#...#\n"
            "#.T.=.P.#\n"
            "#.~.....#\n"
            "#########"
        )
        mapa = mapas.nueva_zona(
            dibujo,
            ["T=mesa", "P=pilar de piedra"],
            luz="oscuridad",
        )
        datos = {
            "escena": {
                "mapa": mapa,
                "posiciones": [
                    {"quien": "Jualjin", "celda": "B3"},
                    {"quien": "Aliado", "celda": "C4"},
                    {"quien": "Matón", "celda": "H3"},
                ],
            },
            "personajes": [{"id": "jualjin", "nombre": "Jualjin"}, {"id": "aliado", "nombre": "Aliado"}],
            "enemigos": [{"nombre": "Matón"}],
        }
        # Tabla de línea de visión y cobertura según SRD 5.2.1 (los grados no se suman; gana el mayor):
        casos_linea = [
            # (origen, destino, visible, cobertura, bono)
            ("B2", "D2", True, "ninguna", 0),
            ("B2", "F2", False, "total", None),          # muro '#' en E2 bloquea visión y da cobertura total
            ("B3", "D3", True, "media", 2),              # mesa 'T' en C3 da cobertura media (+2)
            ("D3", "F3", True, "tres-cuartos", 5),       # ventana '=' en E3 bloquea paso pero no visión (3/4, +5)
            ("B3", "F3", True, "tres-cuartos", 5),       # mesa (media) + ventana (3/4) -> no se suman: 3/4 (+5)
            ("B4", "E4", True, "media", 2),              # otra criatura (Aliado en C4) + agua (~): cobertura media (+2)
        ]
        for orig, dest, vis, cob, bono in casos_linea:
            with self.subTest(origen=orig, destino=dest):
                res = mapas.linea_entre(mapa, orig, dest, datos=datos)
                self.assertEqual((res["visible"], res["cobertura"], res["bono_cobertura"]), (vis, cob, bono))

        # Coste de movimiento: ventana E3 bloquea paso; el camino de D3 a F3 rodea por E4 (1 paso normal)
        # y pasar por agua (~ en C4) o mesa (T en C3) cuesta el doble (2 casillas por casilla).
        cam_recto = mapas.camino_movimiento(mapa, "B2", "D2")
        self.assertEqual((cam_recto["alcanzable"], cam_recto["casillas_coste"]), (True, 2))
        cam_agua = mapas.camino_movimiento(mapa, "B4", "D4")
        # Por C4 (~ agua) costaría 3 casillas; rodear en diagonal por C3 (T mesa, difícil) también cuesta 3.
        self.assertEqual(cam_agua["alcanzable"], True)
        cam_bloqueado = mapas.camino_movimiento(mapa, "B2", "E2")  # E2 es muro
        self.assertFalse(cam_bloqueado["alcanzable"])

        # Iluminación: ambiente en oscuridad + foco en B2 (3 m brillante, 3 m penumbra). E2 (muro) proyecta sombra en F2.
        mapas.poner_luz(mapa, "oscuridad", ["B2:3:3:farol"])
        self.assertEqual(mapas.iluminacion_celda(mapa, "B2"), "brillante")
        self.assertEqual(mapas.iluminacion_celda(mapa, "D2"), "brillante")
        self.assertEqual(mapas.iluminacion_celda(mapa, "D4"), "Brillante" if False else "brillante")
        self.assertEqual(mapas.iluminacion_celda(mapa, "F2"), "oscuridad")  # bloqueado por muro E2
        self.assertEqual(mapas.iluminacion_celda(mapa, "F4"), "penumbra")   # a 4 casillas (6 m), con visión libre por fila 4

        # Plantillas de área (SRD 5.2.1): cono, esfera, línea y cubo, recortados por cobertura total (muros).
        casos_area = [
            ("cono", 3.0, "B3", "E", {"C3", "D2", "D3", "D4"}),
            ("linea", 4.5, "B2", "E", {"C2", "D2"}),  # E2 es muro y corta la línea hacia F2
            ("esfera", 1.5, "D2", None, {"C2", "C3", "D2", "D3"}),  # E2 es muro, E3 es ventana (visible)
            ("cubo", 3.0, "B2", "E", {"B2", "B3", "C2", "C3"}),
        ]
        for forma, tam, orig, hacia, esperadas in casos_area:
            with self.subTest(forma=forma, origen=orig):
                area = mapas.area_efecto(mapa, forma, tam, orig, hacia=hacia, datos=datos)
                self.assertTrue(esperadas.issubset(set(area["casillas"])), f"{area['casillas']} no contiene {esperadas}")
                self.assertNotIn("F2", area["casillas"])  # detrás del muro E2

    def test_cli_y_mcp_consultas_y_errores_sin_mutar(self):
        with repo_temporal():
            correr("mapa", "zona", "--dibujo", ZONA, "--leyenda", "T=mesa [dificil, cobertura=tres-cuartos]", "--luz", "penumbra")
            correr("escena", "posicion", "Jualjin", "mesa", "--celda", "C2")
            correr("escena", "posicion", "Crisljin", "puerta", "--celda", "J3")
            antes = disco()
            cod, sal, _ = correr("mapa", "linea", "Jualjin", "Crisljin")
            self.assertEqual(cod, 0)
            self.assertIn("tres-cuartos (+5", sal)
            self.assertEqual(disco(), antes)  # consulta no muta ni escribe evento
            cod, sal, _ = correr("mapa", "area", "cono", "4.5", "--origen", "Jualjin", "--hacia", "E")
            self.assertEqual(cod, 0)
            self.assertIn("D2", sal)
            self.assertEqual(disco(), antes)
            # Errores legibles sin mutar
            for args in (
                ("mapa", "terreno", "Z", "--dificil"),
                ("mapa", "luz", "--foco", "Z9:6:6"),
                ("mapa", "linea", "Nadie", "C2"),
                ("mapa", "area", "cono", "4.5", "--origen", "C2"),  # falta --hacia
                ("turno", "--accion", "Jualjin=mira", "--resumen", "x", "--cambio", "mapa linea C2 J3"),
            ):
                with self.subTest(args=args):
                    c, _, err = correr(*args)
                    self.assertEqual(c, 1)
                    self.assertTrue(err.startswith("error:"))
            self.assertEqual(disco(), antes)

    def test_generar_zona_determinista_por_semilla_y_retocable(self):
        for tipo in ("mazmorra", "taberna", "interior", "calle", "plaza", "bosque", "claro", "cueva", "puente"):
            with self.subTest(tipo=tipo):
                m1 = mapas.generar_zona(tipo, semilla=42, ancho=14, alto=9, densidad="normal", nombre=f"Prueba {tipo}")
                m2 = mapas.generar_zona(tipo, semilla=42, ancho=14, alto=9, densidad="normal", nombre=f"Prueba {tipo}")
                m_otro = mapas.generar_zona(tipo, semilla=99, ancho=14, alto=9, densidad="alta", nombre=f"Prueba {tipo}")
                self.assertEqual(m1["filas"], m2["filas"])
                self.assertEqual(m1["leyenda"], m2["leyenda"])
                self.assertEqual((len(m1["filas"][0]), len(m1["filas"])), (14, 9))
                self.assertNotEqual((m1["filas"], m1["generador"]), (m_otro["filas"], m_otro["generador"]))
                self.assertTrue(any("." in fila for fila in m1["filas"]))

        with repo_temporal():
            cod, sal, _ = correr("mapa", "generar", "taberna", "--semilla", "7", "--ancho", "12", "--alto", "8", "--nombre", "El Grifo")
            self.assertEqual(cod, 0)
            self.assertIn("Mapa de la zona: El Grifo", sal)
            generado = estado.cargar("neva")["escena"]["mapa"]
            self.assertEqual(generado["generador"]["semilla"], 7)
            filas_editadas = list(generado["filas"])
            fila_central = list(filas_editadas[4])
            fila_central[5] = "."
            filas_editadas[4] = "".join(fila_central)
            self.assertEqual(correr("mapa", "zona", "--dibujo", "\n".join(filas_editadas))[0], 0)
            antes = disco()
            for args in (
                ("mapa", "generar", "castillo-espacial"),
                ("mapa", "generar", "mazmorra", "--ancho", "30"),
                ("mapa", "generar", "mazmorra", "--alto", "3"),
            ):
                with self.subTest(args=args):
                    self.assertEqual(correr(*args)[0], 1)
            self.assertEqual(disco(), antes)


class TestMundo(unittest.TestCase):
    def test_lugares_rutas_y_donde_estan(self):
        with repo_temporal():
            self.assertEqual(correr("mundo", "lugar", "Kronstadt", "--tipo", "puerto")[0], 1)  # nuevo sin coordenadas
            correr("mundo", "ajustar", "--nombre", "Golfo de Finlandia")
            correr("mundo", "lugar", "Petrogrado", "--x", "0", "--y", "0", "--tipo", "ciudad")
            correr("mundo", "lugar", "Kronstadt", "--x", "-29", "--y", "3", "--tipo", "puerto")
            correr("mundo", "lugar", "Petrogrado", "--nota", "Capital revuelta")  # editar no pide coordenadas
            correr("mundo", "ruta", "Petrogrado", "Kronstadt", "--tipo", "barco", "--tiempo", "3 h")
            self.assertEqual(correr("mundo", "aqui", "petro")[0], 0)  # prefijo único
            datos = estado.cargar("neva")
            self.assertEqual(datos["mundo"]["actual"], "petrogrado")
            self.assertEqual(len(datos["mundo"]["lugares"]), 2)
            texto = mapas.mundo_texto(datos)
            self.assertIn("Están en: Petrogrado", texto)
            self.assertIn("Kronstadt 29,2 km en línea recta (ruta: barco, 3 h)", texto)
            self.assertIn("## Mundo", informes.resumen(datos))
            correr("mundo", "quitar", "Petrogrado")
            mundo = estado.cargar("neva")["mundo"]
            self.assertEqual((mundo["rutas"], "actual" in mundo), ([], False))

    def test_regiones_trazos_jerarquia_viaje_srd_y_generador_determinista(self):
        with repo_temporal():
            correr("mundo", "lugar", "Valdris", "--x", "0", "--y", "0", "--tipo", "pueblo")
            correr("mundo", "lugar", "Aethermark", "--x", "30", "--y", "40", "--tipo", "capital")
            correr("mundo", "lugar", "Puente de los Votos", "--x", "-0.6", "--y", "0.3", "--tipo", "edificio", "--en", "Valdris")
            correr("mundo", "region", "Bosque Gris", "--bioma", "bosque", "--puntos", "-10,5 10,15 18,-5 -8,-6", "--nota", "Niebla")
            correr("mundo", "trazo", "Río Lis", "--tipo", "rio", "--puntos", "-10,0 0,0 10,0")
            correr("mundo", "ruta", "Valdris", "Aethermark", "--tipo", "camino", "--trazo", "0,0 30,0 30,40", "--ritmo", "normal")
            correr("mundo", "aqui", "Puente de los Votos")
            datos = estado.cargar("neva")
            m = datos["mundo"]
            # Ir a un lugar hijo marca visitado al hijo y a su lugar padre:
            por_id = {l["id"]: l for l in m["lugares"]}
            self.assertTrue(por_id["puente-de-los-votos"]["visitado"] and por_id["valdris"]["visitado"])
            self.assertEqual(por_id["puente-de-los-votos"]["en"], "valdris")
            self.assertEqual(m["trazos"][0]["longitud"], 20.0)
            # La ruta con trazo 0,0 -> 30,0 -> 30,40 mide 70 km (1 día y 7 h a ritmo normal de 38 km/día, 4,8 km/h):
            ruta = m["rutas"][0]
            self.assertEqual(ruta["distancia_km"], 70.0)
            self.assertIn("1 día y 7 h a pie (normal)", ruta["tiempo"])
            # Consulta de viaje (sin mutar):
            antes = disco()
            cod, sal, _ = correr("mundo", "viaje", "Valdris", "Aethermark")
            self.assertEqual(cod, 0)
            self.assertIn("70 km", sal)
            self.assertIn("Ritmo rapido (6,4 km/h, 48 km/día)", sal)
            self.assertIn("Ritmo normal (4,8 km/h, 38 km/día)", sal)
            self.assertIn("Ritmo lento (3,2 km/h, 29 km/día)", sal)
            self.assertEqual(disco(), antes)

            # Generador determinista de mundo por semilla:
            d1, d2 = {}, {}
            mapas.generar_mundo(d1, semilla=123, bioma="montana", lugares_n=4)
            mapas.generar_mundo(d2, semilla=123, bioma="montana", lugares_n=4)
            self.assertEqual(d1["mundo"], d2["mundo"])

            # Errores sin mutar:
            antes = disco()
            for args in (
                ("mundo", "region", "Mal", "--bioma", "bosque", "--puntos", "0,0 1,1"),  # menos de 3 vértices
                ("mundo", "trazo", "Corto", "--puntos", "0,0"),                          # menos de 2 puntos
                ("mundo", "lugar", "Valdris", "--en", "Valdris"),                        # ciclo consigo mismo
                ("mundo", "viaje", "Valdris", "Narnia"),                                 # lugar inexistente
            ):
                with self.subTest(args=args):
                    self.assertEqual(correr(*args)[0], 1)
            self.assertEqual(disco(), antes)

    def test_catalogo_mapas_prehechos_uvtt_watabou_azgaar_y_seguridad_mcp(self):
        with repo_temporal():
            cod, sal, _ = correr("mapa", "catalogo")
            self.assertEqual(cod, 0)
            self.assertIn("posada-grifo-dorado", sal)
            self.assertIn("cripta-del-pacto", sal)
            self.assertIn("valle-de-valdris", sal)

            # Cargar un .dd2vtt del catálogo extrae el PNG de fondo, muros, puertas y luces:
            self.assertEqual(correr("mapa", "cargar", "posada-grifo-dorado")[0], 0)
            mapa_uvtt = estado.cargar("neva")["escena"]["mapa"]
            self.assertEqual(mapa_uvtt["origen"]["licencia"], "CC0-1.0")
            self.assertTrue(mapa_uvtt.get("fondo", "").endswith(".png"))
            self.assertTrue((estado.dir_partida("neva") / "imagenes" / mapa_uvtt["fondo"]).is_file())
            self.assertTrue(len(mapa_uvtt.get("luces") or []) >= 2)

            # Cargar un JSON de Watabou One Page Dungeon del catálogo:
            self.assertEqual(correr("mapa", "cargar", "cripta-del-pacto")[0], 0)
            mapa_wat = estado.cargar("neva")["escena"]["mapa"]
            self.assertIn("P", mapa_wat["leyenda"])
            self.assertIn("~", mapa_wat["leyenda"])
            self.assertTrue(mapa_wat.get("notas_mapa"))

            # Cargar un mapa de mundo desde el catálogo (compatible con Azgaar/GeoJSON):
            self.assertEqual(correr("mapa", "cargar", "valle-de-valdris")[0], 0)
            mundo_cargado = estado.cargar("neva")["mundo"]
            self.assertTrue(len(mundo_cargado.get("regiones") or []) >= 3)
            self.assertTrue(len(mundo_cargado.get("trazos") or []) >= 1)
            self.assertTrue(len(mundo_cargado.get("lugares") or []) >= 5)

            # El MCP permite `mapa catalogo` y `mapa cargar`, pero rechaza `mapa importar` y `mundo importar` (rutas externas):
            ok_cat, _ = mcp.ejecutar(["mapa", "catalogo"])
            ok_car, _ = mcp.ejecutar(["mapa", "cargar", "puente-de-los-votos"])
            self.assertTrue(ok_cat and ok_car)
            for prohibido in (
                ["mapa", "importar", "/etc/passwd"],
                ["mundo", "importar", "/etc/passwd"],
                ["turno", "--resumen", "x", "--cambio", "mapa importar /etc/passwd"],
            ):
                with self.subTest(prohibido=prohibido):
                    ok, msg = mcp.ejecutar(prohibido)
                    self.assertFalse(ok, msg)
                    self.assertIn("CLI", msg)


    def test_turno_con_escena_nueva_conserva_cuadricula_y_actualiza_mundo(self):
        with repo_temporal():
            correr("mapa", "cargar", "valle-de-valdris")
            correr("mundo", "aqui", "Puente de los Votos")
            correr("mapa", "cargar", "puente-de-los-votos")
            correr("escena", "posicion", "Jualjin", "en el puente", "--celda", "F4")
            correr("escena", "posicion", "Crisljin", "en el puente", "--celda", "G4")

            # El narrador cambia de escena en `turno` sin pasar `mapa` ni `escena posicion`:
            # `turno` carga el mapa del catálogo que coincide con el lugar ("Posada El Grifo Dorado"),
            # mueve `mundo.aqui` y asigna casilla a los personajes.
            cod, _, err = correr(
                "turno",
                "--accion", "Jualjin=vamos a la posada",
                "--accion", "Crisljin=lo sigo",
                "--resumen", "Vuelven a la posada El Grifo Dorado.",
                "--cambio", 'escena nueva --titulo "Noche en la posada" --lugar "Posada El Grifo Dorado, segundo piso" --hora "Noche" --cierre "Dejaron el puente"',
            )
            self.assertEqual(cod, 0, err)
            datos = estado.cargar("neva")
            self.assertEqual(datos["mundo"]["actual"], "posada-el-grifo-dorado")
            self.assertIn("mapa", datos["escena"])
            self.assertEqual(datos["escena"]["mapa"]["origen"]["id"], "posada-grifo-dorado")
            celdas = {p["quien"]: p.get("celda") for p in datos["escena"]["posiciones"]}
            self.assertTrue(celdas.get("Jualjin"))
            self.assertTrue(celdas.get("Crisljin"))


if __name__ == "__main__":
    unittest.main()
