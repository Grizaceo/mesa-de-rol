"""Tiradas, inventario y texto público que llegan por POST /api/tirar."""

from __future__ import annotations

from .. import bloqueo, chat, dados, esquemas, estado, reglas, reglas_2024, vista
from ..texto import con_signo, norm
from .http import Prohibido, _ajustar_ca, _bono_ca, _numero, _texto

class TiradasMixin:
    def _ficha_del_jugador(self, slug: str, datos: dict, quien) -> dict:
        """El PJ que actúa desde el visor: el anfitrión elige; un invitado, solo el suyo. Nunca un enemigo."""
        pjs = datos.get("personajes") or []
        if not pjs:
            raise ValueError("no hay personajes en la partida")
        if not self._es_anfitrion():
            propio = self._pj_reclamado(slug)
            if propio is None:
                raise Prohibido("elige tu personaje («Juego como») antes de tirar")
            if isinstance(quien, str) and quien.strip() and norm(quien) != norm(propio):
                raise Prohibido(f"en la sala actúas con {propio}: las fichas de los demás son suyas")
            quien = propio
        if not isinstance(quien, str) or not quien.strip():
            raise ValueError("falta «quien»: el personaje que actúa")
        clave = norm(quien)
        ficha = next((p for p in pjs if clave in {norm(p.get("nombre", "")), norm(p.get("id", ""))}), None)
        if ficha is None:
            raise ValueError(
                f"{quien.strip()[:40]!r} no es un PJ de esta partida (PJ: {', '.join(p['nombre'] for p in pjs)}); "
                "las fichas de los enemigos las lleva el narrador"
            )
        return ficha

    @staticmethod
    def _objeto(ficha: dict, nombre: str) -> dict:
        clave = norm(nombre or "")
        elegido = next((x for x in ficha.get("equipo") or [] if clave and norm(x.get("nombre", "")) == clave), None)
        if elegido is None:
            raise ValueError(f"no encuentro {nombre!r} en el inventario de {ficha['nombre']}")
        return elegido

    @staticmethod
    def _liberar_ranura(ficha: dict, elegido: dict) -> None:
        """Lo que ocupaba la misma ranura se guarda (y su bono de CA deja de contar)."""
        ranura = str(elegido.get("ranura") or "").strip()
        if not ranura:
            return
        for x in ficha.get("equipo") or []:
            if x is not elegido and x.get("equipado") and str(x.get("ranura") or "").strip() == ranura:
                x["equipado"] = False
                _ajustar_ca(ficha, -_bono_ca(x))

    @staticmethod
    def _texto_publico(pol: dict, evento: dict, texto: str) -> str:
        if evento.get("tipo") in ("prueba", "ataque"):
            return reglas.describir_prueba(vista.evento(pol, evento))
        return vista.texto(pol, texto)

    def _tirar_desde_visor(self, slug: str, cuerpo: dict) -> dict:
        accion = _texto(cuerpo, "accion", 30).lower() or "prueba"
        modo_req = _texto(cuerpo, "modo", 20).lower() or "normal"
        ventaja = "declarada" if modo_req == "ventaja" else False
        desventaja = "declarada" if modo_req == "desventaja" else False
        cd_raw = cuerpo.get("cd")
        if isinstance(cd_raw, str) and cd_raw.strip() and not cd_raw.strip().lstrip("-").isdigit():
            cd = cd_raw.strip()[:30]  # «exigente», «difícil»…: la resuelve el motor
        else:
            cd = _numero(cuerpo, "cd", minimo=1, maximo=40)
        etiqueta = _texto(cuerpo, "etiqueta", 80)

        with bloqueo.candado(estado.ruta_candado(slug)):
            datos = estado.cargar(slug)
            ficha = self._ficha_del_jugador(slug, datos, cuerpo.get("quien"))
            es_2024 = esquemas.version_de(datos) == esquemas.VERSION_2024

            if accion == "prueba":
                atributo = _texto(cuerpo, "atributo", 40) or "fuerza"
                salvacion = bool(cuerpo.get("salvacion")) and es_2024
                evento = reglas.prueba(
                    datos, ficha, atributo, cd=cd, ventaja=ventaja, desventaja=desventaja,
                    oficio=bool(cuerpo.get("oficio")), etiqueta=etiqueta, salvacion=salvacion,
                )
                texto = reglas.describir_prueba(evento)

            elif accion == "iniciativa":
                if es_2024:
                    # Se tira solo la de este PJ y se coloca en el orden que ya hubiera.
                    orden = reglas_2024.tirar_iniciativa(datos, quienes=[ficha], ventaja=ventaja, desventaja=desventaja, fusionar=True)
                    item = next(x for x in orden if x["quien"] == ficha["nombre"])
                    evento = {
                        "tipo": "prueba",
                        "reglamento": esquemas.REGLAMENTO_2024,
                        "quien": ficha["nombre"],
                        "atributo": "destreza",
                        "habilidad": "Iniciativa",
                        "etiqueta": etiqueta or "Iniciativa",
                        "partes": [{"fuente": "Destreza", "valor": item["modificador"]}],
                        "ventajas": item["ventajas"],
                        "desventajas": item["desventajas"],
                        "modo": item["modo"],
                        "caras": 20,
                        "valores": item["valores"],
                        "elegido": item["elegido"],
                        "modificador": item["modificador"],
                        "total": item["total"],
                        "cd": None,
                        "exito": None,
                        "resultado": "sin_cd",
                    }
                else:
                    evento = reglas.prueba(datos, ficha, "agilidad", ventaja=ventaja, desventaja=desventaja, etiqueta=etiqueta or "Iniciativa")
                texto = reglas.describir_prueba(evento)

            elif accion == "ataque":
                subtipo = _texto(cuerpo, "subtipo", 20).lower() or "arma"
                obj_req = _texto(cuerpo, "objetivo", 60)
                vivos = [e for e in datos.get("enemigos", []) if int(e.get("vida", 1) or 0) > 0]
                ca_practica = cd if isinstance(cd, int) else 12
                practica = {"nombre": "Objetivo", "defensa": ca_practica, "ca": ca_practica, "vida": 20, "vida_max": 20, "proteccion": 0}
                if obj_req:
                    # Por el nombre que ven los jugadores: el nombre real de un desconocido no se resuelve.
                    try:
                        objetivo = vista.resolver_objetivo(datos, obj_req)
                    except ValueError:
                        if vivos:
                            raise
                        objetivo = {**practica, "nombre": obj_req[:40]}
                elif vivos:
                    pol = vista.politica(datos)
                    raise ValueError("elige a quién atacas (Objetivo): " + ", ".join(vista.nombre_publico(pol, e["nombre"]) for e in vivos))
                else:
                    objetivo = practica
                if objetivo is ficha:
                    raise ValueError(f"{ficha['nombre']} no puede atacarse a sí mismo")

                armas = [a for a in (ficha.get("equipo") or []) if a.get("dano")]
                arma_nombre = _texto(cuerpo, "arma", 60) or None
                desarmado = {"nombre": "Golpe desarmado", "dano": "1", "tipo_dano": "contundente", "competente": True}
                attr_forzado = None
                arma_temporal = None
                if subtipo == "desarmado":
                    arma_temporal = desarmado
                elif subtipo == "distancia":
                    cand = next((a for a in armas if a.get("distancia")), None)
                    if cand is None:
                        raise ValueError(f"{ficha['nombre']} no lleva arma a distancia ni arrojadiza")
                    arma_nombre = cand["nombre"]
                elif subtipo == "cuerpo":
                    cand = next((a for a in armas if not a.get("distancia")), None)
                    if cand:
                        arma_nombre = cand["nombre"]
                    else:
                        arma_temporal = desarmado
                elif subtipo == "conjuro":
                    if es_2024:
                        attrs_f = ficha.get("atributos") or {}
                        mejor_mental = max(("inteligencia", "sabiduria", "carisma"), key=lambda k: int(attrs_f.get(k, 10)))
                        attr_forzado = str(ficha.get("atributo_conjuro") or mejor_mental)
                    else:
                        attr_forzado = "ingenio"
                    arma_temporal = {"nombre": "Conjuro de ataque", "dano": "1d8", "tipo_dano": "fuerza_magica", "distancia": True, "competente": True}
                    arma_nombre = "Conjuro de ataque"
                elif not armas and not arma_nombre:
                    arma_temporal = desarmado

                if arma_temporal is not None:
                    arma_nombre = arma_temporal["nombre"]
                    ficha.setdefault("equipo", []).append(arma_temporal)
                try:
                    evento = reglas.ataque(
                        datos, ficha, objetivo, arma=arma_nombre, ventaja=ventaja, desventaja=desventaja,
                        oficio=bool(cuerpo.get("oficio")), atributo=attr_forzado, etiqueta=etiqueta,
                    )
                finally:
                    if arma_temporal is not None and arma_temporal in ficha.get("equipo", []):
                        ficha["equipo"].remove(arma_temporal)
                texto = reglas.describir_prueba(evento)

            elif accion == "dano":
                critico = bool(cuerpo.get("critico"))
                expr = _texto(cuerpo, "expr", 60)
                arma_usada = None
                if expr:  # una expresión suelta se tira tal cual, sin modificador
                    r = reglas.dano(datos, expr, None, critico=critico)
                else:
                    arma_usada = reglas.buscar_arma(ficha, _texto(cuerpo, "arma", 60) or None)
                    if es_2024:  # SRD 5.2.1: el daño de un arma suma el modificador con el que se ataca
                        attr = reglas_2024.caracteristica_de_arma(ficha, arma_usada)
                        r = reglas_2024.dano(
                            datos, arma_usada["dano"], None, critico=critico, bonus_mod=reglas_2024.mod_caracteristica(ficha, attr),
                            fuente_mod=esquemas.NOMBRES_2024[attr], tipo_dano=arma_usada.get("tipo_dano"),
                        )
                    else:
                        r = reglas.dano(datos, arma_usada["dano"], None, critico=critico)
                evento = {"tipo": "dano", "quien": ficha["nombre"], "etiqueta": etiqueta or "Daño", **r["tirada"], "bruto": r["bruto"]}
                if arma_usada:
                    evento["arma"] = arma_usada["nombre"]
                if r.get("bonus_mod"):
                    evento.update(bonus_mod=r["bonus_mod"], fuente_mod=r.get("fuente_mod"))
                if r.get("tipo_dano"):
                    evento["tipo_dano"] = r["tipo_dano"]
                valores = " + ".join(str(v) for t in r["tirada"]["dados"] for v in t["valores"]) or str(r["tirada"]["total"])
                extra = f" {con_signo(r['bonus_mod'])} ({r.get('fuente_mod')})" if r.get("bonus_mod") else ""
                texto = f"Daño de {ficha['nombre']}: {r['tirada']['expr']} → {valores}{extra} = {r['bruto']}"

            elif accion == "dados_golpe":
                if not es_2024:
                    raise ValueError("d20-simple no usa Dados de Golpe: para curarse están el vendaje y los descansos")
                g = reglas_2024.gastar_dados_golpe(datos, ficha, 1)
                cv = g["vida"]
                expr_dg = f"1{g['dado']}{con_signo(g['mod_con']) if g['mod_con'] else ''}"
                evento = {
                    "tipo": "tirada",
                    "quien": ficha["nombre"],
                    "etiqueta": etiqueta or f"Dado de Golpe (quedan {g['restantes']}) · vida {cv['antes']} → {cv['despues']}/{cv['maximo']}",
                    "expr": expr_dg, "critico": False, "modificador": g["mod_con"], "total": g["curado"],
                    "dados": [{"dado": g["dado"], "signo": 1, "valores": g["valores"]}],
                }
                texto = f"{ficha['nombre']} · Dado de Golpe ({expr_dg}) = +{g['curado']} PG → vida {cv['antes']} → {cv['despues']}/{cv['maximo']}"

            elif accion == "salvacion_muerte":
                if not es_2024:
                    raise ValueError("d20-simple no tira salvaciones de muerte: a 0 de vida se queda Fuera de combate")
                if True:  # el motor rechaza a quien no está a 0 PG, está estable o ya murió
                    sm = reglas_2024.salvacion_muerte(datos, ficha)
                    evento = {
                        "tipo": "prueba",
                        "reglamento": esquemas.REGLAMENTO_2024,
                        "salvacion": True,
                        "quien": ficha["nombre"],
                        "atributo": "constitucion",
                        "habilidad": "Salvación de muerte",
                        "etiqueta": f"éxitos {sm['exitos']}/3 · fallos {sm['fallos']}/3",
                        "partes": [],
                        "ventajas": [],
                        "desventajas": [],
                        "modo": "normal",
                        "caras": 20,
                        "valores": [sm["valor"]],
                        "elegido": sm["valor"],
                        "modificador": 0,
                        "total": sm["valor"],
                        "cd": 10,
                        "exito": sm["valor"] >= 10,
                        "resultado": "critico" if sm["valor"] == 20 else ("uno_natural" if sm["valor"] == 1 else ("exito" if sm["valor"] >= 10 else "fallo")),
                    }
                    texto = f"{ficha['nombre']} · Salvación de muerte: 1d20 ({sm['valor']}) contra 10 → éxitos {sm['exitos']}/3, fallos {sm['fallos']}/3"

            elif accion == "descanso":
                clase = "largo" if _texto(cuerpo, "clase", 10).lower() == "largo" else "corto"
                if es_2024:
                    dg_gastar = 1 if (clase == "corto" and int(ficha.get("vida", 0)) < int(ficha.get("vida_max", 0))) else 0
                    lineas = reglas_2024.descanso(datos, clase, quienes=[ficha], dados_golpe=dg_gastar)
                else:
                    cambios = []
                    if clase == "largo":
                        v = reglas.aplicar_vida(ficha, int(ficha.get("vida_max", 0)))
                        if v["despues"] != v["antes"]:
                            cambios.append(f"vida {v['antes']} → {v['despues']}/{v['maximo']}")
                    if ficha.pop("vendaje_usado", None):
                        cambios.append("vendaje disponible")
                    recargas = {"descanso"} if clase == "corto" else {"descanso", "escena", "combate", "dia"}
                    for h in ficha.get("habilidades", []):
                        if h.get("recarga") in recargas and h.get("disponible") is False:
                            h["disponible"] = True
                            cambios.append(f"«{h['nombre']}» disponible")
                    lineas = [f"{ficha['nombre']}: {', '.join(cambios) or 'nada que recuperar'}"]
                evento = {"tipo": "descanso", "clase": clase, "quien": [ficha["nombre"]], "cambios": lineas}
                texto = f"Descanso {clase} · " + "; ".join(lineas)

            elif accion == "vida":
                delta = _numero(cuerpo, "delta", 0, minimo=-999, maximo=999)
                if cuerpo.get("temporal"):
                    cambio = reglas_2024.fijar_vida_temporal(ficha, max(0, delta))
                    evento = {"tipo": "vida_temporal", "quien": ficha["nombre"], "cantidad": max(0, delta), **cambio}
                    texto = f"{ficha['nombre']}: PG temporales {cambio['antes']} → {cambio['despues']}"
                else:
                    cambio = reglas.aplicar_vida(ficha, delta, partida=datos)
                    evento = {"tipo": "vida", "quien": ficha["nombre"], "delta": delta, "motivo": etiqueta or ("Curación" if delta >= 0 else "Daño"), **cambio}
                    texto = f"{ficha['nombre']}: vida {cambio['antes']} → {cambio['despues']}/{cambio['maximo']}"

            elif accion == "inspiracion":
                ficha["inspiracion"] = not bool(ficha.get("inspiracion"))
                estado_insp = "activada" if ficha["inspiracion"] else "gastada"
                evento = {"tipo": "nota", "texto": f"{ficha['nombre']}: Inspiración heroica {estado_insp}"}
                texto = evento["texto"]

            elif accion == "equipar":
                elegido = self._objeto(ficha, _texto(cuerpo, "nombre", 60))
                nuevo_estado = not bool(elegido.get("equipado"))
                if nuevo_estado:
                    self._liberar_ranura(ficha, elegido)
                elegido["equipado"] = nuevo_estado
                # La CA guardada es la que usa el motor: el escudo o la armadura la mueven al equiparse.
                _ajustar_ca(ficha, _bono_ca(elegido) if nuevo_estado else -_bono_ca(elegido))
                evento = {
                    "tipo": "nota",
                    "texto": f"{ficha['nombre']} {'equipa' if nuevo_estado else 'guarda'} «{elegido['nombre']}»",
                }
                texto = evento["texto"]

            elif accion == "agregar_item":
                nombre_item = _texto(cuerpo, "nombre", 60)
                if not nombre_item:
                    raise ValueError("falta el nombre del objeto")
                if len(ficha.get("equipo") or []) >= 200:
                    raise ValueError(f"el inventario de {ficha['nombre']} ya tiene 200 objetos")
                categoria = _texto(cuerpo, "categoria", 20).lower() or "gear"
                ranura = _texto(cuerpo, "ranura", 20).lower()
                nuevo_obj: dict = {
                    "nombre": nombre_item,
                    "categoria": categoria if categoria in ("weapon", "armor", "gear") else "gear",
                    "peso": _numero(cuerpo, "peso", 0.0, minimo=0, maximo=10_000, entero=False),
                    "valor": _numero(cuerpo, "valor", 0, minimo=0, maximo=1_000_000_000),
                    "cantidad": _numero(cuerpo, "cantidad", 1, minimo=1, maximo=999),
                    "equipado": bool(cuerpo.get("equipado", False)),
                }
                if ranura:
                    nuevo_obj["ranura"] = ranura
                dano_txt = _texto(cuerpo, "dano", 20)
                if dano_txt:
                    dados.analizar(dano_txt)  # una expresión que el motor no sabe tirar no entra en la ficha
                    nuevo_obj.update(dano=dano_txt, competente=True, categoria="weapon")
                    nuevo_obj.setdefault("ranura", "main_hand")
                if _texto(cuerpo, "tipo_dano", 30):
                    nuevo_obj["tipo_dano"] = _texto(cuerpo, "tipo_dano", 30)
                bono = _numero(cuerpo, "bono_ca", 0, minimo=-10, maximo=10)
                if bono:
                    nuevo_obj.update(bono_ca=bono, categoria="armor")
                    nuevo_obj.setdefault("ranura", "armor")
                if _texto(cuerpo, "efecto", 120):
                    nuevo_obj.update(efecto=_texto(cuerpo, "efecto", 120), consumible=True)
                if _texto(cuerpo, "texto", 160):
                    nuevo_obj["texto"] = _texto(cuerpo, "texto", 160)
                if nuevo_obj["equipado"]:
                    self._liberar_ranura(ficha, nuevo_obj)
                    _ajustar_ca(ficha, _bono_ca(nuevo_obj))
                ficha.setdefault("equipo", []).append(nuevo_obj)
                evento = {"tipo": "nota", "texto": f"{ficha['nombre']} añade «{nombre_item}» al inventario"}
                texto = evento["texto"]

            elif accion == "quitar_item":
                elegido = self._objeto(ficha, _texto(cuerpo, "nombre", 60))
                ficha["equipo"].remove(elegido)
                if elegido.get("equipado"):
                    _ajustar_ca(ficha, -_bono_ca(elegido))
                evento = {"tipo": "nota", "texto": f"{ficha['nombre']} descarta «{elegido['nombre']}»"}
                texto = evento["texto"]

            elif accion == "usar_item":
                res_uso = reglas_2024.usar_consumible(datos, ficha, _texto(cuerpo, "nombre", 60))
                cura_txt = f" (+{res_uso['curacion']['total']} PG)" if res_uso.get("curacion") else ""
                evento = {
                    "tipo": "nota",
                    "texto": f"{ficha['nombre']} usa «{res_uso['objeto']}»{cura_txt} (quedan {res_uso['restantes']})",
                }
                texto = evento["texto"]

            elif accion == "monedas":
                tipos = reglas_2024.monedas_de(datos.get("ambientacion") or {})  # las de la campaña, no oro por defecto
                previas = ficha.get("monedas") if isinstance(ficha.get("monedas"), dict) else {}
                mon = ficha["monedas"] = {k: int(previas.get(k, 0) or 0) for k in tipos}
                for k in tipos:
                    valor = _numero(cuerpo, k, minimo=0, maximo=1_000_000_000)
                    if valor is not None:
                        mon[k] = valor
                evento = {"tipo": "nota", "texto": f"{ficha['nombre']} actualiza su dinero: " + ", ".join(f"{v} {k}" for k, v in mon.items())}
                texto = evento["texto"]

            elif accion == "trasfondo":
                evento = self._aplicar_trasfondo(datos, ficha, cuerpo, es_2024)
                texto = evento["texto"]

            elif accion == "borrar_pj":
                # Un invitado solo borra el suyo (`_ficha_del_jugador`); el anfitrión, cualquiera.
                datos["personajes"].remove(ficha)
                escena = datos.get("escena") or {}
                escena["posiciones"] = [x for x in escena.get("posiciones") or [] if norm(str(x.get("quien", ""))) != norm(ficha["nombre"])]
                evento = {"tipo": "nota", "texto": f"{ficha['nombre']} deja la partida (ficha borrada)"}
                texto = evento["texto"]

            else:
                raise ValueError(f"acción de tirada desconocida: {accion!r}")

            (evento_guardado,) = estado.escribir(slug, datos=datos, eventos=[{**evento, "via": "visor"}])

        pol = vista.politica(datos)
        publico = self._texto_publico(pol, evento_guardado, texto)
        narrado = False
        if cuerpo.get("narrar") and getattr(self.server, "narrador", None) is not None:
            # Lo firma la mesa, no el PJ: es un aviso al narrador, no palabras del jugador. El chat
            # (público) guarda la versión que ven los jugadores; el narrador recibe la completa.
            try:
                self._narrador().enviar(
                    slug, f"[Tirada en la mesa · {publico}]", "Mesa",
                    texto_agente=f"[Tirada en la mesa · {texto}]" + (f" {etiqueta}" if etiqueta else ""),
                )
                narrado = True
            except chat.Ocupado:
                narrado = False

        return {"ok": True, "texto": publico, "evento": vista.evento(pol, evento_guardado), "narrado": narrado}
