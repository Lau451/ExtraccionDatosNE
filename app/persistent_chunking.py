"""
CRUD de sesiones y chunks en Supabase: app/persistent_chunking.py

Maneja el ciclo de vida de una sesión de procesamiento chunked:
  crear_sesion()           — abre un registro processing_sessions
  guardar_chunk()          — upsert en chunk_results (sync, dentro de to_thread)
  cargar_chunks_existentes() — recupera chunks ya guardados (para reanudación)
  cerrar_sesion()          — actualiza status + completed_at

Todas las funciones son no-op (retornan None/False/{}) si el cliente Supabase
no está disponible — el flujo principal NUNCA se interrumpe por fallo de BD.
"""

import asyncio
import logging
from datetime import datetime, timezone
from uuid import UUID

from app.supabase_client import get_client

logger = logging.getLogger(__name__)


async def crear_sesion(
    *,
    doc_name: str,
    client_id: str,
    total_chunks: int,
    doc_type: str,
) -> UUID | None:
    """
    Crea un registro en processing_sessions con status='running'.

    Args:
        doc_name:     Nombre del documento original (ej: "comparativa_mayo.xlsx").
        client_id:    Identificador del cliente/origen del documento.
        total_chunks: Número estimado de chunks (puede ser 0 si aún no se sabe).
        doc_type:     Tipo de documento: "comparativa" | "licitacion" | "orden_compra".

    Returns:
        UUID de la sesión creada, o None si la persistencia no está disponible.
    """
    client = get_client()
    if client is None:
        return None

    payload = {
        "doc_name": doc_name,
        "client_id": client_id,
        "doc_type": doc_type,
        "total_chunks": total_chunks,
        "status": "running",
    }

    try:
        respuesta = await asyncio.to_thread(
            lambda: client.table("processing_sessions").insert(payload).execute()
        )
        if respuesta.data:
            session_id = UUID(respuesta.data[0]["id"])
            logger.info(
                "Sesion creada — session_id=%s doc_name=%s doc_type=%s",
                session_id,
                doc_name,
                doc_type,
            )
            return session_id
        logger.warning(
            "crear_sesion: INSERT sin datos de retorno para doc_name=%s", doc_name
        )
        return None
    except Exception as exc:
        logger.warning(
            "crear_sesion: error al crear sesion para doc_name=%s — %s", doc_name, exc
        )
        return None


def guardar_chunk(
    *,
    session_id: UUID,
    chunk_num: int,
    resultado_json: dict,
) -> bool:
    """
    Upsert de un chunk en chunk_results.

    Función SÍNCRONA — diseñada para ejecutarse dentro de asyncio.to_thread()
    junto con el robot. Usa ON CONFLICT (session_id, chunk_number) DO UPDATE
    para garantizar idempotencia si el mismo chunk se re-intenta.

    Args:
        session_id:     UUID de la sesión de procesamiento.
        chunk_num:      Número de chunk (base 0 o base 1, consistente con el robot).
        resultado_json: Dict con los datos extraídos por Gemini para este chunk.

    Returns:
        True si el guardado fue exitoso, False si falló (sin propagar excepción).
    """
    client = get_client()
    if client is None:
        return False

    payload = {
        "session_id": str(session_id),
        "chunk_number": chunk_num,
        "resultado": resultado_json,
        "status": "completed",
    }

    try:
        # upsert con ON CONFLICT(session_id, chunk_number) — idempotente
        client.table("chunk_results").upsert(
            payload,
            on_conflict="session_id,chunk_number",
        ).execute()
        logger.debug(
            "Chunk guardado — session_id=%s chunk_num=%d", session_id, chunk_num
        )
        return True
    except Exception as exc:
        logger.warning(
            "guardar_chunk: error al guardar chunk %d para session_id=%s — %s",
            chunk_num,
            session_id,
            exc,
        )
        return False


def cargar_chunks_existentes(*, session_id: UUID) -> dict[int, dict]:
    """
    Recupera los chunks ya guardados para una sesión (para reanudación).

    Función SÍNCRONA — puede usarse dentro de to_thread() para decidir qué
    chunks ya están disponibles antes de lanzar llamadas Gemini.

    Args:
        session_id: UUID de la sesión de procesamiento.

    Returns:
        Dict {chunk_number: resultado_json} con los chunks completados.
        Dict vacío si no hay chunks o si la persistencia no está disponible.
    """
    client = get_client()
    if client is None:
        return {}

    try:
        respuesta = (
            client.table("chunk_results")
            .select("chunk_number, resultado")
            .eq("session_id", str(session_id))
            .eq("status", "completed")
            .execute()
        )
        chunks = {
            row["chunk_number"]: row["resultado"]
            for row in (respuesta.data or [])
        }
        logger.debug(
            "cargar_chunks_existentes — session_id=%s chunks_encontrados=%d",
            session_id,
            len(chunks),
        )
        return chunks
    except Exception as exc:
        logger.warning(
            "cargar_chunks_existentes: error al cargar chunks para session_id=%s — %s",
            session_id,
            exc,
        )
        return {}


async def cerrar_sesion(
    *,
    session_id: UUID,
    status: str,
    error_msg: str | None = None,
) -> None:
    """
    Actualiza el status de una sesión y registra la fecha de cierre.

    Args:
        session_id: UUID de la sesión a cerrar.
        status:     Estado final: "completed" | "partial" | "failed".
        error_msg:  Mensaje de error opcional (solo si status != "completed").
    """
    client = get_client()
    if client is None:
        return

    payload: dict = {
        "status": status,
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }
    if error_msg is not None:
        payload["error_msg"] = error_msg

    try:
        await asyncio.to_thread(
            lambda: (
                client.table("processing_sessions")
                .update(payload)
                .eq("id", str(session_id))
                .execute()
            )
        )
        logger.info(
            "Sesion cerrada — session_id=%s status=%s", session_id, status
        )
    except Exception as exc:
        logger.warning(
            "cerrar_sesion: error al cerrar session_id=%s — %s", session_id, exc
        )
