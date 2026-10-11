# Repository del módulo oc_export (openspec/changes/oc-export-progress, D6).
# Todas las funciones esperan el SERVICE client (igual que oc_entregas/repository.py)
# y filtran explícitamente por `drogueria_id`: el aislamiento por droguería que la RLS
# daría gratis se reemplaza acá por ese filtro en cada query.
from typing import Any

from supabase import Client

_TAMANO_LOTE = 200


def buscar_orden_compra(
    client: Client, *, orden_compra_id: str, drogueria_id: str
) -> dict[str, Any] | None:
    resultado = (
        client.table("ordenes_compra")
        .select(
            "id, drogueria_id, cliente_id, numero_oc, estado, es_vigente, deleted_at, "
            "version_numero, fecha_emision, direccion_entrega, "
            "exportado_at, exportado_por, archivo_exportado"
        )
        .eq("id", orden_compra_id)
        .eq("drogueria_id", drogueria_id)
        .limit(1)
        .execute()
    )
    return resultado.data[0] if resultado.data else None


def listar_oc_items(
    client: Client, *, orden_compra_id: str, drogueria_id: str
) -> list[dict[str, Any]]:
    return (
        client.table("oc_items")
        .select("id, numero_renglon, descripcion, cantidad, precio_unitario, producto_id, "
            "presupuesto_item_id, vinculo_descartado")
        .eq("orden_compra_id", orden_compra_id)
        .eq("drogueria_id", drogueria_id)
        .order("numero_renglon")
        .execute()
        .data
    )


def listar_codigos_productos(
    client: Client, *, producto_ids: list[str], drogueria_id: str
) -> dict[str, str | None]:
    """`productos.id` -> `codigo_interno` (código de artículo en Progress)."""
    codigos: dict[str, str | None] = {}
    ids_unicos = list(dict.fromkeys(producto_ids))
    for inicio in range(0, len(ids_unicos), _TAMANO_LOTE):
        lote = ids_unicos[inicio : inicio + _TAMANO_LOTE]
        filas = (
            client.table("productos")
            .select("id, codigo_interno")
            .in_("id", lote)
            .eq("drogueria_id", drogueria_id)
            .execute()
            .data
        )
        codigos.update({fila["id"]: fila.get("codigo_interno") for fila in filas})
    return codigos


def listar_entregas(
    client: Client, *, orden_compra_id: str, drogueria_id: str
) -> list[dict[str, Any]]:
    return (
        client.table("entregas_oc")
        .select("id, numero_entrega, fecha_entrega_planificada")
        .eq("orden_compra_id", orden_compra_id)
        .eq("drogueria_id", drogueria_id)
        .order("numero_entrega")
        .execute()
        .data
    )


def listar_entregas_items(
    client: Client, *, entrega_oc_ids: list[str], drogueria_id: str
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for inicio in range(0, len(entrega_oc_ids), _TAMANO_LOTE):
        lote = entrega_oc_ids[inicio : inicio + _TAMANO_LOTE]
        items.extend(
            client.table("entregas_oc_items")
            .select("entrega_oc_id, oc_item_id, cantidad_planificada")
            .in_("entrega_oc_id", lote)
            .eq("drogueria_id", drogueria_id)
            .execute()
            .data
        )
    return items


def listar_codigos_cliente(
    client: Client, *, tercero_id: str, drogueria_id: str
) -> list[str]:
    """D3: todos los códigos `cliente` del tercero en `terceros_legacy_map`. El caller
    exige exactamente uno."""
    filas = (
        client.table("terceros_legacy_map")
        .select("codigo_legacy")
        .eq("tercero_id", tercero_id)
        .eq("drogueria_id", drogueria_id)
        .eq("entidad_legacy", "cliente")
        .execute()
        .data
    )
    return [fila["codigo_legacy"] for fila in filas]


def buscar_cuit_tercero(client: Client, *, tercero_id: str, drogueria_id: str) -> str | None:
    filas = (
        client.table("terceros")
        .select("cuit")
        .eq("id", tercero_id)
        .eq("drogueria_id", drogueria_id)
        .limit(1)
        .execute()
        .data
    )
    return filas[0].get("cuit") if filas else None


def buscar_nombre_usuario(client: Client, *, usuario_id: str) -> str | None:
    filas = (
        client.table("usuarios").select("nombre").eq("id", usuario_id).limit(1).execute().data
    )
    return filas[0].get("nombre") if filas else None


def hash_plan(client: Client, *, orden_compra_id: str) -> str:
    """Hash del plan de entregas vigente (RPC `hash_plan_oc`, migración 0033): la única
    definición de "el plan" vive en SQL, la misma que usa `marcar_oc_exportada`."""
    return client.rpc("hash_plan_oc", {"p_orden_compra_id": orden_compra_id}).execute().data


def marcar_exportada(
    client: Client,
    *,
    orden_compra_id: str,
    drogueria_id: str,
    usuario_id: str,
    archivo_exportado: str,
    plan_hash: str,
) -> str:
    """CAS (D6) en una sola transacción (RPC `marcar_oc_exportada`, migración 0033):
    bloquea la OC, verifica `exportado_at IS NULL` y que el plan siga siendo el de
    `plan_hash`, y recién entonces marca. Devuelve `ok`, `ya_exportada`,
    `plan_cambiado` o `no_encontrada`."""
    return (
        client.rpc(
            "marcar_oc_exportada",
            {
                "p_orden_compra_id": orden_compra_id,
                "p_drogueria_id": drogueria_id,
                "p_usuario_id": usuario_id,
                "p_archivo": archivo_exportado,
                "p_plan_hash": plan_hash,
            },
        )
        .execute()
        .data
    )
