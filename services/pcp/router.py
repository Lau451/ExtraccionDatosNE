"""Router agregador de `services/pcp/` (design.md D1, File Changes; mismo
criterio que `services/terceros/router.py`, D5).

Combina los routers de sub-módulo en un único `APIRouter` que
`services/presupuestacion/main.py` monta con un solo
`include_router(pcp_router)`. `pcp-historial` (PR3) no tiene router propio
todavía -- ver docstring de `services/pcp/historial/service.py`: es
append-only por ausencia de métodos de servicio (`agregar_evento`/
`listar_eventos` únicamente), no por un endpoint que rechace un verbo HTTP.
Ningún requisito de esta fase (tasks.md 5.7) ni de `specs/pcp-historial/spec.md`
fuerza una superficie HTTP dedicada para historial en este PR -- el launch
prompt de esta fase lo deja explícitamente como "una decisión separada".
Cuando la necesite, se agrega acá con una línea nueva.

PR6 (tasks.md 6.5) agrega `catalogo_router`. PR7 (tasks.md 7.7) agrega
`negociacion_router`.
"""

from fastapi import APIRouter

from services.pcp.catalogo.router import router as catalogo_router
from services.pcp.gestion.router import router as gestion_router
from services.pcp.negociacion.router import router as negociacion_router
from services.pcp.renglones.router import router as renglones_router

router = APIRouter()
router.include_router(gestion_router)
router.include_router(renglones_router)
router.include_router(catalogo_router)
router.include_router(negociacion_router)
