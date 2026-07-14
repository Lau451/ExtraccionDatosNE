import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from services.presupuestacion.auditoria.router import router as auditoria_router
from services.presupuestacion.automatizaciones.router import router as automatizaciones_router
from services.presupuestacion.catalogo.router import router as catalogo_router
from services.presupuestacion.clientes.router import router as clientes_router
from services.presupuestacion.comparativas.router import router as comparativas_router
from services.presupuestacion.compras.router import router as compras_router
from services.presupuestacion.core.config import get_settings
from services.presupuestacion.core.exceptions import register_exception_handlers
from services.presupuestacion.eventos.router import router as eventos_router
from services.presupuestacion.extraccion.router import router as extraccion_router
from services.presupuestacion.imports.router import router as imports_router
from services.presupuestacion.matching.router import router as matching_router
from services.presupuestacion.notificaciones.router import router as notificaciones_router
from services.presupuestacion.presupuestos.router import router as presupuestos_router
from services.presupuestacion.pricing.router import router as pricing_router
from services.presupuestacion.usuarios.router import router as usuarios_router

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

app = FastAPI(title="Presupuestación API")

register_exception_handlers(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(pricing_router, tags=["pricing"])
app.include_router(matching_router, tags=["matching"])
app.include_router(presupuestos_router, tags=["presupuestos"])
app.include_router(extraccion_router, tags=["extraccion"])
app.include_router(comparativas_router, tags=["comparativas"])
app.include_router(compras_router, tags=["compras"])
app.include_router(clientes_router, tags=["clientes"])
app.include_router(imports_router, tags=["imports"])
app.include_router(catalogo_router, tags=["catalogo"])
app.include_router(usuarios_router, tags=["usuarios"])
app.include_router(eventos_router, tags=["eventos"])
app.include_router(notificaciones_router, tags=["notificaciones"])
app.include_router(automatizaciones_router, tags=["automatizaciones"])
app.include_router(auditoria_router, tags=["auditoria"])
