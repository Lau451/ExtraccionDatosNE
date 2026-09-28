"""Caso de integración para oc_entregas (T3, odd/tasks/oc-entregas-
planificacion.md): una OC con 2 renglones CONFIRMADOS (uno con producto de
pack x25 conocido, otro sin producto -- pack desconocido) y 1 DESCARTADO. Sin
renglón pendiente -- `agregar_renglon_pendiente` lo agrega aparte para los
tests que necesitan ejercitar el gate.

No es un pytest fixture en sí: mismo patrón factory (`sembrar`/`limpiar`) que
tests/oc_presupuesto/fixtures/samco_rafaela.py."""

import secrets
import uuid
from typing import Any

from supabase import Client

NUMERO_OC = "OC-ENTREGAS-TEST"
CANTIDAD_CONFIRMADO_CON_PACK = "110"  # x25 -> sugerido [50, 25, 35] para N=3
CANTIDAD_CONFIRMADO_SIN_PACK = "10"
CANTIDAD_DESCARTADO = "7"


def sembrar(service_client: Client, *, drogueria_id: str) -> dict[str, Any]:
    sufijo = uuid.uuid4().hex[:8]
    tercero = (
        service_client.table("terceros")
        .insert(
            {
                "drogueria_id": drogueria_id,
                "razon_social": f"Cliente oc_entregas test {sufijo}",
                "cuit": f"20{secrets.randbelow(10**9):09d}",  # 11 dígitos (ck_terceros_cuit)
            }
        )
        .execute()
        .data[0]
    )
    cliente = (
        service_client.table("clientes")
        .insert({"id": tercero["id"], "drogueria_id": drogueria_id, "tipo": "hospital"})
        .execute()
        .data[0]
    )
    proceso = (
        service_client.table("procesos_comerciales")
        .insert(
            {
                "drogueria_id": drogueria_id,
                "cliente_id": cliente["id"],
                "clase": "cotizacion",
                "nombre": f"oc_entregas test {sufijo}",
            }
        )
        .execute()
        .data[0]
    )
    presupuesto = (
        service_client.table("presupuestos")
        .insert(
            {
                "proceso_comercial_id": proceso["id"],
                "drogueria_id": drogueria_id,
                "estado": "generado",
                "cantidad_items": 1,
            }
        )
        .execute()
        .data[0]
    )
    item_proceso = (
        service_client.table("items_proceso")
        .insert(
            {
                "proceso_comercial_id": proceso["id"],
                "drogueria_id": drogueria_id,
                "numero_renglon": 1,
                "descripcion": "Renglón de presupuesto (oc_entregas test)",
                "cantidad": "1",
            }
        )
        .execute()
        .data[0]
    )
    # Un solo presupuesto_item -- ambos renglones confirmados de la OC pueden
    # apuntar al mismo (no hay unicidad sobre presupuesto_item_id en oc_items,
    # aviso N:1 de D5): acá solo hace falta que la FK resuelva, el contenido
    # del presupuesto no importa para este módulo.
    presupuesto_item = (
        service_client.table("presupuesto_items")
        .insert(
            {
                "presupuesto_id": presupuesto["id"],
                "drogueria_id": drogueria_id,
                "item_proceso_id": item_proceso["id"],
                "precio_unitario": "10.00",
                "cantidad_ofertada": "1",
            }
        )
        .execute()
        .data[0]
    )
    producto = (
        service_client.table("productos")
        .insert(
            {
                "drogueria_id": drogueria_id,
                "codigo_interno": f"OCE-TEST-{sufijo}",
                "nombre": "Producto con pack x25 (oc_entregas test)",
                "unidades_por_presentacion": 25,
            }
        )
        .execute()
        .data[0]
    )
    orden_compra = (
        service_client.table("ordenes_compra")
        .insert(
            {
                "cliente_id": cliente["id"],
                "drogueria_id": drogueria_id,
                "numero_oc": f"{NUMERO_OC}-{sufijo}",
                "cantidad_entregas": 3,
            }
        )
        .execute()
        .data[0]
    )

    oc_item_con_pack = (
        service_client.table("oc_items")
        .insert(
            {
                "orden_compra_id": orden_compra["id"],
                "drogueria_id": drogueria_id,
                "numero_renglon": 1,
                "descripcion": "Renglón confirmado con pack conocido (x25)",
                "cantidad": CANTIDAD_CONFIRMADO_CON_PACK,
                "precio_unitario": "10.00",
                "producto_id": producto["id"],
                "presupuesto_item_id": presupuesto_item["id"],
                # ck_oci_vinculo_origen: presupuesto_item_id IS NULL <=>
                # vinculo_origen IS NULL -- un renglón "confirmado" (D4) SIEMPRE
                # necesita el origen seteado, o el insert revienta el CHECK.
                "vinculo_origen": "manual",
            }
        )
        .execute()
        .data[0]
    )
    oc_item_sin_pack = (
        service_client.table("oc_items")
        .insert(
            {
                "orden_compra_id": orden_compra["id"],
                "drogueria_id": drogueria_id,
                "numero_renglon": 2,
                "descripcion": "Renglón confirmado sin producto (pack desconocido)",
                "cantidad": CANTIDAD_CONFIRMADO_SIN_PACK,
                "precio_unitario": "5.00",
                "presupuesto_item_id": presupuesto_item["id"],
                "vinculo_origen": "manual",
            }
        )
        .execute()
        .data[0]
    )
    oc_item_descartado = (
        service_client.table("oc_items")
        .insert(
            {
                "orden_compra_id": orden_compra["id"],
                "drogueria_id": drogueria_id,
                "numero_renglon": 3,
                "descripcion": "Renglón descartado",
                "cantidad": CANTIDAD_DESCARTADO,
                "precio_unitario": "1.00",
                "vinculo_descartado": True,
            }
        )
        .execute()
        .data[0]
    )

    return {
        "tercero_id": tercero["id"],
        "cliente_id": cliente["id"],
        "proceso_comercial_id": proceso["id"],
        "presupuesto_id": presupuesto["id"],
        "producto_id": producto["id"],
        "orden_compra_id": orden_compra["id"],
        "oc_item_con_pack": oc_item_con_pack,
        "oc_item_sin_pack": oc_item_sin_pack,
        "oc_item_descartado": oc_item_descartado,
    }


def agregar_renglon_pendiente(service_client: Client, *, caso: dict[str, Any]) -> dict[str, Any]:
    """Agrega un 4to renglón sin vincular (D4: 'pendiente' es el estado cero)
    -- para los tests del gate ('puede_planificar' False / 409 en el PUT)."""
    return (
        service_client.table("oc_items")
        .insert(
            {
                "orden_compra_id": caso["orden_compra_id"],
                "drogueria_id": caso["oc_item_con_pack"]["drogueria_id"],
                "numero_renglon": 4,
                "descripcion": "Renglón pendiente de matching",
                "cantidad": "5",
                "precio_unitario": "2.00",
            }
        )
        .execute()
        .data[0]
    )


def limpiar(service_client: Client, caso: dict[str, Any]) -> None:
    """Reversa completa (orden que las FK exigen). Incluye `entregas_oc`
    -- a diferencia de oc_presupuesto, los tests de este módulo SÍ escriben
    ahí (PUT de planificación)."""
    service_client.table("entregas_oc").delete().eq(
        "orden_compra_id", caso["orden_compra_id"]
    ).execute()
    service_client.table("oc_items").delete().eq(
        "orden_compra_id", caso["orden_compra_id"]
    ).execute()
    service_client.table("ordenes_compra").delete().eq("id", caso["orden_compra_id"]).execute()
    service_client.table("productos").delete().eq("id", caso["producto_id"]).execute()
    service_client.table("presupuesto_items").delete().eq(
        "presupuesto_id", caso["presupuesto_id"]
    ).execute()
    service_client.table("presupuestos").delete().eq("id", caso["presupuesto_id"]).execute()
    service_client.table("items_proceso").delete().eq(
        "proceso_comercial_id", caso["proceso_comercial_id"]
    ).execute()
    service_client.table("procesos_comerciales").delete().eq(
        "id", caso["proceso_comercial_id"]
    ).execute()
    service_client.table("clientes").delete().eq("id", caso["cliente_id"]).execute()
    service_client.table("terceros").delete().eq("id", caso["tercero_id"]).execute()
