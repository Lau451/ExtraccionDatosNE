from decimal import Decimal

import pytest

from presupuestacion.core.exceptions import ConflictError, ValidationError
from presupuestacion.presupuestos.service import (
    ajustar_item,
    aprobar_presupuesto,
    presentar_presupuesto,
)


@pytest.mark.integration
def test_aprobar_bloquea_si_hay_items_sin_precio_no_resueltos(
    service_client,
    seed_drogueria,
    seed_proceso_cotizacion,
    seed_presupuesto_factory,
    seed_item_proceso_factory,
    seed_presupuesto_item_factory,
    seed_usuario_sistema,
):
    presupuesto = seed_presupuesto_factory(seed_proceso_cotizacion["id"])
    item = seed_item_proceso_factory(seed_proceso_cotizacion["id"])
    seed_presupuesto_item_factory(
        presupuesto["id"], item["id"], metodo_precio="sin_precio", excluido=False
    )

    with pytest.raises(ValidationError):
        aprobar_presupuesto(
            service_client, presupuesto_id=presupuesto["id"], usuario_id=seed_usuario_sistema["id"]
        )


@pytest.mark.integration
def test_aprobar_permite_si_el_sin_precio_esta_excluido(
    service_client,
    seed_drogueria,
    seed_proceso_cotizacion,
    seed_presupuesto_factory,
    seed_item_proceso_factory,
    seed_presupuesto_item_factory,
    seed_usuario_sistema,
):
    presupuesto = seed_presupuesto_factory(seed_proceso_cotizacion["id"])
    item = seed_item_proceso_factory(seed_proceso_cotizacion["id"])
    seed_presupuesto_item_factory(
        presupuesto["id"], item["id"], metodo_precio="sin_precio", excluido=True
    )

    resultado = aprobar_presupuesto(
        service_client, presupuesto_id=presupuesto["id"], usuario_id=seed_usuario_sistema["id"]
    )

    assert resultado.estado == "aprobado"


@pytest.mark.integration
def test_aprobar_setea_estado_y_audita(
    service_client,
    seed_drogueria,
    seed_proceso_cotizacion,
    seed_presupuesto_factory,
    seed_usuario_sistema,
):
    presupuesto = seed_presupuesto_factory(seed_proceso_cotizacion["id"])

    resultado = aprobar_presupuesto(
        service_client, presupuesto_id=presupuesto["id"], usuario_id=seed_usuario_sistema["id"]
    )

    assert resultado.estado == "aprobado"
    fila = (
        service_client.table("presupuestos").select("*").eq("id", presupuesto["id"]).execute().data[0]
    )
    assert fila["aprobado_por"] == seed_usuario_sistema["id"]
    assert fila["aprobado_at"] is not None

    historial = (
        service_client.table("historial_cambios")
        .select("*")
        .eq("presupuesto_id", presupuesto["id"])
        .execute()
        .data
    )
    assert any(h["campo"] == "estado" and h["valor_nuevo"] == "aprobado" for h in historial)


@pytest.mark.integration
def test_aprobar_falla_si_el_estado_no_es_aprobable(
    service_client,
    seed_drogueria,
    seed_proceso_cotizacion,
    seed_presupuesto_factory,
    seed_usuario_sistema,
):
    presupuesto = seed_presupuesto_factory(
        seed_proceso_cotizacion["id"],
        estado="presentado",
        aprobado_por=seed_usuario_sistema["id"],
        aprobado_at="2026-01-01T00:00:00Z",
    )

    with pytest.raises(ConflictError):
        aprobar_presupuesto(
            service_client, presupuesto_id=presupuesto["id"], usuario_id=seed_usuario_sistema["id"]
        )


@pytest.mark.integration
def test_ajustar_item_guarda_precio_original_y_recalcula_margen(
    service_client,
    seed_drogueria,
    seed_proceso_cotizacion,
    seed_presupuesto_factory,
    seed_item_proceso_factory,
    seed_presupuesto_item_factory,
    seed_usuario_sistema,
):
    presupuesto = seed_presupuesto_factory(seed_proceso_cotizacion["id"])
    item = seed_item_proceso_factory(seed_proceso_cotizacion["id"])
    presupuesto_item = seed_presupuesto_item_factory(
        presupuesto["id"],
        item["id"],
        precio_unitario="130.00",
        cantidad_ofertada="10",
        costo_usado="100.00",
        metodo_precio="margen_objetivo",
    )

    actualizado = ajustar_item(
        service_client,
        presupuesto_item_id=presupuesto_item["id"],
        precio_unitario=Decimal("150.00"),
        cantidad_ofertada=None,
        excluido=None,
        motivo_exclusion=None,
        usuario_id=seed_usuario_sistema["id"],
    )

    assert Decimal(str(actualizado["precio_original_motor"])) == Decimal("130.00")
    assert Decimal(str(actualizado["precio_unitario"])) == Decimal("150.00")
    assert actualizado["metodo_precio"] == "manual"
    assert actualizado["precio_ajustado_por"] == seed_usuario_sistema["id"]
    assert Decimal(str(actualizado["margen_resultante_pct"])) == Decimal("50.00")


@pytest.mark.integration
def test_ajustar_item_no_pisa_precio_original_motor_en_segundo_ajuste(
    service_client,
    seed_drogueria,
    seed_proceso_cotizacion,
    seed_presupuesto_factory,
    seed_item_proceso_factory,
    seed_presupuesto_item_factory,
    seed_usuario_sistema,
):
    presupuesto = seed_presupuesto_factory(seed_proceso_cotizacion["id"])
    item = seed_item_proceso_factory(seed_proceso_cotizacion["id"])
    presupuesto_item = seed_presupuesto_item_factory(
        presupuesto["id"],
        item["id"],
        precio_unitario="130.00",
        cantidad_ofertada="10",
        costo_usado="100.00",
        metodo_precio="margen_objetivo",
    )

    ajustar_item(
        service_client,
        presupuesto_item_id=presupuesto_item["id"],
        precio_unitario=Decimal("150.00"),
        cantidad_ofertada=None,
        excluido=None,
        motivo_exclusion=None,
        usuario_id=seed_usuario_sistema["id"],
    )
    segundo_ajuste = ajustar_item(
        service_client,
        presupuesto_item_id=presupuesto_item["id"],
        precio_unitario=Decimal("160.00"),
        cantidad_ofertada=None,
        excluido=None,
        motivo_exclusion=None,
        usuario_id=seed_usuario_sistema["id"],
    )

    assert Decimal(str(segundo_ajuste["precio_original_motor"])) == Decimal("130.00")
    assert Decimal(str(segundo_ajuste["precio_unitario"])) == Decimal("160.00")


@pytest.mark.integration
def test_ajustar_item_recalcula_monto_total_del_presupuesto(
    service_client,
    seed_drogueria,
    seed_proceso_cotizacion,
    seed_presupuesto_factory,
    seed_item_proceso_factory,
    seed_presupuesto_item_factory,
    seed_usuario_sistema,
):
    presupuesto = seed_presupuesto_factory(seed_proceso_cotizacion["id"], monto_total="1300.00")
    item = seed_item_proceso_factory(seed_proceso_cotizacion["id"])
    presupuesto_item = seed_presupuesto_item_factory(
        presupuesto["id"],
        item["id"],
        precio_unitario="130.00",
        cantidad_ofertada="10",
        costo_usado="100.00",
        metodo_precio="margen_objetivo",
    )

    ajustar_item(
        service_client,
        presupuesto_item_id=presupuesto_item["id"],
        precio_unitario=Decimal("150.00"),
        cantidad_ofertada=None,
        excluido=None,
        motivo_exclusion=None,
        usuario_id=seed_usuario_sistema["id"],
    )

    presupuesto_actualizado = (
        service_client.table("presupuestos").select("*").eq("id", presupuesto["id"]).execute().data[0]
    )
    assert Decimal(str(presupuesto_actualizado["monto_total"])) == Decimal("1500.00")


@pytest.mark.integration
def test_ajustar_item_excluir_lo_saca_del_monto_total(
    service_client,
    seed_drogueria,
    seed_proceso_cotizacion,
    seed_presupuesto_factory,
    seed_item_proceso_factory,
    seed_presupuesto_item_factory,
    seed_usuario_sistema,
):
    presupuesto = seed_presupuesto_factory(seed_proceso_cotizacion["id"], monto_total="1300.00")
    item = seed_item_proceso_factory(seed_proceso_cotizacion["id"])
    presupuesto_item = seed_presupuesto_item_factory(
        presupuesto["id"],
        item["id"],
        precio_unitario="130.00",
        cantidad_ofertada="10",
        costo_usado="100.00",
        metodo_precio="margen_objetivo",
    )

    ajustar_item(
        service_client,
        presupuesto_item_id=presupuesto_item["id"],
        precio_unitario=None,
        cantidad_ofertada=None,
        excluido=True,
        motivo_exclusion="No lo vendemos más",
        usuario_id=seed_usuario_sistema["id"],
    )

    presupuesto_actualizado = (
        service_client.table("presupuestos").select("*").eq("id", presupuesto["id"]).execute().data[0]
    )
    assert Decimal(str(presupuesto_actualizado["monto_total"])) == Decimal("0.00")


@pytest.mark.integration
def test_ajustar_item_sin_campos_levanta_validation_error(
    service_client,
    seed_drogueria,
    seed_proceso_cotizacion,
    seed_presupuesto_factory,
    seed_item_proceso_factory,
    seed_presupuesto_item_factory,
    seed_usuario_sistema,
):
    presupuesto = seed_presupuesto_factory(seed_proceso_cotizacion["id"])
    item = seed_item_proceso_factory(seed_proceso_cotizacion["id"])
    presupuesto_item = seed_presupuesto_item_factory(presupuesto["id"], item["id"])

    with pytest.raises(ValidationError):
        ajustar_item(
            service_client,
            presupuesto_item_id=presupuesto_item["id"],
            precio_unitario=None,
            cantidad_ofertada=None,
            excluido=None,
            motivo_exclusion=None,
            usuario_id=seed_usuario_sistema["id"],
        )


@pytest.mark.integration
def test_presentar_bloquea_si_no_esta_aprobado(
    service_client,
    seed_drogueria,
    seed_proceso_cotizacion,
    seed_presupuesto_factory,
    seed_usuario_sistema,
):
    presupuesto = seed_presupuesto_factory(seed_proceso_cotizacion["id"], estado="generado")

    with pytest.raises(ConflictError):
        presentar_presupuesto(
            service_client, presupuesto_id=presupuesto["id"], usuario_id=seed_usuario_sistema["id"]
        )


@pytest.mark.integration
def test_presentar_cotizacion_compromete_stock(
    service_client,
    seed_drogueria,
    seed_proceso_cotizacion,
    seed_presupuesto_factory,
    seed_item_proceso_factory,
    seed_presupuesto_item_factory,
    seed_producto,
    seed_stock_factory,
    seed_usuario_sistema,
):
    seed_stock_factory(seed_producto["id"], disponible="20")
    presupuesto = seed_presupuesto_factory(
        seed_proceso_cotizacion["id"],
        estado="aprobado",
        aprobado_por=seed_usuario_sistema["id"],
        aprobado_at="2026-01-01T00:00:00Z",
    )
    item = seed_item_proceso_factory(seed_proceso_cotizacion["id"], producto_id=seed_producto["id"])
    seed_presupuesto_item_factory(
        presupuesto["id"],
        item["id"],
        producto_id=seed_producto["id"],
        precio_unitario="130.00",
        cantidad_ofertada="8",
        excluido=False,
    )

    resultado = presentar_presupuesto(
        service_client, presupuesto_id=presupuesto["id"], usuario_id=seed_usuario_sistema["id"]
    )

    assert resultado.estado == "presentado"
    fila_stock = (
        service_client.table("stock_productos")
        .select("cantidad_comprometida")
        .eq("producto_id", seed_producto["id"])
        .execute()
        .data[0]
    )
    assert Decimal(str(fila_stock["cantidad_comprometida"])) == Decimal("8")

    proceso_actualizado = (
        service_client.table("procesos_comerciales")
        .select("estado")
        .eq("id", seed_proceso_cotizacion["id"])
        .execute()
        .data[0]
    )
    assert proceso_actualizado["estado"] == "presentado"


@pytest.mark.integration
def test_presentar_licitacion_no_toca_stock(
    service_client,
    seed_drogueria,
    seed_proceso_licitacion,
    seed_presupuesto_factory,
    seed_item_proceso_factory,
    seed_presupuesto_item_factory,
    seed_producto,
    seed_stock_factory,
    seed_usuario_sistema,
):
    seed_stock_factory(seed_producto["id"], disponible="20")
    presupuesto = seed_presupuesto_factory(
        seed_proceso_licitacion["id"],
        estado="aprobado",
        aprobado_por=seed_usuario_sistema["id"],
        aprobado_at="2026-01-01T00:00:00Z",
    )
    item = seed_item_proceso_factory(seed_proceso_licitacion["id"], producto_id=seed_producto["id"])
    seed_presupuesto_item_factory(
        presupuesto["id"],
        item["id"],
        producto_id=seed_producto["id"],
        precio_unitario="130.00",
        cantidad_ofertada="8",
        excluido=False,
    )

    presentar_presupuesto(
        service_client, presupuesto_id=presupuesto["id"], usuario_id=seed_usuario_sistema["id"]
    )

    fila_stock = (
        service_client.table("stock_productos")
        .select("cantidad_comprometida")
        .eq("producto_id", seed_producto["id"])
        .execute()
        .data[0]
    )
    assert Decimal(str(fila_stock["cantidad_comprometida"])) == Decimal("0")


@pytest.mark.integration
def test_presentar_con_stock_insuficiente_no_presenta_y_no_deja_compromisos_parciales(
    service_client,
    seed_drogueria,
    seed_proceso_cotizacion,
    seed_presupuesto_factory,
    seed_item_proceso_factory,
    seed_presupuesto_item_factory,
    seed_producto,
    seed_producto_factory,
    seed_stock_factory,
    seed_usuario_sistema,
):
    producto_2 = seed_producto_factory("Producto sin stock suficiente")
    seed_stock_factory(seed_producto["id"], disponible="20")
    seed_stock_factory(producto_2["id"], disponible="2")

    presupuesto = seed_presupuesto_factory(
        seed_proceso_cotizacion["id"],
        estado="aprobado",
        aprobado_por=seed_usuario_sistema["id"],
        aprobado_at="2026-01-01T00:00:00Z",
    )
    item_1 = seed_item_proceso_factory(seed_proceso_cotizacion["id"], producto_id=seed_producto["id"])
    item_2 = seed_item_proceso_factory(seed_proceso_cotizacion["id"], producto_id=producto_2["id"])
    seed_presupuesto_item_factory(
        presupuesto["id"],
        item_1["id"],
        producto_id=seed_producto["id"],
        precio_unitario="130.00",
        cantidad_ofertada="8",
        excluido=False,
    )
    seed_presupuesto_item_factory(
        presupuesto["id"],
        item_2["id"],
        producto_id=producto_2["id"],
        precio_unitario="50.00",
        cantidad_ofertada="8",
        excluido=False,
    )

    with pytest.raises(ConflictError):
        presentar_presupuesto(
            service_client, presupuesto_id=presupuesto["id"], usuario_id=seed_usuario_sistema["id"]
        )

    fila_stock_1 = (
        service_client.table("stock_productos")
        .select("cantidad_comprometida")
        .eq("producto_id", seed_producto["id"])
        .execute()
        .data[0]
    )
    assert Decimal(str(fila_stock_1["cantidad_comprometida"])) == Decimal("0")

    presupuesto_final = (
        service_client.table("presupuestos").select("estado").eq("id", presupuesto["id"]).execute().data[0]
    )
    assert presupuesto_final["estado"] == "aprobado"
