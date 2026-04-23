import asyncio
import logging
import os
from fastapi import FastAPI, Form, UploadFile, File, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import FileResponse

from pathlib import Path
from uuid import uuid4
from urllib.parse import urlencode

from app.robot import obtener_cliente, procesar_archivo
from app.robot_comparativas import procesar_comparativa, NoProvidersDetectedError
from app.parsers import parse_document, ParserError, UnsupportedFormatError
from app.config import get_output_dir, get_tmp_dir, OUTPUT_BASE, COMPARATIVAS_OUTPUT_BASE
from app.gemini_errors import GeminiQuotaExceededError, GeminiRateLimitError, GeminiAPIError

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

_GEMINI_SEMAPHORE = asyncio.Semaphore(15)

# ======================
# FRONTEND
# ======================

app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

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


@app.get("/upload", response_class=HTMLResponse)
async def upload_page(request: Request, tipo: str = ""):
    return templates.TemplateResponse(request, "index.html", {"tipo": tipo})


@app.post("/procesar", response_class=HTMLResponse)
async def procesar(
    request: Request,
    archivo: UploadFile = File(...),
    tipo: str = Form(""),
):
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
    # PROCESAR CON ROBOT
    # ======================
    try:
        async with _GEMINI_SEMAPHORE:
            if tipo == "comparativas":
                csv_generado = await asyncio.to_thread(procesar_comparativa, destino, nombre_original)
                params = urlencode({"origen": origen_id, "modulo": "comparativas"})
            else:
                csv_generado = await asyncio.to_thread(procesar_archivo, destino, nombre_original)
                params = urlencode({"origen": origen_id})

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


@app.get("/descargar/{nombre_archivo}")
def descargar(nombre_archivo: str, origen: str = "", modulo: str = ""):
    base = COMPARATIVAS_OUTPUT_BASE if modulo == "comparativas" else OUTPUT_BASE
    archivo = get_output_dir(base_dir=base, origen_id=origen, ensure_exists=False) / nombre_archivo

    return FileResponse(
        path=archivo,
        filename=archivo.name,
        media_type="text/csv"
    )
