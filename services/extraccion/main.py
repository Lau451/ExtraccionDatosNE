import asyncio
import csv
import logging
import os
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
from services.extraccion.persistent_output import calcular_sha256, buscar_duplicado_con_lock
from services.extraccion.persistent_chunking import crear_sesion
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

app = FastAPI(title="Extractor de Documentos")
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
    # PROCESAR CON ROBOT
    # ======================
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
        # LEER CSV + SCHEDULING DE PERSISTENCIA
        # ======================
        csv_path = Path(csv_generado)
        rows = []
        try:
            with open(csv_path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f, delimiter=";")
                rows = list(reader)
        except Exception as e:
            logger.error("Error al leer CSV generado %s: %s", csv_path, e)

        await schedule_persist_output(
            bg_tasks,
            session_id=session_id,
            doc_type=doc_type,
            rows=rows,
            csv_path=csv_path,
            client_id=origen_id,
            source_filename=nombre_original,
            source_sha256=sha256_doc,
            drogueria_id=drogueria_id,
            licitacion_id=licitacion_id_validado,
            grupo_id=grupo_id_validado,
        )

        return _procesar_response({"tipo": tipo})

    except UnsupportedFormatError as e:
        logger.warning("Unsupported format: %s", e.extension)
        return _procesar_response(
            {"error": f"Formato no soportado: {e.extension}", "tipo": tipo},
            status_code=415,
        )

    except ParserError as e:
        logger.error("Parser error: %s - %s", e.filepath, e.cause)
        return _procesar_response(
            {"error": f"No se pudo procesar el archivo: {str(e.cause)[:100]}", "tipo": tipo},
            status_code=422,
        )

    except NoProvidersDetectedError as e:
        logger.warning("No providers detected: %s", e.message)
        return _procesar_response(
            {"error": "No se detectaron proveedores en el documento", "tipo": tipo},
            status_code=422,
        )

    except OrdenCompraSinRenglonesError as e:
        logger.warning("No renglones detected in orden_compra: %s", e.message)
        return _procesar_response(
            {"error": "No se detectaron renglones en el documento", "tipo": tipo},
            status_code=422,
        )

    except GeminiQuotaExceededError as e:
        logger.error("Gemini API quota exceeded: %s", e.message)
        return _procesar_response(
            {"error": "⚠️ Límite de quota alcanzado. Por favor, contacte al administrador para renovar la API key.", "tipo": tipo},
            status_code=503,
        )

    except GeminiRateLimitError as e:
        logger.error("Gemini API rate limit exceeded: %s", e.message)
        return _procesar_response(
            {"error": "El servicio está temporalmente saturado. Intente nuevamente en unos momentos.", "tipo": tipo},
            status_code=429,
        )

    except GeminiAPIError as e:
        logger.error("Gemini API error: %s", e.message)
        return _procesar_response(
            {"error": f"Error en el servicio de IA: {e.message[:80]}", "tipo": tipo},
            status_code=500,
        )

    except Exception as e:
        logger.exception("Unexpected error processing %s: %s", tipo, e)
        return _procesar_response(
            {"error": "Error interno del servidor", "tipo": tipo},
            status_code=500,
        )

    finally:
        if destino.exists():
            try:
                destino.unlink()
                logger.debug("Deleted temp file: %s", destino)
            except Exception as cleanup_error:
                logger.warning("Failed to delete temp file %s: %s", destino, cleanup_error)

        # Clean up empty tmp directory
        try:
            if tmp_dir.exists() and not any(tmp_dir.iterdir()):
                tmp_dir.rmdir()
                logger.debug("Deleted empty tmp directory: %s", tmp_dir)
        except Exception as cleanup_error:
            logger.debug("Could not remove tmp directory: %s", cleanup_error)


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
                "id,source_filename,document_type,row_count,status,created_at,"
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
