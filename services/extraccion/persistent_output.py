"""
SHA256 + deduplicacion + persistencia del resultado final: services/extraccion/persistent_output.py

Funciones:
  calcular_sha256()             — hexdigest SHA256 del archivo fuente
  buscar_duplicado_con_lock()   — llama a RPC reserve_extraction (SELECT FOR UPDATE)
  crear_extraction_processing() — INSERT en extraction_results con status='processing',
                                   ANTES de invocar al robot (carga-asincrona, T1)
  persistir_output_final()      — UPDATE de metadata en extraction_results a
                                   status='completed' (por id, no INSERT desde 0028)
  marcar_extraccion_fallida()   — UPDATE a status='failed' + error_msg
  marcar_processing_interrumpidos() — sweep de arranque: 'processing' huérfanos -> 'failed'

Todas las funciones retornan None/0 (sin propagar excepcion) si el cliente Supabase
no esta disponible. El CSV en disco es siempre la fuente de verdad: las filas
extraidas (`rows`) NO se persisten en Supabase, solo la metadata del documento.
`presupuestacion/extraccion/` lee las filas parseando `csv_disk_path` del disco.
"""

import asyncio
import hashlib
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

from services.extraccion.supabase_client import get_client

logger = logging.getLogger(__name__)

# Umbral de filas que dispara un WARNING (el INSERT igualmente se ejecuta)
_WARN_ROW_COUNT = 50_000

# Tipos de documento con pipeline de extraccion real hoy. "cotizacion" es
# manejado como "licitacion" por el robot generico (no tiene extractor propio).
_DOC_TYPES_SOPORTADOS = {"comparativa", "licitacion", "orden_compra"}


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


async def buscar_duplicado_con_lock(*, source_sha256: str, drogueria_id: str) -> UUID | None:
    """
    Busca un extraction_result completado con el SHA256 dado PARA LA DROGUERIA DEL
    CALLER, usando la RPC reserve_extraction que hace SELECT FOR UPDATE.

    Esto garantiza que dos requests simultaneos del mismo archivo no
    generen dos extracciones paralelas (el segundo espera al primero), y que el
    409 nunca devuelva un extraction_id de OTRA droguería (dedup por
    (drogueria_id, source_sha256) -- migración 0027).

    Args:
        source_sha256: Hexdigest SHA256 del archivo fuente.
        drogueria_id:  droguería del usuario autenticado (obligatorio).

    Returns:
        UUID del extraction_result existente si status='completed',
        None si no existe o si el registro existente es failed (se borra en la RPC)
        (en ese caso se permite el reprocesamiento).
        None tambien si la persistencia no esta disponible.
    """
    client = get_client()
    if client is None:
        return None

    try:
        respuesta = await asyncio.to_thread(
            lambda: client.rpc(
                "reserve_extraction",
                {"p_sha": source_sha256, "p_drogueria_id": drogueria_id},
            ).execute()
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
        logger.error(
            "buscar_duplicado_con_lock: error consultando RPC reserve_extraction — %s. "
            "DEDUPLICACION DESHABILITADA para este request (sha256=%s, drogueria_id=%s): "
            "la carga continua sin verificar duplicados. Posible causa: falta aplicar "
            "la migracion 0027 (reserve_extraction con firma (p_sha, p_drogueria_id)).",
            exc,
            source_sha256[:12] + "..." if source_sha256 else "N/A",
            drogueria_id,
        )
        return None


async def crear_extraction_processing(
    *,
    drogueria_id: str,
    document_type: str,
    source_filename: str,
    source_sha256: str,
    grupo_id: str | None = None,
    proceso_comercial_id: str | None = None,
) -> UUID | None:
    """
    Crea la fila de extraction_results ANTES de invocar al robot, con
    status='processing' y row_count=0 (carga-asincrona, T1). `POST /procesar`
    responde 202 con este id apenas se crea; el robot corre en background y la
    actualiza a 'completed' (`persistir_output_final`) o 'failed'
    (`marcar_extraccion_fallida`) al terminar.

    Una fila en 'processing' cuenta como "tomada" para la RPC reserve_extraction
    (migración 0028) -- si dos requests suben el mismo archivo mientras el primero
    todavía está procesando, el segundo recibe 409 con este mismo id en vez de
    arrancar un segundo robot en paralelo para el mismo documento.

    Args:
        drogueria_id:          droguería del usuario autenticado. Obligatorio.
        document_type:         "comparativa" | "licitacion" | "orden_compra".
        source_filename:       Nombre del archivo original subido.
        source_sha256:         SHA256 del archivo original.
        grupo_id:              UUID v4 ya validado (D13), solo si viene.
        proceso_comercial_id:  proceso_comercial_id ya validado, solo si viene.

    Returns:
        UUID de la fila creada, o None si la persistencia no está disponible o
        el INSERT falla (se logea, nunca se propaga).
    """
    client = get_client()
    if client is None:
        return None

    payload: dict = {
        "drogueria_id": drogueria_id,
        "document_type": document_type,
        "source_filename": source_filename,
        "source_sha256": source_sha256,
        "row_count": 0,
        "status": "processing",
    }
    if grupo_id:
        payload["grupo_id"] = grupo_id
    if proceso_comercial_id:
        payload["proceso_comercial_id"] = proceso_comercial_id

    try:
        respuesta = await asyncio.to_thread(
            lambda: client.table("extraction_results").insert(payload).execute()
        )
        if not respuesta.data:
            logger.error(
                "crear_extraction_processing: INSERT sin datos de retorno. "
                "source_filename=%s",
                source_filename,
            )
            return None

        extraction_id = UUID(respuesta.data[0]["id"])
        logger.info(
            "extraction_results creado en 'processing' — extraction_id=%s doc_type=%s",
            extraction_id,
            document_type,
        )
        return extraction_id
    except Exception as exc:
        logger.error(
            "crear_extraction_processing: error en INSERT — %s. "
            "source_filename=%s sha256=%s",
            exc,
            source_filename,
            source_sha256[:12] + "..." if source_sha256 else "N/A",
        )
        return None


async def persistir_output_final(
    *,
    extraction_id: UUID | None,
    session_id: UUID | None,
    doc_type: str,
    rows: list[dict],
    csv_path: Path,
    client_id: str,
    source_filename: str,
    source_sha256: str,
    drogueria_id: str,
    licitacion_id: str | None = None,
    grupo_id: str | None = None,
) -> UUID | None:
    """
    Actualiza a status='completed' la fila de extraction_results que
    `crear_extraction_processing` ya insertó en 'processing' antes de correr el
    robot (carga-asincrona, T1 -- antes de la migración 0028 esta función hacía
    el INSERT completo; ahora la fila ya existe y esto es un UPDATE por id).
    Las filas extraidas (`rows`) NO se insertan en Supabase — quedan en el CSV
    en disco (`csv_path`), que es la fuente de verdad; presupuestacion/extraccion/
    las lee parseando `csv_disk_path`.

    Ejecuta en este orden:
      1. Valida que rows no este vacio (un documento sin filas no es una
         extraccion valida -- no tiene sentido marcarla 'completed').
      2. Emite WARNING si rows supera 50k filas (igual se seguir con el UPDATE).
      3. Valida doc_type soportado.
      4. UPDATE en extraction_results, filtrado por id Y drogueria_id (nunca
         actualiza una fila de otra droguería aunque el id coincidiera).
      5. Retorna el mismo extraction_id recibido, como señal de éxito.

    Esta funcion corre dentro del job de background de `/procesar`
    (`services/extraccion/main.py::_procesar_documento_background`, vía
    `_retry_persist`), por lo que los errores se logean pero NUNCA se propagan
    al caller -- `_retry_persist` decide cuándo reintentar o rendirse.

    NOTA: `session_id` y `client_id` se siguen aceptando para no romper a los callers
    (background_tasks.py/main.py), pero NO se persisten: no existen como columnas usables en el
    extraction_results del schema nuevo (session_id necesitaria una fila real en
    processing_sessions del schema nuevo, que persistent_chunking.py todavia no crea
    correctamente — mismo tipo de gap, fuera del alcance de este cambio puntual).

    `licitacion_id`/`grupo_id` ya quedaron persistidos por `crear_extraction_processing`
    (si vinieron validados) -- se re-escriben acá también por si acaso, sin costo extra.

    Args:
        extraction_id:   UUID de la fila ya creada en 'processing' por
                          `crear_extraction_processing`. None si la persistencia
                          no estaba disponible al crearla (en ese caso `client`
                          también es None acá, y se retorna temprano igual).
        session_id:      Aceptado por compatibilidad, no se persiste (ver NOTA).
        doc_type:        "comparativa" | "licitacion" | "orden_compra".
        rows:            Lista de dicts con los datos extraidos (leidos del CSV).
        csv_path:        Path al CSV generado en disco (source of truth).
        client_id:       Aceptado por compatibilidad, no se persiste (ver NOTA).
        source_filename: Nombre del archivo original subido (solo para logs).
        source_sha256:   SHA256 del archivo original (solo para logs).
        drogueria_id:    droguería del usuario autenticado que subió el documento.
                          Obligatorio, sin fallback -- viene de
                          services.extraccion.auth.get_drogueria_id_actual.
        licitacion_id:   proceso_comercial_id ya validado (o None). Se persiste tal cual.
        grupo_id:        UUID v4 ya validado (o None) que asocia N extracciones de
                          orden_compra como una sola OC lógica (D13). Se persiste tal
                          cual, solo si viene. Ignorado para doc_type != "orden_compra"
                          por el llamador (main.py), no por esta funcion.

    Returns:
        El mismo extraction_id recibido si el UPDATE afectó una fila, o None si
        falló (rows vacío, doc_type inválido, persistencia no disponible, o el
        UPDATE no afectó ninguna fila).
    """
    client = get_client()
    if client is None:
        return None

    # --- Validacion de rows ---
    if not rows:
        logger.error(
            "persistir_output_final: rows esta vacio — UPDATE abortado. "
            "extraction_id=%s source_filename=%s",
            extraction_id,
            source_filename,
        )
        return None

    if len(rows) > _WARN_ROW_COUNT:
        logger.warning(
            "persistir_output_final: rows contiene %d filas (> %d) — "
            "el UPDATE se ejecuta pero puede ser lento. extraction_id=%s",
            len(rows),
            _WARN_ROW_COUNT,
            extraction_id,
        )

    # --- Validar doc_type soportado ---
    if doc_type not in _DOC_TYPES_SOPORTADOS:
        logger.error(
            "persistir_output_final: doc_type='%s' no soportado. Valores validos: %s",
            doc_type,
            sorted(_DOC_TYPES_SOPORTADOS),
        )
        return None

    # --- UPDATE en extraction_results (solo metadata, ver docstring) ---
    payload: dict = {
        "status": "completed",
        "row_count": len(rows),
        "csv_disk_path": str(csv_path),
    }
    if licitacion_id:
        payload["proceso_comercial_id"] = licitacion_id
    if grupo_id:
        payload["grupo_id"] = grupo_id

    try:
        respuesta = await asyncio.to_thread(
            lambda: (
                client.table("extraction_results")
                .update(payload)
                .eq("id", str(extraction_id))
                .eq("drogueria_id", drogueria_id)
                .execute()
            )
        )
        if not respuesta.data:
            logger.error(
                "persistir_output_final: UPDATE en extraction_results sin filas afectadas. "
                "extraction_id=%s",
                extraction_id,
            )
            return None

        logger.info(
            "extraction_results actualizado a 'completed' — extraction_id=%s row_count=%d doc_type=%s",
            extraction_id,
            len(rows),
            doc_type,
        )
        return extraction_id
    except Exception as exc:
        logger.error(
            "persistir_output_final: error en UPDATE extraction_results — %s. "
            "extraction_id=%s sha256=%s",
            exc,
            extraction_id,
            source_sha256[:12] + "..." if source_sha256 else "N/A",
        )
        return None


async def marcar_extraccion_fallida(
    *,
    extraction_id: UUID | None,
    drogueria_id: str,
    error_msg: str,
) -> None:
    """
    Actualiza una extraction_results de 'processing' a 'failed' con un mensaje de
    error legible en español (carga-asincrona, T1). Se llama tanto cuando el
    robot lanza una excepción (parseo, Gemini, etc.) como cuando
    `persistir_output_final` agota sus reintentos -- en ambos casos la fila
    NUNCA debe quedar en 'processing' sin que el usuario se entere: `GET
    /api/documentos` expone `error_msg` para mostrarlo en la UI.

    Nunca propaga excepción. Si esto mismo falla (ej: Supabase caído), la fila
    queda 'processing' hasta que el sweep de arranque
    (`marcar_processing_interrumpidos`, corrido por el lifespan de FastAPI en
    `services/extraccion/main.py`) la marque 'failed' con un mensaje genérico.

    Args:
        extraction_id: UUID de la fila a marcar. None es un no-op (persistencia
                        no estaba disponible al crear la fila -- no hay nada
                        que actualizar).
        drogueria_id:   droguería dueña de la fila -- nunca actualiza una fila
                        de otra droguería aunque el id coincidiera.
        error_msg:      Mensaje de error en español, ya mapeado desde la
                        excepción original (ver `_mapear_error_procesamiento`
                        en main.py) -- nunca el texto crudo de la excepción.
    """
    if extraction_id is None:
        return

    client = get_client()
    if client is None:
        return

    try:
        await asyncio.to_thread(
            lambda: (
                client.table("extraction_results")
                .update({"status": "failed", "error_msg": error_msg})
                .eq("id", str(extraction_id))
                .eq("drogueria_id", drogueria_id)
                .execute()
            )
        )
        logger.info(
            "extraction_results marcado 'failed' — extraction_id=%s", extraction_id
        )
    except Exception as exc:
        logger.error(
            "marcar_extraccion_fallida: error al marcar failed — extraction_id=%s — %s",
            extraction_id,
            exc,
        )


_SWEEP_PROCESSING_MINUTOS_UMBRAL = 10
_SWEEP_PROCESSING_MENSAJE = "Procesamiento interrumpido, volvé a subir el documento"


async def marcar_processing_interrumpidos(
    *, minutos_umbral: int = _SWEEP_PROCESSING_MINUTOS_UMBRAL
) -> int:
    """
    Sweep de arranque (carga-asincrona, T1): si el servicio se reinició (deploy,
    crash) mientras una extracción estaba en 'processing', esa fila queda
    huérfana para siempre -- ningún background task va a terminar de
    actualizarla porque el proceso que la corría ya no existe. Se corre una vez
    al levantar el servicio (lifespan de FastAPI en `services/extraccion/main.py`)
    y marca 'failed' cualquier fila 'processing' con más de `minutos_umbral`
    minutos de antigüedad -- el margen evita pisar un robot que todavía está
    corriendo de verdad en un proceso vivo (Gemini con documentos grandes puede
    tardar varios minutos).

    Usa el service client (bypassea RLS): es un mantenimiento global entre
    droguerías al arrancar el proceso, no una operación scopeada a un usuario
    -- no hay tenant en un startup hook.

    Returns:
        Cantidad de filas marcadas 'failed'. 0 si no había ninguna, si la
        persistencia no está disponible, o si la query falla (se logea, nunca
        se propaga -- un sweep fallido no debe impedir que el servicio arranque).
    """
    client = get_client()
    if client is None:
        return 0

    corte = (datetime.now(timezone.utc) - timedelta(minutes=minutos_umbral)).isoformat()

    try:
        respuesta = await asyncio.to_thread(
            lambda: (
                client.table("extraction_results")
                .update({"status": "failed", "error_msg": _SWEEP_PROCESSING_MENSAJE})
                .eq("status", "processing")
                .lt("created_at", corte)
                .execute()
            )
        )
        afectadas = len(respuesta.data or [])
        if afectadas:
            logger.warning(
                "Sweep de arranque: %d extraccion(es) en 'processing' interrumpidas -> 'failed'",
                afectadas,
            )
        return afectadas
    except Exception as exc:
        logger.error(
            "marcar_processing_interrumpidos: error en el sweep de arranque — %s", exc
        )
        return 0
