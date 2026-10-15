import json
import threading
import unittest
import urllib.error
import urllib.request

from mesa import servidor

from apoyo import repo_temporal


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


if __name__ == "__main__":
    unittest.main()
