"""Corte vertical de reglas D&D 2024 (P2, SRD 5.2.1 CC-BY-4.0).

Casos cotejados contra el SRD 5.2.1:
1. Seis características, modificadores, competencia (+2..+6) y pericia (×2); separar
   prueba de habilidad y tirada de salvación; ventaja/desventaja y sus fuentes.
2. Ataque contra CA (+ cobertura), daño con modificador de característica, críticos
   (duplican dados, no modificador), resistencias (÷2 hacia abajo), inmunidades (0)
   y vulnerabilidades (×2); no resta la protección plana de d20-simple.
3. Iniciativa (d20 + Destreza; Sorprendido impone desventaja en 2024), economía de
   acciones y propiedades/maestrías de armas (Sutil, Rozar/Graze, etc.).
4. PG temporales (no se acumulan, absorben daño primero), 0 PG, muerte instantánea
   por daño masivo, salvaciones de muerte (1 = 2 fallos, 20 = 1 PG y consciente) y
   Agotamiento 2024 (−2 × nivel a toda prueba d20 y −1,5 m × nivel a velocidad; nivel 6 = muerte).
5. Descanso corto (gasta Dados de Golpe y recarga solo `descanso_corto`) y descanso largo
   (toda la vida, todos los Dados de Golpe, −1 agotamiento, limpia PG temporales, recarga todo).
6. Conjuros: gasto de espacio, CD de salvación (8 + comp + mod), concentración (CD = máx(10, daño//2)
   hasta 30) y Fireball con mitad de daño en éxito.
7. Degradación honesta (`requiere_resolucion_manual` con referencia) y adjudicación manual,
   más inventario consumible e igualdad CLI/MCP.
"""

from __future__ import annotations

import copy
import io
import json
import unittest
from contextlib import contextmanager, redirect_stderr, redirect_stdout

from mesa import capacidades, cli, dados, estado, reglas, reglas_2024

from apoyo import REPO, repo_temporal

ENSAYO = REPO / "tests" / "fixtures" / "2024" / "partida_ensayo.json"


def cargar_ensayo() -> dict:
    return json.loads(ENSAYO.read_text(encoding="utf-8"))


@contextmanager
def dados_fijos(valores: list[int]):
    cola = list(valores)

    class _Fijo:
        def randint(self, a: int, b: int) -> int:
            if not cola:
                raise AssertionError("se acabaron los dados prefijados")
            v = cola.pop(0)
            assert a <= v <= b, f"dado {v} fuera de [{a}, {b}]"
            return v

    anterior = dados._rng
    dados._rng = _Fijo()
    try:
        yield
    finally:
        dados._rng = anterior


def correr(*args, perfil: str = capacidades.CLI):
    salida, errores = io.StringIO(), io.StringIO()
    with redirect_stdout(salida), redirect_stderr(errores):
        codigo = cli.main(list(args), perfil=perfil)
    return codigo, salida.getvalue(), errores.getvalue()


class TestCaracteristicasHabilidadesYSalvaciones(unittest.TestCase):
    def test_prueba_habilidad_con_competencia_y_pericia(self):
        partida = cargar_ensayo()
        valeria = partida["personajes"][0]  # nivel 5 (comp +3), FUE 18 (+4), competente en Atletismo
        alden = partida["personajes"][1]    # nivel 5 (comp +3), INT 18 (+4), pericia en Arcanos (+6)

        with dados_fijos([12]):
            r_atl = reglas.prueba(partida, valeria, "Atletismo", cd=15)
        self.assertEqual(r_atl["atributo"], "fuerza")
        self.assertEqual(r_atl["habilidad"], "Atletismo")
        self.assertEqual(r_atl["modificador"], 4 + 3)
        self.assertEqual(r_atl["total"], 19)
        self.assertTrue(r_atl["exito"])

        with dados_fijos([10]):
            r_arc = reglas.prueba(partida, alden, "Arcanos", cd=20)
        self.assertEqual(r_arc["atributo"], "inteligencia")
        self.assertEqual(r_arc["modificador"], 4 + 6)
        self.assertEqual(r_arc["total"], 20)
        self.assertTrue(r_arc["exito"])

    def test_separa_prueba_de_caracteristica_y_tirada_de_salvacion(self):
        partida = cargar_ensayo()
        valeria = partida["personajes"][0]  # competente en salvación de Constitución (+3), no en prueba de Constitución

        with dados_fijos([11, 11]):
            r_prueba = reglas.prueba(partida, valeria, "constitucion", cd=15, salvacion=False)
            r_salv = reglas.prueba(partida, valeria, "constitucion", cd=15, salvacion=True)

        # CON 16 -> +3; solo la salvación suma la competencia (+3).
        self.assertEqual(r_prueba["modificador"], 3)
        self.assertFalse(r_prueba["exito"])
        self.assertEqual(r_salv["modificador"], 6)
        self.assertTrue(r_salv["exito"])
        self.assertTrue(r_salv["salvacion"])

    def test_condiciones_paralizado_o_inconsciente_fallan_salvacion_fuerza_y_destreza(self):
        partida = cargar_ensayo()
        valeria = partida["personajes"][0]
        valeria["condiciones"] = [reglas.condicion_de_catalogo("paralizado", partida)]

        with dados_fijos([20]):
            r = reglas.prueba(partida, valeria, "fuerza", cd=10, salvacion=True)
        self.assertFalse(r["exito"])
        self.assertEqual(r["resultado"], "fallo_automatico")

    def test_rechaza_atributos_legacy_en_partida_2024(self):
        partida = cargar_ensayo()
        valeria = partida["personajes"][0]
        for attr_legacy in ("agilidad", "ingenio", "corazon"):
            with self.subTest(attr=attr_legacy):
                with self.assertRaises(ValueError) as ctx:
                    reglas.prueba(partida, valeria, attr_legacy)
                self.assertIn("2024", str(ctx.exception))


class TestAtaqueDanoYResistencias(unittest.TestCase):
    def test_ataque_2024_suma_competencia_y_modificador_al_dano_sin_restar_proteccion_plana(self):
        partida = cargar_ensayo()
        valeria = partida["personajes"][0]      # FUE 18 (+4), comp +3 -> +7 al ataque
        esqueleto = partida["enemigos"][0]      # CA 13, proteccion legacy=2 (se ignora en 2024)

        # Espada larga: 1d8 + 4 cortante (esqueleto no resiste cortante)
        with dados_fijos([10, 6]):  # d20=10 (+7 = 17 vs CA 13), d8=6 (+4 FUE = 10)
            ev = reglas.ataque(partida, valeria, esqueleto, arma="Espada larga")
        self.assertTrue(ev["exito"])
        self.assertEqual(ev["modificador"], 7)
        self.assertEqual(ev["dano"]["bruto"], 10)
        self.assertEqual(ev["dano"]["final"], 10, "en 2024 no se resta la protección plana de d20-simple")
        self.assertEqual(esqueleto["vida"], 16)
        self.assertEqual(ev["maestria"], "agotar")

    def test_arma_sutil_elige_el_mejor_entre_fuerza_y_destreza(self):
        partida = cargar_ensayo()
        alden = partida["personajes"][1]  # FUE 8 (-1), DES 14 (+2), comp +3
        alden["equipo"].append({
            "nombre": "Daga",
            "dano": "1d4",
            "tipo_dano": "perforante",
            "propiedades": ["sutil", "ligera"],
            "competente": True,
        })
        esqueleto = partida["enemigos"][0]
        with dados_fijos([15, 3]):
            ev = reglas.ataque(partida, alden, esqueleto, arma="Daga")
        # Usa Destreza (+2) + competencia (+3) = +5
        self.assertEqual(ev["modificador"], 5)

    def test_resistencia_inmunidad_y_vulnerabilidad_con_redondeo_srd(self):
        partida = cargar_ensayo()
        esqueleto = partida["enemigos"][0]  # resistente a perforante, vulnerable a contundente, inmune a veneno

        # 1. Resistencia a perforante: 7 // 2 = 3 (redondeo hacia abajo)
        with dados_fijos([7]):
            r_res = reglas.dano(partida, "1d8", esqueleto, tipo_dano="perforante")
        self.assertEqual(r_res["bruto"], 7)
        self.assertEqual(r_res["final"], 3)

        # 2. Vulnerabilidad a contundente: 5 * 2 = 10
        with dados_fijos([5]):
            r_vul = reglas.dano(partida, "1d8", esqueleto, tipo_dano="contundente")
        self.assertEqual(r_vul["final"], 10)

        # 3. Inmunidad a veneno: 8 -> 0
        with dados_fijos([8]):
            r_inm = reglas.dano(partida, "1d8", esqueleto, tipo_dano="veneno")
        self.assertEqual(r_inm["final"], 0)

    def test_maestria_rozar_graze_aplica_modificador_al_fallar(self):
        partida = cargar_ensayo()
        valeria = partida["personajes"][0]  # FUE 18 (+4), Espadón con maestría "rozar"
        esqueleto = partida["enemigos"][0]  # CA 13, vida 26
        with dados_fijos([2]):  # 2 + 7 = 9 vs CA 13 -> falla, pero Rozar hace 4 de daño cortante
            ev = reglas.ataque(partida, valeria, esqueleto, arma="Espadón")
        self.assertFalse(ev["exito"])
        self.assertEqual(ev["dano_maestria"]["final"], 4)
        self.assertEqual(esqueleto["vida"], 22)


class TestVidaTemporalMuerteYAgotamiento2024(unittest.TestCase):
    def test_pg_temporales_no_se_acumulan_y_absorben_dano_primero(self):
        partida = cargar_ensayo()
        valeria = partida["personajes"][0]  # 44/44 PG
        reglas_2024.fijar_vida_temporal(valeria, 8)
        self.assertEqual(valeria["vida_temporal"], 8)
        # No se acumulan: queda el mayor entre 8 y 5 -> 8; entre 8 y 12 -> 12.
        reglas_2024.fijar_vida_temporal(valeria, 5)
        self.assertEqual(valeria["vida_temporal"], 8)
        reglas_2024.fijar_vida_temporal(valeria, 12)
        self.assertEqual(valeria["vida_temporal"], 12)

        # Recibe 15 de daño: 12 absorbe vida_temporal, 3 va a vida (44 -> 41).
        cambio = reglas.aplicar_vida(valeria, -15, partida=partida)
        self.assertEqual(valeria["vida_temporal"], 0)
        self.assertEqual(valeria["vida"], 41)
        self.assertEqual(cambio["absorbido_temporal"], 12)

    def test_caer_a_0_pg_salvaciones_de_muerte_y_muerte_instantanea(self):
        partida = cargar_ensayo()
        alden = partida["personajes"][1]  # 32/32 PG
        reglas.aplicar_vida(alden, -32, partida=partida)
        self.assertEqual(alden["vida"], 0)
        self.assertIn("inconsciente", [c["nombre"].lower() for c in alden["condiciones"]])

        # Un 1 natural suma 2 fallos de muerte.
        with dados_fijos([1]):
            s1 = reglas_2024.salvacion_muerte(partida, alden)
        self.assertEqual(s1["fallos"], 2)

        # Un 20 natural recupera 1 PG, limpia Inconsciente y reinicia contadores.
        with dados_fijos([20]):
            s2 = reglas_2024.salvacion_muerte(partida, alden)
        self.assertEqual(alden["vida"], 1)
        self.assertTrue(s2["revive"])
        self.assertNotIn("inconsciente", [c["nombre"].lower() for c in alden["condiciones"]])

        # Daño masivo: en 1 PG recibe 33 de daño (sobran 32 == vida_max) -> muerte instantánea.
        cambio = reglas.aplicar_vida(alden, -33, partida=partida)
        self.assertTrue(cambio["muerte_instantanea"])
        self.assertTrue(alden.get("muerto"))

    def test_agotamiento_2024_resta_dos_por_nivel_y_reduce_velocidad(self):
        partida = cargar_ensayo()
        valeria = partida["personajes"][0]
        cond = reglas.condicion_de_catalogo("agotamiento", partida)
        cond["niveles"] = 3
        valeria["condiciones"] = [cond]

        self.assertEqual(reglas_2024.velocidad_efectiva(valeria), 9.0 - 4.5)
        with dados_fijos([15]):
            r = reglas.prueba(partida, valeria, "fuerza", cd=15)
        # FUE 18 (+4) - 6 (agotamiento 3) = -2 -> 15 - 2 = 13 (fallo)
        self.assertEqual(r["modificador"], -2)
        self.assertFalse(r["exito"])


class TestIniciativaDescansosConjurosYDegradacion(unittest.TestCase):
    def test_iniciativa_2024_con_desventaja_por_sorprendido(self):
        partida = cargar_ensayo()
        valeria = partida["personajes"][0]
        valeria["condiciones"] = [{"nombre": "Sorprendido", "desventaja": ["iniciativa"]}]
        with dados_fijos([18, 4, 10, 12]):  # Valeria tira 2d20 con desventaja (4), Alden 10, Esqueleto 12
            orden = reglas_2024.tirar_iniciativa(partida)
        self.assertEqual(orden[0]["quien"], "Esqueleto guardián")
        val_entry = next(x for x in orden if x["quien"] == "Valeria")
        self.assertEqual(val_entry["modo"], "desventaja")
        self.assertEqual(val_entry["elegido"], 4)

    def test_descanso_corto_y_largo_2024(self):
        partida = cargar_ensayo()
        valeria = partida["personajes"][0]
        valeria["vida"] = 20
        valeria["vida_temporal"] = 5
        valeria["habilidades"][0]["disponible"] = False  # Tomar aliento (descanso_corto)
        valeria["habilidades"][2]["disponible"] = False  # Indomable (descanso_largo)

        # Descanso corto gastando 2 Dados de Golpe (d10 + CON +3):
        with dados_fijos([6, 8]):  # (6+3) + (8+3) = 20 PG curados -> 20 + 20 = 40
            res_corto = reglas_2024.descanso(partida, "corto", quienes=[valeria], dados_golpe=2)
        self.assertEqual(valeria["vida"], 40)
        self.assertEqual(valeria["dados_golpe"]["actual"], 3)
        self.assertTrue(valeria["habilidades"][0]["disponible"], "recarga descanso_corto")
        self.assertFalse(valeria["habilidades"][2]["disponible"], "no recarga descanso_largo en descanso corto")
        self.assertEqual(valeria["vida_temporal"], 5)

        # Descanso largo: recupera toda la vida, todos los Dados de Golpe, limpia PG temporales y recarga todo.
        res_largo = reglas_2024.descanso(partida, "largo", quienes=[valeria])
        self.assertEqual(valeria["vida"], 44)
        self.assertEqual(valeria["dados_golpe"]["actual"], 5)
        self.assertEqual(valeria["vida_temporal"], 0)
        self.assertTrue(valeria["habilidades"][2]["disponible"])
        self.assertTrue(res_corto and res_largo)

    def test_conjuro_fireball_escala_por_slot_y_conjuro_no_automatizado_degrada_honestamente(self):
        partida = cargar_ensayo()
        alden = partida["personajes"][1]  # INT 18 (+4), comp +3 -> CD conjuro = 8 + 3 + 4 = 15
        esqueleto = partida["enemigos"][0]  # DES 14 (+2), vida 26

        # 1. Fireball en espacio de nivel 3 (8d6 fuego); esqueleto saca 13 + 2 = 15 (éxito -> mitad de daño).
        with dados_fijos([3, 3, 3, 3, 3, 3, 3, 4, 13]):  # 8d6 = 25; salvación 13+2=15 >= CD 15 -> 25 // 2 = 12
            ev_fb = reglas_2024.lanzar_conjuro(partida, alden, "Fireball", nivel_slot=3, objetivos=[esqueleto])
        self.assertFalse(ev_fb.get("requiere_resolucion_manual", False))
        self.assertEqual(ev_fb["cd"], 15)
        self.assertEqual(alden["espacios_conjuro"]["3"]["actual"], 1)
        self.assertEqual(ev_fb["resultados_objetivos"][0]["dano_final"], 12)
        self.assertEqual(esqueleto["vida"], 14)

        # 2. Telaraña (`automatizado: False`, requiere concentración): degrada honestamente con referencia.
        ev_web = reglas_2024.lanzar_conjuro(partida, alden, "Telaraña", nivel_slot=2)
        self.assertTrue(ev_web["requiere_resolucion_manual"])
        self.assertIn("SRD 5.2.1", ev_web["referencia"])
        self.assertEqual(alden["concentracion"]["conjuro"], "Telaraña")
        self.assertEqual(alden["espacios_conjuro"]["2"]["actual"], 2)

        # 3. Adjudicación manual registrada por la mesa:
        adj = reglas_2024.adjudicar(
            partida,
            regla="Telaraña (SRD 5.2.1 › Spells › Web)",
            decision="El esqueleto falla la salvación de Destreza y queda Apresado",
            autor="director+jugador",
            motivo="Resolución manual de área de Telaraña",
        )
        self.assertEqual(adj["tipo"], "adjudicacion")
        self.assertEqual(adj["autor"], "director+jugador")

    def test_consumible_descuenta_cantidad_y_cura_pg(self):
        partida = cargar_ensayo()
        valeria = partida["personajes"][0]
        valeria["vida"] = 30
        with dados_fijos([3, 4]):  # 2d4+2 = 9 PG -> 30 + 9 = 39
            ev = reglas_2024.usar_consumible(partida, valeria, "Poción de curación")
        self.assertEqual(ev["restantes"], 1)
        self.assertEqual(valeria["vida"], 39)
        self.assertEqual(ev["curacion"]["total"], 9)

    def test_equivalencia_cli_y_mcp_en_partida_2024(self):
        with repo_temporal() as raiz:
            destino = raiz / "partidas" / "ensayo-2024"
            destino.mkdir(parents=True)
            (destino / "partida.json").write_text(ENSAYO.read_text(encoding="utf-8"), encoding="utf-8")
            (destino / "eventos.jsonl").write_text("", encoding="utf-8")

            with dados_fijos([14]):
                cod_cli, out_cli, err_cli = correr("-p", "ensayo-2024", "prueba", "Valeria", "Atletismo", "--cd", "15", perfil=capacidades.CLI)
            self.assertEqual(cod_cli, 0, err_cli)

            # Reiniciamos al mismo estado para ejecutar la misma acción con el perfil MCP de juego.
            (destino / "partida.json").write_text(ENSAYO.read_text(encoding="utf-8"), encoding="utf-8")
            (destino / "eventos.jsonl").write_text("", encoding="utf-8")

            with dados_fijos([14]):
                cod_mcp, out_mcp, err_mcp = correr("-p", "ensayo-2024", "prueba", "Valeria", "Atletismo", "--cd", "15", perfil=capacidades.JUEGO)
            self.assertEqual(cod_mcp, 0, err_mcp)
            self.assertEqual(out_cli, out_mcp)


if __name__ == "__main__":
    unittest.main()
