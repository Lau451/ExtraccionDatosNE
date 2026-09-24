"""tests/oc_presupuesto/test_service.py -- ranking de presupuestos candidatos
(design.md D2, D2.1, D3; tasks.md Phase 2, 2.2-2.5 y 2.12).

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
