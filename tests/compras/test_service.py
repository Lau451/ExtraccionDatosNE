from decimal import Decimal

import pytest

from services.presupuestacion.compras.models import CrearOrdenCompraRequest, EntregaItemRequest, OrdenCompraItemRequest
from services.presupuestacion.compras.service import confirmar_orden_compra, crear_entrega, crear_orden_compra
from services.presupuestacion.core.exceptions import ConflictError, NotFoundError, ValidationError


def _item(**overrides):
    base = {
        "numero_renglon": 1,
        "descripcion": "Ítem de test",
        "cantidad": Decimal("10"),
        "precio_unitario": Decimal("100.00"),
    }
    base.update(overrides)
    return OrdenCompraItemRequest(**base)


@pytest.mark.integration
def test_crear_orden_compra_crea_oc_y_items(
    service_client, seed_drogueria, seed_proceso_comercial, seed_usuario_sistema, numero_oc_unico,
    limpiar_ordenes_compra,
):
    body = CrearOrdenCompraRequest(
        proceso_comercial_id=seed_proceso_comercial["id"],
        numero_oc=numero_oc_unico(),
        items=[_item(numero_renglon=1, cantidad=Decimal("10"), precio_unitario=Decimal("100.00"))],
    )

    resultado = crear_orden_compra(
        service_client, drogueria_id=seed_drogueria["id"], usuario_id=seed_usuario_sistema["id"], body=body
    )
    limpiar_ordenes_compra.append(resultado.orden_compra_id)

    assert resultado.estado == "pendiente"
    assert resultado.items_cantidad == 1
    assert resultado.monto_total == Decimal("1000.00")

    items = (
        service_client.table("oc_items")
        .select("*")
        .eq("orden_compra_id", resultado.orden_compra_id)
        .execute()
        .data
    )
    assert len(items) == 1
    assert Decimal(str(items[0]["cantidad"])) == Decimal("10")


@pytest.mark.integration
def test_crear_orden_compra_numero_duplicado_levanta_conflict(
    service_client, seed_drogueria, seed_proceso_comercial, seed_usuario_sistema, numero_oc_unico,
    limpiar_ordenes_compra,
):
    numero = numero_oc_unico()
    body = CrearOrdenCompraRequest(
        proceso_comercial_id=seed_proceso_comercial["id"], numero_oc=numero, items=[_item()]
    )
    resultado = crear_orden_compra(
        service_client, drogueria_id=seed_drogueria["id"], usuario_id=seed_usuario_sistema["id"], body=body
    )
    limpiar_ordenes_compra.append(resultado.orden_compra_id)

    with pytest.raises(ConflictError):
        crear_orden_compra(service_client, drogueria_id=seed_drogueria["id"], usuario_id=seed_usuario_sistema["id"], body=body)


@pytest.mark.integration
def test_crear_orden_compra_proceso_de_otra_drogueria_falla(
    service_client, seed_drogueria, seed_proceso_comercial, seed_usuario_sistema, numero_oc_unico
):
    otra_drogueria = service_client.table("droguerias").insert(
        {
            "nombre": "Otra Droguería",
            "razon_social": "Otra Droguería SA",
            "cuit": "20-99999999-1",
            "ciudad": "Rosario",
            "provincia": "Santa Fe",
            "contacto_email": "otra-compras@seed.local",
            "contacto_telefono": "0000000000",
        }
    ).execute().data[0]

    body = CrearOrdenCompraRequest(
        proceso_comercial_id=seed_proceso_comercial["id"], numero_oc=numero_oc_unico(), items=[_item()]
    )
    try:
        with pytest.raises(ValidationError):
            crear_orden_compra(
                service_client, drogueria_id=otra_drogueria["id"], usuario_id=seed_usuario_sistema["id"], body=body
            )
    finally:
        service_client.table("droguerias").delete().eq("id", otra_drogueria["id"]).execute()


@pytest.mark.integration
def test_confirmar_orden_compra_marca_adjudicada_si_es_propia(
    service_client, seed_drogueria, seed_proceso_comercial, seed_usuario_sistema, numero_oc_unico,
    limpiar_ordenes_compra,
):
    comparativa = service_client.table("comparativas").insert(
        {"proceso_comercial_id": seed_proceso_comercial["id"], "drogueria_id": seed_drogueria["id"]}
    ).execute().data[0]
    oferta = service_client.table("ofertas_items").insert(
        {
            "comparativa_id": comparativa["id"],
            "drogueria_id": seed_drogueria["id"],
            "proveedor": "Nosotros",
            "precio_unitario": "100.00",
            "es_drogueria_propia": True,
        }
    ).execute().data[0]

    try:
        body = CrearOrdenCompraRequest(
            proceso_comercial_id=seed_proceso_comercial["id"],
            numero_oc=numero_oc_unico(),
            items=[_item(oferta_item_id=oferta["id"])],
        )
        resultado = crear_orden_compra(
            service_client, drogueria_id=seed_drogueria["id"], usuario_id=seed_usuario_sistema["id"], body=body
        )
        limpiar_ordenes_compra.append(resultado.orden_compra_id)

        confirmado = confirmar_orden_compra(
            service_client, orden_compra_id=resultado.orden_compra_id, usuario_id=seed_usuario_sistema["id"]
        )

        assert confirmado.estado == "emitida"
        oferta_final = (
            service_client.table("ofertas_items")
            .select("adjudicada")
            .eq("id", oferta["id"])
            .execute()
            .data[0]
        )
        assert oferta_final["adjudicada"] is True
    finally:
        service_client.table("oc_items").update({"oferta_item_id": None}).eq(
            "oferta_item_id", oferta["id"]
        ).execute()
        service_client.table("ofertas_items").delete().eq("id", oferta["id"]).execute()
        service_client.table("comparativas").delete().eq("id", comparativa["id"]).execute()


@pytest.mark.integration
def test_confirmar_orden_compra_no_marca_adjudicada_si_no_es_propia(
    service_client, seed_drogueria, seed_proceso_comercial, seed_usuario_sistema, numero_oc_unico,
    limpiar_ordenes_compra,
):
    comparativa = service_client.table("comparativas").insert(
        {"proceso_comercial_id": seed_proceso_comercial["id"], "drogueria_id": seed_drogueria["id"]}
    ).execute().data[0]
    oferta = service_client.table("ofertas_items").insert(
        {
            "comparativa_id": comparativa["id"],
            "drogueria_id": seed_drogueria["id"],
            "proveedor": "Competidor",
            "precio_unitario": "100.00",
            "es_drogueria_propia": False,
        }
    ).execute().data[0]

    try:
        body = CrearOrdenCompraRequest(
            proceso_comercial_id=seed_proceso_comercial["id"],
            numero_oc=numero_oc_unico(),
            items=[_item(oferta_item_id=oferta["id"])],
        )
        resultado = crear_orden_compra(
            service_client, drogueria_id=seed_drogueria["id"], usuario_id=seed_usuario_sistema["id"], body=body
        )
        limpiar_ordenes_compra.append(resultado.orden_compra_id)

        confirmar_orden_compra(service_client, orden_compra_id=resultado.orden_compra_id, usuario_id=seed_usuario_sistema["id"])

        oferta_final = (
            service_client.table("ofertas_items")
            .select("adjudicada")
            .eq("id", oferta["id"])
            .execute()
            .data[0]
        )
        assert oferta_final["adjudicada"] is False
    finally:
        service_client.table("oc_items").update({"oferta_item_id": None}).eq(
            "oferta_item_id", oferta["id"]
        ).execute()
        service_client.table("ofertas_items").delete().eq("id", oferta["id"]).execute()
        service_client.table("comparativas").delete().eq("id", comparativa["id"]).execute()


@pytest.mark.integration
def test_confirmar_orden_compra_ya_confirmada_levanta_conflict(
    service_client, seed_drogueria, seed_proceso_comercial, seed_usuario_sistema, numero_oc_unico,
    limpiar_ordenes_compra,
):
    body = CrearOrdenCompraRequest(
        proceso_comercial_id=seed_proceso_comercial["id"], numero_oc=numero_oc_unico(), items=[_item()]
    )
    resultado = crear_orden_compra(
        service_client, drogueria_id=seed_drogueria["id"], usuario_id=seed_usuario_sistema["id"], body=body
    )
    limpiar_ordenes_compra.append(resultado.orden_compra_id)
    confirmar_orden_compra(service_client, orden_compra_id=resultado.orden_compra_id, usuario_id=seed_usuario_sistema["id"])

    with pytest.raises(ConflictError):
        confirmar_orden_compra(service_client, orden_compra_id=resultado.orden_compra_id, usuario_id=seed_usuario_sistema["id"])


@pytest.mark.integration
def test_crear_entrega_en_oc_no_emitida_levanta_conflict(
    service_client, seed_drogueria, seed_proceso_comercial, seed_usuario_sistema, numero_oc_unico,
    limpiar_ordenes_compra,
):
    body = CrearOrdenCompraRequest(
        proceso_comercial_id=seed_proceso_comercial["id"], numero_oc=numero_oc_unico(), items=[_item()]
    )
    resultado = crear_orden_compra(
        service_client, drogueria_id=seed_drogueria["id"], usuario_id=seed_usuario_sistema["id"], body=body
    )
    limpiar_ordenes_compra.append(resultado.orden_compra_id)

    oc_item = (
        service_client.table("oc_items")
        .select("id")
        .eq("orden_compra_id", resultado.orden_compra_id)
        .execute()
        .data[0]
    )

    with pytest.raises(ConflictError):
        crear_entrega(
            service_client,
            orden_compra_id=resultado.orden_compra_id,
            items=[EntregaItemRequest(oc_item_id=oc_item["id"], cantidad_entregada=Decimal("10"))],
            fecha_entrega_planificada=None,
            fecha_entrega_real=None,
            observaciones=None,
        )


@pytest.mark.integration
def test_crear_entrega_completa_libera_stock_y_marca_oc_entregada(
    service_client,
    seed_drogueria,
    seed_proceso_comercial,
    seed_producto,
    seed_stock_factory,
    seed_usuario_sistema,
    numero_oc_unico,
    limpiar_ordenes_compra,
):
    seed_stock_factory(seed_producto["id"], disponible="20", comprometida="10")

    body = CrearOrdenCompraRequest(
        proceso_comercial_id=seed_proceso_comercial["id"],
        numero_oc=numero_oc_unico(),
        items=[_item(producto_id=seed_producto["id"], cantidad=Decimal("10"))],
    )
    resultado = crear_orden_compra(
        service_client, drogueria_id=seed_drogueria["id"], usuario_id=seed_usuario_sistema["id"], body=body
    )
    limpiar_ordenes_compra.append(resultado.orden_compra_id)
    confirmar_orden_compra(service_client, orden_compra_id=resultado.orden_compra_id, usuario_id=seed_usuario_sistema["id"])

    oc_item = (
        service_client.table("oc_items")
        .select("id")
        .eq("orden_compra_id", resultado.orden_compra_id)
        .execute()
        .data[0]
    )

    resultado_entrega = crear_entrega(
        service_client,
        orden_compra_id=resultado.orden_compra_id,
        items=[EntregaItemRequest(oc_item_id=oc_item["id"], cantidad_entregada=Decimal("10"))],
        fecha_entrega_planificada=None,
        fecha_entrega_real=None,
        observaciones=None,
    )

    assert resultado_entrega.estado == "entregada"
    assert resultado_entrega.orden_compra_estado == "entregada"

    fila_stock = (
        service_client.table("stock_productos")
        .select("cantidad_comprometida, cantidad_disponible")
        .eq("producto_id", seed_producto["id"])
        .execute()
        .data[0]
    )
    assert Decimal(str(fila_stock["cantidad_comprometida"])) == Decimal("0")
    assert Decimal(str(fila_stock["cantidad_disponible"])) == Decimal("10")

    oc_final = (
        service_client.table("ordenes_compra")
        .select("estado")
        .eq("id", resultado.orden_compra_id)
        .execute()
        .data[0]
    )
    assert oc_final["estado"] == "entregada"


@pytest.mark.integration
def test_crear_entrega_parcial_deja_oc_parcialmente_entregada(
    service_client,
    seed_drogueria,
    seed_proceso_comercial,
    seed_producto,
    seed_stock_factory,
    seed_usuario_sistema,
    numero_oc_unico,
    limpiar_ordenes_compra,
):
    seed_stock_factory(seed_producto["id"], disponible="20", comprometida="10")

    body = CrearOrdenCompraRequest(
        proceso_comercial_id=seed_proceso_comercial["id"],
        numero_oc=numero_oc_unico(),
        items=[_item(producto_id=seed_producto["id"], cantidad=Decimal("10"))],
    )
    resultado = crear_orden_compra(
        service_client, drogueria_id=seed_drogueria["id"], usuario_id=seed_usuario_sistema["id"], body=body
    )
    limpiar_ordenes_compra.append(resultado.orden_compra_id)
    confirmar_orden_compra(service_client, orden_compra_id=resultado.orden_compra_id, usuario_id=seed_usuario_sistema["id"])

    oc_item = (
        service_client.table("oc_items")
        .select("id")
        .eq("orden_compra_id", resultado.orden_compra_id)
        .execute()
        .data[0]
    )

    resultado_entrega = crear_entrega(
        service_client,
        orden_compra_id=resultado.orden_compra_id,
        items=[EntregaItemRequest(oc_item_id=oc_item["id"], cantidad_entregada=Decimal("6"))],
        fecha_entrega_planificada=None,
        fecha_entrega_real=None,
        observaciones=None,
    )

    assert resultado_entrega.orden_compra_estado == "parcialmente_entregada"

    oc_final = (
        service_client.table("ordenes_compra")
        .select("estado")
        .eq("id", resultado.orden_compra_id)
        .execute()
        .data[0]
    )
    assert oc_final["estado"] == "parcialmente_entregada"


@pytest.mark.integration
def test_crear_entrega_con_rechazo_no_descuenta_disponible_por_lo_rechazado(
    service_client,
    seed_drogueria,
    seed_proceso_comercial,
    seed_producto,
    seed_stock_factory,
    seed_usuario_sistema,
    numero_oc_unico,
    limpiar_ordenes_compra,
):
    seed_stock_factory(seed_producto["id"], disponible="20", comprometida="10")

    body = CrearOrdenCompraRequest(
        proceso_comercial_id=seed_proceso_comercial["id"],
        numero_oc=numero_oc_unico(),
        items=[_item(producto_id=seed_producto["id"], cantidad=Decimal("10"))],
    )
    resultado = crear_orden_compra(
        service_client, drogueria_id=seed_drogueria["id"], usuario_id=seed_usuario_sistema["id"], body=body
    )
    limpiar_ordenes_compra.append(resultado.orden_compra_id)
    confirmar_orden_compra(service_client, orden_compra_id=resultado.orden_compra_id, usuario_id=seed_usuario_sistema["id"])

    oc_item = (
        service_client.table("oc_items")
        .select("id")
        .eq("orden_compra_id", resultado.orden_compra_id)
        .execute()
        .data[0]
    )

    resultado_entrega = crear_entrega(
        service_client,
        orden_compra_id=resultado.orden_compra_id,
        items=[
            EntregaItemRequest(
                oc_item_id=oc_item["id"],
                cantidad_entregada=Decimal("10"),
                cantidad_rechazada=Decimal("3"),
                motivo_rechazo="Vencido",
            )
        ],
        fecha_entrega_planificada=None,
        fecha_entrega_real=None,
        observaciones=None,
    )

    assert resultado_entrega.estado == "parcial"

    fila_stock = (
        service_client.table("stock_productos")
        .select("cantidad_comprometida, cantidad_disponible")
        .eq("producto_id", seed_producto["id"])
        .execute()
        .data[0]
    )
    # Se libera el compromiso por el total (10) pero disponible solo baja por lo
    # aceptado (10 - 3 = 7): 20 - 7 = 13.
    assert Decimal(str(fila_stock["cantidad_comprometida"])) == Decimal("0")
    assert Decimal(str(fila_stock["cantidad_disponible"])) == Decimal("13")
