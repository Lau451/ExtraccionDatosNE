import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from services.presupuestacion.clientes.router import router as clientes_router
from services.presupuestacion.comparativas.router import router as comparativas_router
from services.presupuestacion.compras.router import router as compras_router
from services.presupuestacion.core.config import get_settings
from services.presupuestacion.core.exceptions import register_exception_handlers
from services.presupuestacion.extraccion.router import router as extraccion_router
from services.presupuestacion.matching.router import router as matching_router
from services.presupuestacion.presupuestos.router import router as presupuestos_router
from services.presupuestacion.pricing.router import router as pricing_router

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
