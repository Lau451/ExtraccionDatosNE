"""Router agregador de `services/terceros/` (design.md D5).

"Un prefijo único" (design.md, File Changes) se interpreta acá como un único
punto de registro: este módulo combina los cuatro routers de subdominio en un
solo `APIRouter` que `services/presupuestacion/main.py` monta con un único
`include_router(terceros_router)`, en vez de que main.py conozca cada
subdominio de terceros por separado. No se agrega un prefijo de URL nuevo
(`/terceros-algo`) porque cada subrouter ya define sus propias rutas
completas y coherentes (`/terceros`, `/terceros/{id}/direcciones`,
`/sectores-contacto`, `/condiciones-pago`, `/formas-pago`, etc.); agregar un
prefijo de path duplicaría el segmento `terceros` en las rutas de
`identidad/router.py` y rompería la convención plana que ya usan los
catálogos.
"""

from fastapi import APIRouter

from services.terceros.catalogos.router import router as catalogos_router
from services.terceros.contactos.router import router as contactos_router
from services.terceros.direcciones.router import router as direcciones_router
from services.terceros.identidad.router import router as identidad_router

router = APIRouter()
router.include_router(identidad_router)
router.include_router(catalogos_router)
router.include_router(direcciones_router)
router.include_router(contactos_router)
