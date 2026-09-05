from typing import Any

from supabase import Client

# -- sectores_contacto --------------------------------------------------------


def crear_sector(client: Client, fila: dict[str, Any]) -> dict[str, Any]:
    return client.table("sectores_contacto").insert(fila).execute().data[0]


def obtener_sector(client: Client, *, sector_id: str) -> dict[str, Any] | None:
    resultado = (
        client.table("sectores_contacto").select("*").eq("id", sector_id).limit(1).execute()
    )
    return resultado.data[0] if resultado.data else None


def listar_sectores(
    client: Client, *, drogueria_id: str, activo: bool | None = None
) -> list[dict[str, Any]]:
    query = client.table("sectores_contacto").select("*").eq("drogueria_id", drogueria_id)
    if activo is not None:
        query = query.eq("activo", activo)
    return query.order("nombre").execute().data


def actualizar_sector(client: Client, *, sector_id: str, campos: dict[str, Any]) -> dict[str, Any]:
    return client.table("sectores_contacto").update(campos).eq("id", sector_id).execute().data[0]


# -- condiciones_pago -----------------------------------------------------------


def crear_condicion_pago(client: Client, fila: dict[str, Any]) -> dict[str, Any]:
    return client.table("condiciones_pago").insert(fila).execute().data[0]


def obtener_condicion_pago(client: Client, *, condicion_pago_id: str) -> dict[str, Any] | None:
    resultado = (
        client.table("condiciones_pago")
        .select("*")
        .eq("id", condicion_pago_id)
        .limit(1)
        .execute()
    )
    return resultado.data[0] if resultado.data else None


def listar_condiciones_pago(
    client: Client, *, drogueria_id: str, activo: bool | None = None
) -> list[dict[str, Any]]:
    query = client.table("condiciones_pago").select("*").eq("drogueria_id", drogueria_id)
    if activo is not None:
        query = query.eq("activo", activo)
    return query.order("nombre").execute().data


def actualizar_condicion_pago(
    client: Client, *, condicion_pago_id: str, campos: dict[str, Any]
) -> dict[str, Any]:
    return (
        client.table("condiciones_pago")
        .update(campos)
        .eq("id", condicion_pago_id)
        .execute()
        .data[0]
    )


# -- formas_pago ------------------------------------------------------------------


def crear_forma_pago(client: Client, fila: dict[str, Any]) -> dict[str, Any]:
    return client.table("formas_pago").insert(fila).execute().data[0]


def obtener_forma_pago(client: Client, *, forma_pago_id: str) -> dict[str, Any] | None:
    resultado = (
        client.table("formas_pago").select("*").eq("id", forma_pago_id).limit(1).execute()
    )
    return resultado.data[0] if resultado.data else None


def listar_formas_pago(
    client: Client, *, drogueria_id: str, activo: bool | None = None
) -> list[dict[str, Any]]:
    query = client.table("formas_pago").select("*").eq("drogueria_id", drogueria_id)
    if activo is not None:
        query = query.eq("activo", activo)
    return query.order("nombre").execute().data


def actualizar_forma_pago(client: Client, *, forma_pago_id: str, campos: dict[str, Any]) -> dict[str, Any]:
    return client.table("formas_pago").update(campos).eq("id", forma_pago_id).execute().data[0]
