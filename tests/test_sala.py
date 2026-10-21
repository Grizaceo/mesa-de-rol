"""La sala del visor: campaña segura, lo que ven los jugadores y lo que cada uno puede hacer con su ficha."""

import io
import json
import threading
import unittest
import urllib.error
import urllib.request
from contextlib import redirect_stderr, redirect_stdout

from mesa import chat, cli, estado, mapas, reglas_2024, servidor

from apoyo import dados_fijos, repo_temporal

CLAVE = "clave-de-sala-de-prueba"
REAL = "Centinela del Pacto"


def correr(*args) -> tuple[int, str]:
    salida = io.StringIO()
    with redirect_stdout(salida), redirect_stderr(io.StringIO()):
        codigo = cli.main(list(args))
    return codigo, salida.getvalue()


class Sala(unittest.TestCase):
    def setUp(self):
        self._ctx = repo_temporal()
        self.raiz = self._ctx.__enter__()
        self.srv = servidor.crear("127.0.0.1", 0, None, None, clave_sala=CLAVE)
        self.base = f"http://127.0.0.1:{self.srv.server_address[1]}"
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.host = {"Content-Type": "application/json", "X-Mesa-Token": self.pedir("GET", "/api/visor")[1]["token"]}

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()
        self._ctx.__exit__(None, None, None)

    def pedir(self, metodo, ruta, cuerpo=None, cabeceras=None, crudo=None):
        datos = crudo.encode() if crudo is not None else (None if cuerpo is None else json.dumps(cuerpo).encode())
        peticion = urllib.request.Request(self.base + ruta, data=datos, method=metodo, headers=cabeceras or {})
        try:
            with urllib.request.urlopen(peticion, timeout=10) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            with e:
                return e.code, json.loads(e.read())

    def campana(self, titulo="Corsarios de Prueba") -> str:
        codigo, r = self.pedir("POST", "/api/campana", {
            "modo": "nueva", "titulo": titulo, "personajes": "Kael (Guerrero), Lyra (Pícara)",
            "lugar": "Puerto Tormenta", "tono": "fantasía, piratas", "iniciar_chat": False,
        }, self.host)
        self.assertEqual(codigo, 200, r)
        return r["slug"]

    def invitado(self, slug, pj):
        remoto = {"Host": "tunel.trycloudflare.com", "X-Mesa-Sala": CLAVE}
        token = self.pedir("GET", "/api/visor", cabeceras=remoto)[1]["token"]
        cab = {**remoto, "Content-Type": "application/json", "X-Mesa-Token": token, "Origin": "https://tunel.trycloudflare.com"}
        codigo, r = self.pedir("POST", f"/api/reclamar?p={slug}", {"pj": pj}, cab)
        self.assertEqual(codigo, 200, r)
        return {**cab, "X-Mesa-Reclamo": r["reclamo"]}

    def tirar(self, slug, cuerpo, cab, crudo=None):
        return self.pedir("POST", f"/api/tirar?p={slug}", cuerpo, cab, crudo=crudo)

    def ficha(self, slug, nombre):
        return next(p for p in estado.cargar(slug)["personajes"] if p["nombre"] == nombre)

    def enemigo_oculto(self, slug):
        codigo, salida = correr("-p", slug, "enemigo", "agregar", REAL, "--vida", "14", "--defensa", "15", "--ataque", "4",
                                "--dano", "1d10+2", "--desconocido")
        self.assertEqual(codigo, 0, salida)


class TestCampanaSegura(Sala):
    def test_nueva_no_cambia_la_partida_activa_y_crea_fichas_por_clase(self):
        activa = (self.raiz / ".mesa-activa").read_text(encoding="utf-8")
        slug = self.campana()
        self.assertEqual((self.raiz / ".mesa-activa").read_text(encoding="utf-8"), activa, "el visor no cambia la partida del narrador")
        self.assertEqual(self.campana(), f"{slug}-2", "una partida existente no se pisa")
        kael, lyra = self.ficha(slug, "Kael"), self.ficha(slug, "Lyra")
        self.assertEqual((kael["dados_golpe"]["dado"], kael["vida"], kael["ca"]), ("d10", 12, 11))
        self.assertEqual(kael["competencias"]["salvaciones"], ["fuerza", "constitucion"])
        self.assertEqual((lyra["dados_golpe"]["dado"], lyra["atributos"]["destreza"], lyra["vida"]), ("d8", 15, 10))
        biblia = (estado.dir_partida(slug) / "biblia.md").read_text(encoding="utf-8")
        self.assertTrue(biblia.startswith("<!-- generada por el visor · "))

    def test_configurar_suma_pj_sin_tocar_los_existentes_ni_la_biblia_escrita_a_mano(self):
        slug = self.campana()
        kael = self.ficha(slug, "Kael")
        codigo, r = self.pedir("POST", f"/api/campana?p={slug}", {
            "modo": "configurar", "personajes": "Kael (Mago), Mira (Maga)", "lugar": "Isla Bruma",
        }, self.host)
        self.assertEqual(codigo, 200, r)
        self.assertEqual(self.ficha(slug, "Kael"), kael)
        self.assertEqual(self.ficha(slug, "Mira")["dados_golpe"]["dado"], "d6")
        self.assertTrue(any("Kael ya está" in a for a in r["avisos"]))
        ruta = estado.dir_partida(slug) / "biblia.md"
        self.assertIn("Isla Bruma", ruta.read_text(encoding="utf-8"), "la que generó el visor y nadie tocó se rehace")
        ruta.write_text(ruta.read_text(encoding="utf-8") + "\nNotas del narrador a mano.\n", encoding="utf-8")
        codigo, r = self.pedir("POST", f"/api/campana?p={slug}", {"modo": "configurar", "lugar": "Otra"}, self.host)
        self.assertEqual(codigo, 200, r)
        self.assertIn("Notas del narrador a mano.", ruta.read_text(encoding="utf-8"))
        self.assertTrue(any("biblia.md" in a for a in r["avisos"]))

    def test_configurar_una_partida_legacy_no_toca_sus_pj_ni_su_biblia(self):
        antes = estado.cargar("neva")["personajes"]
        biblia = (estado.dir_partida("neva") / "biblia.md").read_text(encoding="utf-8")
        codigo, r = self.pedir("POST", "/api/campana?p=neva", {"modo": "configurar", "personajes": "Crisljin (Abogado)"}, self.host)
        self.assertEqual(codigo, 200, r)
        self.assertEqual(estado.cargar("neva")["personajes"], antes)
        self.assertEqual((estado.dir_partida("neva") / "biblia.md").read_text(encoding="utf-8"), biblia)
        self.assertTrue(any("d20-simple" in a for a in r["avisos"]))
        self.assertEqual(self.pedir("POST", "/api/campana?p=neva", {"modo": "crear"}, self.host)[0], 400)


class TestLoQueVenLosJugadores(Sala):
    def test_un_desconocido_no_deja_ver_ni_su_nombre_ni_sus_estadisticas(self):
        slug = self.campana()
        self.enemigo_oculto(slug)
        datos = estado.cargar(slug)
        datos["escena"]["mapa"] = mapas.generar_zona("mazmorra", semilla=5, ancho=12, alto=9)
        datos["escena"]["posiciones"] = [{"quien": "Kael", "celda": "F4"}, {"quien": REAL, "celda": "B2", "donde": f"{REAL} tras la reja"}]
        estado.guardar(slug, datos)
        chat_ruta = estado.dir_partida(slug) / "chat.jsonl"
        chat_ruta.write_text(json.dumps({"seq": 1, "ts": estado.ahora(), "rol": "narrador", "texto": f"El {REAL} se mueve.",
                                         "partes": [{"tipo": "texto", "texto": f"El {REAL} se mueve."}]}) + "\n", encoding="utf-8")

        publico = self.pedir("GET", f"/api/estado?p={slug}", cabeceras=self.host)[1]
        figura = publico["enemigos"][0]
        self.assertEqual(figura["nombre"], "Figura desconocida")
        self.assertEqual(figura["estado_aparente"], "ileso")
        for campo in ("vida", "ca", "defensa", "ataque", "dano"):
            self.assertNotIn(campo, figura)
        self.assertIn("atributos", publico["personajes"][0], "los PJ que juega una persona se ven enteros")
        for ruta in (f"/api/estado?p={slug}", f"/api/eventos?p={slug}", f"/api/chat?p={slug}",
                     f"/api/zona?p={slug}&origen=Kael&destino=Figura%20desconocida"):
            with self.subTest(ruta=ruta):
                codigo, cuerpo = self.pedir("GET", ruta, cabeceras=self.host)
                self.assertEqual(codigo, 200, cuerpo)
                self.assertNotIn("Centinela", json.dumps(cuerpo, ensure_ascii=False))
        zona = self.pedir("GET", f"/api/zona?p={slug}&origen=Kael&destino=Figura%20desconocida", cabeceras=self.host)[1]
        self.assertEqual(next(f for f in zona["fichas"] if f["quien"] == "Figura desconocida")["marca"], "?")
        self.assertIsNotNone(zona["linea"], "el alias se resuelve para medir")

        kael = self.invitado(slug, "Kael")
        self.assertEqual(self.tirar(slug, {"accion": "ataque"}, kael)[0], 400, "sin objetivo no se elige uno solo")
        codigo, r = self.tirar(slug, {"accion": "ataque", "objetivo": "Centinela"}, kael)
        self.assertEqual(codigo, 400)
        self.assertNotIn(REAL, r["error"], "el nombre real no se resuelve ni se lista")
        with dados_fijos(19, 3, 4):
            codigo, r = self.tirar(slug, {"accion": "ataque", "objetivo": "Figura desconocida"}, kael)
        self.assertEqual(codigo, 200, r)
        self.assertEqual((r["evento"]["objetivo"], r["evento"]["cd"]), ("Figura desconocida", None))
        self.assertNotIn("vida", r["evento"]["dano"])
        self.assertNotIn("/14", r["texto"])
        self.assertEqual(estado.cargar(slug)["enemigos"][0]["vida"], 14 - (3 + 2), "1d8 del arma + FUE, contra la vida real")

        correr("-p", slug, "enemigo", "quitar", REAL)
        self.assertNotIn("Centinela", json.dumps(self.pedir("GET", f"/api/eventos?p={slug}", cabeceras=self.host)[1], ensure_ascii=False),
                         "quien sale sin revelarse sigue oculto en la bitácora")
        self.assertNotIn("identidades_ocultas", self.pedir("GET", f"/api/estado?p={slug}", cabeceras=self.host)[1])
        correr("-p", slug, "enemigo", "revelar", REAL)
        self.assertIn(REAL, json.dumps(self.pedir("GET", f"/api/eventos?p={slug}", cabeceras=self.host)[1], ensure_ascii=False))

    def test_un_pj_que_pilota_el_narrador_se_ve_por_el_lore_y_no_se_reclama(self):
        slug = self.campana()
        self.assertEqual(correr("-p", slug, "piloto", "Lyra", "narrador")[0], 0)
        lyra = next(p for p in self.pedir("GET", f"/api/estado?p={slug}", cabeceras=self.host)[1]["personajes"] if p["nombre"] == "Lyra")
        self.assertNotIn("atributos", lyra)
        self.assertEqual(lyra["estado_aparente"], "ileso")
        remoto = {"Host": "tunel.trycloudflare.com", "X-Mesa-Sala": CLAVE}
        token = self.pedir("GET", "/api/visor", cabeceras=remoto)[1]["token"]
        cab = {**remoto, "Content-Type": "application/json", "X-Mesa-Token": token}
        self.assertEqual(self.pedir("POST", f"/api/reclamar?p={slug}", {"pj": "Lyra"}, cab)[0], 400)


class TestTirarDesdeLaSala(Sala):
    def test_cada_uno_actua_con_su_pj_y_nunca_con_un_enemigo(self):
        slug = self.campana()
        self.enemigo_oculto(slug)
        kael = self.invitado(slug, "Kael")
        codigo, r = self.tirar(slug, {"accion": "prueba", "atributo": "atletismo"}, kael)
        self.assertEqual((codigo, r["evento"]["quien"]), (200, "Kael"))
        self.assertEqual(self.tirar(slug, {"accion": "vida", "quien": "Lyra", "delta": -3}, kael)[0], 403)
        codigo, r = self.tirar(slug, {"accion": "vida", "quien": "Cen", "delta": -100}, self.host)
        self.assertEqual(codigo, 400)
        self.assertNotIn(REAL, r["error"], "ni se resuelve un enemigo ni se listan")
        self.assertIn("PJ: Kael, Lyra", r["error"])
        self.assertEqual(estado.cargar(slug)["enemigos"][0]["vida"], 14)
        self.assertEqual(self.tirar(slug, {"accion": "vida", "delta": -1}, self.host)[0], 400, "sin «quien» no se elige al primero")

    def test_la_iniciativa_se_suma_al_orden_y_respeta_la_ventaja(self):
        slug = self.campana()
        correr("-p", slug, "iniciativa")
        with dados_fijos(3, 17):
            codigo, r = self.tirar(slug, {"accion": "iniciativa", "modo": "ventaja"}, self.invitado(slug, "Lyra"))
        self.assertEqual(codigo, 200, r)
        self.assertEqual((r["evento"]["modo"], r["evento"]["valores"], r["evento"]["total"]), ("ventaja", [3, 17], 19))
        self.assertEqual(sorted(x["quien"] for x in estado.cargar(slug)["combate"]["orden_iniciativa"]), ["Kael", "Lyra"])

    def test_dados_de_golpe_descansos_y_muerte_siguen_el_srd(self):
        slug = self.campana()
        kael = self.invitado(slug, "Kael")
        self.assertEqual(self.tirar(slug, {"accion": "dados_golpe"}, kael)[0], 400, "a vida completa no se gastan")
        self.tirar(slug, {"accion": "vida", "delta": -6}, kael)
        with dados_fijos(5):
            self.assertEqual(self.tirar(slug, {"accion": "dados_golpe"}, kael)[0], 200)
        self.assertEqual((self.ficha(slug, "Kael")["vida"], self.ficha(slug, "Kael")["dados_golpe"]["actual"]), (12, 0))
        self.tirar(slug, {"accion": "vida", "delta": -3}, kael)
        codigo, r = self.tirar(slug, {"accion": "dados_golpe"}, kael)
        self.assertEqual(codigo, 400)
        self.assertIn("no tiene Dados de Golpe", r["error"])
        self.tirar(slug, {"accion": "vida", "delta": -20}, kael)
        codigo, r = self.tirar(slug, {"accion": "descanso", "clase": "corto"}, kael)
        self.assertIn("0 PG", r["texto"])
        self.assertEqual(self.ficha(slug, "Kael")["vida"], 0)
        self.assertEqual(self.tirar(slug, {"accion": "salvacion_muerte", "quien": "Lyra"}, self.host)[0], 400)
        datos = estado.cargar(slug)
        next(p for p in datos["personajes"] if p["nombre"] == "Kael")["muerto"] = True
        estado.guardar(slug, datos)
        codigo, r = self.tirar(slug, {"accion": "vida", "delta": 5}, kael)
        self.assertEqual(codigo, 400)
        self.assertIn("ha muerto", r["error"])
        self.tirar(slug, {"accion": "descanso", "clase": "largo"}, kael)
        self.assertEqual(self.ficha(slug, "Kael")["vida"], 0, "un descanso no resucita")

    def test_el_inventario_mueve_la_ca_que_usa_el_motor(self):
        slug = self.campana()
        kael = self.invitado(slug, "Kael")
        escudo = {"accion": "agregar_item", "nombre": "Escudo", "ranura": "off_hand", "bono_ca": 2, "equipado": True}
        self.assertEqual(self.tirar(slug, escudo, kael)[0], 200)
        self.assertEqual(self.ficha(slug, "Kael")["ca"], 13)
        self.tirar(slug, {"accion": "equipar", "nombre": "Escudo"}, kael)
        self.assertEqual(self.ficha(slug, "Kael")["ca"], 11)
        self.tirar(slug, {"accion": "equipar", "nombre": "Escudo"}, kael)
        self.tirar(slug, {**escudo, "nombre": "Escudo grande", "bono_ca": 3}, kael)
        self.assertEqual(self.ficha(slug, "Kael")["ca"], 14, "el nuevo ocupa la ranura y el viejo deja de contar")
        with dados_fijos(2):
            codigo, r = self.tirar(slug, {"accion": "ataque", "quien": "Lyra", "objetivo": "Kael"}, self.host)
        self.assertEqual((codigo, r["evento"]["cd"]), (200, 14))
        self.tirar(slug, {"accion": "quitar_item", "nombre": "Escudo grande"}, kael)
        self.assertEqual(self.ficha(slug, "Kael")["ca"], 11)
        for nombre in ("Arma principal", ""):
            with self.subTest(nombre=nombre):
                self.assertEqual(self.tirar(slug, {"accion": "usar_item", "nombre": nombre}, kael)[0], 400)

    def test_el_dano_del_arma_suma_su_modificador_y_el_desarmado_es_1_mas_fuerza(self):
        slug = self.campana()
        kael = self.invitado(slug, "Kael")
        with dados_fijos(3):
            r = self.tirar(slug, {"accion": "dano", "arma": "Arma principal"}, kael)[1]
        self.assertEqual((r["evento"]["bruto"], r["evento"]["bonus_mod"]), (5, 2))
        with dados_fijos(15):
            r = self.tirar(slug, {"accion": "ataque", "subtipo": "desarmado"}, kael)[1]
        self.assertEqual((r["evento"]["arma"], r["evento"]["dano"]["bruto"]), ("Golpe desarmado", 3))
        self.assertEqual(self.tirar(slug, {"accion": "ataque", "subtipo": "distancia"}, kael)[0], 400)

    def test_numeros_y_tipos_invalidos_son_400_sin_tocar_el_disco(self):
        slug = self.campana()
        kael = self.invitado(slug, "Kael")
        antes = (estado.dir_partida(slug) / "partida.json").read_text(encoding="utf-8")
        for crudo in (
            '{"accion":"agregar_item","nombre":"Pluma","peso":1e999}',
            '{"accion":"agregar_item","nombre":"Pluma","peso":NaN}',
            '{"accion":"vida","delta":[1]}',
            '{"accion":"agregar_item","nombre":"Pluma","valor":"mucho"}',
            '{"accion":"agregar_item","nombre":"Pluma","dano":"99d999"}',
            '{"accion":"monedas","oro":1e999}',
        ):
            with self.subTest(crudo=crudo):
                self.assertEqual(self.tirar(slug, None, kael, crudo=crudo)[0], 400)
        self.assertEqual((estado.dir_partida(slug) / "partida.json").read_text(encoding="utf-8"), antes)


class TestElNarradorNoHablaPorLosJugadores(unittest.TestCase):
    def setUp(self):
        self._ctx = repo_temporal()
        self._ctx.__enter__()

    def tearDown(self):
        self._ctx.__exit__(None, None, None)

    def jugador(self, autor, texto, ooc=False):
        ruta = estado.dir_partida("neva") / "chat.jsonl"
        previos = chat.leer_chat("neva")
        mensaje = {"seq": len(previos) + 1, "ts": estado.ahora(), "rol": "jugador", "autor": autor, "texto": texto}
        if ooc:
            mensaje["ooc"] = True
        with ruta.open("a", encoding="utf-8") as f:
            f.write(json.dumps(mensaje, ensure_ascii=False) + "\n")

    def turno(self):
        return correr("-p", "neva", "turno", "--accion", "Crisljin=salta al muelle", "--accion", "Jualjin=lo sigue", "--resumen", "Saltan.")

    def ultimo_turno(self):
        return [e for e in estado.leer_eventos("neva") if e["tipo"] == "turno"][-1]

    def test_turno_avisa_de_la_accion_que_su_jugador_no_escribio(self):
        self.jugador("Crisljin", "Salto al muelle")
        self.jugador("Jualjin", "¿Cuánto mide el muelle?", ooc=True)
        codigo, salida = self.turno()
        self.assertEqual(codigo, 0, salida)
        self.assertEqual(self.ultimo_turno()["sin_declarar"], ["Jualjin"])
        self.assertIn("Sin declarar por su jugador: Jualjin", salida)

    def test_sin_chat_desde_el_turno_anterior_no_avisa_y_el_piloto_tampoco(self):
        self.assertNotIn("sin_declarar", (self.turno(), self.ultimo_turno())[1], "en la terminal el motor no ve a los jugadores")
        self.assertEqual(correr("-p", "neva", "piloto", "Jualjin", "narrador")[0], 0)
        self.jugador("Crisljin", "Salto al muelle")
        self.turno()
        self.assertNotIn("sin_declarar", self.ultimo_turno())

    def test_detecta_cuando_el_narrador_pone_voz_o_decision_a_un_pj(self):
        casos = {
            "**Kael:** ¡Vamos ya!": ["Kael"],
            "—Cuidado —dice Lyra, y retrocede.": ["Lyra"],
            "Kael decide abrir la puerta.": ["Kael"],
            "El guardia mira a Kael y a Lyra.": [],
            "Kael ve la puerta entreabierta.": [],
        }
        for texto, esperado in casos.items():
            with self.subTest(texto=texto):
                self.assertEqual(chat.voces_de_pj(texto, ["Kael", "Lyra"]), esperado)


class TestFichaInicial(unittest.TestCase):
    def test_clase_y_matriz_estandar(self):
        mago = reglas_2024.ficha_inicial("Mira", "Maga / Estratega", 2)
        self.assertEqual((mago["dados_golpe"]["dado"], mago["vida"], mago["atributos"]["inteligencia"]), ("d6", 8, 15))
        self.assertEqual(mago["competencias"]["salvaciones"], ["inteligencia", "sabiduria"])
        self.assertEqual(reglas_2024.clase_de("Exploradora / Navegante"), "explorador")
        self.assertIsNone(reglas_2024.clase_de("Aventurero"))


if __name__ == "__main__":
    unittest.main()
