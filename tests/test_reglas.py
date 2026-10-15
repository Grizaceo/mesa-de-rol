import copy
import json
import unittest

from mesa import reglas

from apoyo import REPO, dados_fijos

PARTIDA = json.loads((REPO / "partidas" / "los-hermanos-del-neva" / "partida.json").read_text(encoding="utf-8"))


def partida():
    return copy.deepcopy(PARTIDA)


def ficha(datos, nombre):
    return next(p for p in datos["personajes"] if p["nombre"] == nombre)


class TestTraducciones(unittest.TestCase):
    def test_atributos_y_habilidades(self):
        self.assertEqual(reglas.resolver_atributo("Corazón"), ("corazon", None))
        self.assertEqual(reglas.resolver_atributo("dex"), ("agilidad", None))
        self.assertEqual(reglas.resolver_atributo("percepcion"), ("ingenio", "Percepción"))
        self.assertEqual(reglas.resolver_atributo("Stealth"), ("agilidad", "Sigilo"))
        with self.assertRaises(ValueError):
            reglas.resolver_atributo("magia")

    def test_dificultades_por_nombre(self):
        self.assertEqual(reglas.resolver_cd("media"), 15)
        self.assertEqual(reglas.resolver_cd("muy-dificil"), 25)
        self.assertEqual(reglas.resolver_cd("12"), 12)
        self.assertIsNone(reglas.resolver_cd(None))
        with self.assertRaises(ValueError):
            reglas.resolver_cd("imposible del todo")

    def test_las_18_habilidades_del_srd(self):
        self.assertEqual(len(reglas.HABILIDADES), 18)


class TestPrueba(unittest.TestCase):
    def test_empapado_impone_desventaja_en_agilidad(self):
        d = partida()
        with dados_fijos(18, 11):
            e = reglas.prueba(d, ficha(d, "Crisljin"), "agilidad", cd=15)
        self.assertEqual(e["modo"], "desventaja")
        self.assertEqual(e["elegido"], 11)
        self.assertIn("Empapado", e["desventajas"])

    def test_ventaja_declarada_anula_empapado(self):
        d = partida()
        with dados_fijos(7):
            e = reglas.prueba(d, ficha(d, "Crisljin"), "sigilo", cd=15, ventaja="Jualjin distrae")
        self.assertEqual(e["modo"], "normal")
        self.assertEqual(e["habilidad"], "Sigilo")

    def test_habilidad_suma_su_bono_y_se_gasta(self):
        d = partida()
        c = ficha(d, "Crisljin")
        with dados_fijos(10):
            e = reglas.prueba(d, c, "ingenio", cd=20, usar="tengo una idea", oficio=True)
        self.assertEqual(e["total"], 10 + 2 + 2 + 4)
        self.assertFalse(c["habilidades"][0]["disponible"])
        with self.assertRaises(ValueError):
            reglas.prueba(d, c, "ingenio", usar="tengo una idea")

    def test_agotamiento_resta_por_nivel(self):
        d = partida()
        j = ficha(d, "Jualjin")
        cond = reglas.condicion_de_catalogo("agotamiento")
        cond["niveles"] = 2
        j["condiciones"].append(cond)
        with dados_fijos(10):
            e = reglas.prueba(d, j, "fuerza", cd=10)
        self.assertEqual(e["total"], 10 + 3 - 4)


class TestCombate(unittest.TestCase):
    def setUp(self):
        self.d = partida()
        maton = dict(reglas.PLANTILLAS_ENEMIGO["maton"], vida_max=8, condiciones=[])
        self.d["enemigos"].append(maton)
        self.maton = maton

    def test_ataque_acierta_y_aplica_dano(self):
        with dados_fijos(12, 6):
            e = reglas.ataque(self.d, ficha(self.d, "Jualjin"), self.maton, arma="bichero")
        self.assertTrue(e["exito"])
        self.assertEqual(e["dano"]["final"], 6)
        self.assertEqual(self.maton["vida"], 2)

    def test_critico_dobla_dados_y_deja_fuera_de_combate(self):
        with dados_fijos(20, 8, 7):
            e = reglas.ataque(self.d, ficha(self.d, "Jualjin"), self.maton, arma="bichero")
        self.assertEqual(e["resultado"], "critico")
        self.assertEqual(self.maton["vida"], 0)
        self.assertIn("Fuera de combate", [c["nombre"] for c in self.maton["condiciones"]])

    def test_proteccion_deja_minimo_uno(self):
        crisljin = ficha(self.d, "Crisljin")
        with dados_fijos(15, 1):
            e = reglas.ataque(self.d, self.maton, crisljin)
        self.assertEqual(e["dano"]["final"], 1)
        self.assertEqual(crisljin["vida"], 10)

    def test_ventaja_contra_derribado(self):
        self.maton["condiciones"].append(reglas.condicion_de_catalogo("derribado"))
        with dados_fijos(3, 15, 2):
            e = reglas.ataque(self.d, ficha(self.d, "Jualjin"), self.maton, arma="bichero")
        self.assertEqual(e["modo"], "ventaja")

    def test_vida_no_sale_de_rango_y_se_recupera(self):
        j = ficha(self.d, "Jualjin")
        self.assertEqual(reglas.aplicar_vida(j, -99)["despues"], 0)
        self.assertIn("Fuera de combate", [c["nombre"] for c in j["condiciones"]])
        self.assertEqual(reglas.aplicar_vida(j, 99)["despues"], 14)
        self.assertNotIn("Fuera de combate", [c["nombre"] for c in j["condiciones"]])


if __name__ == "__main__":
    unittest.main()
