from datetime import datetime, timezone
from typing import Any

from supabase import Client


def buscar_item_proceso(client: Client, *, item_proceso_id: str) -> dict[str, Any] | None:
    resultado = (
        client.table("items_proceso").select("*").eq("id", item_proceso_id).limit(1).execute()
    )
    return resultado.data[0] if resultado.data else None


def buscar_proceso_comercial(client: Client, *, proceso_comercial_id: str) -> dict[str, Any] | None:
    resultado = (
        client.table("procesos_comerciales")
        .select("id, drogueria_id, cliente_id")
        .eq("id", proceso_comercial_id)
        .limit(1)
        .execute()
    )
    return resultado.data[0] if resultado.data else None


def buscar_alias_vigente(
    client: Client, *, cliente_id: str, descripcion_normalizada: str
) -> dict[str, Any] | None:
    resultado = (
        client.table("cliente_producto_alias")
        .select("*")
        .eq("cliente_id", cliente_id)
        .eq("descripcion_normalizada", descripcion_normalizada)
        .eq("vigente", True)
        .limit(1)
        .execute()
    )
    return resultado.data[0] if resultado.data else None


def listar_productos_activos(client: Client, *, drogueria_id: str) -> list[dict[str, Any]]:
    resultado = (
        client.table("productos")
        .select("id, nombre")
        .eq("drogueria_id", drogueria_id)
        .eq("activo", True)
        .is_("deleted_at", None)
        .execute()
    )
    return resultado.data


def marcar_alias_usado(client: Client, *, alias_id: str, veces_usado: int) -> None:
    client.table("cliente_producto_alias").update(
        {
            "veces_usado": veces_usado + 1,
            "ultimo_uso_at": datetime.now(timezone.utc).isoformat(),
        }
    ).eq("id", alias_id).execute()


def invalidar_alias(client: Client, *, alias_id: str) -> None:
    client.table("cliente_producto_alias").update({"vigente": False}).eq("id", alias_id).execute()


def crear_alias(
    client: Client,
    *,
    cliente_id: str,
    drogueria_id: str,
    producto_id: str,
    descripcion_original: str,
    descripcion_normalizada: str,
    creado_por: str,
) -> dict[str, Any]:
    fila = {
        "cliente_id": cliente_id,
        "drogueria_id": drogueria_id,
        "producto_id": producto_id,
        "descripcion_original": descripcion_original,
        "descripcion_normalizada": descripcion_normalizada,
        "creado_por": creado_por,
    }
    return client.table("cliente_producto_alias").insert(fila).execute().data[0]


def insertar_candidatos(client: Client, filas: list[dict[str, Any]]) -> None:
    if filas:
        client.table("matching_candidatos").insert(filas).execute()


def marcar_candidato_elegido(client: Client, *, item_proceso_id: str, producto_id: str) -> None:
    client.table("matching_candidatos").update({"elegido": True}).eq(
        "item_proceso_id", item_proceso_id
    ).eq("producto_id", producto_id).execute()


def actualizar_item_matching(
    client: Client, *, item_proceso_id: str, campos: dict[str, Any]
) -> dict[str, Any]:
    return client.table("items_proceso").update(campos).eq("id", item_proceso_id).execute().data[0]
