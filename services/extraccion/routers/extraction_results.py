"""Router de Extraction Results — services/extraccion/routers/extraction_results.py"""
from __future__ import annotations

import asyncio
import logging
from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from services.extraccion.schemas.licitaciones import ExtractionResultOut, ExtractionResultUpdate
from services.extraccion.supabase_client import get_client

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/extraction-results", tags=["extraction-results"])

_SELECT_FIELDS = (
    "id, source_filename, document_type, client_id, "
    "row_count, status, created_at, licitacion_id"
)


def _require_client():
    client = get_client()
    if client is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Supabase no disponible",
        )
    return client


@router.patch("/{result_id}", response_model=ExtractionResultOut)
async def actualizar(result_id: UUID, payload: ExtractionResultUpdate):
    client = _require_client()
    update_body = payload.to_db_payload()
    if not update_body:
        raise HTTPException(status_code=400, detail="Body vacío: nada para actualizar")

    def _run():
        upd = (
            client.table("extraction_results")
            .update(update_body)
            .eq("id", str(result_id))
            .execute()
        )
        if not upd.data:
            return None
        return (
            client.table("extraction_results")
            .select(_SELECT_FIELDS)
            .eq("id", str(result_id))
            .limit(1)
            .execute()
        )

    res = await asyncio.to_thread(_run)
    if res is None or not res.data:
        raise HTTPException(status_code=404, detail="Extraction result no encontrado")

    return ExtractionResultOut(**res.data[0])
