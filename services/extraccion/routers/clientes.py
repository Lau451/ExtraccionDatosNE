"""Router mínimo de clientes para el selector de upload — services/extraccion/routers/clientes.py

Lee `presupuestacion.clientes` (mismo Supabase que este backend) para que el usuario
pueda elegir el cliente real al subir un documento, en vez de depender del parseo de
nombre de archivo (§8 del spec de presupuestación: inyectar formato-por-cliente al
prompt de Gemini requiere un cliente_id real, no el texto libre que hoy deriva
obtener_cliente() del nombre del archivo).
"""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter
from pydantic import BaseModel

from services.extraccion.supabase_client import get_client, resolver_drogueria_id_unica

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/clientes", tags=["clientes"])


class ClienteActivo(BaseModel):
    """Payload mínimo para el selector de upload."""
    id: str
    nombre: str


@router.get("", response_model=list[ClienteActivo])
async def listar_activos() -> list[ClienteActivo]:
    """Clientes activos de la droguería, para el selector opcional de upload.
    Si Supabase no está disponible, devuelve lista vacía (el selector queda oculto,
    la carga sigue funcionando igual que hoy — ver index.html)."""
    client = get_client()
    if client is None:
        return []

    drogueria_id = await asyncio.to_thread(resolver_drogueria_id_unica, client)
    if drogueria_id is None:
        return []

    try:
        respuesta = await asyncio.to_thread(
            lambda: client.table("clientes")
            .select("id, nombre")
            .eq("drogueria_id", drogueria_id)
            .eq("activo", True)
            .order("nombre")
            .execute()
        )
        return [ClienteActivo(**r) for r in (respuesta.data or [])]
    except Exception as exc:
        logger.warning("listar_activos (clientes): error consultando Supabase — %s", exc)
        return []
