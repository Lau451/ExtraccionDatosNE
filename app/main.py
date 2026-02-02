from fastapi import FastAPI, UploadFile, File, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import FileResponse

from pathlib import Path
import shutil

from app.robot import procesar_archivo
from app.config import INPUT_DIR, OUTPUT_DIR

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
    return templates.TemplateResponse(
        "index.html",
        {"request": request}
    )


@app.post("/procesar", response_class=HTMLResponse)
async def procesar(
    request: Request,
    archivo: UploadFile = File(...)
):
    # ======================
    # GUARDAR ARCHIVO
    # ======================
    destino = INPUT_DIR / archivo.filename

    with open(destino, "wb") as buffer:
        shutil.copyfileobj(archivo.file, buffer)

    # ======================
    # PROCESAR CON ROBOT
    # ======================
    try:
        csv_generado = procesar_archivo(destino)

        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "resultado": f"/descargar/{csv_generado.name}"
            }
        )

    except Exception as e:
        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "error": str(e)
            }
        )


@app.get("/descargar/{nombre_archivo}")
def descargar(nombre_archivo: str):
    archivo = OUTPUT_DIR / nombre_archivo

    return FileResponse(
        path=archivo,
        filename=archivo.name,
        media_type="text/csv"
    )
