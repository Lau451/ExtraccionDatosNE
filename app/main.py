import logging
import os
from fastapi import FastAPI, Form, UploadFile, File, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import FileResponse

from pathlib import Path
import shutil
from uuid import uuid4
from urllib.parse import urlencode

from app.robot import obtener_cliente, procesar_archivo
from app.robot_comparativas import procesar_comparativa, NoProvidersDetectedError
from app.parsers import parse_document, ParserError, UnsupportedFormatError
from app.config import get_output_dir, get_tmp_dir, OUTPUT_BASE, COMPARATIVAS_OUTPUT_BASE

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

# ======================
# FRONTEND
# ======================

app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

# ======================
# RUTAS
# ======================

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("home.html", {"request": request})


@app.get("/upload", response_class=HTMLResponse)
async def upload_page(request: Request, tipo: str = ""):
    return templates.TemplateResponse("index.html", {"request": request, "tipo": tipo})


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
        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "error": "Tipo de archivo no permitido",
                "tipo": tipo,
            }
        )

    tmp_dir = get_tmp_dir(origen_id=origen_id)
    destino = tmp_dir / f"{uuid4()}_{nombre_original}"
    destino.parent.mkdir(parents=True, exist_ok=True)

    with open(destino, "wb") as buffer:
        shutil.copyfileobj(archivo.file, buffer)

    # ======================
    # PROCESAR CON ROBOT
    # ======================
    try:
        if tipo == "comparativas":
            csv_generado = procesar_comparativa(destino, nombre_original)
            params = urlencode({"origen": origen_id, "modulo": "comparativas"})
        else:
            csv_generado = procesar_archivo(destino, nombre_original)
            params = urlencode({"origen": origen_id})

        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "resultado": f"/descargar/{csv_generado.name}?{params}",
                "tipo": tipo,
            }
        )

    except UnsupportedFormatError as e:
        logger.warning("Unsupported format: %s", e.extension)
        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "error": f"Formato no soportado: {e.extension}",
                "tipo": tipo,
            },
            status_code=415,
        )

    except ParserError as e:
        logger.error("Parser error: %s - %s", e.filepath, e.cause)
        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "error": f"No se pudo procesar el archivo: {str(e.cause)[:100]}",
                "tipo": tipo,
            },
            status_code=422,
        )

    except NoProvidersDetectedError as e:
        logger.warning("No providers detected: %s", e.message)
        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "error": "No se detectaron proveedores en el documento",
                "tipo": tipo,
            },
            status_code=422,
        )

    except Exception as e:
        logger.exception("Unexpected error processing %s: %s", tipo, e)
        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "error": "Error interno del servidor",
                "tipo": tipo,
            },
            status_code=500,
        )

    finally:
        if destino.exists():
            try:
                destino.unlink()
                logger.debug("Deleted temp file: %s", destino)
            except Exception as cleanup_error:
                logger.warning("Failed to delete temp file %s: %s", destino, cleanup_error)


@app.get("/descargar/{nombre_archivo}")
def descargar(nombre_archivo: str, origen: str = "", modulo: str = ""):
    base = COMPARATIVAS_OUTPUT_BASE if modulo == "comparativas" else OUTPUT_BASE
    archivo = get_output_dir(base_dir=base, origen_id=origen) / nombre_archivo

    return FileResponse(
        path=archivo,
        filename=archivo.name,
        media_type="text/csv"
    )
