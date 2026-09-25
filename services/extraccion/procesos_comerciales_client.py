"""Cliente de solo lectura para `procesos_comerciales` — services/extraccion/procesos_comerciales_client.py

`procesos_comerciales` es una tabla del schema de `presupuestacion/`, pero vive en el mismo
proyecto de Supabase que este backend, así que se consulta directo en vez de pegarle por HTTP a
`services/presupuestacion` (mismo criterio que `routers/clientes.py`).

Reemplaza a `routers.licitaciones.validar_licitacion_id()` para el flujo de carga de documentos,
porque esa tabla (`licitaciones`) ya no existe. `routers/licitaciones.py` y el HTML legacy que
lo consumía se retiraron en T2 (ver `odd/tasks/extraccion-multi-tenant.md`).

Este cliente usa `get_client()` (service_role, bypasea RLS) — por eso el filtro
`.eq("drogueria_id", drogueria_id)` es OBLIGATORIO en cada query, no una opción de diseño. Sin él,
cualquier consulta acá se ejecuta contra procesos_comerciales de TODAS las droguerías de la base.
"""
from __future__ import annotations

import asyncio
import logging
from uuid import UUID

from fastapi import HTTPException, status

from services.extraccion.supabase_client import get_client

logger = logging.getLogger(__name__)


async def validar_proceso_comercial_id(
    proceso_comercial_id: str | None, *, drogueria_id: str
) -> str | None:
    """Valida que proceso_comercial_id sea un UUID existente en la BD, para la droguería del
    usuario autenticado.

    Retorna el id normalizado o None si viene vacío.
    Lanza HTTPException 422 si el id no es UUID válido, no existe, o pertenece a otra droguería
    (SC-25: fail-fast antes de cualquier I/O o invocación a Gemini). No se distingue "no existe"
    de "es de otra droguería" en el mensaje de error, para no filtrar existencia entre tenants.

    Args:
        proceso_comercial_id: id a validar (o vacío).
        drogueria_id: droguería del usuario autenticado (obligatorio, sin fallback --
            viene de services.extraccion.auth.get_drogueria_id_actual).
    """
    if not proceso_comercial_id or not proceso_comercial_id.strip():
        return None

    try:
        UUID(proceso_comercial_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"licitacion_id no es un UUID válido: {proceso_comercial_id}",
        )

    client = get_client()
    if client is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Supabase no disponible",
        )

    res = await asyncio.to_thread(
        lambda: client.table("procesos_comerciales")
        .select("id")
        .eq("id", proceso_comercial_id)
        .eq("drogueria_id", drogueria_id)
        .limit(1)
        .execute()
    )
    if not res.data:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Proceso comercial {proceso_comercial_id} no existe",
        )
    return proceso_comercial_id


async def listar_nombres_procesos_comerciales(
    ids: list[str], *, drogueria_id: str
) -> dict[str, str]:
    """Resuelve {id: nombre} para una lista de proceso_comercial_id, escopeado a la droguería
    del usuario autenticado.

    Los ids que no matchean (borrados, o de otra droguería — no debería pasar si
    validar_proceso_comercial_id() se usó al crear el vínculo, pero esta función no confía en
    eso) se omiten del resultado en vez de fallar. El caller (GET /api/documentos) trata un id
    ausente en el dict igual que "sin vincular" — nunca debe mostrar el nombre real de un proceso
    de otra droguería.
    """
    if not ids:
        return {}

    client = get_client()
    if client is None:
        return {}

    try:
        res = await asyncio.to_thread(
            lambda: client.table("procesos_comerciales")
            .select("id, nombre")
            .in_("id", ids)
            .eq("drogueria_id", drogueria_id)
            .execute()
        )
        return {r["id"]: r["nombre"] for r in (res.data or [])}
    except Exception as exc:
        logger.warning(
            "listar_nombres_procesos_comerciales: error consultando Supabase — %s", exc
        )
        return {}
