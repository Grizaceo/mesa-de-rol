import json
import sys
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from mesa import chat, estado, servidor

from apoyo import REPO, repo_temporal

FALSO = [sys.executable, str(Path(__file__).resolve().parent / "fixtures" / "agente_acp_falso.py")]


def esperar(condicion, segundos=15):
    limite = time.monotonic() + segundos
    while time.monotonic() < limite:
        if condicion():
            return True
        time.sleep(0.05)
    raise AssertionError("no pasó a tiempo")


class Base(unittest.TestCase):
    def setUp(self):
        self._ctx = repo_temporal()
        self.raiz = self._ctx.__enter__()
        self.narradores = []

    def tearDown(self):
        for n in self.narradores:
            n.cerrar()
        self._ctx.__exit__(None, None, None)

    def narrador(self, comando=None):
        n = chat.Narrador("falso", comando or FALSO, cwd=str(REPO))
        self.narradores.append(n)
        return n

    def turno(self, n, texto, slug="neva"):
        n.enviar(slug, texto)
        esperar(lambda: n.vista(slug)["en_curso"] is None)
        return chat.leer_chat(slug)


class TestNarradorACP(Base):
    """El chat del visor: el jugador escribe, el agente ACP responde y lo que registra entra como tarjetas."""

    def test_turno_con_tirada_en_orden_y_sin_secretos(self):
        n = self.narrador()
        mensajes = self.turno(n, "tira el dado, por favor")
        jugador, narrador = mensajes[-2], mensajes[-1]
        self.assertEqual((jugador["rol"], jugador["texto"]), ("jugador", "tira el dado, por favor"))
        self.assertEqual(narrador["rol"], "narrador")
        self.assertEqual(narrador["autor"], "falso/modelo-de-prueba")
        tipos = [p["tipo"] for p in narrador["partes"]]
        self.assertEqual(tipos, ["texto", "evento", "texto"])  # el dado cae a mitad de la frase
        evento = next(e for e in estado.leer_eventos("neva") if e["seq"] == narrador["partes"][1]["seq"])
        self.assertEqual((evento["tipo"], evento["etiqueta"]), ("tirada", "falso"))
        self.assertTrue(narrador["texto"].startswith("nueva. Tiras el dado"))
        guardado = (estado.dir_partida("neva") / "chat.jsonl").read_text(encoding="utf-8")
        self.assertNotIn("SECRETO", guardado)
        self.assertNotIn("PENSAMIENTO", guardado)
        self.assertEqual(json.loads((estado.dir_partida("neva") / ".narrador.json").read_text())["agente"], "falso")

    def test_el_preambulo_va_solo_en_la_sesion_nueva_y_se_retoma_tras_reiniciar(self):
        n = self.narrador()
        self.assertTrue(self.turno(n, "hola")[-1]["texto"].startswith("nueva"))
        self.assertTrue(self.turno(n, "sigo")[-1]["texto"].startswith("seguida"))
        n.cerrar()
        otro = self.narrador()  # el visor se reinició: retoma la sesión guardada
        ultimo = self.turno(otro, "aquí sigo")[-1]
        self.assertTrue(ultimo["texto"].startswith("seguida"), ultimo)
        self.assertNotIn("HISTORIA REPETIDA", json.dumps(chat.leer_chat("neva"), ensure_ascii=False))
        otro.nueva_sesion("neva")
        self.assertTrue(self.turno(otro, "de nuevo")[-1]["texto"].startswith("nueva"))

    def test_permiso_para_lo_que_no_es_de_la_mesa(self):
        n = self.narrador()
        n.enviar("neva", "pide permiso")
        esperar(lambda: n.vista("neva")["permiso"] is not None)
        permiso = n.vista("neva")["permiso"]
        self.assertEqual((permiso["titulo"], permiso["tipo"]), ("rm -rf /tmp/algo", "execute"))
        n.responder_permiso("neva", permiso["id"], False)
        esperar(lambda: n.vista("neva")["en_curso"] is None)
        mensajes = chat.leer_chat("neva")
        self.assertIn("permiso=no", mensajes[-1]["texto"])
        self.assertTrue(any(m["rol"] == "sistema" and m["texto"].startswith("Rechazado: rm -rf") for m in mensajes))

    def test_ocupado_y_cancelar(self):
        n = self.narrador()
        n.enviar("neva", "ve lento")
        esperar(lambda: n.vista("neva")["en_curso"] and n._p("neva")["sesion"])
        with self.assertRaises(chat.Ocupado):
            n.enviar("neva", "otra cosa")
        with self.assertRaises(chat.Ocupado):
            n.nueva_sesion("neva")
        self.assertTrue(n.cancelar("neva"))
        esperar(lambda: n.vista("neva")["en_curso"] is None)
        self.assertEqual(chat.leer_chat("neva")[-1]["parada"], "cancelled")
        with self.assertRaises(ValueError):
            n.enviar("neva", "   ")

    def test_si_el_agente_no_arranca_queda_dicho_en_el_chat(self):
        n = self.narrador([sys.executable, "-c", "pass"])
        ultimo = self.turno(n, "hola")[-1]
        self.assertEqual(ultimo["rol"], "sistema")
        self.assertIn("El narrador falló", ultimo["texto"])
        self.assertIsNone(n.vista("neva")["en_curso"])


class TestMCPDeUnaPartida(Base):
    """El MCP del chat se lanza con MESA_PARTIDA: no puede escribir en otra partida aunque el modelo la nombre."""

    def test_rechaza_otra_partida_y_cambiar_de_partida(self):
        from unittest import mock

        from mesa import mcp

        with mock.patch.dict("os.environ", {"MESA_PARTIDA": "neva"}):
            ok, texto = mcp.ejecutar(mcp.construir_argumentos("turno", {"partida": "otra", "resumen": "x"}))
            self.assertFalse(ok)
            self.assertIn("es de la partida `neva`", texto)
            for args in (["usar", "otra"], ["nueva", "otra", "--titulo", "Otra"]):
                with self.subTest(args=args):
                    self.assertFalse(mcp.ejecutar(args)[0])
            self.assertTrue(mcp.ejecutar(mcp.construir_argumentos("estado", {"partida": "neva"}))[0])
            self.assertTrue(mcp.ejecutar(["estado"])[0])
        self.assertEqual(self.narrador()._mcp("neva")[0]["env"][1], {"name": "MESA_PARTIDA", "value": "neva"})


class TestChatPorHTTP(Base):
    def setUp(self):
        super().setUp()
        self.srv = None

    def tearDown(self):
        if self.srv:
            self.srv.shutdown()
            self.srv.server_close()
        super().tearDown()

    def arrancar(self, narrador=None, tailscale=None, clave_sala=None):
        self.srv = servidor.crear("127.0.0.1", 0, narrador, tailscale, clave_sala=clave_sala)
        self.puerto = self.srv.server_address[1]
        self.base = f"http://127.0.0.1:{self.puerto}"
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def pedir(self, metodo, ruta, cuerpo=None, cabeceras=None):
        datos = None if cuerpo is None else json.dumps(cuerpo).encode()
        peticion = urllib.request.Request(self.base + ruta, data=datos, method=metodo, headers=cabeceras or {})
        try:
            with urllib.request.urlopen(peticion, timeout=10) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            with e:
                return e.code, json.loads(e.read())

    def test_chat_completo_por_la_api(self):
        n = self.narrador()
        self.arrancar(n)
        visor = self.pedir("GET", "/api/visor")[1]
        self.assertTrue(visor["chat"])
        cabeceras = {"Content-Type": "application/json", "X-Mesa-Token": visor["token"]}
        codigo, r = self.pedir("POST", "/api/chat?p=neva", {"texto": "tira"}, cabeceras)
        self.assertEqual(codigo, 202, r)
        self.assertEqual(self.pedir("POST", "/api/chat?p=neva", {"texto": "otra"}, cabeceras)[0], 409)
        esperar(lambda: self.pedir("GET", "/api/chat?p=neva")[1]["narrador"]["en_curso"] is None)
        mensajes = self.pedir("GET", "/api/chat?p=neva&desde=1")[1]["mensajes"]
        self.assertEqual([m["rol"] for m in mensajes], ["narrador"])
        self.assertEqual(self.pedir("POST", "/api/chat?p=neva", {"texto": "x"}, {"Content-Type": "application/json"})[0], 403)

    def test_sin_narrador_el_chat_es_de_solo_lectura(self):
        self.arrancar()
        visor = self.pedir("GET", "/api/visor")[1]
        self.assertFalse(visor["chat"])
        self.assertEqual(self.pedir("GET", "/api/chat?p=neva")[1], {"mensajes": [], "narrador": {"activo": False}})
        cabeceras = {"Content-Type": "application/json", "X-Mesa-Token": visor["token"]}
        self.assertEqual(self.pedir("POST", "/api/chat?p=neva", {"texto": "hola"}, cabeceras)[0], 409)

    def test_tailscale_solo_para_el_usuario_autorizado(self):
        ts = {"host": "nodo.tail-ejemplo.ts.net", "usuarios": {"yo@ejemplo.com"}}
        self.arrancar(tailscale=ts)
        mio = {"Host": "nodo.tail-ejemplo.ts.net:8799", "Tailscale-User-Login": "yo@ejemplo.com", "Tailscale-User-Name": "Yo"}
        ajeno = {**mio, "Tailscale-User-Login": "otro@ejemplo.com"}
        self.assertFalse(self.pedir("GET", "/api/visor", cabeceras=ajeno)[1]["escritura"])
        self.assertFalse(self.pedir("GET", "/api/visor", cabeceras={"Host": "otro-nodo.ts.net", "Tailscale-User-Login": "yo@ejemplo.com"})[1]["escritura"])
        visor = self.pedir("GET", "/api/visor", cabeceras=mio)[1]
        self.assertTrue(visor["escritura"])
        self.assertEqual(visor["autor"], "Yo")
        base = {**mio, "Content-Type": "application/json", "X-Mesa-Token": visor["token"]}
        codigo, r = self.pedir("POST", "/api/memoria?p=neva", {"accion": "agregar", "texto": "Desde el notebook"},
                               {**base, "Origin": "https://nodo.tail-ejemplo.ts.net:8799"})
        self.assertEqual(codigo, 200, r)
        self.assertEqual(self.pedir("POST", "/api/memoria?p=neva", {"accion": "agregar", "texto": "x"}, {**base, "Origin": "https://malo.example"})[0], 403)
        self.assertEqual(self.pedir("POST", "/api/memoria?p=neva", {"accion": "agregar", "texto": "y"}, {**base, "Tailscale-User-Login": "otro@ejemplo.com"})[0], 403)

    def test_cambiar_agente_desde_el_visor(self):
        self.arrancar(self.narrador())
        visor = self.pedir("GET", "/api/visor")[1]
        cabeceras = {"Content-Type": "application/json", "X-Mesa-Token": visor["token"]}
        codigo, r = self.pedir("POST", "/api/chat/agente?p=neva", {"agente": "devin"}, cabeceras)
        self.assertEqual(codigo, 200, r)
        self.assertEqual(r["narrador"]["agente"], "devin")
        self.assertIn("hermes", r["narrador"]["agentes"])
        self.assertEqual(self.pedir("POST", "/api/chat/agente?p=neva", {"agente": "inexistente"}, cabeceras)[0], 400)

    CLAVE = "clave-de-sala-de-prueba"

    def invitado(self):
        """Cabeceras de quien entra por el túnel con la clave de sala (sin PJ reclamado todavía)."""
        remoto = {"Host": "tunel.trycloudflare.com", "X-Mesa-Sala": self.CLAVE}
        visor = self.pedir("GET", "/api/visor", cabeceras=remoto)[1]
        return {**remoto, "Content-Type": "application/json", "X-Mesa-Token": visor["token"], "Origin": "https://tunel.trycloudflare.com"}

    def anfitrion(self):
        return {"Content-Type": "application/json", "X-Mesa-Token": self.pedir("GET", "/api/visor")[1]["token"]}

    def test_sala_con_clave_y_autor_por_personaje(self):
        with self.assertRaises(ValueError):
            servidor.crear("127.0.0.1", 0, clave_sala="corta")  # una clave que se adivina no abre la mesa
        self.arrancar(self.narrador(), clave_sala=self.CLAVE)
        sin_clave = {"Host": "tunel.trycloudflare.com"}
        v_sin = self.pedir("GET", "/api/visor", cabeceras=sin_clave)[1]
        self.assertEqual((v_sin["escritura"], v_sin["sala"], v_sin["lectura"], v_sin["anfitrion"]), (False, True, False, False))
        self.assertEqual(self.pedir("GET", "/api/estado?p=neva", cabeceras=sin_clave)[0], 403, "con sala, leer también pide la clave")
        self.assertFalse(self.pedir("GET", "/api/visor", cabeceras={**sin_clave, "X-Mesa-Sala": "equivocada-pero-larga"})[1]["escritura"])
        base = self.invitado()
        v_inv = self.pedir("GET", "/api/visor", cabeceras=base)[1]
        self.assertEqual((v_inv["escritura"], v_inv["anfitrion"]), (True, False))
        # Sin PJ reclamado no se escribe; reclamado, se firma siempre como él.
        self.assertEqual(self.pedir("POST", "/api/chat?p=neva", {"texto": "hola"}, base)[0], 403)
        codigo, rec = self.pedir("POST", "/api/reclamar?p=neva", {"pj": "Crisljin"}, base)
        self.assertEqual(codigo, 200, rec)
        con_pj = {**base, "X-Mesa-Reclamo": rec["reclamo"]}
        self.assertEqual(self.pedir("POST", "/api/reclamar?p=neva", {"pj": "Crisljin"}, self.invitado())[0], 409, "un PJ, una persona")
        codigo, r = self.pedir("POST", "/api/chat?p=neva", {"texto": "avanzo con cuidado"}, con_pj)
        self.assertEqual(codigo, 202, r)
        self.assertEqual(r["mensaje"]["autor"], "Crisljin")
        esperar(lambda: self.pedir("GET", "/api/chat?p=neva")[1]["narrador"]["en_curso"] is None)
        self.assertEqual(self.pedir("POST", "/api/chat?p=neva", {"texto": "hablo por otro", "autor": "Jualjin"}, con_pj)[0], 403)
        codigo_ooc, r_ooc = self.pedir("POST", "/api/chat?p=neva", {"texto": "¿cuántos metros hay?", "fuera_de_personaje": True}, con_pj)
        self.assertEqual(codigo_ooc, 202, r_ooc)
        self.assertTrue(r_ooc["mensaje"].get("ooc"))
        esperar(lambda: self.pedir("GET", "/api/chat?p=neva")[1]["narrador"]["en_curso"] is None)
        self.pedir("GET", "/api/chat?p=neva", cabeceras={"X-Mesa-Cliente": "tab-1", "X-Mesa-Jugador": "Jualjin"})  # el anfitrión dice a quién lleva
        conectados = self.pedir("GET", "/api/chat?p=neva", cabeceras={**con_pj, "X-Mesa-Cliente": "tab-2", "X-Mesa-Jugador": "Inventado"})[1]["conectados"]
        self.assertEqual(conectados["jugadores"], ["Jualjin", "Crisljin"], "el invitado aparece con su PJ reclamado, no con lo que diga")
        self.assertEqual(self.pedir("POST", "/api/chat?p=neva", {"texto": "x"}, {**con_pj, "Origin": "https://malo.example"})[0], 403)

    def test_el_invitado_no_maneja_el_agente_ni_la_campana(self):
        self.arrancar(self.narrador(), clave_sala=self.CLAVE)
        inv = self.invitado()
        inv = {**inv, "X-Mesa-Reclamo": self.pedir("POST", "/api/reclamar?p=neva", {"pj": "Crisljin"}, inv)[1]["reclamo"]}
        for ruta, cuerpo in (
            ("/api/chat/permiso?p=neva", {"id": "x", "permitir": True}),
            ("/api/chat/sesion-nueva?p=neva", {}),
        ):
            with self.subTest(ruta=ruta):
                codigo, r = self.pedir("POST", ruta, cuerpo, inv)
                self.assertEqual(codigo, 403, r)
                self.assertIn("anfitrión", r["error"])
        # La sala sí construye campañas (sin cambiar la partida activa), con un tope por arranque.
        activa = (self.raiz / ".mesa-activa").read_text(encoding="utf-8")
        codigo, r = self.pedir("POST", "/api/campana?p=neva", {"modo": "nueva", "titulo": "De la Sala", "iniciar_chat": False}, inv)
        self.assertEqual(codigo, 200, r)
        self.assertTrue((self.raiz / "partidas" / "de-la-sala" / "partida.json").exists())
        self.assertEqual((self.raiz / ".mesa-activa").read_text(encoding="utf-8"), activa)
        self.assertEqual(estado.leer_eventos("de-la-sala")[-1]["autor"], "Crisljin")
        self.srv.campanas_sala = servidor.MAX_CAMPANAS_SALA
        self.assertEqual(self.pedir("POST", "/api/campana?p=neva", {"modo": "nueva", "titulo": "Otra más"}, inv)[0], 400)
        self.assertEqual(self.pedir("POST", "/api/campana?p=neva", {"modo": "nueva", "titulo": "Del anfitrión", "iniciar_chat": False}, self.anfitrion())[0], 200)
        # El agente pide permiso para un comando: el invitado no lo aprueba; el anfitrión sí.
        self.assertEqual(self.pedir("POST", "/api/chat?p=neva", {"texto": "pide permiso"}, inv)[0], 202)
        esperar(lambda: self.pedir("GET", "/api/chat?p=neva")[1]["narrador"]["permiso"] is not None)
        permiso = self.pedir("GET", "/api/chat?p=neva")[1]["narrador"]["permiso"]
        self.assertEqual(self.pedir("POST", "/api/chat/permiso?p=neva", {"id": permiso["id"], "permitir": True}, inv)[0], 403)
        self.assertEqual(self.pedir("POST", "/api/chat/permiso?p=neva", {"id": permiso["id"], "permitir": False}, self.anfitrion())[0], 200)
        esperar(lambda: self.pedir("GET", "/api/chat?p=neva")[1]["narrador"]["en_curso"] is None)
        self.assertTrue(any(m["texto"].startswith("Rechazado: rm -rf") for m in chat.leer_chat("neva") if m["rol"] == "sistema"))


if __name__ == "__main__":
    unittest.main()
