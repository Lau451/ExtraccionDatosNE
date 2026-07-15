from fastapi import APIRouter, Depends

from services.presupuestacion.core.auth import UsuarioPerfil, require_roles
from services.presupuestacion.procesos_comerciales.models import (
    ProcesoComercialCreate,
    ProcesoComercialOut,
)
from services.presupuestacion.procesos_comerciales.service import (
    crear_proceso_comercial_para_endpoint,
)

router = APIRouter()

_ROLES_ESCRITURA = ("admin", "gerencia", "lider_comercial", "comercial")


@router.post("/procesos-comerciales", response_model=ProcesoComercialOut)
def crear_proceso_comercial_endpoint(
    body: ProcesoComercialCreate,
    usuario: UsuarioPerfil = Depends(require_roles(*_ROLES_ESCRITURA)),
) -> ProcesoComercialOut:
    return crear_proceso_comercial_para_endpoint(
        drogueria_id=usuario.drogueria_id, body=body, usuario_id=usuario.id
    )
