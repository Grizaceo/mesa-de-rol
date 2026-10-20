import json
import threading
import unittest
import urllib.error
import urllib.request

from mesa import cli, estado, mapas, servidor

from apoyo import repo_temporal


def pet(url, cuerpo=None):
    """POST mínimo, para comprobar el método de un endpoint."""
    peticion = urllib.request.Request(url, data=cuerpo, method="POST")
    try:
        with urllib.request.urlopen(peticion, timeout=5) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        with e:
            return e.code, e.read()


class TestServidor(unittest.TestCase):
    def setUp(self):
        self._ctx = repo_temporal()
        self.raiz = self._ctx.__enter__()
        self.srv = servidor.crear("127.0.0.1", 0)
        self.base = f"http://127.0.0.1:{self.srv.server_address[1]}"
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()
        self._ctx.__exit__(None, None, None)

    def get(self, ruta):
        try:
            with urllib.request.urlopen(self.base + ruta, timeout=5) as r:
                return r.status, r.headers.get_content_type(), r.read()
        except urllib.error.HTTPError as e:
            with e:
                return e.code, e.headers.get_content_type(), e.read()

    def test_visor_y_api(self):
        self.assertEqual(self.get("/")[0], 200)
        codigo, tipo, cuerpo = self.get("/api/estado?p=neva")
        self.assertEqual((codigo, tipo), (200, "application/json"))
        self.assertEqual(json.loads(cuerpo)["slug"], "neva")
        eventos = json.loads(self.get("/api/eventos?p=neva&desde=30")[2])["eventos"]
        self.assertTrue(all(e["seq"] > 30 for e in eventos))
        self.assertEqual(json.loads(self.get("/api/partidas")[2])["activa"], "neva")

    def test_no_sirve_secretos_ni_escapa_de_carpetas(self):
        for ruta in (
            "/media/neva/..%2Fdirector.md",
            "/media/neva/..%2F..%2F..%2Fetc%2Fpasswd",
            "/visor/..%2Fpartidas%2Fneva%2Fdirector.md",
            "/partidas/neva/director.md",
        ):
            with self.subTest(ruta=ruta):
                self.assertEqual(self.get(ruta)[0], 404)
        self.assertEqual(self.get("/api/estado?p=..%2Fetc")[0], 400)

    def test_un_conflicto_responde_503_json(self):
        estado.ruta_diario("neva").write_text("{esto no es json", encoding="utf-8")
        codigo, tipo, cuerpo = self.get("/api/estado?p=neva")
        self.assertEqual((codigo, tipo), (503, "application/json"))
        self.assertIn("diario", json.loads(cuerpo)["error"])


class TestProyeccionDeZona(unittest.TestCase):
    """La zona la resuelve el motor: el visor pinta, no vuelve a decidir las reglas."""

    def setUp(self):
        self._ctx = repo_temporal()
        self.raiz = self._ctx.__enter__()
        self.srv = servidor.crear("127.0.0.1", 0)
        self.base = f"http://127.0.0.1:{self.srv.server_address[1]}"
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        cli.main(["usar", "neva"])
        datos = estado.cargar("neva")
        datos["escena"]["mapa"] = mapas.generar_zona("mazmorra", semilla=5, ancho=12, alto=9)
        datos["escena"]["posiciones"] = [
            {"quien": "Bruna", "celda": "F4"},
            {"quien": "Bandido", "celda": "B2"},
        ]
        estado.guardar("neva", datos)

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()
        self._ctx.__exit__(None, None, None)

    def zona(self, consulta=""):
        with urllib.request.urlopen(self.base + f"/api/zona?p=neva{consulta}", timeout=5) as r:
            self.assertEqual(r.status, 200)
            return json.loads(r.read())

    def test_una_zona_sin_mapa_no_rompe(self):
        datos = estado.cargar("neva")
        datos["escena"].pop("mapa", None)
        estado.guardar("neva", datos)
        p = self.zona()
        self.assertFalse(p["hay_mapa"])
        for clave in ("terrenos", "luz", "fichas", "focos", "linea", "camino", "area"):
            self.assertIn(clave, p)

    def test_los_terrenos_llegan_por_caracter_con_su_semantica(self):
        p = self.zona()
        self.assertTrue(p["hay_mapa"])
        # Un registro por carácter del dibujo, no uno por casilla.
        mapa = estado.cargar("neva")["escena"]["mapa"]
        self.assertEqual(len(p["terrenos"]), len({c for f in mapa["filas"] for c in f if c != " "}))
        muro = next(t for t in p["terrenos"] if t["caracter"] == "#")
        self.assertTrue(muro["bloquea_paso"])
        self.assertTrue(muro["bloquea_vision"])
        self.assertEqual(muro["cobertura"], "total")
        self.assertEqual(muro["clase"], "solido")
        for t in p["terrenos"]:
            # Lo que llega es lo mismo que decide el motor: una sola fuente de verdad.
            sem = mapas.semantica_terreno(mapa, t["caracter"])
            self.assertEqual(t["bloquea_paso"], bool(sem["bloquea_paso"]))
            self.assertEqual(t["cobertura"], sem["cobertura"])
            self.assertEqual(t["dificil"], bool(sem["dificil"]))

    def test_la_luz_solo_travela_donde_no_es_la_del_ambiente(self):
        p = self.zona()
        mapa = estado.cargar("neva")["escena"]["mapa"]
        completa = mapas.mapa_iluminacion(mapa)
        # Solo manda lo que difiere del ambiente; lo demás lo deduce el visor.
        self.assertEqual(
            {x["celda"] for x in p["luz"]},
            {c for c, n in completa.items() if n != p["luz_base"]},
        )
        for x in p["luz"]:
            self.assertEqual(x["nivel"], completa[x["celda"]])

    def test_la_medicion_devuelve_linea_camino_y_area_del_motor(self):
        p = self.zona("&origen=F4&destino=B2")
        mapa = estado.cargar("neva")["escena"]["mapa"]
        lin = mapas.linea_entre(mapa, "F4", "B2")
        cam = mapas.camino_movimiento(mapa, "F4", "B2")
        self.assertEqual(p["linea"]["visible"], lin["visible"])
        self.assertEqual(p["linea"]["cobertura"], lin["cobertura"])
        self.assertEqual(p["linea"]["bono"], lin["bono_cobertura"])
        self.assertEqual(p["camino"]["alcanzable"], cam["alcanzable"])
        self.assertEqual(p["camino"]["casillas_coste"], cam["casillas_coste"])
        self.assertEqual(p["camino"]["camino"], cam["camino"])
        self.assertIsNone(p["area"], "sin plantilla no hay área")
        con = self.zona("&origen=F4&destino=B2&forma=cono&tamano=6")
        self.assertEqual(con["area"]["forma"], "cono")
        self.assertIn("Bruna", con["fichas"][0]["quien"])

    def test_una_esquina_es_dos_casillas_obstaculo(self):
        p = self.zona("&origen=F4&destino=B2")
        mapa = estado.cargar("neva")["escena"]["mapa"]
        lin = mapas.linea_entre(mapa, "F4", "B2")
        for celda in p["linea"]["obstaculos"]:
            self.assertRegex(celda, r"^[A-Z]\d{1,2}$", f"{celda} no es una casilla")

    def test_un_origen_que_no_existe_no_rompe_el_endpoint(self):
        p = self.zona("&origen=ZZ99&destino=B2")
        self.assertTrue(p["hay_mapa"])
        self.assertIsNone(p["linea"])

    def test_solo_lectura(self):
        # `/api/zona` solo existe en GET: por POST no se acepta nada, así que la
        # proyección no es una vía de escritura desde el navegador.
        codigo, _ = pet(self.base + "/api/zona?p=neva", b'{"origen":"F4"}')
        self.assertNotEqual(codigo, 200)


class TestMemoriaDesdeElVisor(unittest.TestCase):
    """La única escritura del visor: la memoria, solo desde este equipo y con el token de la ejecución."""

    def setUp(self):
        self._ctx = repo_temporal()
        self.raiz = self._ctx.__enter__()
        self.srv = servidor.crear("127.0.0.1", 0)
        self.puerto = self.srv.server_address[1]
        self.base = f"http://127.0.0.1:{self.puerto}"
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.token = self.pedir("GET", "/api/visor")[1]["token"]

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()
        self._ctx.__exit__(None, None, None)

    def pedir(self, metodo, ruta, cuerpo=None, cabeceras=None):
        datos = cuerpo if isinstance(cuerpo, bytes) or cuerpo is None else json.dumps(cuerpo).encode()
        peticion = urllib.request.Request(self.base + ruta, data=datos, method=metodo, headers=cabeceras or {})
        try:
            with urllib.request.urlopen(peticion, timeout=5) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            with e:
                return e.code, json.loads(e.read())

    def post(self, cuerpo, cambios=None):
        """POST como el visor; `cambios` sustituye cabeceras (None la quita)."""
        cabeceras = {"Content-Type": "application/json", "X-Mesa-Token": self.token, **(cambios or {})}
        return self.pedir("POST", "/api/memoria?p=neva", cuerpo, {k: v for k, v in cabeceras.items() if v is not None})

    def disco(self):
        return (estado.dir_partida("neva") / "partida.json").read_text(encoding="utf-8")

    def test_el_jugador_agrega_y_corrige_con_su_evento(self):
        codigo, r = self.post({"accion": "agregar", "texto": "Belov es el sargento", "categoria": "pnj", "fijado": True})
        self.assertEqual(codigo, 200, r)
        self.assertEqual(r["memoria"]["hechos"][0]["autor"], "jugador")
        codigo, r = self.post({"accion": "editar", "id": "H1", "texto": "Belov es el sargento del Puente de Hierro"})
        self.assertEqual(codigo, 200, r)
        codigo, r = self.post({"accion": "hasta-ahora", "texto": "Esconden a Stepán."}, {"Origin": self.base})
        self.assertEqual(codigo, 200, r)
        # detrás de un proxy local el puerto del origen cambia: sigue siendo este equipo
        codigo, r = self.post({"accion": "soltar", "id": "H1"}, {"Origin": "http://localhost:44165"})
        self.assertEqual(codigo, 200, r)
        self.assertEqual(self.post({"accion": "fijar", "id": "H1"})[0], 200)
        hecho = estado.cargar("neva")["memoria"]["hechos"][0]
        self.assertEqual((hecho["texto"], hecho["fijado"], hecho["editado_por"]), ("Belov es el sargento del Puente de Hierro", True, "jugador"))
        eventos = [e for e in estado.leer_eventos("neva") if e["tipo"] in ("hecho", "memoria")]
        self.assertTrue(all(e["autor"] == "jugador" and e["via"] == "visor" for e in eventos))
        uso = self.pedir("GET", "/api/estado?p=neva")[1]["memoria_uso"]
        self.assertEqual(uso["en_contexto"], ["H1"])

    def test_rechaza_lo_que_no_viene_del_visor_local_sin_mutar(self):
        antes = self.disco()
        casos = {
            "sin token": (403, {"X-Mesa-Token": None}),
            "token falso": (403, {"X-Mesa-Token": "otro"}),
            "host ajeno (DNS rebinding)": (403, {"Host": f"malo.example:{self.puerto}"}),
            "origen ajeno": (403, {"Origin": "http://malo.example"}),
            "origen que imita a localhost": (403, {"Origin": "http://127.0.0.1.malo.example"}),
            "origen null": (403, {"Origin": "null"}),
            "no es JSON": (400, {"Content-Type": "text/plain"}),
        }
        for nombre, (esperado, cabeceras) in casos.items():
            with self.subTest(nombre):
                codigo, r = self.post({"accion": "agregar", "texto": "intruso"}, cabeceras)
                self.assertEqual(codigo, esperado, r)
        for cuerpo in ({"accion": "borrar-todo"}, {"accion": "agregar", "texto": 3}, {"accion": "editar", "id": "H9", "texto": "x"}, b"[1]", b"{roto"):
            with self.subTest(cuerpo=cuerpo):
                self.assertEqual(self.post(cuerpo)[0], 400)
        self.assertEqual(self.pedir("POST", "/api/estado?p=neva", {"x": 1}, {"Content-Type": "application/json"})[0], 404)
        self.assertEqual(self.disco(), antes)

    def test_el_token_solo_se_entrega_con_host_local(self):
        codigo, r = self.pedir("GET", "/api/visor", cabeceras={"Host": f"malo.example:{self.puerto}"})
        self.assertEqual((codigo, r["escritura"], r["token"]), (200, False, None))
        self.assertTrue(self.pedir("GET", "/api/visor", cabeceras={"Host": f"localhost:{self.puerto}"})[1]["escritura"])
        otro = servidor.crear("127.0.0.1", 0)  # cada ejecución trae su token
        self.addCleanup(otro.server_close)
        self.assertNotEqual(otro.token, self.token)


if __name__ == "__main__":
    unittest.main()
