"""tests/oc_presupuesto/test_service.py -- ranking de presupuestos candidatos
(design.md D2, D2.1, D3; tasks.md Phase 2, 2.2-2.5 y 2.12) y vinculación
renglón a renglón (design.md D4-D9, D12; tasks.md Phase 3, 3.1-3.9).

Confirmar RED antes de 2.6-2.10: `ModuleNotFoundError: No module named
'services.presupuestacion.oc_presupuesto'`.
"""

from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from services.presupuestacion.core.exceptions import NotFoundError, ValidationError
from services.presupuestacion.oc_presupuesto import repository as repo
from services.presupuestacion.oc_presupuesto import service

# =============================================================================
# 2.4 -- _q2: normalización de escala de precio (D3). Comparación siempre
# sobre Decimal, nunca sobre float.
# =============================================================================


def test_q2_normaliza_escala_109_750_igual_a_109_75():
    assert service._q2("109.750") == service._q2("109.75")
    assert str(service._q2("109.750")) == str(service._q2("109.75"))


def test_q2_siempre_devuelve_decimal():
    assert isinstance(service._q2("10"), Decimal)
    assert isinstance(service._q2(10.5), Decimal)


# =============================================================================
# 2.2 / 2.4 -- _rankear_presupuestos: función pura, sin cliente Supabase.
# =============================================================================


def _presupuesto(
    id_: str,
    *,
    proceso_comercial_id: str = "proc-1",
    estado: str = "generado",
    generado_at: str = "2026-01-01T00:00:00+00:00",
    cantidad_items: int = 1,
) -> dict:
    return {
        "id": id_,
        "proceso_comercial_id": proceso_comercial_id,
        "estado": estado,
        "generado_at": generado_at,
        "cantidad_items": cantidad_items,
    }


def _item(presupuesto_id: str, precio: str | None) -> dict:
    return {"presupuesto_id": presupuesto_id, "precio_unitario": precio}


def test_rankear_ordena_por_cantidad_de_coincidencias_desc():
    presupuestos = [_presupuesto("A"), _presupuesto("B"), _presupuesto("C")]
    items = [_item("A", "100.00"), _item("A", "200.00"), _item("B", "100.00")]
    precios_oc = [Decimal("100.00"), Decimal("200.00")]

    resultado = service._rankear_presupuestos(presupuestos, items, precios_oc)

    puntajes = {presupuesto["id"]: score for presupuesto, score in resultado}
    assert [presupuesto["id"] for presupuesto, _ in resultado] == ["A", "B", "C"]
    assert puntajes == {"A": 2, "B": 1, "C": 0}


def test_rankear_desempata_por_generado_at_desc_luego_presupuesto_id_asc():
    presupuestos = [
        _presupuesto("Z", generado_at="2026-01-01T00:00:00+00:00"),
        _presupuesto("A", generado_at="2026-06-01T00:00:00+00:00"),
        _presupuesto("M", generado_at="2026-06-01T00:00:00+00:00"),
    ]
    items = [_item("Z", "50.00"), _item("A", "50.00"), _item("M", "50.00")]
    precios_oc = [Decimal("50.00")]

    resultado = service._rankear_presupuestos(presupuestos, items, precios_oc)

    # A y M empatan en puntaje (1) y generado_at -- desempate final determinista
    # por presupuesto_id ASC (D2).
    assert [presupuesto["id"] for presupuesto, _ in resultado] == ["A", "M", "Z"]


def test_rankear_precio_unitario_none_en_presupuesto_item_queda_fuera_sin_romper():
    # C4: presupuesto_items.precio_unitario es nullable. Un None no debe
    # lanzar excepción ni contar como coincidencia.
    presupuestos = [_presupuesto("A")]
    items = [_item("A", None), _item("A", "100.00")]
    precios_oc = [Decimal("100.00")]

    resultado = service._rankear_presupuestos(presupuestos, items, precios_oc)

    assert resultado[0][1] == 1


def test_rankear_cuenta_renglones_de_oc_no_presupuesto_items_repetidos():
    # Dos renglones de OC con el MISMO precio, un solo presupuesto_item con
    # ese precio -> el puntaje es 2 (una vez por renglón de OC que matchea),
    # no 1 -- el puntaje es sobre renglones de LA OC, no sobre presupuesto_items.
    presupuestos = [_presupuesto("A")]
    items = [_item("A", "100.00")]
    precios_oc = [Decimal("100.00"), Decimal("100.00")]

    resultado = service._rankear_presupuestos(presupuestos, items, precios_oc)

    assert resultado[0][1] == 2


def test_rankear_presupuesto_sin_ningun_item_puntua_cero_sin_excepcion():
    # spec oc-presupuesto-candidato § "Ningún renglón de la OC coincide en
    # precio con un presupuesto dado": no se excluye, aparece con puntaje 0.
    presupuestos = [_presupuesto("A"), _presupuesto("B")]
    items = [_item("A", "100.00")]
    precios_oc = [Decimal("100.00")]

    resultado = service._rankear_presupuestos(presupuestos, items, precios_oc)

    puntajes = {presupuesto["id"]: score for presupuesto, score in resultado}
    assert puntajes["B"] == 0
    assert "B" in puntajes  # no se excluye del resultado de la función pura


# =============================================================================
# 2.5 -- troceo de in_() en lotes de 200 (D3): 450 ids -> 3 llamadas al
# cliente Supabase mockeado, concatenación de resultados intacta.
# =============================================================================


def test_en_lotes_de_450_ids_produce_3_lotes_de_200_200_50():
    ids = [f"id-{i}" for i in range(450)]

    lotes = list(repo._en_lotes(ids))

    assert [len(lote) for lote in lotes] == [200, 200, 50]
    assert [item for lote in lotes for item in lote] == ids  # concatenación intacta


def test_listar_presupuestos_de_procesos_trocea_450_ids_en_3_llamadas_al_cliente_mockeado():
    proceso_ids = [f"proc-{i}" for i in range(450)]
    lotes_recibidos: list[list[str]] = []

    def _fake_in_(columna: str, lote: list[str]):
        assert columna == "proceso_comercial_id"
        lotes_recibidos.append(lote)
        query = MagicMock()
        resultado = MagicMock()
        resultado.data = [{"id": f"presupuesto-de-{pid}"} for pid in lote]
        query.execute.return_value = resultado
        return query

    client = MagicMock()
    client.table.return_value.select.return_value.in_.side_effect = _fake_in_

    resultado = repo.listar_presupuestos_de_procesos(client, proceso_comercial_ids=proceso_ids)

    assert len(lotes_recibidos) == 3
    assert [len(lote) for lote in lotes_recibidos] == [200, 200, 50]
    assert len(resultado) == 450  # concatenación de las 3 llamadas, intacta


def test_listar_presupuesto_items_por_precio_excluye_excluido_true():
    # C4: excluido = TRUE nunca puede ser el origen de un match -- se verifica
    # que la query efectivamente pide excluido = FALSE al cliente mockeado.
    llamadas_eq: list[tuple] = []

    query_final = MagicMock()
    query_final.execute.return_value = MagicMock(data=[])

    def _fake_eq(columna, valor):
        llamadas_eq.append((columna, valor))
        return query_final

    client = MagicMock()
    cadena = client.table.return_value.select.return_value.in_.return_value.in_.return_value
    cadena.eq.side_effect = _fake_eq

    repo.listar_presupuesto_items_por_precio(
        client, presupuesto_ids=["p1"], precios=["100.00"]
    )

    assert ("excluido", False) in llamadas_eq


# =============================================================================
# 2.3 -- rankear_presupuestos_candidatos: casos vacíos de D2 (HTTP 200 en los
# 3 casos salvo el anclaje por proceso comercial, que es 422).
# =============================================================================


def _stub_oc(*, cliente_id: str | None = "cli-1") -> dict:
    return {"id": "oc-1", "drogueria_id": "d1", "cliente_id": cliente_id, "numero_oc": "OC-1"}


def _parchear_dependencias_basicas(monkeypatch, *, oc: dict, oc_items: list[dict]):
    monkeypatch.setattr(repo, "buscar_orden_compra", lambda client, **kw: oc)
    monkeypatch.setattr(
        service.terceros_api,
        "obtener_tercero",
        lambda client, **kw: {"razon_social": "Cliente de Test"},
    )
    monkeypatch.setattr(repo, "listar_oc_items_precios", lambda client, **kw: oc_items)
    monkeypatch.setattr(service, "get_service_client", lambda: MagicMock())
    monkeypatch.setattr(repo, "buscar_numeros_presupuesto_legacy", lambda client, **kw: {})


def test_cliente_sin_ningun_presupuesto_devuelve_candidatos_vacio_con_advertencia_a(monkeypatch):
    _parchear_dependencias_basicas(
        monkeypatch, oc=_stub_oc(), oc_items=[{"id": "i1", "precio_unitario": "100.00"}]
    )
    monkeypatch.setattr(repo, "listar_procesos_comerciales_del_cliente", lambda client, **kw: [])
    monkeypatch.setattr(repo, "listar_presupuestos_de_procesos", lambda client, **kw: [])

    resultado = service.rankear_presupuestos_candidatos(
        MagicMock(), orden_compra_id="oc-1", drogueria_id="d1"
    )

    assert resultado.candidatos == []
    assert resultado.presupuestos_del_cliente == 0
    assert resultado.presupuesto_sugerido_id is None
    assert len(resultado.advertencias) == 1


def test_cliente_con_presupuestos_pero_ninguno_coincide_devuelve_candidatos_vacio_con_advertencia_b(
    monkeypatch,
):
    _parchear_dependencias_basicas(
        monkeypatch, oc=_stub_oc(), oc_items=[{"id": "i1", "precio_unitario": "100.00"}]
    )
    monkeypatch.setattr(
        repo,
        "listar_procesos_comerciales_del_cliente",
        lambda client, **kw: [{"id": "proc-A", "nombre": "Proceso A"}],
    )
    monkeypatch.setattr(
        repo, "listar_presupuestos_de_procesos", lambda client, **kw: [_presupuesto("A")]
    )
    monkeypatch.setattr(
        repo,
        "listar_presupuesto_items_por_precio",
        lambda client, **kw: [_item("A", "999.99")],  # no coincide con 100.00
    )

    resultado = service.rankear_presupuestos_candidatos(
        MagicMock(), orden_compra_id="oc-1", drogueria_id="d1"
    )

    assert resultado.candidatos == []
    assert resultado.presupuestos_del_cliente == 1
    assert resultado.presupuesto_sugerido_id is None
    assert len(resultado.advertencias) == 1
    # Las dos advertencias (sin presupuestos vs. ninguno coincide) son distintas
    # entre sí -- confirmado en test_advertencia_sin_presupuestos_es_distinta_de_advertencia_ninguno_coincide.


def test_advertencia_sin_presupuestos_es_distinta_de_advertencia_ninguno_coincide(monkeypatch):
    _parchear_dependencias_basicas(
        monkeypatch, oc=_stub_oc(), oc_items=[{"id": "i1", "precio_unitario": "100.00"}]
    )

    monkeypatch.setattr(repo, "listar_procesos_comerciales_del_cliente", lambda client, **kw: [])
    monkeypatch.setattr(repo, "listar_presupuestos_de_procesos", lambda client, **kw: [])
    sin_presupuestos = service.rankear_presupuestos_candidatos(
        MagicMock(), orden_compra_id="oc-1", drogueria_id="d1"
    )

    monkeypatch.setattr(
        repo,
        "listar_procesos_comerciales_del_cliente",
        lambda client, **kw: [{"id": "proc-A", "nombre": "Proceso A"}],
    )
    monkeypatch.setattr(
        repo, "listar_presupuestos_de_procesos", lambda client, **kw: [_presupuesto("A")]
    )
    monkeypatch.setattr(
        repo, "listar_presupuesto_items_por_precio", lambda client, **kw: [_item("A", "999.99")]
    )
    ninguno_coincide = service.rankear_presupuestos_candidatos(
        MagicMock(), orden_compra_id="oc-1", drogueria_id="d1"
    )

    assert sin_presupuestos.advertencias != ninguno_coincide.advertencias


def test_oc_anclada_por_proceso_comercial_sin_cliente_levanta_validation_error(monkeypatch):
    monkeypatch.setattr(repo, "buscar_orden_compra", lambda client, **kw: _stub_oc(cliente_id=None))

    with pytest.raises(ValidationError):
        service.rankear_presupuestos_candidatos(
            MagicMock(), orden_compra_id="oc-1", drogueria_id="d1"
        )


def test_orden_compra_inexistente_levanta_not_found_error(monkeypatch):
    monkeypatch.setattr(repo, "buscar_orden_compra", lambda client, **kw: None)

    with pytest.raises(NotFoundError):
        service.rankear_presupuestos_candidatos(
            MagicMock(), orden_compra_id="oc-inexistente", drogueria_id="d1"
        )


# =============================================================================
# 2.2 -- tope de 5 aplicado DESPUÉS de ordenar; 0 coincidencias sigue
# apareciendo (no se excluye) cuando hay al menos un presupuesto que sí
# puntúa; presupuesto_sugerido_id = candidatos[0], sin autoconfirmar nada.
# =============================================================================


def test_tope_de_5_aplicado_despues_de_ordenar_no_esconde_al_mejor(monkeypatch):
    _parchear_dependencias_basicas(
        monkeypatch, oc=_stub_oc(), oc_items=[{"id": "i1", "precio_unitario": "100.00"}]
    )
    # 7 presupuestos candidatos; solo "MEJOR" puntúa (score=1), los otros 6
    # puntúan 0 -- el tope de 5 debe incluir a "MEJOR" siempre, sin importar
    # en qué posición alfabética caiga.
    presupuestos = [_presupuesto("MEJOR")] + [_presupuesto(f"P{i}") for i in range(6)]
    monkeypatch.setattr(
        repo,
        "listar_procesos_comerciales_del_cliente",
        lambda client, **kw: [{"id": "proc-1", "nombre": "Proceso"}],
    )
    monkeypatch.setattr(repo, "listar_presupuestos_de_procesos", lambda client, **kw: presupuestos)
    monkeypatch.setattr(
        repo, "listar_presupuesto_items_por_precio", lambda client, **kw: [_item("MEJOR", "100.00")]
    )

    resultado = service.rankear_presupuestos_candidatos(
        MagicMock(), orden_compra_id="oc-1", drogueria_id="d1"
    )

    assert len(resultado.candidatos) == 5
    assert resultado.candidatos[0].presupuesto_id == "MEJOR"
    assert resultado.presupuesto_sugerido_id == "MEJOR"
    # La cola de candidatos con score 0 SIGUE apareciendo (no se excluye) --
    # spec § "Ningún renglón... coincide en precio con un presupuesto dado".
    assert any(c.renglones_oc_con_coincidencia == 0 for c in resultado.candidatos[1:])


def test_presupuesto_sugerido_id_nunca_autoconfirma_incluso_con_un_solo_candidato(monkeypatch):
    _parchear_dependencias_basicas(
        monkeypatch, oc=_stub_oc(), oc_items=[{"id": "i1", "precio_unitario": "100.00"}]
    )
    monkeypatch.setattr(
        repo,
        "listar_procesos_comerciales_del_cliente",
        lambda client, **kw: [{"id": "proc-1", "nombre": "Proceso"}],
    )
    monkeypatch.setattr(
        repo, "listar_presupuestos_de_procesos", lambda client, **kw: [_presupuesto("UNICO")]
    )
    monkeypatch.setattr(
        repo, "listar_presupuesto_items_por_precio", lambda client, **kw: [_item("UNICO", "100.00")]
    )

    resultado = service.rankear_presupuestos_candidatos(
        MagicMock(), orden_compra_id="oc-1", drogueria_id="d1"
    )

    # spec § "Selección explícita del presupuesto por el usuario": el sistema
    # lo sugiere (presupuesto_sugerido_id), pero eso NO es un vínculo -- el
    # modelo no expone ningún campo de "elegido"/"confirmado" acá, la
    # elección la hace el usuario en una llamada posterior (Phase 3, D8).
    assert resultado.presupuesto_sugerido_id == "UNICO"
    assert len(resultado.candidatos) == 1


# =============================================================================
# 2.12 -- integración: fixture real SAMCo Rafaela contra el proyecto Supabase
# de test.
# =============================================================================


@pytest.mark.integration
def test_ranking_integracion_samco_rafaela_pone_el_presupuesto_primero_con_2_coincidencias(
    service_client, seed_drogueria, seed_caso_samco_rafaela
):
    resultado = service.rankear_presupuestos_candidatos(
        service_client,
        orden_compra_id=seed_caso_samco_rafaela["orden_compra_id"],
        drogueria_id=seed_drogueria["id"],
    )

    assert resultado.presupuestos_del_cliente == 1
    assert len(resultado.candidatos) == 1
    candidato = resultado.candidatos[0]
    assert candidato.presupuesto_id == seed_caso_samco_rafaela["presupuesto_id"]
    assert candidato.renglones_oc_con_coincidencia == 2
    assert candidato.renglones_oc_totales == 2
    # Cargado a mano (sin presupuesto_legacy_map) -- D2.1: numero_presupuesto
    # viaja null por diseño, no por dato faltante.
    assert candidato.numero_presupuesto is None
    assert resultado.presupuesto_sugerido_id == seed_caso_samco_rafaela["presupuesto_id"]


# =============================================================================
# Phase 3 -- vinculación renglón a renglón (design.md D4-D9, D12).
# =============================================================================


def _stub_oc_item(**overrides) -> dict:
    base = {
        "id": "oci-1",
        "orden_compra_id": "oc-1",
        "drogueria_id": "d1",
        "numero_renglon": 1,
        "descripcion": "Renglón de test",
        "cantidad": "10",
        "precio_unitario": "100.00",
        "producto_id": None,
        "presupuesto_item_id": None,
        "vinculo_descartado": False,
        "vinculo_origen": None,
        "vinculo_confirmado_por": None,
        "vinculo_confirmado_at": None,
    }
    base.update(overrides)
    return base


def _stub_presupuesto_item(**overrides) -> dict:
    base = {
        "id": "pi-1",
        "presupuesto_id": "pres-1",
        "item_proceso_id": "ip-1",
        "producto_id": "prod-1",
        "precio_unitario": "100.00",
        "cantidad_ofertada": "10",
        "excluido": False,
    }
    base.update(overrides)
    return base


# -----------------------------------------------------------------------
# 3.2 -- _ordenar_por_similitud (D7): ordena, NUNCA filtra por score; None
# con un solo candidato; reusa normalizar_descripcion tal cual.
# -----------------------------------------------------------------------


def test_ordenar_por_similitud_ordena_descendente_por_wratio():
    candidatos = {
        "pi-exacto": "AMOXICILINA 500MG X 21 COMPRIMIDOS",
        "pi-parecido": "AMOXICILINA 500 MG COMP",
        "pi-lejano": "IBUPROFENO 600MG",
    }
    resultado = service._ordenar_por_similitud("Amoxicilina 500mg x 21 comprimidos", candidatos)
    ids_en_orden = [pid for pid, _ in resultado]
    assert ids_en_orden[0] == "pi-exacto"
    assert len(resultado) == 3


def test_ordenar_por_similitud_no_filtra_incluye_scores_bajos():
    # Ejemplo real de design.md D7: HCT 50MG X30 puntúa muy por debajo de 70
    # contra HIDROCLOROTIAZIDA 50MG COMP, pero SIGUE apareciendo -- el precio
    # ya hizo la selección, la similitud solo ordena.
    candidatos = {
        "pi-otra-forma": "HCT 50MG X30",
        "pi-literal": "HIDROCLOROTIAZIDA 50MG COMP",
    }
    resultado = service._ordenar_por_similitud("HIDROCLOROTIAZIDA 50MG COMP", candidatos)
    assert {pid for pid, _ in resultado} == {"pi-otra-forma", "pi-literal"}  # ninguno se esconde


def test_ordenar_por_similitud_none_con_un_solo_candidato():
    resultado = service._ordenar_por_similitud("cualquier cosa", {"pi-unico": "otra descripcion"})
    assert resultado == [("pi-unico", None)]


def test_ordenar_por_similitud_reusa_normalizar_descripcion_sin_parametrizar(monkeypatch):
    llamadas: list[str] = []
    original = service.normalizar_descripcion

    def _espia(texto):
        llamadas.append(texto)
        return original(texto)

    monkeypatch.setattr(service, "normalizar_descripcion", _espia)
    service._ordenar_por_similitud("Á é", {"pi-1": "descripción Ñ", "pi-2": "otra"})
    assert "Á é" in llamadas


# -----------------------------------------------------------------------
# 3.3 -- herencia de producto_id (D6): COALESCE(presupuesto_items.producto_id,
# items_proceso.producto_id), los 4 casos, ninguno lanza excepción.
# -----------------------------------------------------------------------


def test_heredar_producto_id_ambos_presentes_gana_presupuesto():
    resultado = service._heredar_producto_id(
        {"producto_id": "prod-presupuesto"}, {"producto_id": "prod-item-proceso"}
    )
    assert resultado == "prod-presupuesto"


def test_heredar_producto_id_solo_presupuesto():
    resultado = service._heredar_producto_id(
        {"producto_id": "prod-presupuesto"}, {"producto_id": None}
    )
    assert resultado == "prod-presupuesto"


def test_heredar_producto_id_solo_item_proceso():
    resultado = service._heredar_producto_id(
        {"producto_id": None}, {"producto_id": "prod-item-proceso"}
    )
    assert resultado == "prod-item-proceso"


def test_heredar_producto_id_ninguno_devuelve_none_sin_excepcion():
    resultado = service._heredar_producto_id({"producto_id": None}, {"producto_id": None})
    assert resultado is None


def test_heredar_producto_id_item_proceso_none_no_rompe():
    resultado = service._heredar_producto_id({"producto_id": None}, None)
    assert resultado is None


# -----------------------------------------------------------------------
# _derivar_estado (D4): el estado de 3 valores se DERIVA, no se guarda.
# -----------------------------------------------------------------------


def test_derivar_estado_los_tres_valores():
    assert service._derivar_estado(None, False) == "pendiente"
    assert service._derivar_estado(None, True) == "sin_presupuesto"
    assert service._derivar_estado("pi-1", False) == "confirmado"


# -----------------------------------------------------------------------
# 3.7 -- aviso N:1 (D5): alcance TODA la droguería, nunca bloquea.
# -----------------------------------------------------------------------


def test_agregar_aviso_n1_cuenta_total_otras_oc_y_suma_cantidad():
    oc_items_vinculados = [
        {"id": "a", "orden_compra_id": "oc-1", "presupuesto_item_id": "pi-1", "cantidad": "3"},
        {"id": "b", "orden_compra_id": "oc-2", "presupuesto_item_id": "pi-1", "cantidad": "5"},
    ]
    resultado = service._agregar_aviso_n1(oc_items_vinculados, orden_compra_id="oc-1")
    assert resultado["pi-1"]["total"] == 2
    assert resultado["pi-1"]["otras_oc"] == 1  # solo "oc-2" es otra OC
    assert resultado["pi-1"]["cantidad"] == Decimal("8")


def test_agregar_aviso_n1_lista_vacia_no_lanza_excepcion():
    assert service._agregar_aviso_n1([], orden_compra_id="oc-1") == {}


# -----------------------------------------------------------------------
# 3.1 -- _resolver_presupuesto_activo (D8): vínculos confirmados > query
# param > sugerido del ranking. Invariante duro verificado, no asumido.
# -----------------------------------------------------------------------


def test_resolver_presupuesto_prioriza_vinculos_confirmados_sobre_query_param(monkeypatch):
    oc_items = [_stub_oc_item(presupuesto_item_id="pi-1"), _stub_oc_item(id="oci-2")]
    monkeypatch.setattr(
        repo,
        "listar_presupuesto_items_por_ids",
        lambda client, **kw: [{"id": "pi-1", "presupuesto_id": "PRES-CONFIRMADO"}],
    )

    presupuesto_id, advertencia = service._resolver_presupuesto_activo(
        MagicMock(),
        drogueria_id="d1",
        cliente_id="cli-1",
        oc_items=oc_items,
        presupuesto_id_query="PRES-QUERY",
    )

    assert presupuesto_id == "PRES-CONFIRMADO"
    assert advertencia is None


def test_resolver_presupuesto_usa_query_param_si_no_hay_vinculos_confirmados():
    presupuesto_id, advertencia = service._resolver_presupuesto_activo(
        MagicMock(),
        drogueria_id="d1",
        cliente_id="cli-1",
        oc_items=[_stub_oc_item()],
        presupuesto_id_query="PRES-QUERY",
    )

    assert presupuesto_id == "PRES-QUERY"
    assert advertencia is None


def test_resolver_presupuesto_cae_al_sugerido_del_ranking_sin_vinculos_ni_query(monkeypatch):
    monkeypatch.setattr(
        service, "_top_presupuesto_sugerido", lambda client, **kw: (2, "PRES-SUGERIDO")
    )

    presupuesto_id, advertencia = service._resolver_presupuesto_activo(
        MagicMock(),
        drogueria_id="d1",
        cliente_id="cli-1",
        oc_items=[_stub_oc_item()],
        presupuesto_id_query=None,
    )

    assert presupuesto_id == "PRES-SUGERIDO"
    assert advertencia is None


def test_resolver_presupuesto_sin_candidatos_de_ranking_advierte_segun_si_tiene_presupuestos(
    monkeypatch,
):
    monkeypatch.setattr(service, "_top_presupuesto_sugerido", lambda client, **kw: (0, None))
    presupuesto_id, advertencia = service._resolver_presupuesto_activo(
        MagicMock(), drogueria_id="d1", cliente_id="cli-1", oc_items=[_stub_oc_item()],
        presupuesto_id_query=None,
    )
    assert presupuesto_id is None
    assert "no tiene presupuestos" in advertencia

    monkeypatch.setattr(service, "_top_presupuesto_sugerido", lambda client, **kw: (3, None))
    presupuesto_id, advertencia = service._resolver_presupuesto_activo(
        MagicMock(), drogueria_id="d1", cliente_id="cli-1", oc_items=[_stub_oc_item()],
        presupuesto_id_query=None,
    )
    assert presupuesto_id is None
    assert "3 presupuesto" in advertencia


def test_invariante_vinculos_confirmados_de_distintos_presupuestos_levanta_validation_error(
    monkeypatch,
):
    # No debería pasar nunca en la práctica (confirmar_vinculo lo impide antes
    # de escribir), pero obtener_matching lo verifica también al leer (D8).
    monkeypatch.setattr(
        repo,
        "listar_presupuesto_items_por_ids",
        lambda client, **kw: [
            {"id": "pi-1", "presupuesto_id": "A"},
            {"id": "pi-2", "presupuesto_id": "B"},
        ],
    )
    oc_items = [
        _stub_oc_item(presupuesto_item_id="pi-1"),
        _stub_oc_item(id="oci-2", presupuesto_item_id="pi-2"),
    ]

    with pytest.raises(ValidationError):
        service._resolver_presupuesto_activo(
            MagicMock(),
            drogueria_id="d1",
            cliente_id="cli-1",
            oc_items=oc_items,
            presupuesto_id_query=None,
        )


# -----------------------------------------------------------------------
# obtener_matching -- ensamblado completo (D8, D5, candidatos solo en
# pendiente).
# -----------------------------------------------------------------------


def test_obtener_matching_orden_compra_inexistente_levanta_not_found(monkeypatch):
    monkeypatch.setattr(repo, "buscar_orden_compra", lambda client, **kw: None)
    with pytest.raises(NotFoundError):
        service.obtener_matching(
            MagicMock(), orden_compra_id="oc-x", drogueria_id="d1", presupuesto_id=None
        )


def test_obtener_matching_oc_anclada_por_proceso_comercial_levanta_validation_error(monkeypatch):
    monkeypatch.setattr(repo, "buscar_orden_compra", lambda client, **kw: _stub_oc(cliente_id=None))
    with pytest.raises(ValidationError):
        service.obtener_matching(
            MagicMock(), orden_compra_id="oc-1", drogueria_id="d1", presupuesto_id=None
        )


def _parchear_dependencias_obtener_matching(
    monkeypatch,
    *,
    oc_items: list[dict],
    presupuesto_activo: tuple,
    presupuesto_items: list[dict],
    items_proceso: list[dict],
    oc_items_vinculados: list[dict] | None = None,
):
    monkeypatch.setattr(repo, "buscar_orden_compra", lambda client, **kw: _stub_oc())
    monkeypatch.setattr(repo, "listar_oc_items_completos", lambda client, **kw: oc_items)
    monkeypatch.setattr(service, "_resolver_presupuesto_activo", lambda client, **kw: presupuesto_activo)
    monkeypatch.setattr(
        service.presupuestos_repo, "listar_items_presupuesto", lambda client, **kw: presupuesto_items
    )
    monkeypatch.setattr(repo, "listar_items_proceso_por_ids", lambda client, **kw: items_proceso)
    monkeypatch.setattr(
        repo, "listar_oc_items_por_presupuesto_item_ids", lambda client, **kw: oc_items_vinculados or []
    )


def test_obtener_matching_devuelve_candidato_unico_sin_desempate(monkeypatch):
    _parchear_dependencias_obtener_matching(
        monkeypatch,
        oc_items=[_stub_oc_item(precio_unitario="100.00", descripcion="Renglón OC")],
        presupuesto_activo=("pres-1", None),
        presupuesto_items=[_stub_presupuesto_item(precio_unitario="100.00")],
        items_proceso=[
            {"id": "ip-1", "descripcion": "Item de presupuesto", "numero_renglon": 1, "producto_id": None}
        ],
    )

    resultado = service.obtener_matching(
        MagicMock(), orden_compra_id="oc-1", drogueria_id="d1", presupuesto_id=None
    )

    assert resultado.presupuesto_id == "pres-1"
    renglon = resultado.renglones_oc[0]
    assert renglon.estado == "pendiente"
    assert len(renglon.candidatos) == 1
    assert renglon.candidatos[0].presupuesto_item_id == "pi-1"
    assert renglon.candidatos[0].similitud is None  # un solo candidato: nada que desempatar


def test_obtener_matching_sin_match_de_precio_queda_pendiente_sin_candidatos(monkeypatch):
    _parchear_dependencias_obtener_matching(
        monkeypatch,
        oc_items=[_stub_oc_item(precio_unitario="999.99")],
        presupuesto_activo=("pres-1", None),
        presupuesto_items=[_stub_presupuesto_item(precio_unitario="100.00")],
        items_proceso=[{"id": "ip-1", "descripcion": "x", "numero_renglon": 1, "producto_id": None}],
    )

    resultado = service.obtener_matching(
        MagicMock(), orden_compra_id="oc-1", drogueria_id="d1", presupuesto_id=None
    )

    renglon = resultado.renglones_oc[0]
    assert renglon.estado == "pendiente"
    assert renglon.candidatos == []


def test_obtener_matching_renglon_confirmado_no_calcula_candidatos(monkeypatch):
    _parchear_dependencias_obtener_matching(
        monkeypatch,
        oc_items=[
            _stub_oc_item(
                presupuesto_item_id="pi-1", producto_id="prod-1", vinculo_origen="precio_exacto"
            )
        ],
        presupuesto_activo=("pres-1", None),
        presupuesto_items=[_stub_presupuesto_item(precio_unitario="100.00")],
        items_proceso=[{"id": "ip-1", "descripcion": "x", "numero_renglon": 1, "producto_id": None}],
    )

    resultado = service.obtener_matching(
        MagicMock(), orden_compra_id="oc-1", drogueria_id="d1", presupuesto_id=None
    )

    renglon = resultado.renglones_oc[0]
    assert renglon.estado == "confirmado"
    assert renglon.candidatos == []  # solo pendiente calcula candidatos


def test_obtener_matching_renglon_descartado_expone_sin_presupuesto(monkeypatch):
    _parchear_dependencias_obtener_matching(
        monkeypatch,
        oc_items=[_stub_oc_item(vinculo_descartado=True)],
        presupuesto_activo=("pres-1", None),
        presupuesto_items=[_stub_presupuesto_item(precio_unitario="100.00")],
        items_proceso=[{"id": "ip-1", "descripcion": "x", "numero_renglon": 1, "producto_id": None}],
    )

    resultado = service.obtener_matching(
        MagicMock(), orden_compra_id="oc-1", drogueria_id="d1", presupuesto_id=None
    )

    assert resultado.renglones_oc[0].estado == "sin_presupuesto"


def test_obtener_matching_aviso_n1_viaja_en_renglon_presupuesto(monkeypatch):
    _parchear_dependencias_obtener_matching(
        monkeypatch,
        oc_items=[_stub_oc_item(precio_unitario="100.00")],
        presupuesto_activo=("pres-1", None),
        presupuesto_items=[_stub_presupuesto_item(precio_unitario="100.00", cantidad_ofertada="7")],
        items_proceso=[{"id": "ip-1", "descripcion": "x", "numero_renglon": 1, "producto_id": None}],
        oc_items_vinculados=[
            {"id": "a", "orden_compra_id": "oc-1", "presupuesto_item_id": "pi-1", "cantidad": "10"},
            {"id": "b", "orden_compra_id": "OTRA-OC", "presupuesto_item_id": "pi-1", "cantidad": "5"},
        ],
    )

    resultado = service.obtener_matching(
        MagicMock(), orden_compra_id="oc-1", drogueria_id="d1", presupuesto_id=None
    )

    renglon_presupuesto = resultado.renglones_presupuesto[0]
    assert renglon_presupuesto.renglones_oc_vinculados == 2
    assert renglon_presupuesto.renglones_oc_vinculados_otras_oc == 1
    assert renglon_presupuesto.cantidad_vinculada == Decimal("15")


def test_obtener_matching_sin_presupuesto_activo_devuelve_pendientes_sin_columna_izquierda(
    monkeypatch,
):
    monkeypatch.setattr(repo, "buscar_orden_compra", lambda client, **kw: _stub_oc())
    monkeypatch.setattr(repo, "listar_oc_items_completos", lambda client, **kw: [_stub_oc_item()])
    monkeypatch.setattr(
        service,
        "_resolver_presupuesto_activo",
        lambda client, **kw: (None, "El cliente no tiene presupuestos cargados para elegir uno."),
    )

    resultado = service.obtener_matching(
        MagicMock(), orden_compra_id="oc-1", drogueria_id="d1", presupuesto_id=None
    )

    assert resultado.presupuesto_id is None
    assert resultado.renglones_presupuesto == []
    assert len(resultado.renglones_oc) == 1
    assert resultado.renglones_oc[0].estado == "pendiente"
    assert resultado.renglones_oc[0].candidatos == []
    assert resultado.advertencias == ["El cliente no tiene presupuestos cargados para elegir uno."]


# -----------------------------------------------------------------------
# 3.4 -- confirmar_vinculo (D4, D13): un solo UPDATE tras TODAS las
# validaciones de pertenencia (D12).
# -----------------------------------------------------------------------


def _parchear_dependencias_confirmar(
    monkeypatch,
    *,
    oc,
    oc_item,
    presupuesto_item,
    presupuesto,
    procesos_del_cliente,
    oc_items_de_la_oc=None,
):
    monkeypatch.setattr(repo, "buscar_orden_compra", lambda client, **kw: oc)
    monkeypatch.setattr(repo, "buscar_oc_item", lambda client, **kw: oc_item)
    monkeypatch.setattr(
        repo, "buscar_presupuesto_item_con_drogueria", lambda client, **kw: presupuesto_item
    )
    monkeypatch.setattr(
        repo, "listar_procesos_comerciales_del_cliente", lambda client, **kw: procesos_del_cliente
    )
    monkeypatch.setattr(service.presupuestos_repo, "buscar_presupuesto", lambda client, **kw: presupuesto)
    monkeypatch.setattr(
        repo, "listar_oc_items_completos", lambda client, **kw: oc_items_de_la_oc or [oc_item]
    )
    monkeypatch.setattr(
        repo,
        "listar_items_proceso_por_ids",
        lambda client, **kw: [
            {
                "id": presupuesto_item["item_proceso_id"],
                "producto_id": None,
                "descripcion": "x",
                "numero_renglon": 1,
            }
        ],
    )
    monkeypatch.setattr(service, "obtener_matching", lambda client, **kw: "MATCHING_OUT_SENTINEL")


def test_confirmar_vinculo_hace_un_solo_update_despues_de_validar(monkeypatch):
    llamadas_update: list[tuple] = []
    monkeypatch.setattr(
        repo,
        "actualizar_oc_item",
        lambda client, *, oc_item_id, campos: llamadas_update.append((oc_item_id, campos))
        or {"id": oc_item_id},
    )
    _parchear_dependencias_confirmar(
        monkeypatch,
        oc=_stub_oc(),
        oc_item=_stub_oc_item(),
        presupuesto_item=_stub_presupuesto_item(),
        presupuesto={"id": "pres-1", "proceso_comercial_id": "proc-1"},
        procesos_del_cliente=[{"id": "proc-1", "nombre": "Proceso"}],
    )

    resultado = service.confirmar_vinculo(
        MagicMock(),
        orden_compra_id="oc-1",
        oc_item_id="oci-1",
        presupuesto_item_id="pi-1",
        drogueria_id="d1",
        usuario_id="user-1",
    )

    assert resultado == "MATCHING_OUT_SENTINEL"
    assert len(llamadas_update) == 1
    oc_item_id, campos = llamadas_update[0]
    assert oc_item_id == "oci-1"
    assert campos["presupuesto_item_id"] == "pi-1"
    assert campos["producto_id"] == "prod-1"
    assert campos["vinculo_origen"] == "precio_exacto"
    assert campos["vinculo_confirmado_por"] == "user-1"


def test_confirmar_vinculo_acepta_precio_no_coincidente_como_manual(monkeypatch):
    llamadas_update: list[tuple] = []
    monkeypatch.setattr(
        repo,
        "actualizar_oc_item",
        lambda client, *, oc_item_id, campos: llamadas_update.append((oc_item_id, campos))
        or {"id": oc_item_id},
    )
    _parchear_dependencias_confirmar(
        monkeypatch,
        oc=_stub_oc(),
        oc_item=_stub_oc_item(precio_unitario="999.99"),  # no coincide con pi-1 (100.00)
        presupuesto_item=_stub_presupuesto_item(),
        presupuesto={"id": "pres-1", "proceso_comercial_id": "proc-1"},
        procesos_del_cliente=[{"id": "proc-1", "nombre": "Proceso"}],
    )

    service.confirmar_vinculo(
        MagicMock(),
        orden_compra_id="oc-1",
        oc_item_id="oci-1",
        presupuesto_item_id="pi-1",
        drogueria_id="d1",
        usuario_id="user-1",
    )

    _, campos = llamadas_update[0]
    assert campos["vinculo_origen"] == "manual"  # nunca bloquea (D4)


def test_confirmar_vinculo_reemplaza_vinculo_ya_confirmado_sin_error(monkeypatch):
    llamadas_update: list[tuple] = []
    monkeypatch.setattr(
        repo,
        "actualizar_oc_item",
        lambda client, *, oc_item_id, campos: llamadas_update.append((oc_item_id, campos))
        or {"id": oc_item_id},
    )
    # El propio renglón ya está confirmado contra OTRO presupuesto_item --
    # re-confirmar no debe chocar contra su propio vínculo previo.
    oc_item = _stub_oc_item(presupuesto_item_id="pi-anterior", vinculo_origen="precio_exacto")
    _parchear_dependencias_confirmar(
        monkeypatch,
        oc=_stub_oc(),
        oc_item=oc_item,
        presupuesto_item=_stub_presupuesto_item(id="pi-1"),
        presupuesto={"id": "pres-1", "proceso_comercial_id": "proc-1"},
        procesos_del_cliente=[{"id": "proc-1", "nombre": "Proceso"}],
        oc_items_de_la_oc=[oc_item],
    )

    service.confirmar_vinculo(
        MagicMock(),
        orden_compra_id="oc-1",
        oc_item_id="oci-1",
        presupuesto_item_id="pi-1",
        drogueria_id="d1",
        usuario_id="user-1",
    )

    assert len(llamadas_update) == 1  # no levantó excepción -- idempotente


def test_confirmar_vinculo_contra_presupuesto_distinto_del_activo_levanta_validation_error(
    monkeypatch,
):
    otro_oc_item = _stub_oc_item(id="oci-2", presupuesto_item_id="pi-del-activo")
    oc_item = _stub_oc_item()
    monkeypatch.setattr(
        repo,
        "listar_presupuesto_items_por_ids",
        lambda client, **kw: [{"id": "pi-del-activo", "presupuesto_id": "pres-activo"}],
    )
    _parchear_dependencias_confirmar(
        monkeypatch,
        oc=_stub_oc(),
        oc_item=oc_item,
        presupuesto_item=_stub_presupuesto_item(id="pi-1", presupuesto_id="pres-otro"),
        presupuesto={"id": "pres-otro", "proceso_comercial_id": "proc-1"},
        procesos_del_cliente=[{"id": "proc-1", "nombre": "Proceso"}],
        oc_items_de_la_oc=[oc_item, otro_oc_item],
    )

    with pytest.raises(ValidationError, match="pres-activo"):
        service.confirmar_vinculo(
            MagicMock(),
            orden_compra_id="oc-1",
            oc_item_id="oci-1",
            presupuesto_item_id="pi-1",
            drogueria_id="d1",
            usuario_id="user-1",
        )


def test_confirmar_vinculo_oc_item_ajeno_a_la_oc_levanta_not_found(monkeypatch):
    monkeypatch.setattr(repo, "buscar_orden_compra", lambda client, **kw: _stub_oc())
    monkeypatch.setattr(
        repo, "buscar_oc_item", lambda client, **kw: _stub_oc_item(orden_compra_id="OTRA-OC")
    )
    with pytest.raises(NotFoundError):
        service.confirmar_vinculo(
            MagicMock(),
            orden_compra_id="oc-1",
            oc_item_id="oci-1",
            presupuesto_item_id="pi-1",
            drogueria_id="d1",
            usuario_id="user-1",
        )


def test_confirmar_vinculo_presupuesto_item_de_otra_drogueria_levanta_not_found(monkeypatch):
    monkeypatch.setattr(repo, "buscar_orden_compra", lambda client, **kw: _stub_oc())
    monkeypatch.setattr(repo, "buscar_oc_item", lambda client, **kw: _stub_oc_item())
    monkeypatch.setattr(repo, "buscar_presupuesto_item_con_drogueria", lambda client, **kw: None)
    with pytest.raises(NotFoundError):
        service.confirmar_vinculo(
            MagicMock(),
            orden_compra_id="oc-1",
            oc_item_id="oci-1",
            presupuesto_item_id="pi-otra-drogueria",
            drogueria_id="d1",
            usuario_id="user-1",
        )


def test_confirmar_vinculo_presupuesto_item_de_otro_cliente_levanta_not_found(monkeypatch):
    # Misma droguería, pero el proceso comercial del presupuesto NO pertenece
    # al cliente de la OC (D12: pertenencia completa, no solo tenant).
    monkeypatch.setattr(repo, "buscar_orden_compra", lambda client, **kw: _stub_oc())
    monkeypatch.setattr(repo, "buscar_oc_item", lambda client, **kw: _stub_oc_item())
    monkeypatch.setattr(
        repo, "buscar_presupuesto_item_con_drogueria", lambda client, **kw: _stub_presupuesto_item()
    )
    monkeypatch.setattr(repo, "listar_procesos_comerciales_del_cliente", lambda client, **kw: [])
    monkeypatch.setattr(
        service.presupuestos_repo,
        "buscar_presupuesto",
        lambda client, **kw: {"id": "pres-1", "proceso_comercial_id": "proc-de-otro-cliente"},
    )
    with pytest.raises(NotFoundError):
        service.confirmar_vinculo(
            MagicMock(),
            orden_compra_id="oc-1",
            oc_item_id="oci-1",
            presupuesto_item_id="pi-1",
            drogueria_id="d1",
            usuario_id="user-1",
        )


def test_confirmar_vinculo_presupuesto_item_excluido_levanta_validation_error(monkeypatch):
    monkeypatch.setattr(repo, "buscar_orden_compra", lambda client, **kw: _stub_oc())
    monkeypatch.setattr(repo, "buscar_oc_item", lambda client, **kw: _stub_oc_item())
    monkeypatch.setattr(
        repo,
        "buscar_presupuesto_item_con_drogueria",
        lambda client, **kw: _stub_presupuesto_item(excluido=True),
    )
    with pytest.raises(ValidationError):
        service.confirmar_vinculo(
            MagicMock(),
            orden_compra_id="oc-1",
            oc_item_id="oci-1",
            presupuesto_item_id="pi-1",
            drogueria_id="d1",
            usuario_id="user-1",
        )


def test_confirmar_vinculo_oc_anclada_por_proceso_comercial_levanta_validation_error(monkeypatch):
    monkeypatch.setattr(repo, "buscar_orden_compra", lambda client, **kw: _stub_oc(cliente_id=None))
    with pytest.raises(ValidationError):
        service.confirmar_vinculo(
            MagicMock(),
            orden_compra_id="oc-1",
            oc_item_id="oci-1",
            presupuesto_item_id="pi-1",
            drogueria_id="d1",
            usuario_id="user-1",
        )


# -----------------------------------------------------------------------
# 3.5 -- deshacer_vinculo (D9): vuelve a pendiente; revierte producto_id
# SOLO si sigue intacto.
# -----------------------------------------------------------------------


def _parchear_dependencias_deshacer(monkeypatch, *, oc, oc_item, presupuesto_item=None):
    monkeypatch.setattr(repo, "buscar_orden_compra", lambda client, **kw: oc)
    monkeypatch.setattr(repo, "buscar_oc_item", lambda client, **kw: oc_item)
    monkeypatch.setattr(
        repo, "buscar_presupuesto_item_con_drogueria", lambda client, **kw: presupuesto_item
    )
    monkeypatch.setattr(
        repo,
        "listar_items_proceso_por_ids",
        lambda client, **kw: [
            {
                "id": presupuesto_item["item_proceso_id"] if presupuesto_item else "ip-1",
                "producto_id": None,
            }
        ],
    )
    monkeypatch.setattr(service, "obtener_matching", lambda client, **kw: "MATCHING_OUT_SENTINEL")


def test_deshacer_vinculo_revierte_producto_id_si_coincide_con_el_heredado(monkeypatch):
    llamadas: list[tuple] = []
    monkeypatch.setattr(
        repo,
        "actualizar_oc_item",
        lambda client, *, oc_item_id, campos: llamadas.append((oc_item_id, campos))
        or {"id": oc_item_id},
    )
    oc_item = _stub_oc_item(
        presupuesto_item_id="pi-1", producto_id="prod-1", vinculo_origen="precio_exacto"
    )
    _parchear_dependencias_deshacer(
        monkeypatch, oc=_stub_oc(), oc_item=oc_item, presupuesto_item=_stub_presupuesto_item(producto_id="prod-1")
    )

    service.deshacer_vinculo(MagicMock(), orden_compra_id="oc-1", oc_item_id="oci-1", drogueria_id="d1")

    _, campos = llamadas[0]
    assert campos["presupuesto_item_id"] is None
    assert campos["vinculo_descartado"] is False
    assert campos["producto_id"] is None


def test_deshacer_vinculo_respeta_producto_id_cambiado_por_otro_camino(monkeypatch):
    llamadas: list[tuple] = []
    monkeypatch.setattr(
        repo,
        "actualizar_oc_item",
        lambda client, *, oc_item_id, campos: llamadas.append((oc_item_id, campos))
        or {"id": oc_item_id},
    )
    oc_item = _stub_oc_item(
        presupuesto_item_id="pi-1", producto_id="prod-DISTINTO", vinculo_origen="precio_exacto"
    )
    # El vínculo daba prod-1, no prod-DISTINTO -- alguien lo cambió después.
    _parchear_dependencias_deshacer(
        monkeypatch, oc=_stub_oc(), oc_item=oc_item, presupuesto_item=_stub_presupuesto_item(producto_id="prod-1")
    )

    service.deshacer_vinculo(MagicMock(), orden_compra_id="oc-1", oc_item_id="oci-1", drogueria_id="d1")

    _, campos = llamadas[0]
    assert "producto_id" not in campos  # se deja intacto, ni siquiera se toca


def test_deshacer_vinculo_no_op_si_producto_id_ya_era_none(monkeypatch):
    llamadas: list[tuple] = []
    monkeypatch.setattr(
        repo,
        "actualizar_oc_item",
        lambda client, *, oc_item_id, campos: llamadas.append((oc_item_id, campos))
        or {"id": oc_item_id},
    )
    oc_item = _stub_oc_item(presupuesto_item_id="pi-1", producto_id=None, vinculo_origen="manual")
    _parchear_dependencias_deshacer(
        monkeypatch, oc=_stub_oc(), oc_item=oc_item, presupuesto_item=_stub_presupuesto_item(producto_id="prod-1")
    )

    service.deshacer_vinculo(MagicMock(), orden_compra_id="oc-1", oc_item_id="oci-1", drogueria_id="d1")

    _, campos = llamadas[0]
    assert "producto_id" not in campos


def test_deshacer_vinculo_sirve_para_sin_presupuesto(monkeypatch):
    llamadas: list[tuple] = []
    monkeypatch.setattr(
        repo,
        "actualizar_oc_item",
        lambda client, *, oc_item_id, campos: llamadas.append((oc_item_id, campos))
        or {"id": oc_item_id},
    )
    oc_item = _stub_oc_item(vinculo_descartado=True)  # sin_presupuesto
    _parchear_dependencias_deshacer(monkeypatch, oc=_stub_oc(), oc_item=oc_item, presupuesto_item=None)

    service.deshacer_vinculo(MagicMock(), orden_compra_id="oc-1", oc_item_id="oci-1", drogueria_id="d1")

    _, campos = llamadas[0]
    assert campos["vinculo_descartado"] is False
    assert campos["presupuesto_item_id"] is None


def test_deshacer_vinculo_oc_item_ajeno_levanta_not_found(monkeypatch):
    monkeypatch.setattr(repo, "buscar_orden_compra", lambda client, **kw: _stub_oc())
    monkeypatch.setattr(
        repo, "buscar_oc_item", lambda client, **kw: _stub_oc_item(orden_compra_id="OTRA-OC")
    )
    with pytest.raises(NotFoundError):
        service.deshacer_vinculo(
            MagicMock(), orden_compra_id="oc-1", oc_item_id="oci-1", drogueria_id="d1"
        )


# -----------------------------------------------------------------------
# 3.6 -- descartar_renglon (D4): sin_presupuesto, distinto de pendiente.
# -----------------------------------------------------------------------


def test_descartar_renglon_marca_vinculo_descartado_true(monkeypatch):
    llamadas: list[tuple] = []
    monkeypatch.setattr(
        repo,
        "actualizar_oc_item",
        lambda client, *, oc_item_id, campos: llamadas.append((oc_item_id, campos))
        or {"id": oc_item_id},
    )
    monkeypatch.setattr(repo, "buscar_orden_compra", lambda client, **kw: _stub_oc())
    monkeypatch.setattr(repo, "buscar_oc_item", lambda client, **kw: _stub_oc_item())
    monkeypatch.setattr(service, "obtener_matching", lambda client, **kw: "MATCHING_OUT_SENTINEL")

    service.descartar_renglon(MagicMock(), orden_compra_id="oc-1", oc_item_id="oci-1", drogueria_id="d1")

    _, campos = llamadas[0]
    assert campos["vinculo_descartado"] is True
    assert campos["presupuesto_item_id"] is None


def test_descartar_renglon_oc_item_ajeno_levanta_not_found(monkeypatch):
    monkeypatch.setattr(repo, "buscar_orden_compra", lambda client, **kw: _stub_oc())
    monkeypatch.setattr(
        repo, "buscar_oc_item", lambda client, **kw: _stub_oc_item(orden_compra_id="OTRA-OC")
    )
    with pytest.raises(NotFoundError):
        service.descartar_renglon(
            MagicMock(), orden_compra_id="oc-1", oc_item_id="oci-1", drogueria_id="d1"
        )


# -----------------------------------------------------------------------
# 3.9 -- integración: caso real SAMCo Rafaela, dos renglones sin ambigüedad,
# herencia de producto_id verificada con productos reales.
# -----------------------------------------------------------------------


@pytest.mark.integration
def test_matching_integracion_samco_rafaela_sugiere_sin_ambiguedad_y_hereda_producto(
    service_client, seed_drogueria, seed_caso_samco_rafaela
):
    productos = [
        service_client.table("productos")
        .insert(
            {
                "drogueria_id": seed_drogueria["id"],
                "codigo_interno": f"TEST-SAMCO-{i}",
                "nombre": f"Producto SAMCo {i}",
            }
        )
        .execute()
        .data[0]
        for i in range(2)
    ]
    try:
        for presupuesto_item, producto in zip(
            seed_caso_samco_rafaela["presupuesto_items"], productos
        ):
            service_client.table("presupuesto_items").update(
                {"producto_id": producto["id"]}
            ).eq("id", presupuesto_item["id"]).execute()

        matching = service.obtener_matching(
            service_client,
            orden_compra_id=seed_caso_samco_rafaela["orden_compra_id"],
            drogueria_id=seed_drogueria["id"],
            presupuesto_id=None,
        )

        assert matching.presupuesto_id == seed_caso_samco_rafaela["presupuesto_id"]
        assert len(matching.renglones_oc) == 2
        for renglon in matching.renglones_oc:
            assert renglon.estado == "pendiente"
            assert len(renglon.candidatos) == 1  # sin ambigüedad, sin desempate
            assert renglon.candidatos[0].similitud is None

        for oc_item, producto in zip(seed_caso_samco_rafaela["oc_items"], productos):
            resultado = service.confirmar_vinculo(
                service_client,
                orden_compra_id=seed_caso_samco_rafaela["orden_compra_id"],
                oc_item_id=oc_item["id"],
                presupuesto_item_id=matching.renglones_oc[
                    seed_caso_samco_rafaela["oc_items"].index(oc_item)
                ].candidatos[0].presupuesto_item_id,
                drogueria_id=seed_drogueria["id"],
                usuario_id=seed_drogueria["id"],  # cualquier UUID válido sirve de auditoría
            )
            matching = resultado

        producto_ids_heredados = {r.producto_id for r in matching.renglones_oc}
        assert producto_ids_heredados == {p["id"] for p in productos}
        assert all(r.estado == "confirmado" for r in matching.renglones_oc)
        assert all(r.vinculo_origen == "precio_exacto" for r in matching.renglones_oc)
    finally:
        # fk_pi_prod / fk_oci_prod (RESTRICT): hay que soltar CADA referencia
        # -- presupuesto_items Y los oc_items que heredaron el producto -- ANTES
        # de borrar el producto. El teardown de seed_caso_samco_rafaela recién
        # borra esas filas DESPUÉS de que este `finally` corra (orden de
        # fixtures), así que acá todas todavía existen.
        for presupuesto_item in seed_caso_samco_rafaela["presupuesto_items"]:
            service_client.table("presupuesto_items").update({"producto_id": None}).eq(
                "id", presupuesto_item["id"]
            ).execute()
        for oc_item in seed_caso_samco_rafaela["oc_items"]:
            service_client.table("oc_items").update({"producto_id": None}).eq(
                "id", oc_item["id"]
            ).execute()
        for producto in productos:
            service_client.table("productos").delete().eq("id", producto["id"]).execute()


# -----------------------------------------------------------------------
# 3.8 -- invariante duro: items_proceso.estado_matching / confianza_matching
# quedan sin modificar tras una sesión completa (confirmar + deshacer +
# descartar).
# -----------------------------------------------------------------------


@pytest.mark.integration
def test_sesion_completa_no_modifica_estado_matching_ni_confianza_matching(
    service_client, seed_drogueria, seed_caso_samco_rafaela
):
    item_proceso_ids = [ip["id"] for ip in seed_caso_samco_rafaela["items_proceso"]]

    def _snapshot() -> dict[str, tuple]:
        filas = (
            service_client.table("items_proceso")
            .select("id, estado_matching, confianza_matching")
            .in_("id", item_proceso_ids)
            .execute()
            .data
        )
        return {fila["id"]: (fila["estado_matching"], fila["confianza_matching"]) for fila in filas}

    antes = _snapshot()

    oc_item_1, oc_item_2 = seed_caso_samco_rafaela["oc_items"]
    presupuesto_item_1, presupuesto_item_2 = seed_caso_samco_rafaela["presupuesto_items"]

    service.confirmar_vinculo(
        service_client,
        orden_compra_id=seed_caso_samco_rafaela["orden_compra_id"],
        oc_item_id=oc_item_1["id"],
        presupuesto_item_id=presupuesto_item_1["id"],
        drogueria_id=seed_drogueria["id"],
        usuario_id=seed_drogueria["id"],
    )
    service.confirmar_vinculo(
        service_client,
        orden_compra_id=seed_caso_samco_rafaela["orden_compra_id"],
        oc_item_id=oc_item_2["id"],
        presupuesto_item_id=presupuesto_item_2["id"],
        drogueria_id=seed_drogueria["id"],
        usuario_id=seed_drogueria["id"],
    )
    service.deshacer_vinculo(
        service_client,
        orden_compra_id=seed_caso_samco_rafaela["orden_compra_id"],
        oc_item_id=oc_item_1["id"],
        drogueria_id=seed_drogueria["id"],
    )
    service.descartar_renglon(
        service_client,
        orden_compra_id=seed_caso_samco_rafaela["orden_compra_id"],
        oc_item_id=oc_item_1["id"],
        drogueria_id=seed_drogueria["id"],
    )

    despues = _snapshot()
    assert antes == despues
