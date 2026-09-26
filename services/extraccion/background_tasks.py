"""
Wrapper de retry con backoff exponencial para persistencia: services/extraccion/background_tasks.py

Registra persistir_output_final como BackgroundTask de FastAPI con:
  - 3 intentos maximos
  - Backoff exponencial: 2^n segundos (2s, 4s, 8s entre intentos)
  - Errores logeados como ERROR con session_id + sha256 para reconciliacion
  - NUNCA propaga excepcion al caller (el CSV en disco siempre esta disponible)

Uso en main.py (dentro de _procesar_documento_background, ya en background --
carga-asincrona, T1):
    await schedule_persist_output(
        bg_descartable,
        extraction_id=extraction_id,
        session_id=session_id,
        doc_type="comparativa",
        rows=rows,
        csv_path=csv_generado,
        client_id=origen_id,
        source_filename=nombre_original,
        source_sha256=sha256,
    )
    await bg_descartable()
"""

import asyncio
import logging
from pathlib import Path
from uuid import UUID

from fastapi import BackgroundTasks

from services.extraccion.persistent_chunking import cerrar_sesion
from services.extraccion.persistent_output import marcar_extraccion_fallida, persistir_output_final

logger = logging.getLogger(__name__)

# Cantidad maxima de intentos antes de loguear ERROR y rendirse
_MAX_ATTEMPTS = 3


async def _retry_persist(
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
    attempt: int = 0,
    max_attempts: int = _MAX_ATTEMPTS,
) -> None:
    """
    Intenta persistir el resultado final con backoff exponencial.

    Esquema de backoff:
      intento 0 -> falla -> espera 2^1 = 2s -> intento 1
      intento 1 -> falla -> espera 2^2 = 4s -> intento 2
      intento 2 -> falla -> ERROR final, no se reintenta

    Args:
        extraction_id:   UUID de la fila 'processing' a actualizar (carga-asincrona,
                          T1 -- creada por crear_extraction_processing ANTES de
                          correr el robot). None si la persistencia no estaba
                          disponible al crearla.
        session_id:      UUID de la sesion (puede ser None).
        doc_type:        "comparativa" | "licitacion" | "orden_compra".
        rows:            Filas extraidas del CSV.
        csv_path:        Path al CSV en disco.
        client_id:       Identificador del cliente.
        source_filename: Nombre del archivo original.
        source_sha256:   SHA256 del archivo original.
        attempt:         Numero de intento actual (base 0, uso interno).
        max_attempts:    Maximo de intentos permitidos.
    """
    try:
        resultado = await asyncio.wait_for(
            persistir_output_final(
                extraction_id=extraction_id,
                session_id=session_id,
                doc_type=doc_type,
                rows=rows,
                csv_path=csv_path,
                client_id=client_id,
                source_filename=source_filename,
                source_sha256=source_sha256,
                drogueria_id=drogueria_id,
                licitacion_id=licitacion_id,
                grupo_id=grupo_id,
            ),
            timeout=60.0,
        )

        if resultado is not None:
            logger.info(
                "Persistencia exitosa en intento %d/%d — "
                "extraction_id=%s session_id=%s",
                attempt + 1,
                max_attempts,
                resultado,
                session_id,
            )
            if session_id is not None:
                await cerrar_sesion(session_id=session_id, status="completed")
            return

        # persistir_output_final retorno None sin exception (error interno logueado ahi)
        raise RuntimeError("persistir_output_final retorno None sin excepcion")

    except Exception as exc:
        siguiente_intento = attempt + 1

        if siguiente_intento >= max_attempts:
            # Agotamos los reintentos — loguear ERROR para reconciliacion manual
            logger.error(
                "Persistencia fallida definitivamente tras %d intentos. "
                "El CSV en disco sigue disponible. "
                "extraction_id=%s session_id=%s sha256=%s source_filename=%s error=%s",
                max_attempts,
                extraction_id,
                session_id,
                source_sha256[:12] + "..." if source_sha256 else "N/A",
                source_filename,
                exc,
            )
            mensaje_usuario = (
                "No se pudo guardar el resultado de la extracción tras varios "
                "intentos. Volvé a subir el documento."
            )
            await marcar_extraccion_fallida(
                extraction_id=extraction_id,
                drogueria_id=drogueria_id,
                error_msg=mensaje_usuario,
            )
            if session_id is not None:
                await cerrar_sesion(
                    session_id=session_id,
                    status="failed",
                    error_msg=str(exc),
                )
            return  # NUNCA propagar

        # Calcular espera con backoff exponencial: 2^(attempt+1)
        espera = 2 ** siguiente_intento
        logger.warning(
            "Persistencia fallida (intento %d/%d) — reintentando en %ds. "
            "extraction_id=%s session_id=%s error=%s",
            siguiente_intento,
            max_attempts,
            espera,
            extraction_id,
            session_id,
            exc,
        )

        await asyncio.sleep(espera)

        await _retry_persist(
            extraction_id=extraction_id,
            session_id=session_id,
            doc_type=doc_type,
            rows=rows,
            csv_path=csv_path,
            client_id=client_id,
            source_filename=source_filename,
            source_sha256=source_sha256,
            drogueria_id=drogueria_id,
            licitacion_id=licitacion_id,
            grupo_id=grupo_id,
            attempt=siguiente_intento,
            max_attempts=max_attempts,
        )


async def schedule_persist_output(
    bg: BackgroundTasks,
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
) -> None:
    """
    Registra la persistencia del resultado final como BackgroundTask de FastAPI.

    Desde carga-asincrona (T1), el caller (`services/extraccion/main.py::
    _procesar_documento_background`) ya corre DENTRO de un BackgroundTask del
    endpoint (el robot mismo pasó a ser asincrónico, no solo la persistencia) --
    le pasa una `BackgroundTasks` descartable y la ejecuta en el acto (`await
    bg()` inmediatamente después de este llamado) en vez de depender de que
    FastAPI la dispare tras enviar la respuesta HTTP, porque para entonces la
    respuesta 202 ya se envió hace rato.

    Si la persistencia falla 3 veces con backoff exponencial, se logea un ERROR
    y la fila de extraction_results queda 'failed' con error_msg -- el usuario
    no recibe ninguna excepcion, el CSV en disco permanece intacto.

    Args:
        bg:              Instancia de BackgroundTasks (puede ser descartable,
                          ver docstring).
        extraction_id:   UUID de la fila 'processing' a actualizar (puede ser None).
        session_id:      UUID de la sesion creada antes del robot (puede ser None).
        doc_type:        Tipo de documento: "comparativa" | "licitacion" | "orden_compra".
        rows:            Lista de dicts leidos del CSV generado.
        csv_path:        Path al CSV generado en disco.
        client_id:       Identificador del cliente/origen.
        source_filename: Nombre original del archivo subido.
        source_sha256:   SHA256 calculado del archivo original.
    """
    bg.add_task(
        _retry_persist,
        extraction_id=extraction_id,
        session_id=session_id,
        doc_type=doc_type,
        rows=rows,
        csv_path=csv_path,
        client_id=client_id,
        source_filename=source_filename,
        source_sha256=source_sha256,
        drogueria_id=drogueria_id,
        licitacion_id=licitacion_id,
        grupo_id=grupo_id,
        attempt=0,
        max_attempts=_MAX_ATTEMPTS,
    )
    logger.debug(
        "Background task registrada — extraction_id=%s session_id=%s doc_type=%s rows=%d",
        extraction_id,
        session_id,
        doc_type,
        len(rows),
    )
