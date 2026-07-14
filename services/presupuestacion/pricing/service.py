import json
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from supabase import Client

from services.presupuestacion.core.audit import registrar_cambios, registrar_evento_ciclo_vida
from services.presupuestacion.core.database import get_service_client
from services.presupuestacion.core.exceptions import NotFoundError
from services.presupuestacion.pricing import repository as repo
from services.presupuestacion.pricing.models import (
    DetalleCalculo,
    OrigenCosto,
    ResultadoGenerarPresupuesto,
    ResultadoPricingItem,
)

_DOS_DECIMALES = Decimal("0.01")


def _q(valor: Decimal) -> Decimal:
    return valor.quantize(_DOS_DECIMALES, rounding=ROUND_HALF_UP)


def _decimal_o_none(valor: Any) -> Decimal | None:
    return None if valor is None else Decimal(str(valor))


def resolver_costo(
    client: Client, *, item: dict[str, Any], drogueria_id: str
) -> tuple[Decimal | None, OrigenCosto | None, str | None, date | None]:
    cantidad = Decimal(str(item["cantidad"]))
    producto_id = item["producto_id"]

    especial = repo.buscar_precio_especial_puntual(
        client, item_proceso_id=item["id"], cantidad=cantidad
    ) or repo.buscar_precio_especial_general(
        client, producto_id=producto_id, drogueria_id=drogueria_id, cantidad=cantidad
    )
    estandar = repo.buscar_costo_estandar_vigente(client, producto_id=producto_id)

    costo_especial = _decimal_o_none(especial["precio_unitario"]) if especial else None
    costo_estandar = _decimal_o_none(estandar["costo_unitario"]) if estandar else None

    if costo_especial is not None and (costo_estandar is None or costo_especial < costo_estandar):
        return costo_especial, "precio_especial", especial["id"], especial["mantenimiento_hasta"]
    if costo_estandar is not None:
        return costo_estandar, "costo_estandar", None, None
    return None, None, None, None


def calcular_precio(
    client: Client, *, costo: Decimal, regla: dict[str, Any], producto_id: str, drogueria_id: str
) -> tuple[Decimal, DetalleCalculo] | None:
    margen_minimo_pct = Decimal(str(regla["margen_minimo_pct"]))
    piso = _q(costo * (1 + margen_minimo_pct / 100))

    mercado = repo.buscar_precio_mercado(
        client,
        producto_id=producto_id,
        drogueria_id=drogueria_id,
        meses_ventana=regla["meses_ventana_mercado"],
    )
    mediana = _decimal_o_none(mercado["precio_mediana"]) if mercado else None

    if mediana is not None:
        descuento_pct = _decimal_o_none(regla["descuento_vs_mercado_pct"]) or Decimal("0")
        referencia = _q(mediana * (1 - descuento_pct / 100))
        precio, metodo = (referencia, "mercado") if referencia >= piso else (piso, "piso_margen")
        detalle = DetalleCalculo(
            origen_mercado=True,
            precio_mediana=mediana,
            muestras=mercado.get("muestras"),
            ventana_meses=regla["meses_ventana_mercado"],
            descuento_aplicado_pct=descuento_pct,
            piso_calculado=piso,
            referencia_calculada=referencia,
            gano=metodo,
        )
        return precio, detalle

    margen_objetivo_pct = _decimal_o_none(regla["margen_objetivo_pct"])
    if margen_objetivo_pct is None:
        return None

    precio = _q(costo * (1 + margen_objetivo_pct / 100))
    detalle = DetalleCalculo(
        origen_mercado=False,
        precio_mediana=None,
        muestras=None,
        ventana_meses=regla["meses_ventana_mercado"],
        descuento_aplicado_pct=None,
        piso_calculado=piso,
        referencia_calculada=None,
        gano="margen_objetivo",
    )
    return precio, detalle


def verificar_stock(client: Client, *, producto_id: str, cantidad: Decimal) -> tuple[bool, Decimal]:
    libre = repo.buscar_stock_libre(client, producto_id=producto_id)
    return libre >= cantidad, libre


def calcular_item(
    client: Client,
    *,
    item: dict[str, Any],
    drogueria_id: str,
    clase_proceso: str,
    cliente_id: str | None,
) -> ResultadoPricingItem:
    producto_id = item["producto_id"]
    cantidad = Decimal(str(item["cantidad"]))

    costo, origen_costo, precio_proveedor_id, mantenimiento = resolver_costo(
        client, item=item, drogueria_id=drogueria_id
    )

    producto = repo.buscar_producto(client, producto_id=producto_id)
    regla = repo.buscar_regla_aplicable(
        client,
        drogueria_id=drogueria_id,
        cliente_id=cliente_id,
        clase_proceso=clase_proceso,
        categoria_id=producto["categoria_id"] if producto else None,
    )

    resultado_precio = None
    if costo is not None and regla is not None:
        resultado_precio = calcular_precio(
            client, costo=costo, regla=regla, producto_id=producto_id, drogueria_id=drogueria_id
        )

    if resultado_precio is None:
        return ResultadoPricingItem(
            item_proceso_id=item["id"],
            producto_id=producto_id,
            costo_usado=costo,
            origen_costo=origen_costo,
            precio_proveedor_id=precio_proveedor_id,
            mantenimiento_hasta_usado=mantenimiento,
            precio_unitario=None,
            cantidad_ofertada=cantidad,
            precio_mercado_usado=None,
            regla_pricing_id=regla["id"] if regla else None,
            metodo_precio="sin_precio",
            margen_resultante_pct=None,
            detalle_calculo=None,
            stock_verificado=False,
            stock_al_generar=None,
        )

    precio, detalle = resultado_precio
    margen_resultante_pct = _q((precio - costo) / costo * 100)

    stock_verificado = False
    stock_al_generar = None
    if clase_proceso == "cotizacion":
        _, stock_al_generar = verificar_stock(client, producto_id=producto_id, cantidad=cantidad)
        stock_verificado = True

    return ResultadoPricingItem(
        item_proceso_id=item["id"],
        producto_id=producto_id,
        costo_usado=costo,
        origen_costo=origen_costo,
        precio_proveedor_id=precio_proveedor_id,
        mantenimiento_hasta_usado=mantenimiento,
        precio_unitario=precio,
        cantidad_ofertada=cantidad,
        precio_mercado_usado=detalle.precio_mediana,
        regla_pricing_id=regla["id"],
        metodo_precio=detalle.gano,
        margen_resultante_pct=margen_resultante_pct,
        detalle_calculo=detalle,
        stock_verificado=stock_verificado,
        stock_al_generar=stock_al_generar,
    )


def _decimal_a_texto(valor: Decimal | None) -> str | None:
    return None if valor is None else str(valor)


def _a_fila_presupuesto_item(
    presupuesto_id: str, drogueria_id: str, resultado: ResultadoPricingItem
) -> dict[str, Any]:
    return {
        "presupuesto_id": presupuesto_id,
        "drogueria_id": drogueria_id,
        "item_proceso_id": resultado.item_proceso_id,
        "producto_id": resultado.producto_id,
        "precio_unitario": _decimal_a_texto(resultado.precio_unitario),
        "cantidad_ofertada": _decimal_a_texto(resultado.cantidad_ofertada),
        "regla_pricing_id": resultado.regla_pricing_id,
        "metodo_precio": resultado.metodo_precio,
        "costo_usado": _decimal_a_texto(resultado.costo_usado),
        "origen_costo": resultado.origen_costo,
        "precio_proveedor_id": resultado.precio_proveedor_id,
        "mantenimiento_hasta_usado": (
            resultado.mantenimiento_hasta_usado.isoformat()
            if resultado.mantenimiento_hasta_usado
            else None
        ),
        "precio_mercado_usado": _decimal_a_texto(resultado.precio_mercado_usado),
        "margen_resultante_pct": _decimal_a_texto(resultado.margen_resultante_pct),
        "detalle_calculo": (
            json.loads(resultado.detalle_calculo.model_dump_json())
            if resultado.detalle_calculo
            else None
        ),
        "stock_verificado": resultado.stock_verificado,
        "stock_al_generar": _decimal_a_texto(resultado.stock_al_generar),
    }


def generar_presupuesto(
    client: Client, *, proceso_comercial_id: str, drogueria_id: str, disparado_por: str
) -> ResultadoGenerarPresupuesto:
    proceso = repo.buscar_proceso_comercial(client, proceso_comercial_id=proceso_comercial_id)
    if proceso is None:
        raise NotFoundError("No se encontró el proceso comercial")

    items = repo.buscar_items_con_producto(client, proceso_comercial_id=proceso_comercial_id)
    resultados = [
        calcular_item(
            client,
            item=item,
            drogueria_id=drogueria_id,
            clase_proceso=proceso["clase"],
            cliente_id=proceso["cliente_id"],
        )
        for item in items
    ]

    monto_total = _q(
        sum(
            (
                r.precio_unitario * r.cantidad_ofertada
                for r in resultados
                if r.precio_unitario is not None and r.cantidad_ofertada is not None
            ),
            Decimal("0"),
        )
    )
    items_sin_precio = sum(1 for r in resultados if r.metodo_precio == "sin_precio")
    cantidad_items = len(resultados)

    existente = repo.buscar_presupuesto_abierto(client, proceso_comercial_id=proceso_comercial_id)
    regenerado = existente is not None

    if not regenerado:
        fila_presupuesto = {
            "proceso_comercial_id": proceso_comercial_id,
            "drogueria_id": drogueria_id,
            "estado": "generado",
            "monto_total": str(monto_total),
            "cantidad_items": cantidad_items,
            "items_sin_precio": items_sin_precio,
        }
        presupuesto_id = client.table("presupuestos").insert(fila_presupuesto).execute().data[0]["id"]
        registrar_evento_ciclo_vida(
            client,
            entidad="presupuesto",
            entidad_id=presupuesto_id,
            drogueria_id=drogueria_id,
            tipo_cambio="creacion",
            origen="sistema",
            usuario_id=disparado_por,
        )
    else:
        presupuesto_id = existente["id"]
        client.table("presupuesto_items").delete().eq("presupuesto_id", presupuesto_id).execute()
        client.table("presupuestos").update(
            {
                "monto_total": str(monto_total),
                "cantidad_items": cantidad_items,
                "items_sin_precio": items_sin_precio,
            }
        ).eq("id", presupuesto_id).execute()

        monto_total_anterior = _q(_decimal_o_none(existente["monto_total"]) or Decimal("0"))
        posibles_cambios = {
            "monto_total": (monto_total_anterior, monto_total),
            "cantidad_items": (existente["cantidad_items"], cantidad_items),
            "items_sin_precio": (existente["items_sin_precio"], items_sin_precio),
        }
        cambios_reales = {
            campo: (anterior, nuevo)
            for campo, (anterior, nuevo) in posibles_cambios.items()
            if anterior != nuevo
        }
        if cambios_reales:
            registrar_cambios(
                client,
                entidad="presupuesto",
                entidad_id=presupuesto_id,
                drogueria_id=drogueria_id,
                cambios=cambios_reales,
                origen="sistema",
                usuario_id=disparado_por,
            )

    filas_items = [_a_fila_presupuesto_item(presupuesto_id, drogueria_id, r) for r in resultados]
    if filas_items:
        client.table("presupuesto_items").insert(filas_items).execute()

    return ResultadoGenerarPresupuesto(
        presupuesto_id=presupuesto_id,
        monto_total=monto_total,
        cantidad_items=cantidad_items,
        items_sin_precio=items_sin_precio,
        regenerado=regenerado,
    )


def generar_presupuesto_para_endpoint(
    *, proceso_comercial_id: str, drogueria_id: str, disparado_por: str
) -> ResultadoGenerarPresupuesto:
    """Único punto donde `pricing` usa service_role — el router nunca lo importa directamente."""
    return generar_presupuesto(
        get_service_client(),
        proceso_comercial_id=proceso_comercial_id,
        drogueria_id=drogueria_id,
        disparado_por=disparado_por,
    )
