import asyncio
import csv
import logging
import os
from contextlib import asynccontextmanager
from fastapi import BackgroundTasks, Depends, FastAPI, Form, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from pathlib import Path
from uuid import UUID, uuid4

from services.extraccion.auth import UsuarioPerfil, get_current_user, get_drogueria_id_actual
from services.extraccion.supabase_client import get_client
from services.shared.exceptions import register_exception_handlers
from services.extraccion.routers.extraction_results import router as extraction_results_router
from services.extraccion.routers.clientes import router as clientes_router
from services.extraccion.procesos_comerciales_client import (
    validar_proceso_comercial_id,
    listar_nombres_procesos_comerciales,
)
from services.extraccion.robot import obtener_cliente, procesar_archivo
from services.extraccion.robot_comparativas import procesar_comparativa, NoProvidersDetectedError
from services.extraccion.robot_orden_compra import procesar_orden_compra, OrdenCompraSinRenglonesError
from services.extraccion.parsers import parse_document, ParserError, UnsupportedFormatError
from services.extraccion.config import get_tmp_dir, OUTPUT_BASE, COMPARATIVAS_OUTPUT_BASE
from services.extraccion.gemini_errors import GeminiQuotaExceededError, GeminiRateLimitError, GeminiAPIError
from services.extraccion.persistent_output import (
    calcular_sha256,
    buscar_duplicado_con_lock,
    crear_extraction_processing,
    marcar_extraccion_fallida,
    marcar_processing_interrumpidos,
    _SWEEP_INTERVALO_SEGUNDOS,
)
from services.extraccion.persistent_chunking import crear_sesion, cerrar_sesion
from services.extraccion.background_tasks import schedule_persist_output

# ======================
# LOGGING
# ======================

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# ======================
# APP
# ======================

async def _sweep_periodico() -> None:
    """T1c (carga-asincrona): corre `marcar_processing_interrumpidos` cada
    `_SWEEP_INTERVALO_SEGUNDOS` mientras el proceso está vivo -- el sweep de
    arranque (T1/T1b) solo limpia huérfanas al reiniciar el servicio; una fila
    puede quedar huérfana (ej. el proceso que corría el robot muere) sin que el
    servicio se reinicie, y esa fila necesita este loop para no quedar
    'processing' para siempre hasta el próximo deploy.

    Tolerante a fallos: una excepción en una iteración (ej. Supabase caído en
    ese momento) se logea y el loop sigue en la próxima iteración -- aunque
    `marcar_processing_interrumpidos` ya atrapa sus propios errores y nunca
    debería propagar, este try/except es la red de seguridad del loop en sí
    (para no perder el sweep periódico entero por un cambio futuro ahí)."""
    while True:
        await asyncio.sleep(_SWEEP_INTERVALO_SEGUNDOS)
        try:
            await marcar_processing_interrumpidos()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception(
                "_sweep_periodico: error inesperado en una iteración, se reintenta "
                "en la próxima (cada %ds)",
                _SWEEP_INTERVALO_SEGUNDOS,
            )


@asynccontextmanager
async def _lifespan(app: FastAPI):
    """carga-asincrona (T1/T1c): al levantar el servicio, cualquier extraction_results
    en 'processing' que haya quedado huérfana (reinicio/crash anterior, o más vieja
    que el umbral de `marcar_processing_interrumpidos`) se marca 'failed'. Además se
    arranca `_sweep_periodico` para seguir barriendo huérfanas mientras el proceso
    sigue corriendo (T1c: el sweep de solo-arranque de T1b es inseguro si un segundo
    proceso comparte la misma base -- ver persistent_output.marcar_processing_interrumpidos).
    La tarea periódica se cancela limpiamente al apagar el servicio."""
    await marcar_processing_interrumpidos()
    tarea_sweep = asyncio.create_task(_sweep_periodico())
    try:
        yield
    finally:
        tarea_sweep.cancel()
        try:
            await tarea_sweep
        except asyncio.CancelledError:
            pass


app = FastAPI(title="Extractor de Documentos", lifespan=_lifespan)
app.include_router(extraction_results_router)
app.include_router(clientes_router)
register_exception_handlers(app)

_cors_origins = [
    origen.strip()
    for origen in os.environ.get("CORS_ORIGINS", "http://localhost:3000,http://localhost:5173").split(",")
    if origen.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_GEMINI_SEMAPHORE = asyncio.Semaphore(15)

# T1b (carga-asincrona): mensaje fijo cuando `crear_extraction_processing` devuelve
# None (Supabase no disponible o el INSERT falló) -- no hay fila 'processing' que el
# robot pueda actualizar, así que /procesar responde 503 antes de agendarlo.
_MENSAJE_PERSISTENCIA_NO_DISPONIBLE = (
    "No se pudo registrar el documento para su procesamiento. Intente nuevamente en unos instantes."
)

# T1c: mismos mensajes fijos que T1b introdujo inline en las ramas `except` de
# `_procesar_documento_background` -- hoisteados a constantes (junto a
# `_MENSAJE_PERSISTENCIA_NO_DISPONIBLE` arriba) para que los tests los reusen en vez
# de repetir el literal, y para que un cambio de copy quede en un solo lugar.
_MENSAJE_PARSER_ERROR = "No se pudo procesar el archivo. Verificá el formato del documento."
_MENSAJE_GEMINI_API_ERROR = "Error en el servicio de IA. Intente nuevamente en unos momentos."

# ======================
# HELPERS
# ======================

def _procesar_response(context: dict, status_code: int = 200) -> JSONResponse:
    """`POST /procesar` responde siempre JSON (el HTML legacy se retiró en T2,
    ver odd/tasks/extraccion-multi-tenant.md). `extraction_id` se incluye acá
    porque el 409 de duplicado lo necesita — el frontend lo lee del body."""
    payload = {"ok": status_code < 400}
    for key in ("resultado", "error", "tipo", "extraction_id"):
        if key in context:
            payload[key] = context[key]
    return JSONResponse(payload, status_code=status_code)


def _limpiar_archivos_temporales(destino: Path, tmp_dir: Path) -> None:
    """Borra el archivo temporal ya guardado en disco y el directorio tmp si quedó
    vacío (T1b, carga-asincrona) -- extraído del `finally` de
    `_procesar_documento_background` porque `/procesar` necesita el mismo cleanup
    cuando `crear_extraction_processing` devuelve None y el background job nunca
    llega a agendarse (no hay fila 'processing' que el robot pueda actualizar)."""
    if destino.exists():
        try:
            destino.unlink()
            logger.debug("Deleted temp file: %s", destino)
        except Exception as cleanup_error:
            logger.warning("Failed to delete temp file %s: %s", destino, cleanup_error)

    try:
        if tmp_dir.exists() and not any(tmp_dir.iterdir()):
            tmp_dir.rmdir()
            logger.debug("Deleted empty tmp directory: %s", tmp_dir)
    except Exception as cleanup_error:
        logger.debug("Could not remove tmp directory: %s", cleanup_error)

# ======================
# RUTAS
# ======================

async def _resolver_formato_prompt(
    client, *, cliente_id: str, doc_type: str
) -> tuple[str | None, str | None]:
    """§8: si hay instrucciones cargadas para este cliente+doc_type, las devuelve para
    inyectar al prompt de Gemini. (formato_id, instrucciones_prompt) — ambos None si no
    hay nada configurado o la consulta falla (nunca bloquea la carga del documento)."""
    if client is None or not cliente_id:
        return None, None

    try:
        respuesta = await asyncio.to_thread(
            lambda: client.table("cliente_formato_documentos")
            .select("id, instrucciones_prompt")
            .eq("cliente_id", cliente_id)
            .eq("doc_type", doc_type)
            .eq("activo", True)
            .limit(1)
            .execute()
        )
        if respuesta.data and respuesta.data[0].get("instrucciones_prompt"):
            fila = respuesta.data[0]
            return fila["id"], fila["instrucciones_prompt"]
    except Exception as exc:
        logger.warning(
            "_resolver_formato_prompt: error consultando cliente_formato_documentos — %s", exc
        )

    return None, None


def _validar_grupo_id(grupo_id: str) -> str | None:
    """D13: valida que `grupo_id`, si viene, sea un UUID v4.

    Vacío -> None (extracción suelta, comportamiento idéntico al actual).
    Inválido -> HTTPException 422, fail-fast antes de cualquier I/O (mismo patrón
    que validar_proceso_comercial_id / SC-25). El llamador solo invoca esta función
    cuando tipo == "ordenes" — para cualquier otro tipo, grupo_id se ignora entero.
    """
    valor = grupo_id.strip()
    if not valor:
        return None

    try:
        parsed = UUID(valor)
    except (ValueError, AttributeError, TypeError) as exc:
        raise HTTPException(
            status_code=422,
            detail=f"grupo_id no es un UUID v4 válido: {grupo_id}",
        ) from exc

    if parsed.version != 4:
        raise HTTPException(
            status_code=422,
            detail=f"grupo_id no es un UUID v4 válido: {grupo_id}",
        )

    return str(parsed)


async def _fallar_extraccion(
    *,
    extraction_id: UUID | None,
    drogueria_id: str,
    session_id: UUID | None,
    mensaje: str,
) -> None:
    """Marca la extraccion 'failed' + cierra la sesión 'failed' -- se llama desde
    cada rama except de `_procesar_documento_background` para asegurar que la
    fila de extraction_results NUNCA quede en 'processing' cuando el robot o la
    lectura del CSV fallan (carga-asincrona, T1). No propaga excepción: ambas
    funciones internas ya atrapan las suyas."""
    await marcar_extraccion_fallida(
        extraction_id=extraction_id, drogueria_id=drogueria_id, error_msg=mensaje
    )
    if session_id is not None:
        await cerrar_sesion(session_id=session_id, status="failed", error_msg=mensaje)


async def _procesar_documento_background(
    *,
    tipo: str,
    destino: Path,
    tmp_dir: Path,
    nombre_original: str,
    session_id: UUID | None,
    extraction_id: UUID | None,
    doc_type: str,
    drogueria_id: str,
    origen_id: str,
    source_sha256: str,
    instrucciones_prompt: str | None,
    licitacion_id: str | None,
    grupo_id: str | None,
) -> None:
    """
    Corre el robot (Gemini), lee el CSV resultante y persiste el resultado final
    -- TODO esto en background, después de que `/procesar` ya respondió 202 con
    `extraction_id` (carga-asincrona, T1). Antes de esta tarea, este mismo código
    vivía inline en el endpoint y el cliente esperaba a que terminara para
    recibir la respuesta HTTP.

    Nunca propaga excepción (es un BackgroundTask: nadie está esperando su
    resultado). Cualquier falla acá se traduce al mismo mapeo de mensajes en
    español que antes armaba la respuesta HTTP de error, ahora escrito en
    `extraction_results.error_msg` vía `_fallar_extraccion` -- la fila NUNCA debe
    quedar en 'processing' al salir de esta función, sea cual sea el motivo.
    El cleanup del archivo temporal (que antes vivía en el `finally` del
    endpoint) se movió acá porque ahora es este job, no el endpoint, quien
    termina de usar `destino`.
    """
    try:
        async with _GEMINI_SEMAPHORE:
            if tipo == "comparativas":
                csv_generado = await asyncio.to_thread(
                    procesar_comparativa, destino, nombre_original,
                    session_id=session_id,
                    drogueria_id=drogueria_id,
                    instrucciones_extra=instrucciones_prompt,
                )
            elif tipo == "ordenes":
                csv_generado = await asyncio.to_thread(
                    procesar_orden_compra, destino, nombre_original,
                    session_id=session_id,
                    instrucciones_extra=instrucciones_prompt,
                )
            else:
                csv_generado = await asyncio.to_thread(
                    procesar_archivo, destino, nombre_original,
                    session_id=session_id,
                    instrucciones_extra=instrucciones_prompt,
                )

        # ======================
        # LEER CSV + PERSISTENCIA FINAL
        # ======================
        csv_path = Path(csv_generado)
        rows = []
        try:
            with open(csv_path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f, delimiter=";")
                rows = list(reader)
        except Exception as e:
            logger.error("Error al leer CSV generado %s: %s", csv_path, e)

        # Ya estamos corriendo dentro de un BackgroundTask del endpoint (no hay
        # otro request/response del cual "colgar" una segunda tanda de tareas) --
        # se le da a schedule_persist_output una BackgroundTasks descartable y se
        # la corre en el acto, reusando tal cual su lógica de retry/backoff.
        persist_bg = BackgroundTasks()
        await schedule_persist_output(
            persist_bg,
            extraction_id=extraction_id,
            session_id=session_id,
            doc_type=doc_type,
            rows=rows,
            csv_path=csv_path,
            client_id=origen_id,
            source_filename=nombre_original,
            source_sha256=source_sha256,
            drogueria_id=drogueria_id,
            licitacion_id=licitacion_id,
            grupo_id=grupo_id,
        )
        await persist_bg()

    except UnsupportedFormatError as e:
        logger.warning("Unsupported format: %s", e.extension)
        await _fallar_extraccion(
            extraction_id=extraction_id, drogueria_id=drogueria_id, session_id=session_id,
            mensaje=f"Formato no soportado: {e.extension}",
        )

    except ParserError as e:
        # T1b: el detalle crudo de la excepción queda en el log, no en error_msg --
        # extraction_results.error_msg lo ve cualquier usuario de la droguería
        # (GET /api/documentos), así que es un mensaje fijo en español.
        logger.error("Parser error: %s - %s", e.filepath, e.cause)
        await _fallar_extraccion(
            extraction_id=extraction_id, drogueria_id=drogueria_id, session_id=session_id,
            mensaje=_MENSAJE_PARSER_ERROR,
        )

    except NoProvidersDetectedError as e:
        logger.warning("No providers detected: %s", e.message)
        await _fallar_extraccion(
            extraction_id=extraction_id, drogueria_id=drogueria_id, session_id=session_id,
            mensaje="No se detectaron proveedores en el documento",
        )

    except OrdenCompraSinRenglonesError as e:
        logger.warning("No renglones detected in orden_compra: %s", e.message)
        await _fallar_extraccion(
            extraction_id=extraction_id, drogueria_id=drogueria_id, session_id=session_id,
            mensaje="No se detectaron renglones en el documento",
        )

    except GeminiQuotaExceededError as e:
        logger.error("Gemini API quota exceeded: %s", e.message)
        await _fallar_extraccion(
            extraction_id=extraction_id, drogueria_id=drogueria_id, session_id=session_id,
            mensaje="⚠️ Límite de quota alcanzado. Por favor, contacte al administrador para renovar la API key.",
        )

    except GeminiRateLimitError as e:
        logger.error("Gemini API rate limit exceeded: %s", e.message)
        await _fallar_extraccion(
            extraction_id=extraction_id, drogueria_id=drogueria_id, session_id=session_id,
            mensaje="El servicio está temporalmente saturado. Intente nuevamente en unos momentos.",
        )

    except GeminiAPIError as e:
        # T1b: mismo criterio que ParserError arriba -- detalle crudo solo al log.
        logger.error("Gemini API error: %s", e.message)
        await _fallar_extraccion(
            extraction_id=extraction_id, drogueria_id=drogueria_id, session_id=session_id,
            mensaje=_MENSAJE_GEMINI_API_ERROR,
        )

    except Exception as e:
        logger.exception("Unexpected error processing %s: %s", tipo, e)
        await _fallar_extraccion(
            extraction_id=extraction_id, drogueria_id=drogueria_id, session_id=session_id,
            mensaje="Error interno del servidor",
        )

    finally:
        _limpiar_archivos_temporales(destino, tmp_dir)


@app.post("/procesar")
async def procesar(
    bg_tasks: BackgroundTasks,
    archivo: UploadFile = File(...),
    tipo: str = Form(""),
    licitacion_id: str = Form(""),
    cliente_id: str = Form(""),
    grupo_id: str = Form(""),
    usuario: UsuarioPerfil = Depends(get_current_user),
    drogueria_id: str = Depends(get_drogueria_id_actual),
):
    # D13: grupo_id solo aplica a tipo=="ordenes" — se ignora entero para cualquier
    # otro tipo. Fail-fast antes de cualquier I/O si viene y no es un UUID v4 (SC-25).
    grupo_id_validado: str | None = None
    if tipo == "ordenes":
        grupo_id_validado = _validar_grupo_id(grupo_id)

    # La vinculación a un proceso comercial NO se exige acá — es una decisión de negocio
    # sin impacto en la extracción, se resuelve en la pantalla "Validar extracción" (ver
    # openspec/changes/validar-extraccion/proposal.md). licitacion_id sigue aceptado y
    # validado si viene seteado (por compatibilidad / otros callers), simplemente no es
    # obligatorio para ningún tipo de documento en este endpoint.
    licitacion_id_validado = await validar_proceso_comercial_id(
        licitacion_id, drogueria_id=drogueria_id
    )

    # ======================
    # GUARDAR ARCHIVO
    # ======================
    nombre_original = Path(archivo.filename).name
    origen_id = obtener_cliente(Path(nombre_original).stem)
    extension = Path(nombre_original).suffix.lower()

    if tipo == "comparativas":
        permitidos = {".pdf", ".jpg", ".jpeg", ".png", ".xls", ".xlsx", ".ods", ".html", ".htm"}
    elif tipo == "ordenes":
        permitidos = {".pdf", ".jpg", ".jpeg", ".png", ".xls", ".xlsx", ".html", ".htm"}
    else:
        permitidos = {".pdf", ".jpg", ".jpeg", ".png", ".xls", ".xlsx"}

    if extension not in permitidos:
        return _procesar_response(
            {"error": "Tipo de archivo no permitido", "tipo": tipo},
            status_code=415,
        )

    base_dir = COMPARATIVAS_OUTPUT_BASE if tipo == "comparativas" else OUTPUT_BASE
    tmp_dir = get_tmp_dir(base_dir=base_dir, origen_id=origen_id)
    destino = tmp_dir / f"{uuid4()}_{nombre_original}"
    destino.parent.mkdir(parents=True, exist_ok=True)

    contenido_bytes = await archivo.read()
    await asyncio.to_thread(destino.write_bytes, contenido_bytes)

    # ======================
    # SHA256 + DEDUPLICACIÓN
    # ======================
    sha256_doc = await asyncio.to_thread(calcular_sha256, destino)

    existing_extraction = await buscar_duplicado_con_lock(
        source_sha256=sha256_doc, drogueria_id=drogueria_id
    )
    if existing_extraction:
        logger.warning("Documento duplicado detectado: %s - extraction_id: %s", nombre_original, existing_extraction)
        return _procesar_response(
            {"error": "Este documento ya fue procesado", "extraction_id": str(existing_extraction), "tipo": tipo},
            status_code=409,
        )

    # ======================
    # FORMATO POR CLIENTE (§8) — opcional, nunca bloquea la carga
    # ======================
    if tipo == "comparativas":
        doc_type = "comparativa"
    elif tipo == "ordenes":
        doc_type = "orden_compra"
    else:
        doc_type = "licitacion"
    formato_id, instrucciones_prompt = await _resolver_formato_prompt(
        get_client(), cliente_id=cliente_id, doc_type=doc_type
    )

    # ======================
    # CREAR SESIÓN EN SUPABASE
    # ======================
    session_id = await crear_sesion(
        doc_name=nombre_original,
        client_id=origen_id,
        total_chunks=0,  # placeholder; se actualiza al procesar chunks
        doc_type=doc_type,
        drogueria_id=drogueria_id,
        formato_usado_id=formato_id,
        subido_por=usuario.id,
    )

    # ======================
    # REGISTRO 'processing' + RESPUESTA INMEDIATA (carga-asincrona, T1)
    # ======================
    # A partir de acá el robot (Gemini), la lectura del CSV y la persistencia
    # final corren en background -- el cliente ya no espera nada de eso. La fila
    # 'processing' es lo que permite: (a) responder 202 con un extraction_id real
    # que el frontend puede pollear, y (b) que un segundo upload del mismo
    # archivo mientras este todavía corre reciba 409 (reserve_extraction trata
    # 'processing' como tomada, migración 0028).
    extraction_id = await crear_extraction_processing(
        drogueria_id=drogueria_id,
        document_type=doc_type,
        source_filename=nombre_original,
        source_sha256=sha256_doc,
        grupo_id=grupo_id_validado,
        proceso_comercial_id=licitacion_id_validado,
    )

    if extraction_id is None:
        # T1b: sin fila 'processing' no hay nada que el robot pueda actualizar al
        # terminar -- antes de esta guarda el robot corría igual en background y el
        # resultado (o el error) se perdía en silencio (persistir_output_final /
        # marcar_extraccion_fallida son no-op con extraction_id=None). Se corta acá,
        # ANTES de agendar el background task.
        if session_id is not None:
            # T1c: si cerrar_sesion en sí explota (no su propio try/except interno,
            # sino algo antes, ej. el client de Supabase), el cleanup del archivo
            # temporal y el 503 de abajo NUNCA deben perderse por eso -- antes de
            # esta guarda, una excepción acá se propagaba como 500 sin cleanup.
            try:
                await cerrar_sesion(
                    session_id=session_id, status="failed", error_msg=_MENSAJE_PERSISTENCIA_NO_DISPONIBLE
                )
            except Exception as exc:
                logger.error(
                    "procesar: error al cerrar la sesión tras 503 (persistencia no "
                    "disponible) — %s. session_id=%s",
                    exc,
                    session_id,
                )
        _limpiar_archivos_temporales(destino, tmp_dir)
        return _procesar_response(
            {"error": _MENSAJE_PERSISTENCIA_NO_DISPONIBLE, "tipo": tipo},
            status_code=503,
        )

    bg_tasks.add_task(
        _procesar_documento_background,
        tipo=tipo,
        destino=destino,
        tmp_dir=tmp_dir,
        nombre_original=nombre_original,
        session_id=session_id,
        extraction_id=extraction_id,
        doc_type=doc_type,
        drogueria_id=drogueria_id,
        origen_id=origen_id,
        source_sha256=sha256_doc,
        instrucciones_prompt=instrucciones_prompt,
        licitacion_id=licitacion_id_validado,
        grupo_id=grupo_id_validado,
    )

    return _procesar_response(
        {"tipo": tipo, "extraction_id": str(extraction_id) if extraction_id else None},
        status_code=202,
    )


@app.get("/api/documentos")
async def listar_documentos(
    tipo: str = "", drogueria_id: str = Depends(get_drogueria_id_actual)
):
    client = get_client()
    if not client:
        return JSONResponse({"documentos": [], "sin_persistencia": True})

    def _query():
        q = (
            client.table("extraction_results")
            .select(
                "id,source_filename,document_type,row_count,status,error_msg,created_at,"
                "proceso_comercial_id"
            )
            .eq("drogueria_id", drogueria_id)
            .order("created_at", desc=True)
        )
        if tipo in ("comparativa", "licitacion"):
            q = q.eq("document_type", tipo)
        return q.execute()

    result = await asyncio.to_thread(_query)
    docs = result.data or []

    # Resuelve nombres via procesos_comerciales_client (escopeado por drogueria_id) en vez del
    # embed roto contra la tabla "licitaciones" inexistente.
    proceso_ids = {row["proceso_comercial_id"] for row in docs if row.get("proceso_comercial_id")}
    nombres = await listar_nombres_procesos_comerciales(
        list(proceso_ids), drogueria_id=drogueria_id
    )

    for row in docs:
        proceso_id = row.pop("proceso_comercial_id", None)
        nombre = nombres.get(proceso_id) if proceso_id else None
        row["proceso_comercial"] = {"id": proceso_id, "nombre": nombre} if nombre else None
    return JSONResponse({"documentos": docs})


@app.get("/api/documentos/{doc_id}")
async def detalle_documento(
    doc_id: str, drogueria_id: str = Depends(get_drogueria_id_actual)
):
    client = get_client()
    if not client:
        return JSONResponse({"error": "Persistencia no disponible"}, status_code=503)

    def _query():
        # .eq("drogueria_id", drogueria_id): un doc_id de OTRA droguería no matchea
        # -> mismo 404 que un doc_id inexistente (no filtra existencia entre tenants).
        meta_r = (
            client.table("extraction_results")
            .select("id,source_filename,document_type,client_id,row_count,status,created_at")
            .eq("id", doc_id)
            .eq("drogueria_id", drogueria_id)
            .limit(1)
            .execute()
        )
        if not meta_r.data:
            return None, None
        meta = meta_r.data[0]
        tabla = "comparativas_results" if meta["document_type"] == "comparativa" else "licitaciones_results"
        rows_r = (
            client.table(tabla)
            .select("rows")
            .eq("extraction_id", doc_id)
            .limit(1)
            .execute()
        )
        rows = rows_r.data[0]["rows"] if rows_r.data else []
        return meta, rows

    meta, rows = await asyncio.to_thread(_query)
    if meta is None:
        return JSONResponse({"error": "Documento no encontrado"}, status_code=404)

    return JSONResponse({"meta": meta, "rows": rows})
