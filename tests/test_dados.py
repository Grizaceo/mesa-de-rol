import unittest

from mesa import dados

from apoyo import dados_fijos


class TestAnalizar(unittest.TestCase):
    def test_expresiones_validas(self):
        self.assertEqual(dados.analizar("2d6+1d4-1"), [(1, 2, 6), (1, 1, 4), (-1, 1, 0)])
        self.assertEqual(dados.analizar("d%"), [(1, 1, 100)])
        self.assertEqual(dados.analizar(" 1d20 + 3 "), [(1, 1, 20), (1, 3, 0)])

    def test_expresiones_invalidas(self):
        for mala in ("", "1d7", "2d63", "1d6d6", "1d20+", "3x", "0d6", "60d6"):
            with self.subTest(mala=mala), self.assertRaises(ValueError):
                dados.analizar(mala)


class TestTirar(unittest.TestCase):
    def test_suma_y_modificador(self):
        with dados_fijos(3, 4, 2):
            r = dados.tirar("2d6+1d4-1")
        self.assertEqual(r["total"], 3 + 4 + 2 - 1)
        self.assertEqual(r["modificador"], -1)

    def test_critico_duplica_dados_no_modificador(self):
        with dados_fijos(5, 6):
            r = dados.tirar("1d8+2", critico=True)
        self.assertEqual(r["dados"][0]["valores"], [5, 6])
        self.assertEqual(r["total"], 13)


class TestPruebaD20(unittest.TestCase):
    def test_modo_se_anula(self):
        self.assertEqual(dados.resolver_modo(["a", "b"], ["c"]), "normal")
        self.assertEqual(dados.resolver_modo(["a"], []), "ventaja")
        self.assertEqual(dados.resolver_modo([], ["c"]), "desventaja")

    def test_ventaja_y_desventaja_eligen_bien(self):
        with dados_fijos(14, 18):
            self.assertEqual(dados.prueba_d20(2, 15, "ventaja")["elegido"], 18)
        with dados_fijos(14, 18):
            self.assertEqual(dados.prueba_d20(2, 15, "desventaja")["elegido"], 14)

    def test_veinte_natural_siempre_exito(self):
        with dados_fijos(20):
            r = dados.prueba_d20(-5, 30)
        self.assertTrue(r["exito"])
        self.assertEqual(r["resultado"], "critico")

    def test_uno_natural_siempre_fallo(self):
        with dados_fijos(1):
            r = dados.prueba_d20(20, 5)
        self.assertFalse(r["exito"])
        self.assertEqual(r["resultado"], "uno_natural")

    def test_sin_naturales_manda_el_total(self):
        with dados_fijos(1):
            self.assertTrue(dados.prueba_d20(20, 5, naturales=False)["exito"])

    def test_igualar_es_exito(self):
        with dados_fijos(9):
            r = dados.prueba_d20(1, 10)
        self.assertTrue(r["exito"])
        self.assertEqual(r["margen"], 0)


if __name__ == "__main__":
    unittest.main()
