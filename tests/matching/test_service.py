from decimal import Decimal

import pytest

from presupuestacion.matching.service import (
    confirmar_matching,
    marcar_sin_match,
    procesar_matching_item,
)


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
