from typing import Any

from supabase import Client


def obtener_drogueria(client: Client, *, drogueria_id: str) -> dict[str, Any] | None:
    resultado = client.table("droguerias").select("*").eq("id", drogueria_id).limit(1).execute()
    return resultado.data[0] if resultado.data else None


def crear_drogueria(client: Client, fila: dict[str, Any]) -> dict[str, Any]:
    return client.table("droguerias").insert(fila).execute().data[0]


def actualizar_drogueria(client: Client, *, drogueria_id: str, campos: dict[str, Any]) -> dict[str, Any]:
    return client.table("droguerias").update(campos).eq("id", drogueria_id).execute().data[0]


def eliminar_drogueria(client: Client, *, drogueria_id: str) -> None:
    client.table("droguerias").delete().eq("id", drogueria_id).execute()
