from decimal import Decimal

import pytest

from services.presupuestacion.matching import repository as matching_repo
from services.presupuestacion.matching.service import (
    confirmar_matching,
    marcar_sin_match,
    procesar_matching_item,
    procesar_matching_items,
)


@pytest.fixture
def crear_items(service_client, seed_proceso_con_cliente, seed_drogueria):
    """Inserts items_proceso rows with the given descripciones and removes them
    (and their candidatos) afterwards."""
    creados: list[dict] = []

    def _crear(*descripciones: str) -> list[dict]:
        filas = [
            {
                "proceso_comercial_id": seed_proceso_con_cliente["id"],
                "drogueria_id": seed_drogueria["id"],
                "numero_renglon": numero,
                "descripcion": descripcion,
                "cantidad": "10",
            }
            for numero, descripcion in enumerate(descripciones, start=1)
        ]
        items = service_client.table("items_proceso").insert(filas).execute().data
        creados.extend(items)
        return items

    yield _crear
    for item in creados:
        service_client.table("matching_candidatos").delete().eq("item_proceso_id", item["id"]).execute()
        service_client.table("items_proceso").delete().eq("id", item["id"]).execute()


def _contar_llamadas(monkeypatch, nombre: str) -> list[int]:
    """Wraps a matching repository function and counts how many times it runs."""
    original = getattr(matching_repo, nombre)
    llamadas = [0]

    def _envuelta(*args, **kwargs):
        llamadas[0] += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(matching_repo, nombre, _envuelta)
    return llamadas


@pytest.mark.integration
def test_procesar_matching_items_resuelve_el_lote_con_una_consulta_por_tabla(
    service_client,
    monkeypatch,
    seed_drogueria,
    seed_alias,
    seed_producto_con_nombre,
    crear_items,
):
    """A licitación's items are matched as one batch: the catalog, the alias
    lookup and the candidatos insert run once, not once per item."""
    producto_similar = seed_producto_con_nombre("Amoxicilina 500mg x16")
    seed_producto_con_nombre("Guantes de latex talle M")
    con_alias, similar, sin_parecido = crear_items(
        "Ibuprofeno 600mg x30", "Amoxicilina 500mg x16", "Jeringa descartable 5ml"
    )
    catalogo = _contar_llamadas(monkeypatch, "listar_productos_activos")
    alias = _contar_llamadas(monkeypatch, "listar_alias_vigentes")
    candidatos = _contar_llamadas(monkeypatch, "insertar_candidatos")

    resultados = procesar_matching_items(
        service_client,
        items=[con_alias, similar, sin_parecido],
        drogueria_id=seed_drogueria["id"],
        cliente_id=seed_alias["cliente_id"],
    )

    assert (catalogo[0], alias[0], candidatos[0]) == (1, 1, 1)
    assert [r.item_proceso_id for r in resultados] == [con_alias["id"], similar["id"], sin_parecido["id"]]
    assert resultados[0].estado_matching == "automatico"
    assert resultados[0].producto_id == seed_alias["producto_id"]
    assert resultados[1].estado_matching == "sugerido"
    assert max(resultados[1].candidatos, key=lambda c: c.confianza).producto_id == producto_similar["id"]
    assert resultados[2].estado_matching == "pendiente"

    ids = [con_alias["id"], similar["id"], sin_parecido["id"]]
    items_en_db = {
        fila["id"]: fila
        for fila in service_client.table("items_proceso")
        .select("id, estado_matching, producto_id")
        .in_("id", ids)
        .execute()
        .data
    }
    assert items_en_db[con_alias["id"]]["estado_matching"] == "automatico"
    assert items_en_db[con_alias["id"]]["producto_id"] == seed_alias["producto_id"]
    assert items_en_db[similar["id"]]["estado_matching"] == "sugerido"
    assert items_en_db[sin_parecido["id"]]["estado_matching"] == "pendiente"

    candidatos_en_db = (
        service_client.table("matching_candidatos")
        .select("item_proceso_id")
        .in_("item_proceso_id", ids)
        .execute()
        .data
    )
    assert len(candidatos_en_db) == len(resultados[1].candidatos) + len(resultados[2].candidatos)
    assert all(fila["item_proceso_id"] != con_alias["id"] for fila in candidatos_en_db)


@pytest.mark.integration
def test_procesar_matching_items_suma_un_uso_del_alias_por_cada_item_que_lo_usa(
    service_client, seed_drogueria, seed_alias, crear_items
):
    items = crear_items("Ibuprofeno 600mg x30", "ibuprofeno 600mg x30")
    veces_usado_previo = seed_alias["veces_usado"]

    procesar_matching_items(
        service_client,
        items=items,
        drogueria_id=seed_drogueria["id"],
        cliente_id=seed_alias["cliente_id"],
    )

    alias_actualizado = (
        service_client.table("cliente_producto_alias")
        .select("veces_usado")
        .eq("id", seed_alias["id"])
        .execute()
        .data[0]
    )
    assert alias_actualizado["veces_usado"] == veces_usado_previo + 2


@pytest.mark.integration
def test_procesar_matching_item_usa_alias_vigente_y_marca_automatico(
    service_client, seed_drogueria, seed_item_sin_producto, seed_alias, limpiar_matching
):
    limpiar_matching["items"].append(seed_item_sin_producto["id"])

    resultado = procesar_matching_item(
        service_client,
        item=seed_item_sin_producto,
        drogueria_id=seed_drogueria["id"],
        cliente_id=seed_alias["cliente_id"],
    )

    assert resultado.estado_matching == "automatico"
    assert resultado.producto_id == seed_alias["producto_id"]
    assert resultado.alias_id == seed_alias["id"]
    assert resultado.candidatos == []

    item_actualizado = (
        service_client.table("items_proceso")
        .select("*")
        .eq("id", seed_item_sin_producto["id"])
        .execute()
        .data[0]
    )
    assert item_actualizado["estado_matching"] == "automatico"
    assert item_actualizado["producto_id"] == seed_alias["producto_id"]


@pytest.mark.integration
def test_procesar_matching_item_incrementa_veces_usado_del_alias(
    service_client, seed_drogueria, seed_item_sin_producto, seed_alias, limpiar_matching
):
    limpiar_matching["items"].append(seed_item_sin_producto["id"])
    veces_usado_previo = seed_alias["veces_usado"]

    procesar_matching_item(
        service_client,
        item=seed_item_sin_producto,
        drogueria_id=seed_drogueria["id"],
        cliente_id=seed_alias["cliente_id"],
    )

    alias_actualizado = (
        service_client.table("cliente_producto_alias")
        .select("*")
        .eq("id", seed_alias["id"])
        .execute()
        .data[0]
    )
    assert alias_actualizado["veces_usado"] == veces_usado_previo + 1


@pytest.mark.integration
def test_procesar_matching_item_genera_candidatos_fuzzy_y_marca_sugerido(
    service_client,
    seed_drogueria,
    seed_item_sin_producto,
    seed_producto_con_nombre,
    limpiar_matching,
):
    limpiar_matching["items"].append(seed_item_sin_producto["id"])
    producto_similar = seed_producto_con_nombre("Ibuprofeno 600mg x30")
    seed_producto_con_nombre("Gasa esteril x10")

    resultado = procesar_matching_item(
        service_client,
        item=seed_item_sin_producto,
        drogueria_id=seed_drogueria["id"],
        cliente_id=None,
    )

    assert resultado.estado_matching == "sugerido"
    assert len(resultado.candidatos) >= 1
    mejor = max(resultado.candidatos, key=lambda c: c.confianza)
    assert mejor.producto_id == producto_similar["id"]
    assert mejor.confianza >= Decimal("70")
    assert mejor.metodo == "fuzzy"

    candidatos_en_db = (
        service_client.table("matching_candidatos")
        .select("*")
        .eq("item_proceso_id", seed_item_sin_producto["id"])
        .execute()
        .data
    )
    assert len(candidatos_en_db) == len(resultado.candidatos)


@pytest.mark.integration
def test_procesar_matching_item_marca_pendiente_si_mejor_candidato_es_bajo(
    service_client,
    seed_drogueria,
    seed_item_sin_producto,
    seed_producto_con_nombre,
    limpiar_matching,
):
    limpiar_matching["items"].append(seed_item_sin_producto["id"])
    seed_producto_con_nombre("Guantes de latex talle M")

    resultado = procesar_matching_item(
        service_client,
        item=seed_item_sin_producto,
        drogueria_id=seed_drogueria["id"],
        cliente_id=None,
    )

    assert resultado.estado_matching == "pendiente"
    assert all(c.confianza < Decimal("70") for c in resultado.candidatos)


@pytest.mark.integration
def test_procesar_matching_item_sin_catalogo_queda_pendiente_sin_candidatos(
    service_client, seed_drogueria, seed_item_sin_producto, limpiar_matching
):
    limpiar_matching["items"].append(seed_item_sin_producto["id"])

    resultado = procesar_matching_item(
        service_client,
        item=seed_item_sin_producto,
        drogueria_id=seed_drogueria["id"],
        cliente_id=None,
    )

    assert resultado.estado_matching == "pendiente"
    assert resultado.candidatos == []
    assert resultado.confianza_matching is None


@pytest.mark.integration
def test_confirmar_matching_crea_alias_nuevo_si_no_habia(
    service_client,
    seed_drogueria,
    seed_cliente,
    seed_proceso_con_cliente,
    seed_item_sin_producto,
    seed_producto,
    seed_usuario_sistema,
    limpiar_matching,
):
    limpiar_matching["items"].append(seed_item_sin_producto["id"])

    resultado = confirmar_matching(
        service_client,
        item_proceso_id=seed_item_sin_producto["id"],
        producto_id=seed_producto["id"],
        usuario_id=seed_usuario_sistema["id"],
    )
    limpiar_matching["alias"].append(resultado.alias_id)

    assert resultado.estado_matching == "confirmado"
    assert resultado.producto_id == seed_producto["id"]

    alias_creado = (
        service_client.table("cliente_producto_alias")
        .select("*")
        .eq("id", resultado.alias_id)
        .execute()
        .data[0]
    )
    assert alias_creado["cliente_id"] == seed_cliente["id"]
    assert alias_creado["producto_id"] == seed_producto["id"]
    assert alias_creado["vigente"] is True
    assert alias_creado["creado_por"] == seed_usuario_sistema["id"]


@pytest.mark.integration
def test_confirmar_matching_invalida_alias_viejo_si_cambia_producto(
    service_client,
    seed_drogueria,
    seed_item_sin_producto,
    seed_alias,
    seed_producto_con_nombre,
    seed_usuario_sistema,
    limpiar_matching,
):
    limpiar_matching["items"].append(seed_item_sin_producto["id"])
    otro_producto = seed_producto_con_nombre("Otro producto distinto")

    resultado = confirmar_matching(
        service_client,
        item_proceso_id=seed_item_sin_producto["id"],
        producto_id=otro_producto["id"],
        usuario_id=seed_usuario_sistema["id"],
    )
    limpiar_matching["alias"].append(resultado.alias_id)

    assert resultado.alias_id != seed_alias["id"]

    alias_viejo = (
        service_client.table("cliente_producto_alias")
        .select("vigente")
        .eq("id", seed_alias["id"])
        .execute()
        .data[0]
    )
    assert alias_viejo["vigente"] is False

    alias_nuevo = (
        service_client.table("cliente_producto_alias")
        .select("*")
        .eq("id", resultado.alias_id)
        .execute()
        .data[0]
    )
    assert alias_nuevo["producto_id"] == otro_producto["id"]
    assert alias_nuevo["vigente"] is True


@pytest.mark.integration
def test_confirmar_matching_no_duplica_alias_si_ya_apunta_al_mismo_producto(
    service_client,
    seed_drogueria,
    seed_item_sin_producto,
    seed_alias,
    seed_usuario_sistema,
    limpiar_matching,
):
    limpiar_matching["items"].append(seed_item_sin_producto["id"])

    resultado = confirmar_matching(
        service_client,
        item_proceso_id=seed_item_sin_producto["id"],
        producto_id=seed_alias["producto_id"],
        usuario_id=seed_usuario_sistema["id"],
    )

    assert resultado.alias_id == seed_alias["id"]

    alias_vigente = (
        service_client.table("cliente_producto_alias")
        .select("vigente")
        .eq("id", seed_alias["id"])
        .execute()
        .data[0]
    )
    assert alias_vigente["vigente"] is True


@pytest.mark.integration
def test_confirmar_matching_marca_candidato_elegido(
    service_client,
    seed_drogueria,
    seed_item_sin_producto,
    seed_producto,
    seed_usuario_sistema,
    limpiar_matching,
):
    limpiar_matching["items"].append(seed_item_sin_producto["id"])
    fila_candidato = {
        "item_proceso_id": seed_item_sin_producto["id"],
        "drogueria_id": seed_drogueria["id"],
        "producto_id": seed_producto["id"],
        "confianza": "85.00",
        "metodo": "fuzzy",
    }
    service_client.table("matching_candidatos").insert(fila_candidato).execute()

    resultado = confirmar_matching(
        service_client,
        item_proceso_id=seed_item_sin_producto["id"],
        producto_id=seed_producto["id"],
        usuario_id=seed_usuario_sistema["id"],
    )
    limpiar_matching["alias"].append(resultado.alias_id)

    candidato = (
        service_client.table("matching_candidatos")
        .select("elegido")
        .eq("item_proceso_id", seed_item_sin_producto["id"])
        .eq("producto_id", seed_producto["id"])
        .execute()
        .data[0]
    )
    assert candidato["elegido"] is True


@pytest.mark.integration
def test_marcar_sin_match_deja_item_sin_producto(
    service_client, seed_item_sin_producto, limpiar_matching
):
    limpiar_matching["items"].append(seed_item_sin_producto["id"])

    resultado = marcar_sin_match(service_client, item_proceso_id=seed_item_sin_producto["id"])

    assert resultado.estado_matching == "sin_match"
    assert resultado.producto_id is None

    item_actualizado = (
        service_client.table("items_proceso")
        .select("*")
        .eq("id", seed_item_sin_producto["id"])
        .execute()
        .data[0]
    )
    assert item_actualizado["estado_matching"] == "sin_match"
    assert item_actualizado["producto_id"] is None


def _candidatos_elegidos(service_client, item_proceso_id: str) -> dict[str, bool]:
    filas = (
        service_client.table("matching_candidatos")
        .select("producto_id, elegido")
        .eq("item_proceso_id", item_proceso_id)
        .execute()
        .data
    )
    return {fila["producto_id"]: fila["elegido"] for fila in filas}


@pytest.mark.integration
def test_confirmar_matching_reelegido_deja_un_solo_candidato_elegido(
    service_client,
    seed_drogueria,
    seed_item_sin_producto,
    seed_producto_con_nombre,
    seed_usuario_sistema,
    limpiar_matching,
):
    limpiar_matching["items"].append(seed_item_sin_producto["id"])
    primero = seed_producto_con_nombre("Ibuprofeno 600mg x30 primero")
    segundo = seed_producto_con_nombre("Ibuprofeno 600mg x30 segundo")
    service_client.table("matching_candidatos").insert(
        [
            {
                "item_proceso_id": seed_item_sin_producto["id"],
                "drogueria_id": seed_drogueria["id"],
                "producto_id": producto["id"],
                "confianza": confianza,
                "metodo": "fuzzy",
            }
            for producto, confianza in ((primero, "90.00"), (segundo, "80.00"))
        ]
    ).execute()

    for producto in (primero, segundo):
        resultado = confirmar_matching(
            service_client,
            item_proceso_id=seed_item_sin_producto["id"],
            producto_id=producto["id"],
            usuario_id=seed_usuario_sistema["id"],
        )
        limpiar_matching["alias"].append(resultado.alias_id)

    assert resultado.producto_id == segundo["id"]
    assert _candidatos_elegidos(service_client, seed_item_sin_producto["id"]) == {
        primero["id"]: False,
        segundo["id"]: True,
    }


@pytest.mark.integration
def test_marcar_sin_match_invalida_el_alias_del_renglon(
    service_client,
    seed_drogueria,
    seed_item_sin_producto,
    seed_alias,
    limpiar_matching,
):
    # A renglón matched by the cliente's alias that the user rejects: the alias
    # is wrong, so the next licitación must not match it automatically again.
    limpiar_matching["items"].append(seed_item_sin_producto["id"])
    service_client.table("items_proceso").update(
        {
            "producto_id": seed_alias["producto_id"],
            "alias_id": seed_alias["id"],
            "estado_matching": "automatico",
        }
    ).eq("id", seed_item_sin_producto["id"]).execute()
    service_client.table("matching_candidatos").insert(
        {
            "item_proceso_id": seed_item_sin_producto["id"],
            "drogueria_id": seed_drogueria["id"],
            "producto_id": seed_alias["producto_id"],
            "confianza": "95.00",
            "metodo": "fuzzy",
            "elegido": True,
        }
    ).execute()

    resultado = marcar_sin_match(service_client, item_proceso_id=seed_item_sin_producto["id"])

    assert resultado.estado_matching == "sin_match"
    assert resultado.alias_id is None
    item = (
        service_client.table("items_proceso")
        .select("producto_id, alias_id, estado_matching")
        .eq("id", seed_item_sin_producto["id"])
        .execute()
        .data[0]
    )
    assert item == {"producto_id": None, "alias_id": None, "estado_matching": "sin_match"}
    alias = (
        service_client.table("cliente_producto_alias")
        .select("vigente")
        .eq("id", seed_alias["id"])
        .execute()
        .data[0]
    )
    assert alias["vigente"] is False
    assert _candidatos_elegidos(service_client, seed_item_sin_producto["id"]) == {
        seed_alias["producto_id"]: False
    }
