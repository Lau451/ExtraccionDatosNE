import asyncio
import csv
import io
import logging
import os
from fastapi import BackgroundTasks, Depends, FastAPI, Form, UploadFile, File, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import FileResponse

from pathlib import Path
from uuid import uuid4
from urllib.parse import urlencode

from services.extraccion.auth import get_usuario_id_actual
from services.extraccion.supabase_client import get_client, resolver_drogueria_id_unica
from services.extraccion.routers.licitaciones import router as licitaciones_router, validar_licitacion_id
from services.extraccion.routers.extraction_results import router as extraction_results_router
from services.extraccion.routers.clientes import router as clientes_router
from services.extraccion.robot import obtener_cliente, procesar_archivo
from services.extraccion.robot_comparativas import procesar_comparativa, NoProvidersDetectedError
from services.extraccion.parsers import parse_document, ParserError, UnsupportedFormatError
from services.extraccion.config import get_output_dir, get_tmp_dir, OUTPUT_BASE, COMPARATIVAS_OUTPUT_BASE
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
app.include_router(licitaciones_router)
app.include_router(extraction_results_router)
app.include_router(clientes_router)

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
# FRONTEND
# ======================

app.mount("/static", StaticFiles(directory="services/extraccion/static"), name="static")
templates = Jinja2Templates(directory="services/extraccion/templates")

# ======================
# HELPERS
# ======================

def wants_json(request: Request) -> bool:
    accept = request.headers.get("accept", "").lower()
    requested_with = request.headers.get("x-requested-with", "").lower()
    return "application/json" in accept or requested_with in {"fetch", "xmlhttprequest"}


def render_upload_response(
    request: Request,
    context: dict,
    status_code: int = 200,
):
    if wants_json(request):
        payload = {"ok": status_code < 400}
        if "resultado" in context:
            payload["resultado"] = context["resultado"]
        if "error" in context:
            payload["error"] = context["error"]
        if "tipo" in context:
            payload["tipo"] = context["tipo"]
        return JSONResponse(payload, status_code=status_code)

    return templates.TemplateResponse(request, "index.html", context, status_code=status_code)

# ======================
# RUTAS
# ======================

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(request, "home.html")


@app.get("/licitaciones", response_class=HTMLResponse)
async def licitaciones_page(request: Request):
    return templates.TemplateResponse(request, "licitaciones.html", {})


@app.get("/upload", response_class=HTMLResponse)
async def upload_page(request: Request, tipo: str = ""):
    return templates.TemplateResponse(request, "index.html", {"tipo": tipo})


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


@app.post("/procesar", response_class=HTMLResponse)
async def procesar(
    request: Request,
    bg_tasks: BackgroundTasks,
    archivo: UploadFile = File(...),
    tipo: str = Form(""),
    licitacion_id: str = Form(""),
    cliente_id: str = Form(""),
    usuario_id: str | None = Depends(get_usuario_id_actual),
):
    # SC-25: fail-fast antes de cualquier I/O o invocación a Gemini
    licitacion_id_validado = await validar_licitacion_id(licitacion_id)

    # ======================
    # GUARDAR ARCHIVO
    # ======================
    nombre_original = Path(archivo.filename).name
    origen_id = obtener_cliente(Path(nombre_original).stem)
    extension = Path(nombre_original).suffix.lower()

    if tipo == "comparativas":
        permitidos = {".pdf", ".jpg", ".jpeg", ".png", ".xls", ".xlsx", ".ods", ".html", ".htm"}
    else:
        permitidos = {".pdf", ".jpg", ".jpeg", ".png", ".xls", ".xlsx"}

    if extension not in permitidos:
        return render_upload_response(
            request,
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

    existing_extraction = await buscar_duplicado_con_lock(source_sha256=sha256_doc)
    if existing_extraction:
        logger.warning("Documento duplicado detectado: %s - extraction_id: %s", nombre_original, existing_extraction)
        return render_upload_response(
            request,
            {"error": "Este documento ya fue procesado", "extraction_id": str(existing_extraction), "tipo": tipo},
            status_code=409,
        )

    # ======================
    # FORMATO POR CLIENTE (§8) — opcional, nunca bloquea la carga
    # ======================
    doc_type = "comparativa" if tipo == "comparativas" else "licitacion"
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
        formato_usado_id=formato_id,
        subido_por=usuario_id,
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
                    instrucciones_extra=instrucciones_prompt,
                )
                params = urlencode({"origen": origen_id, "modulo": "comparativas"})
            else:
                csv_generado = await asyncio.to_thread(
                    procesar_archivo, destino, nombre_original,
                    session_id=session_id,
                    instrucciones_extra=instrucciones_prompt,
                )
                params = urlencode({"origen": origen_id})

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
            licitacion_id=licitacion_id_validado,
        )

        return render_upload_response(request, {"tipo": tipo})

    except UnsupportedFormatError as e:
        logger.warning("Unsupported format: %s", e.extension)
        return render_upload_response(
            request,
            {"error": f"Formato no soportado: {e.extension}", "tipo": tipo},
            status_code=415,
        )

    except ParserError as e:
        logger.error("Parser error: %s - %s", e.filepath, e.cause)
        return render_upload_response(
            request,
            {"error": f"No se pudo procesar el archivo: {str(e.cause)[:100]}", "tipo": tipo},
            status_code=422,
        )

    except NoProvidersDetectedError as e:
        logger.warning("No providers detected: %s", e.message)
        return render_upload_response(
            request,
            {"error": "No se detectaron proveedores en el documento", "tipo": tipo},
            status_code=422,
        )

    except GeminiQuotaExceededError as e:
        logger.error("Gemini API quota exceeded: %s", e.message)
        return render_upload_response(
            request,
            {"error": "⚠️ Límite de quota alcanzado. Por favor, contacte al administrador para renovar la API key.", "tipo": tipo},
            status_code=503,
        )

    except GeminiRateLimitError as e:
        logger.error("Gemini API rate limit exceeded: %s", e.message)
        return render_upload_response(
            request,
            {"error": "El servicio está temporalmente saturado. Intente nuevamente en unos momentos.", "tipo": tipo},
            status_code=429,
        )

    except GeminiAPIError as e:
        logger.error("Gemini API error: %s", e.message)
        return render_upload_response(
            request,
            {"error": f"Error en el servicio de IA: {e.message[:80]}", "tipo": tipo},
            status_code=500,
        )

    except Exception as e:
        logger.exception("Unexpected error processing %s: %s", tipo, e)
        return render_upload_response(
            request,
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


@app.get("/calendario", response_class=HTMLResponse)
async def calendario_page(request: Request):
    return templates.TemplateResponse(request, "calendario.html", {})


@app.get("/historial", response_class=HTMLResponse)
async def historial_page(request: Request):
    return templates.TemplateResponse(request, "historial.html")


@app.get("/api/documentos")
async def listar_documentos(tipo: str = ""):
    client = get_client()
    if not client:
        return JSONResponse({"documentos": [], "sin_persistencia": True})

    def _query():
        q = (
            client.table("extraction_results")
            .select("id,source_filename,document_type,row_count,status,created_at,licitacion:licitaciones(id,nombre)")
            .order("created_at", desc=True)
        )
        if tipo in ("comparativa", "licitacion"):
            q = q.eq("document_type", tipo)
        return q.execute()

    result = await asyncio.to_thread(_query)
    docs = result.data or []
    for row in docs:
        row["licitacion"] = row.get("licitacion") or None
    return JSONResponse({"documentos": docs})


@app.get("/api/documentos/{doc_id}")
async def detalle_documento(doc_id: str):
    client = get_client()
    if not client:
        return JSONResponse({"error": "Persistencia no disponible"}, status_code=503)

    def _query():
        meta_r = (
            client.table("extraction_results")
            .select("id,source_filename,document_type,client_id,row_count,status,created_at")
            .eq("id", doc_id)
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


@app.get("/api/documentos/{doc_id}/descargar")
async def descargar_documento_supabase(doc_id: str):
    client = get_client()
    if not client:
        return JSONResponse({"error": "Persistencia no disponible"}, status_code=503)

    def _query():
        meta_r = (
            client.table("extraction_results")
            .select("document_type,source_filename")
            .eq("id", doc_id)
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
        return meta["source_filename"], rows

    source_filename, rows = await asyncio.to_thread(_query)

    if source_filename is None:
        return JSONResponse({"error": "Documento no encontrado"}, status_code=404)
    if not rows:
        return JSONResponse({"error": "Sin datos para descargar"}, status_code=404)

    stem = Path(source_filename).stem
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=list(rows[0].keys()), delimiter=";")
    writer.writeheader()
    writer.writerows(rows)
    csv_bytes = output.getvalue().encode("utf-8-sig")  # utf-8-sig: Excel abre sin conversión

    return StreamingResponse(
        iter([csv_bytes]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{stem}.csv"'},
    )


@app.get("/guia", response_class=HTMLResponse)
async def guia_usuario():
    return FileResponse(Path(__file__).parent.parent / "docs" / "guia_usuario.html", media_type="text/html")


@app.get("/descargar/{nombre_archivo}")
def descargar(nombre_archivo: str, origen: str = "", modulo: str = ""):
    base = COMPARATIVAS_OUTPUT_BASE if modulo == "comparativas" else OUTPUT_BASE
    archivo = get_output_dir(base_dir=base, origen_id=origen, ensure_exists=False) / nombre_archivo

    return FileResponse(
        path=archivo,
        filename=archivo.name,
        media_type="text/csv"
    )
