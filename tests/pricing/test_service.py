from datetime import date, timedelta
from decimal import Decimal

import pytest

from services.presupuestacion.pricing.service import generar_presupuesto


@pytest.mark.integration
def test_generar_presupuesto_sin_mercado_usa_margen_objetivo(
    service_client,
    seed_drogueria,
    seed_proceso_comercial,
    seed_usuario_sistema,
    seed_item_proceso,
    seed_costo_estandar,
    seed_regla_pricing,
    limpiar_presupuestos,
):
    resultado = generar_presupuesto(
        service_client,
        proceso_comercial_id=seed_proceso_comercial["id"],
        drogueria_id=seed_drogueria["id"],
        disparado_por=seed_usuario_sistema["id"],
    )
    limpiar_presupuestos.append(resultado.presupuesto_id)

    assert resultado.regenerado is False
    assert resultado.items_sin_precio == 0
    assert resultado.cantidad_items == 1
    assert resultado.monto_total == Decimal("1300.00")

    fila_item = (
        service_client.table("presupuesto_items")
        .select("*")
        .eq("presupuesto_id", resultado.presupuesto_id)
        .execute()
        .data[0]
    )
    assert fila_item["metodo_precio"] == "margen_objetivo"
    assert Decimal(str(fila_item["costo_usado"])) == Decimal("100.00")
    assert Decimal(str(fila_item["precio_unitario"])) == Decimal("130.00")
    assert fila_item["origen_costo"] == "costo_estandar"
    assert fila_item["stock_verificado"] is True
    assert Decimal(str(fila_item["stock_al_generar"])) == Decimal("0")

    historial = (
        service_client.table("historial_cambios")
        .select("*")
        .eq("presupuesto_id", resultado.presupuesto_id)
        .execute()
        .data
    )
    assert len(historial) == 1
    assert historial[0]["tipo_cambio"] == "creacion"


@pytest.mark.integration
def test_precio_especial_gana_al_costo_estandar(
    service_client,
    seed_drogueria,
    seed_proceso_comercial,
    seed_producto,
    seed_usuario_sistema,
    seed_item_proceso,
    seed_costo_estandar,
    seed_regla_pricing,
    seed_proveedor,
    limpiar_presupuestos,
):
    especial = (
        service_client.table("precios_proveedor")
        .insert(
            {
                "drogueria_id": seed_drogueria["id"],
                "proveedor_id": seed_proveedor["id"],
                "producto_id": seed_producto["id"],
                "item_proceso_id": seed_item_proceso["id"],
                "precio_unitario": "60.00",
                "mantenimiento_hasta": (date.today() + timedelta(days=30)).isoformat(),
            }
        )
        .execute()
        .data[0]
    )
    resultado = None
    try:
        resultado = generar_presupuesto(
            service_client,
            proceso_comercial_id=seed_proceso_comercial["id"],
            drogueria_id=seed_drogueria["id"],
            disparado_por=seed_usuario_sistema["id"],
        )
        limpiar_presupuestos.append(resultado.presupuesto_id)

        fila_item = (
            service_client.table("presupuesto_items")
            .select("*")
            .eq("presupuesto_id", resultado.presupuesto_id)
            .execute()
            .data[0]
        )
        # costo especial (60) < costo estándar (100) -> gana el especial.
        # sin mercado: precio = 60 * 1.30 = 78.
        assert fila_item["origen_costo"] == "precio_especial"
        assert fila_item["precio_proveedor_id"] == especial["id"]
        assert Decimal(str(fila_item["costo_usado"])) == Decimal("60.00")
        assert Decimal(str(fila_item["precio_unitario"])) == Decimal("78.00")
    finally:
        # presupuesto_items referencia precios_proveedor (fk_pi_pp) -> hay que
        # borrar el item antes que el precio especial, no al revés.
        if resultado is not None:
            service_client.table("presupuesto_items").delete().eq(
                "presupuesto_id", resultado.presupuesto_id
            ).execute()
        service_client.table("precios_proveedor").delete().eq("id", especial["id"]).execute()


@pytest.mark.integration
def test_mercado_gana_al_piso(
    service_client,
    seed_drogueria,
    seed_proceso_comercial,
    seed_usuario_sistema,
    seed_item_proceso,
    seed_costo_estandar,
    seed_regla_pricing,
    limpiar_presupuestos,
):
    comparativa = (
        service_client.table("comparativas")
        .insert({"proceso_comercial_id": seed_proceso_comercial["id"], "drogueria_id": seed_drogueria["id"]})
        .execute()
        .data[0]
    )
    oferta = (
        service_client.table("ofertas_items")
        .insert(
            {
                "comparativa_id": comparativa["id"],
                "drogueria_id": seed_drogueria["id"],
                "item_proceso_id": seed_item_proceso["id"],
                "proveedor": "Proveedor de mercado",
                "precio_unitario": "200.00",
                "adjudicacion_estimada": True,
            }
        )
        .execute()
        .data[0]
    )
    try:
        resultado = generar_presupuesto(
            service_client,
            proceso_comercial_id=seed_proceso_comercial["id"],
            drogueria_id=seed_drogueria["id"],
            disparado_por=seed_usuario_sistema["id"],
        )
        limpiar_presupuestos.append(resultado.presupuesto_id)

        fila_item = (
            service_client.table("presupuesto_items")
            .select("*")
            .eq("presupuesto_id", resultado.presupuesto_id)
            .execute()
            .data[0]
        )
        # piso = 100*1.20=120; mediana=200, sin descuento -> referencia=200 >= piso -> gana mercado
        assert fila_item["metodo_precio"] == "mercado"
        assert Decimal(str(fila_item["precio_unitario"])) == Decimal("200.00")
        assert Decimal(str(fila_item["precio_mercado_usado"])) == Decimal("200.00")
    finally:
        service_client.table("ofertas_items").delete().eq("id", oferta["id"]).execute()
        service_client.table("comparativas").delete().eq("id", comparativa["id"]).execute()


@pytest.mark.integration
def test_piso_gana_al_mercado(
    service_client,
    seed_drogueria,
    seed_proceso_comercial,
    seed_usuario_sistema,
    seed_item_proceso,
    seed_costo_estandar,
    seed_regla_pricing,
    limpiar_presupuestos,
):
    comparativa = (
        service_client.table("comparativas")
        .insert({"proceso_comercial_id": seed_proceso_comercial["id"], "drogueria_id": seed_drogueria["id"]})
        .execute()
        .data[0]
    )
    oferta = (
        service_client.table("ofertas_items")
        .insert(
            {
                "comparativa_id": comparativa["id"],
                "drogueria_id": seed_drogueria["id"],
                "item_proceso_id": seed_item_proceso["id"],
                "proveedor": "Proveedor de mercado barato",
                "precio_unitario": "50.00",
                "adjudicacion_estimada": True,
            }
        )
        .execute()
        .data[0]
    )
    try:
        resultado = generar_presupuesto(
            service_client,
            proceso_comercial_id=seed_proceso_comercial["id"],
            drogueria_id=seed_drogueria["id"],
            disparado_por=seed_usuario_sistema["id"],
        )
        limpiar_presupuestos.append(resultado.presupuesto_id)

        fila_item = (
            service_client.table("presupuesto_items")
            .select("*")
            .eq("presupuesto_id", resultado.presupuesto_id)
            .execute()
            .data[0]
        )
        # piso = 100*1.20=120; mediana=50, sin descuento -> referencia=50 < piso -> gana el piso
        assert fila_item["metodo_precio"] == "piso_margen"
        assert Decimal(str(fila_item["precio_unitario"])) == Decimal("120.00")
        assert Decimal(str(fila_item["precio_mercado_usado"])) == Decimal("50.00")
    finally:
        service_client.table("ofertas_items").delete().eq("id", oferta["id"]).execute()
        service_client.table("comparativas").delete().eq("id", comparativa["id"]).execute()


@pytest.mark.integration
def test_sin_precio_por_falta_de_costo(
    service_client,
    seed_drogueria,
    seed_proceso_comercial,
    seed_usuario_sistema,
    seed_item_proceso,
    seed_regla_pricing,
    limpiar_presupuestos,
):
    resultado = generar_presupuesto(
        service_client,
        proceso_comercial_id=seed_proceso_comercial["id"],
        drogueria_id=seed_drogueria["id"],
        disparado_por=seed_usuario_sistema["id"],
    )
    limpiar_presupuestos.append(resultado.presupuesto_id)

    assert resultado.items_sin_precio == 1
    fila_item = (
        service_client.table("presupuesto_items")
        .select("*")
        .eq("presupuesto_id", resultado.presupuesto_id)
        .execute()
        .data[0]
    )
    assert fila_item["metodo_precio"] == "sin_precio"
    assert fila_item["costo_usado"] is None
    assert fila_item["precio_unitario"] is None
    assert fila_item["regla_pricing_id"] is not None  # había regla, faltó costo


@pytest.mark.integration
def test_sin_precio_por_falta_de_regla(
    service_client,
    seed_drogueria,
    seed_proceso_comercial,
    seed_usuario_sistema,
    seed_item_proceso,
    seed_costo_estandar,
    limpiar_presupuestos,
):
    resultado = generar_presupuesto(
        service_client,
        proceso_comercial_id=seed_proceso_comercial["id"],
        drogueria_id=seed_drogueria["id"],
        disparado_por=seed_usuario_sistema["id"],
    )
    limpiar_presupuestos.append(resultado.presupuesto_id)

    assert resultado.items_sin_precio == 1
    fila_item = (
        service_client.table("presupuesto_items")
        .select("*")
        .eq("presupuesto_id", resultado.presupuesto_id)
        .execute()
        .data[0]
    )
    assert fila_item["metodo_precio"] == "sin_precio"
    assert Decimal(str(fila_item["costo_usado"])) == Decimal("100.00")  # había costo, faltó regla
    assert fila_item["regla_pricing_id"] is None
    assert fila_item["precio_unitario"] is None


@pytest.mark.integration
def test_regenerar_presupuesto_no_deja_items_huerfanos(
    service_client,
    seed_drogueria,
    seed_proceso_comercial,
    seed_usuario_sistema,
    seed_item_proceso,
    seed_costo_estandar,
    seed_regla_pricing,
    limpiar_presupuestos,
):
    primera = generar_presupuesto(
        service_client,
        proceso_comercial_id=seed_proceso_comercial["id"],
        drogueria_id=seed_drogueria["id"],
        disparado_por=seed_usuario_sistema["id"],
    )
    limpiar_presupuestos.append(primera.presupuesto_id)
    assert primera.regenerado is False
    assert primera.monto_total == Decimal("1300.00")  # 100 * 1.30 * 10

    service_client.table("costos_productos").update({"costo_unitario": "50.00"}).eq(
        "id", seed_costo_estandar["id"]
    ).execute()

    segunda = generar_presupuesto(
        service_client,
        proceso_comercial_id=seed_proceso_comercial["id"],
        drogueria_id=seed_drogueria["id"],
        disparado_por=seed_usuario_sistema["id"],
    )

    assert segunda.regenerado is True
    assert segunda.presupuesto_id == primera.presupuesto_id
    assert segunda.monto_total == Decimal("650.00")  # 50 * 1.30 * 10

    presupuestos_del_proceso = (
        service_client.table("presupuestos")
        .select("id")
        .eq("proceso_comercial_id", seed_proceso_comercial["id"])
        .execute()
        .data
    )
    assert len(presupuestos_del_proceso) == 1  # no se duplicó el presupuesto

    items_del_presupuesto = (
        service_client.table("presupuesto_items")
        .select("*")
        .eq("presupuesto_id", primera.presupuesto_id)
        .execute()
        .data
    )
    assert len(items_del_presupuesto) == 1  # no quedaron huérfanos de la primera corrida
    assert Decimal(str(items_del_presupuesto[0]["costo_usado"])) == Decimal("50.00")

    historial = (
        service_client.table("historial_cambios")
        .select("*")
        .eq("presupuesto_id", primera.presupuesto_id)
        .order("created_at")
        .execute()
        .data
    )
    tipos = [fila["tipo_cambio"] for fila in historial]
    assert tipos.count("creacion") == 1
    # solo monto_total cambió realmente (650 != 1300); cantidad_items e items_sin_precio quedaron iguales
    assert tipos.count("campo") == 1
    fila_campo = next(f for f in historial if f["tipo_cambio"] == "campo")
    assert fila_campo["campo"] == "monto_total"
    assert fila_campo["valor_anterior"] == "1300.00"
    assert fila_campo["valor_nuevo"] == "650.00"
