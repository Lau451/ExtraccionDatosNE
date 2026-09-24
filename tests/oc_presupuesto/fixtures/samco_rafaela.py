"""Caso real validado end-to-end (proposal.md § Intent, design.md): cliente
SAMCo Rafaela -- Hospital Dr. Jaime Ferré (CUIT 30-67428388-8), presupuesto
`00246033` cargado a mano (sin fila en `presupuesto_legacy_map` -- D2.1: fue
cargado a mano, no por el import legado, así que `numero_presupuesto` viaja
`null` por diseño, no por un dato faltante), OC real Nro 00104857 con 2
renglones que matchean exacto por precio contra los 2 renglones del
presupuesto, sin ambigüedad.

No es un pytest fixture en sí: es un factory de bajo nivel (`sembrar`/
`limpiar`) para que tests/oc_presupuesto/conftest.py lo envuelva en un
fixture que siembra en el setup y limpia en el `finally` del teardown --
mismo patrón que tests/extraccion/conftest.py::seed_cliente_factory
(tasks.md 2.1)."""

from typing import Any

from supabase import Client

# ck_terceros_cuit exige 11 dígitos sin guiones (docs/schema/extractor_final.sql
# ck_terceros_cuit): 30-67428388-8 (formato humano de proposal.md) normalizado.
CUIT_SAMCO_RAFAELA = "30674283888"
NUMERO_OC = "00104857"

# Dos renglones sin ambigüedad: precios distintos entre sí, así que el join
# por precio exacto no necesita desempate por descripción (ese caso propio de
# D7 vive en sus propios tests unitarios, no en esta fixture de integración).
RENGLONES = [
    {
        "descripcion": "Amoxicilina 500mg x 21 comprimidos",
        "cantidad": "10",
        "precio_unitario": "1234.56",
    },
    {
        "descripcion": "Ibuprofeno 600mg x 30 comprimidos",
        "cantidad": "5",
        "precio_unitario": "567.89",
    },
]


def sembrar(service_client: Client, *, drogueria_id: str) -> dict[str, Any]:
    """Crea cliente + proceso + presupuesto + 2 presupuesto_items + OC + 2
    oc_items, con precio exacto entre cada par (renglón de OC <-> renglón de
    presupuesto). Devuelve un dict con todos los ids/filas relevantes."""
    tercero = (
        service_client.table("terceros")
        .insert(
            {
                "drogueria_id": drogueria_id,
                "razon_social": "SAMCo Rafaela — Hospital Dr. Jaime Ferré",
                "cuit": CUIT_SAMCO_RAFAELA,
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
                "nombre": "SAMCo Rafaela — caso real de test (oc-presupuesto)",
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
                "cantidad_items": len(RENGLONES),
            }
        )
        .execute()
        .data[0]
    )

    items_proceso: list[dict[str, Any]] = []
    presupuesto_items: list[dict[str, Any]] = []
    for numero, renglon in enumerate(RENGLONES, start=1):
        item_proceso = (
            service_client.table("items_proceso")
            .insert(
                {
                    "proceso_comercial_id": proceso["id"],
                    "drogueria_id": drogueria_id,
                    "numero_renglon": numero,
                    "descripcion": renglon["descripcion"],
                    "cantidad": renglon["cantidad"],
                }
            )
            .execute()
            .data[0]
        )
        items_proceso.append(item_proceso)

        presupuesto_item = (
            service_client.table("presupuesto_items")
            .insert(
                {
                    "presupuesto_id": presupuesto["id"],
                    "drogueria_id": drogueria_id,
                    "item_proceso_id": item_proceso["id"],
                    "precio_unitario": renglon["precio_unitario"],
                    "cantidad_ofertada": renglon["cantidad"],
                }
            )
            .execute()
            .data[0]
        )
        presupuesto_items.append(presupuesto_item)

    orden_compra = (
        service_client.table("ordenes_compra")
        .insert(
            {
                "cliente_id": cliente["id"],
                "drogueria_id": drogueria_id,
                "numero_oc": NUMERO_OC,
            }
        )
        .execute()
        .data[0]
    )

    oc_items: list[dict[str, Any]] = []
    for numero, renglon in enumerate(RENGLONES, start=1):
        oc_item = (
            service_client.table("oc_items")
            .insert(
                {
                    "orden_compra_id": orden_compra["id"],
                    "drogueria_id": drogueria_id,
                    "numero_renglon": numero,
                    "descripcion": renglon["descripcion"],
                    "cantidad": renglon["cantidad"],
                    "precio_unitario": renglon["precio_unitario"],
                }
            )
            .execute()
            .data[0]
        )
        oc_items.append(oc_item)

    return {
        "tercero_id": tercero["id"],
        "cliente_id": cliente["id"],
        "proceso_comercial_id": proceso["id"],
        "presupuesto_id": presupuesto["id"],
        "items_proceso": items_proceso,
        "presupuesto_items": presupuesto_items,
        "orden_compra_id": orden_compra["id"],
        "oc_items": oc_items,
    }


def limpiar(service_client: Client, caso: dict[str, Any]) -> None:
    """Reversa completa en el orden que las FK exigen. Se llama desde el
    `finally` del fixture de conftest.py (tasks.md 2.1) -- nunca desde el
    propio test, para que corra incluso si el test falla a mitad."""
    service_client.table("oc_items").delete().eq(
        "orden_compra_id", caso["orden_compra_id"]
    ).execute()
    service_client.table("ordenes_compra").delete().eq("id", caso["orden_compra_id"]).execute()
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
