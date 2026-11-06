# Repository del registro de archivos de Progress (progress_archivos, migración 0043).
# Todas las funciones esperan el SERVICE client: la tabla no tiene políticas de
# escritura para authenticated, así que RLS no protege nada: toda lectura y escritura
# filtra explícitamente por `drogueria_id` (también las que van por id).
from datetime import datetime
from typing import Any

from supabase import Client

_TABLA = "progress_archivos"


def buscar_por_contenido(
    client: Client, *, drogueria_id: str, sentido: str, tipo: str, sha256: str
) -> dict[str, Any] | None:
    """Lookup por la clave de uq_parch_contenido."""
    resultado = (
        client.table(_TABLA)
        .select("*")
        .eq("drogueria_id", drogueria_id)
        .eq("sentido", sentido)
        .eq("tipo", tipo)
        .eq("sha256", sha256)
        .limit(1)
        .execute()
    )
    return resultado.data[0] if resultado.data else None


def buscar_por_id(
    client: Client, *, drogueria_id: str, registro_id: str
) -> dict[str, Any] | None:
    resultado = (
        client.table(_TABLA)
        .select("*")
        .eq("id", registro_id)
        .eq("drogueria_id", drogueria_id)
        .limit(1)
        .execute()
    )
    return resultado.data[0] if resultado.data else None


def insertar(client: Client, fila: dict[str, Any]) -> dict[str, Any]:
    return client.table(_TABLA).insert(fila).execute().data[0]


def actualizar(
    client: Client,
    *,
    drogueria_id: str,
    registro_id: str,
    campos: dict[str, Any],
    estado_esperado: str | None = None,
    intentos_esperados: int | None = None,
) -> dict[str, Any] | None:
    """UPDATE por id y droguería. Con `estado_esperado` o `intentos_esperados` es un
    CAS: si el registro ya no está en ese estado o con esos intentos, no actualiza
    nada y devuelve None."""
    query = (
        client.table(_TABLA).update(campos).eq("id", registro_id).eq("drogueria_id", drogueria_id)
    )
    if estado_esperado is not None:
        query = query.eq("estado", estado_esperado)
    if intentos_esperados is not None:
        query = query.eq("intentos", intentos_esperados)
    resultado = query.execute()
    return resultado.data[0] if resultado.data else None


def reclamar(
    client: Client,
    *,
    drogueria_id: str,
    registro_id: str,
    estado_esperado: str,
    updated_at_esperado: datetime,
) -> dict[str, Any] | None:
    """CAS para reprocesar: vuelve el registro a 'recibido' solo si sigue en
    `estado_esperado` con el mismo `updated_at` (el trigger lo renueva). Si otro
    proceso ya lo reclamó, no actualiza nada y devuelve None."""
    resultado = (
        client.table(_TABLA)
        .update({"estado": "recibido"})
        .eq("id", registro_id)
        .eq("drogueria_id", drogueria_id)
        .eq("estado", estado_esperado)
        .eq("updated_at", updated_at_esperado.isoformat())
        .execute()
    )
    return resultado.data[0] if resultado.data else None


def listar(
    client: Client,
    *,
    drogueria_id: str,
    sentido: str | None,
    estado: str | None,
    limit: int,
    offset: int,
) -> list[dict[str, Any]]:
    query = client.table(_TABLA).select("*").eq("drogueria_id", drogueria_id)
    if sentido is not None:
        query = query.eq("sentido", sentido)
    if estado is not None:
        query = query.eq("estado", estado)
    return (
        query.order("created_at", desc=True)
        .order("id")
        .range(offset, offset + limit - 1)
        .execute()
        .data
    )
