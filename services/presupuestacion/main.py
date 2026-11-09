import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from services.presupuestacion.core.config import get_settings
from services.presupuestacion.core.exceptions import register_exception_handlers
from services.presupuestacion.modulos import MODULOS
from services.integracion_progress import api as integracion_progress

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)


@asynccontextmanager
async def _lifespan(app: FastAPI):
    """integracion-progress S4: recepción automática de archivos de Progress como
    tarea de fondo (escanea al arrancar y cada intervalo; se apaga sola si no está
    configurada). Se cancela limpiamente al apagar el servicio."""
    tarea_recepcion = asyncio.create_task(
        integracion_progress.recepcion_automatica_periodica(get_settings())
    )
    try:
        yield
    finally:
        tarea_recepcion.cancel()
        try:
            await tarea_recepcion
        except asyncio.CancelledError:
            pass


app = FastAPI(title="Presupuestación API", lifespan=_lifespan)

register_exception_handlers(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# X-ARQ-006 (odd/tasks/routers-por-modulo.md): un router por módulo objetivo;
# qué routers agrupa cada uno está en `modulos.py`.
for modulo in MODULOS:
    app.include_router(modulo.router)
