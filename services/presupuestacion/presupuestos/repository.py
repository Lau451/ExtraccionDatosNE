from typing import Any

from supabase import Client


def buscar_presupuesto(client: Client, *, presupuesto_id: str) -> dict[str, Any] | None:
    resultado = (
        client.table("presupuestos")
        .select("*")
        .eq("id", presupuesto_id)
        .is_("deleted_at", None)
        .limit(1)
        .execute()
    )
    return resultado.data[0] if resultado.data else None


def buscar_proceso_comercial(client: Client, *, proceso_comercial_id: str) -> dict[str, Any] | None:
    resultado = (
        client.table("procesos_comerciales")
        .select("id, drogueria_id, clase, estado")
        .eq("id", proceso_comercial_id)
        .limit(1)
        .execute()
    )
    return resultado.data[0] if resultado.data else None


def listar_items_presupuesto(client: Client, *, presupuesto_id: str) -> list[dict[str, Any]]:
    return (
        client.table("presupuesto_items")
        .select("*")
        .eq("presupuesto_id", presupuesto_id)
        .execute()
        .data
    )


def buscar_presupuesto_item(client: Client, *, presupuesto_item_id: str) -> dict[str, Any] | None:
    resultado = (
        client.table("presupuesto_items")
        .select("*")
        .eq("id", presupuesto_item_id)
        .limit(1)
        .execute()
    )
    return resultado.data[0] if resultado.data else None


def actualizar_presupuesto_item(
    client: Client, *, presupuesto_item_id: str, campos: dict[str, Any]
) -> dict[str, Any]:
    return (
        client.table("presupuesto_items")
        .update(campos)
        .eq("id", presupuesto_item_id)
        .execute()
        .data[0]
    )


def actualizar_presupuesto(
    client: Client, *, presupuesto_id: str, campos: dict[str, Any]
) -> dict[str, Any]:
    return client.table("presupuestos").update(campos).eq("id", presupuesto_id).execute().data[0]


def actualizar_proceso_comercial(
    client: Client, *, proceso_comercial_id: str, campos: dict[str, Any]
) -> None:
    client.table("procesos_comerciales").update(campos).eq("id", proceso_comercial_id).execute()


def listar_presupuesto_comercial(client: Client, *, presupuesto_id: str) -> list[dict[str, Any]]:
    return (
        client.table("v_presupuesto_comercial")
        .select("*")
        .eq("presupuesto_id", presupuesto_id)
        .execute()
        .data
    )


def listar_presupuesto_revision(client: Client, *, presupuesto_id: str) -> list[dict[str, Any]]:
    return (
        client.table("v_presupuesto_revision")
        .select("*")
        .eq("presupuesto_id", presupuesto_id)
        .execute()
        .data
    )
