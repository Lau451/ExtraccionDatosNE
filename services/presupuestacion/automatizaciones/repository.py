from datetime import datetime, timezone
from typing import Any

from supabase import Client

# columnas FK soportadas por acciones_ejecutadas / historial_cambios (ck_ae_una_entidad
# solo cubre estas 5 -- reglas_automatizacion.entidad_objetivo admite además
# 'extraction_result' y 'entrega', que NO tienen columna equivalente en esta tabla).
COLUMNA_FK_POR_ENTIDAD: dict[str, str] = {
    "proceso_comercial": "proceso_comercial_id",
    "comparativa": "comparativa_id",
    "orden_compra": "orden_compra_id",
    "presupuesto": "presupuesto_id",
    "evento": "evento_id",
}


def crear_regla(client: Client, fila: dict[str, Any]) -> dict[str, Any]:
    return client.table("reglas_automatizacion").insert(fila).execute().data[0]


def obtener_regla(client: Client, *, regla_id: str) -> dict[str, Any] | None:
    resultado = (
        client.table("reglas_automatizacion").select("*").eq("id", regla_id).limit(1).execute()
    )
    return resultado.data[0] if resultado.data else None


def listar_reglas(client: Client, *, drogueria_id: str, activa: bool | None = None) -> list[dict[str, Any]]:
    query = client.table("reglas_automatizacion").select("*").eq("drogueria_id", drogueria_id)
    if activa is not None:
        query = query.eq("activa", activa)
    return query.order("prioridad", desc=True).execute().data


def actualizar_regla(client: Client, *, regla_id: str, campos: dict[str, Any]) -> dict[str, Any]:
    return client.table("reglas_automatizacion").update(campos).eq("id", regla_id).execute().data[0]


def reglas_activas_para(
    client: Client, *, drogueria_id: str, entidad_objetivo: str, evento_disparador: str
) -> list[dict[str, Any]]:
    return (
        client.table("reglas_automatizacion")
        .select("*")
        .eq("drogueria_id", drogueria_id)
        .eq("entidad_objetivo", entidad_objetivo)
        .eq("evento_disparador", evento_disparador)
        .eq("activa", True)
        .order("prioridad", desc=True)
        .execute()
        .data
    )


def crear_accion_ejecutada(client: Client, fila: dict[str, Any]) -> dict[str, Any]:
    return client.table("acciones_ejecutadas").insert(fila).execute().data[0]


def actualizar_accion_ejecutada(client: Client, *, accion_id: str, campos: dict[str, Any]) -> dict[str, Any]:
    return client.table("acciones_ejecutadas").update(campos).eq("id", accion_id).execute().data[0]


def listar_acciones_pendientes(client: Client) -> list[dict[str, Any]]:
    ahora = datetime.now(timezone.utc).isoformat()
    return (
        client.table("acciones_ejecutadas")
        .select("*")
        .eq("estado", "pendiente")
        .or_(f"proximo_intento_at.is.null,proximo_intento_at.lte.{ahora}")
        .execute()
        .data
    )


def metricas(client: Client, *, drogueria_id: str) -> list[dict[str, Any]]:
    return (
        client.table("v_metricas_automatizacion")
        .select("*")
        .eq("drogueria_id", drogueria_id)
        .execute()
        .data
    )
