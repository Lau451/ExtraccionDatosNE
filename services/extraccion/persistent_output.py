"""
SHA256 + deduplicacion + persistencia del resultado final: services/extraccion/persistent_output.py

Funciones:
  calcular_sha256()           — hexdigest SHA256 del archivo fuente
  buscar_duplicado_con_lock() — llama a RPC reserve_extraction (SELECT FOR UPDATE)
  persistir_output_final()    — INSERT de metadata en extraction_results

Todas las funciones retornan None (sin propagar excepcion) si el cliente Supabase
no esta disponible. El CSV en disco es siempre la fuente de verdad: las filas
extraidas (`rows`) NO se persisten en Supabase, solo la metadata del documento.
`presupuestacion/extraccion/` lee las filas parseando `csv_disk_path` del disco.
"""

import asyncio
import hashlib
import logging
from pathlib import Path
from uuid import UUID

from services.extraccion.supabase_client import get_client, resolver_drogueria_id_unica

logger = logging.getLogger(__name__)

# Umbral de filas que dispara un WARNING (el INSERT igualmente se ejecuta)
_WARN_ROW_COUNT = 50_000

# Tipos de documento con pipeline de extraccion real hoy. "orden_compra" todavia
# no tiene extractor propio (ver presupuestacion/extraccion/) y "cotizacion" es
# manejado como "licitacion" por el robot generico.
_DOC_TYPES_SOPORTADOS = {"comparativa", "licitacion"}


def calcular_sha256(path: Path) -> str:
    """
    Calcula el SHA256 hexadecimal del contenido binario de un archivo.

    Usa lectura en bloques para soportar archivos grandes sin cargar todo
    en memoria de una vez.

    Args:
        path: Ruta al archivo del cual calcular el hash.

    Returns:
        String hexadecimal del SHA256 (64 caracteres).
    """
    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        for bloque in iter(lambda: f.read(65_536), b""):
            hasher.update(bloque)
    digest = hasher.hexdigest()
    logger.debug("SHA256 calculado — path=%s digest=%s", path.name, digest[:12] + "...")
    return digest


async def buscar_duplicado_con_lock(*, source_sha256: str) -> UUID | None:
    """
    Busca un extraction_result completado con el SHA256 dado, usando
    la RPC reserve_extraction que hace SELECT FOR UPDATE.

    Esto garantiza que dos requests simultaneos del mismo archivo no
    generen dos extracciones paralelas (el segundo espera al primero).

    Args:
        source_sha256: Hexdigest SHA256 del archivo fuente.

    Returns:
        UUID del extraction_result existente si status='completed',
        None si no existe o si el registro existente es partial/failed
        (en ese caso se permite el reprocesamiento).
        None tambien si la persistencia no esta disponible.
    """
    client = get_client()
    if client is None:
        return None

    try:
        respuesta = await asyncio.to_thread(
            lambda: client.rpc("reserve_extraction", {"p_sha": source_sha256}).execute()
        )
        # La RPC retorna NULL (None en Python) o un UUID string
        resultado = respuesta.data
        if resultado is None:
            logger.debug(
                "buscar_duplicado_con_lock: sin duplicado para sha256=%s",
                source_sha256[:12] + "...",
            )
            return None

        extraction_id = UUID(resultado)
        logger.info(
            "Duplicado detectado — extraction_id=%s sha256=%s",
            extraction_id,
            source_sha256[:12] + "...",
        )
        return extraction_id
    except Exception as exc:
        logger.warning(
            "buscar_duplicado_con_lock: error consultando RPC — %s. "
            "Se procedera sin verificacion de duplicados.",
            exc,
        )
        return None


async def persistir_output_final(
    *,
    session_id: UUID | None,
    doc_type: str,
    rows: list[dict],
    csv_path: Path,
    client_id: str,
    source_filename: str,
    source_sha256: str,
    licitacion_id: str | None = None,
) -> UUID | None:
    """
    Persiste la METADATA de una extraccion en extraction_results (schema nuevo de
    presupuestacion/). Las filas extraidas (`rows`) NO se insertan en Supabase —
    quedan en el CSV en disco (`csv_path`), que es la fuente de verdad;
    presupuestacion/extraccion/ las lee parseando `csv_disk_path`.

    Ejecuta en este orden:
      1. Valida que rows no este vacio (igual se descartan del INSERT, pero un
         documento sin filas no es una extraccion valida).
      2. Emite WARNING si rows supera 50k filas.
      3. Resuelve drogueria_id (unica droguoria que sirve esta app hoy).
      4. INSERT en extraction_results.
      5. Retorna el UUID generado.

    Esta funcion se ejecuta como BackgroundTask (post-respuesta), por lo que
    los errores se logean pero NUNCA se propagan al caller.

    NOTA: `session_id`, `client_id` y `licitacion_id` se siguen aceptando para no
    romper a los callers (background_tasks.py/main.py), pero YA NO se persisten:
    no existen como columnas usables en el extraction_results del schema nuevo
    (session_id necesitaria una fila real en processing_sessions del schema nuevo,
    que persistent_chunking.py todavia no crea correctamente — mismo tipo de gap,
    fuera del alcance de este cambio puntual).

    Args:
        session_id:      Aceptado por compatibilidad, no se persiste (ver NOTA).
        doc_type:        "comparativa" | "licitacion".
        rows:            Lista de dicts con los datos extraidos (leidos del CSV).
        csv_path:        Path al CSV generado en disco (source of truth).
        client_id:       Aceptado por compatibilidad, no se persiste (ver NOTA).
        source_filename: Nombre del archivo original subido.
        source_sha256:   SHA256 del archivo original (para deduplicacion futura).

    Returns:
        UUID del extraction_result insertado, o None si fallo.
    """
    client = get_client()
    if client is None:
        return None

    # --- Validacion de rows ---
    if not rows:
        logger.error(
            "persistir_output_final: rows esta vacio — INSERT abortado. "
            "session_id=%s source_filename=%s",
            session_id,
            source_filename,
        )
        return None

    if len(rows) > _WARN_ROW_COUNT:
        logger.warning(
            "persistir_output_final: rows contiene %d filas (> %d) — "
            "el INSERT se ejecuta pero puede ser lento. session_id=%s",
            len(rows),
            _WARN_ROW_COUNT,
            session_id,
        )

    # --- Validar doc_type soportado ---
    if doc_type not in _DOC_TYPES_SOPORTADOS:
        logger.error(
            "persistir_output_final: doc_type='%s' no soportado. Valores validos: %s",
            doc_type,
            sorted(_DOC_TYPES_SOPORTADOS),
        )
        return None

    drogueria_id = await asyncio.to_thread(resolver_drogueria_id_unica, client)
    if drogueria_id is None:
        logger.error(
            "persistir_output_final: no se pudo resolver drogueria_id — INSERT abortado. "
            "source_filename=%s",
            source_filename,
        )
        return None

    # --- INSERT en extraction_results (solo metadata, ver docstring) ---
    payload_base = {
        "drogueria_id": drogueria_id,
        "document_type": doc_type,
        "source_filename": source_filename,
        "source_sha256": source_sha256,
        "row_count": len(rows),
        "csv_disk_path": str(csv_path),
        "status": "completed",
    }

    try:
        respuesta_base = await asyncio.to_thread(
            lambda: (
                client.table("extraction_results")
                .insert(payload_base)
                .execute()
            )
        )
        if not respuesta_base.data:
            logger.error(
                "persistir_output_final: INSERT en extraction_results sin datos de retorno. "
                "session_id=%s",
                session_id,
            )
            return None

        extraction_id = UUID(respuesta_base.data[0]["id"])
        logger.info(
            "extraction_results insertado — extraction_id=%s row_count=%d doc_type=%s",
            extraction_id,
            len(rows),
            doc_type,
        )
        return extraction_id
    except Exception as exc:
        logger.error(
            "persistir_output_final: error en INSERT extraction_results — %s. "
            "session_id=%s sha256=%s",
            exc,
            session_id,
            source_sha256[:12] + "...",
        )
        return None
