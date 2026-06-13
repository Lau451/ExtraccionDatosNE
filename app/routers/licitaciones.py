"""Router de Gestión de Licitaciones — app/routers/licitaciones.py"""
from __future__ import annotations

import asyncio
import logging
from datetime import date
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status

from app.schemas.licitaciones import (
    ArchivoVinculado,
    LicitacionActiva,
    LicitacionCalendario,
    LicitacionCreate,
    LicitacionDetalle,
    LicitacionListResponse,
    LicitacionOut,
    LicitacionUpdate,
    _normalize_count,
)
from app.supabase_client import get_client

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/licitaciones", tags=["licitaciones"])

_SELECT_FIELDS = (
    "id, nombre, tipo, apertura, vencimiento, tipo_gestion, "
    "modalidad, estado, monto_estimado, notas, comparativa_estado, "
    "created_at, updated_at, archivos_count:extraction_results(count)"
)


def _require_client():
    client = get_client()
    if client is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Supabase no disponible",
        )
    return client


async def validar_licitacion_id(licitacion_id: Optional[str]) -> Optional[str]:
    """Valida que licitacion_id sea un UUID existente en la BD.

    Retorna el id normalizado o None si viene vacío.
    Lanza HTTPException 422 si el id no es UUID válido o no existe en DB (SC-25).
    """
    if not licitacion_id or not licitacion_id.strip():
        return None

    try:
        UUID(licitacion_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"licitacion_id no es un UUID válido: {licitacion_id}",
        )

    client = _require_client()
    res = await asyncio.to_thread(
        lambda: client.table("licitaciones")
        .select("id")
        .eq("id", licitacion_id)
        .limit(1)
        .execute()
    )
    if not res.data:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Licitación {licitacion_id} no existe",
        )
    return licitacion_id


# ---------------------------------------------------------------------------
# Endpoints — ORDEN IMPORTA: /activas y /calendario deben ir antes de /{lic_id}
# ---------------------------------------------------------------------------

@router.get("", response_model=LicitacionListResponse)
async def listar(
    estado: Optional[str] = Query(None),
    tipo: Optional[str] = Query(None),
    q: Optional[str] = Query(None, max_length=120),
    licitacion_id: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    client = _require_client()
    offset = (page - 1) * page_size

    def _run():
        qb = (
            client.table("licitaciones")
            .select(_SELECT_FIELDS, count="exact")
            .order("created_at", desc=True)
            .range(offset, offset + page_size - 1)
        )
        if estado:
            qb = qb.eq("estado", estado)
        if tipo:
            qb = qb.eq("tipo", tipo)
        if q:
            qb = qb.ilike("nombre", f"%{q}%")
        return qb.execute()

    res = await asyncio.to_thread(_run)
    items = [LicitacionOut(**_normalize_count(r)) for r in (res.data or [])]
    return LicitacionListResponse(
        items=items,
        total=res.count or 0,
        page=page,
        page_size=page_size,
    )


@router.get("/activas", response_model=list[LicitacionActiva])
async def listar_activas():
    """Payload mínimo para el selector de upload. Solo abierta/en_evaluacion."""
    client = _require_client()
    res = await asyncio.to_thread(
        lambda: client.table("licitaciones")
        .select("id, nombre, tipo")
        .in_("estado", ["abierta", "en_evaluacion"])
        .order("nombre", desc=False)
        .execute()
    )
    return [LicitacionActiva(**r) for r in (res.data or [])]


@router.get("/calendario", response_model=list[LicitacionCalendario])
async def calendario(
    desde: Optional[date] = Query(None),
    hasta: Optional[date] = Query(None),
):
    """Licitaciones con estado derivado de comparativa para el calendario."""
    client = _require_client()

    def _run():
        lics_qb = (
            client.table("licitaciones")
            .select("id, nombre, tipo, apertura, vencimiento, estado, comparativa_estado")
            .order("apertura", desc=False)
        )
        if desde and hasta:
            lics_qb = lics_qb.or_(
                f"apertura.is.null,and(apertura.gte.{desde},apertura.lte.{hasta})"
            )
        lics_res = lics_qb.execute()
        comps_res = (
            client.table("extraction_results")
            .select("licitacion_id")
            .eq("document_type", "comparativa")
            .not_.is_("licitacion_id", "null")
            .execute()
        )
        return lics_res, comps_res

    lics_res, comps_res = await asyncio.to_thread(_run)
    con_comparativa = {
        str(r["licitacion_id"])
        for r in (comps_res.data or [])
        if r.get("licitacion_id")
    }

    items = []
    for row in (lics_res.data or []):
        if str(row["id"]) in con_comparativa:
            derivado = "cargada"
        elif row.get("comparativa_estado") == "pedida":
            derivado = "pedida"
        else:
            derivado = "sin_comparativa"
        items.append(LicitacionCalendario(
            id=row["id"],
            nombre=row["nombre"],
            tipo=row["tipo"],
            apertura=row.get("apertura"),
            vencimiento=row.get("vencimiento"),
            estado=row["estado"],
            comparativa_estado=derivado,
        ))

    items.sort(key=lambda x: (x.apertura or x.vencimiento or date.max))
    return items


@router.get("/{lic_id}", response_model=LicitacionDetalle)
async def obtener(lic_id: UUID):
    client = _require_client()

    def _run():
        lic_res = (
            client.table("licitaciones")
            .select(_SELECT_FIELDS)
            .eq("id", str(lic_id))
            .limit(1)
            .execute()
        )
        archivos_res = (
            client.table("extraction_results")
            .select(
                "id, source_filename, document_type, client_id, "
                "row_count, status, created_at"
            )
            .eq("licitacion_id", str(lic_id))
            .order("created_at", desc=True)
            .execute()
        )
        return lic_res, archivos_res

    lic_res, archivos_res = await asyncio.to_thread(_run)

    if not lic_res.data:
        raise HTTPException(status_code=404, detail="Licitación no encontrada")

    row = _normalize_count(lic_res.data[0])
    archivos = [ArchivoVinculado(**a) for a in (archivos_res.data or [])]
    return LicitacionDetalle(**row, archivos=archivos)


@router.post("", response_model=LicitacionOut, status_code=status.HTTP_201_CREATED)
async def crear(payload: LicitacionCreate):
    client = _require_client()
    body = payload.model_dump(mode="json")

    res = await asyncio.to_thread(
        lambda: client.table("licitaciones").insert(body).execute()
    )
    if not res.data:
        raise HTTPException(status_code=500, detail="Insert sin filas devueltas")

    row = {**res.data[0], "archivos_count": 0}
    return LicitacionOut(**row)


@router.patch("/{lic_id}", response_model=LicitacionOut)
async def actualizar(lic_id: UUID, payload: LicitacionUpdate):
    client = _require_client()
    update_body = payload.to_db_payload()
    if not update_body:
        raise HTTPException(status_code=400, detail="Body vacío: nada para actualizar")

    def _run():
        upd = (
            client.table("licitaciones")
            .update(update_body)
            .eq("id", str(lic_id))
            .execute()
        )
        if not upd.data:
            return None
        return (
            client.table("licitaciones")
            .select(_SELECT_FIELDS)
            .eq("id", str(lic_id))
            .limit(1)
            .execute()
        )

    res = await asyncio.to_thread(_run)
    if res is None or not res.data:
        raise HTTPException(status_code=404, detail="Licitación no encontrada")

    return LicitacionOut(**_normalize_count(res.data[0]))


@router.delete("/{lic_id}", status_code=status.HTTP_204_NO_CONTENT)
async def eliminar(lic_id: UUID):
    client = _require_client()

    def _run():
        count_res = (
            client.table("extraction_results")
            .select("id", count="exact")
            .eq("licitacion_id", str(lic_id))
            .limit(1)
            .execute()
        )
        if (count_res.count or 0) > 0:
            return "has_files", count_res.count

        del_res = (
            client.table("licitaciones")
            .delete()
            .eq("id", str(lic_id))
            .execute()
        )
        if not del_res.data:
            return "not_found", None
        return "ok", None

    result, count = await asyncio.to_thread(_run)

    if result == "has_files":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"No se puede eliminar: la licitación tiene {count} archivo(s) vinculado(s). "
                "Desvincule los archivos antes de eliminar, o cambie el estado a 'cerrada'."
            ),
        )
    if result == "not_found":
        raise HTTPException(status_code=404, detail="Licitación no encontrada")

    return None
