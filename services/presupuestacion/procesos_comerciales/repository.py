from typing import Any

from supabase import Client


def crear_proceso_comercial(client: Client, fila: dict[str, Any]) -> dict[str, Any]:
    return client.table("procesos_comerciales").insert(fila).execute().data[0]
