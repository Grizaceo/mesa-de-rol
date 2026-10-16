"""P0-03: ni markup activo en la tarjeta ni SVG (o contenido que miente) importado.

Los casos de servidor (cabeceras, tipos servidos) viven en test_servidor.py.
"""

import json
import threading
import unittest
import urllib.error
import urllib.request
from unittest import mock

from mesa import imagenes, servidor

from apoyo import repo_temporal

PNG_1X1 = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000d4944415478da62f8cfc0f01f00050001ff9c8a6d4d0000000049454e44ae426082"
)
SVG_CON_SCRIPT = b'<svg xmlns="http://www.w3.org/2000/svg" onload="alert(1)"><script>alert(2)</script></svg>'


class TestAcento(unittest.TestCase):
    def test_acento_invalido_no_se_inyecta_en_la_tarjeta(self):
        with repo_temporal() as raiz:
            archivo = raiz / "partidas" / "neva" / "partida.json"
            datos = json.loads(archivo.read_text(encoding="utf-8"))
            datos["tema"]["acento"] = '"><script>alert(1)</script>'
            archivo.write_text(json.dumps(datos, ensure_ascii=False), encoding="utf-8")
            e = imagenes.tarjeta_svg("neva")
            svg = (raiz / "partidas" / "neva" / "imagenes" / e["archivo"]).read_text(encoding="utf-8")
            self.assertNotIn("<script>", svg)
            self.assertNotIn("alert", svg)
            self.assertIn(imagenes.ACENTO_POR_DEFECTO, svg)

    def test_acento_valido_se_conserva(self):
        with repo_temporal() as raiz:
            archivo = raiz / "partidas" / "neva" / "partida.json"
            datos = json.loads(archivo.read_text(encoding="utf-8"))
            datos["tema"]["acento"] = "#1234ab"
            archivo.write_text(json.dumps(datos, ensure_ascii=False), encoding="utf-8")
            e = imagenes.tarjeta_svg("neva")
            svg = (raiz / "partidas" / "neva" / "imagenes" / e["archivo"]).read_text(encoding="utf-8")
            self.assertIn("#1234ab", svg)


class TestImportaciones(unittest.TestCase):
    def test_svg_externo_se_rechaza_en_biblioteca_y_seleccion(self):
        with repo_temporal() as raiz:
            origen = raiz / "plano.svg"
            origen.write_bytes(SVG_CON_SCRIPT)
            with self.assertRaises(ValueError):
                imagenes.agregar_biblioteca(str(origen), ["mapa"], "plano", "internet", "?")

    def test_svg_por_url_se_rechaza_aunque_diga_que_es_imagen(self):
        respuesta = mock.MagicMock()
        respuesta.headers.get_content_type.return_value = "image/svg+xml"
        respuesta.read.return_value = SVG_CON_SCRIPT
        respuesta.__enter__ = lambda s: s
        respuesta.__exit__ = lambda s, *a: None
        with mock.patch.object(imagenes.urllib.request, "urlopen", return_value=respuesta):
            with self.assertRaises(ValueError) as e:
                imagenes._descargar("http://ejemplo.test/plano.svg")
            self.assertIn("SVG", str(e.exception))

    def test_el_contenido_manda_sobre_la_extension(self):
        with repo_temporal() as raiz:
            mentiroso = raiz / "foto.png"  # dice .png, es SVG
            mentiroso.write_bytes(SVG_CON_SCRIPT)
            with self.assertRaises(ValueError):
                imagenes.elegir("neva", str(mentiroso))

    def test_raster_de_verdad_se_acepta_y_se_nombra_por_su_tipo(self):
        with repo_temporal() as raiz:
            origen = raiz / "foto.jpeg"
            origen.write_bytes(PNG_1X1)  # dice .jpeg, es PNG: manda el contenido
            e = imagenes.elegir("neva", str(origen))
            self.assertTrue(e["archivo"].endswith(".png"))
            self.assertEqual(e["modo"], "elegir")

    def test_tamano_maximo(self):
        with repo_temporal() as raiz:
            origen = raiz / "grande.png"
            origen.write_bytes(PNG_1X1 + b"\x00" * 64)
            with mock.patch.object(imagenes, "TAMANO_MAXIMO", 32):
                with self.assertRaises(ValueError) as e:
                    imagenes.elegir("neva", str(origen))
                self.assertIn("15 MB", str(e.exception))
                with self.assertRaises(ValueError):
                    imagenes.agregar_biblioteca(str(origen), [], "", "", "")

    def test_biblioteca_solo_publica_contenido_verificado(self):
        with repo_temporal() as raiz:
            png = raiz / "libre.png"
            png.write_bytes(PNG_1X1)
            item = imagenes.agregar_biblioteca(str(png), ["libre"], "png real", "propia", "CC0")
            # Si alguien cambia el archivo de la biblioteca por markup, elegir lo detecta.
            (raiz / "biblioteca" / "imagenes" / item["archivo"]).write_bytes(SVG_CON_SCRIPT)
            with self.assertRaises(ValueError):
                imagenes.elegir("neva", item["id"])


class TestServidorMedios(unittest.TestCase):
    """Lo que el visor sirve como medio: tipos permitidos y cabeceras de riesgo."""

    def setUp(self):
        self._ctx = repo_temporal()
        self.raiz = self._ctx.__enter__()
        self.srv = servidor.crear("127.0.0.1", 0)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()
        self._ctx.__exit__(None, None, None)

    def _get(self, ruta):
        base = f"http://127.0.0.1:{self.srv.server_address[1]}"
        try:
            with urllib.request.urlopen(base + ruta, timeout=5) as r:
                return r.status, dict(r.headers), r.read()
        except urllib.error.HTTPError as e:
            with e:
                return e.code, dict(e.headers), e.read()

    def test_el_svg_generado_se_sirve_neutralizado(self):
        tarjeta = imagenes.tarjeta_svg("neva")
        codigo, cabeceras, cuerpo = self._get(f"/media/neva/{tarjeta['archivo']}")
        self.assertEqual(codigo, 200)
        self.assertEqual(cabeceras["Content-Type"], "image/svg+xml; charset=utf-8")
        csp = cabeceras.get("Content-Security-Policy", "")
        self.assertIn("sandbox", csp)
        self.assertIn("default-src 'none'", csp)

    def test_un_svg_colado_en_medios_no_ejecuta_su_script(self):
        (self.raiz / "partidas" / "neva" / "imagenes" / "colado.svg").write_bytes(SVG_CON_SCRIPT)
        codigo, cabeceras, cuerpo = self._get("/media/neva/colado.svg")
        self.assertEqual(codigo, 200)  # se sirve, pero con las defensas puestas
        self.assertIn("sandbox", cabeceras.get("Content-Security-Policy", ""))
        self.assertEqual(cuerpo, SVG_CON_SCRIPT)

    def test_html_escondido_en_medios_no_se_sirve(self):
        (self.raiz / "partidas" / "neva" / "imagenes" / "pagina.html").write_bytes(b"<script>alert(1)</script>")
        self.assertEqual(self._get("/media/neva/pagina.html")[0], 404)
        (self.raiz / "biblioteca" / "imagenes" / "pagina.html").write_bytes(b"<script>alert(1)</script>")
        self.assertEqual(self._get("/biblioteca/pagina.html")[0], 404)

    def test_png_legitimo_se_sirve_como_imagen(self):
        (self.raiz / "partidas" / "neva" / "imagenes" / "foto.png").write_bytes(PNG_1X1)
        codigo, cabeceras, cuerpo = self._get("/media/neva/foto.png")
        self.assertEqual((codigo, cabeceras["Content-Type"]), (200, "image/png"))
        self.assertEqual(cuerpo, PNG_1X1)


if __name__ == "__main__":
    unittest.main()
