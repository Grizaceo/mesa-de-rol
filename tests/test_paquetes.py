"""Los god archives se partieron en paquetes; la fachada pública no cambió."""

from __future__ import annotations

import unittest
from pathlib import Path


class TestMapasModulos(unittest.TestCase):
    def test_zona_es_fachada_de_submodulos(self):
        from mesa.mapas import zona
        from mesa.mapas import terreno, tokens, vision, luz, movimiento
        self.assertEqual(zona.nueva_zona, terreno.nueva_zona)
        self.assertEqual(zona.linea_entre, vision.linea_entre)
        self.assertEqual(zona.poner_luz, luz.poner_luz)
        self.assertEqual(zona.camino_movimiento, movimiento.camino_movimiento)
        self.assertEqual(zona.fichas, tokens.fichas)
        self.assertLess(Path(zona.__file__).stat().st_size, Path(terreno.__file__).stat().st_size * 3)

    def test_fachada_mapas_sigue_exportando(self):
        from mesa import mapas
        for nombre in ("zona_texto", "nueva_zona", "linea_entre", "proyeccion_zona", "poner_luz"):
            self.assertTrue(callable(getattr(mapas, nombre)), nombre)


class TestServidorMixins(unittest.TestCase):
    def test_manejador_compone_sala_campana_y_tiradas(self):
        from mesa.servidor.manejador import Manejador
        from mesa.servidor.sala import SalaMixin
        from mesa.servidor.campanas import CampanaMixin
        from mesa.servidor.tiradas import TiradasMixin
        self.assertTrue(issubclass(Manejador, SalaMixin))
        self.assertTrue(issubclass(Manejador, CampanaMixin))
        self.assertTrue(issubclass(Manejador, TiradasMixin))
        self.assertTrue(callable(Manejador._exigir_visor_local))
        self.assertTrue(callable(Manejador._configurar_campana))
        self.assertTrue(callable(Manejador._tirar_desde_visor))
        self.assertTrue(callable(Manejador._texto_publico))


class TestReglas2024Modulos(unittest.TestCase):
    def test_fachada_reexporta_catalogo_personaje_combate_y_magia(self):
        from mesa import reglas_2024
        from mesa.reglas_2024 import catalogo, personaje, combate, magia
        self.assertIs(reglas_2024.HABILIDADES_2024, catalogo.HABILIDADES_2024)
        self.assertIs(reglas_2024.ficha_inicial, personaje.ficha_inicial)
        self.assertIs(reglas_2024.prueba, combate.prueba)
        self.assertIs(reglas_2024.lanzar_conjuro, magia.lanzar_conjuro)
        self.assertLess(Path(reglas_2024.__file__).stat().st_size, 4000)


if __name__ == "__main__":
    unittest.main()
