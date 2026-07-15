from fastapi import APIRouter, Depends
from supabase import Client

from services.presupuestacion.core.auth import UsuarioPerfil, require_roles
from services.presupuestacion.core.database import get_user_client
from services.presupuestacion.procesos_comerciales.models import (
    ProcesoComercialCreate,
    ProcesoComercialOut,
    ProcesoComercialResumen,
)
from services.presupuestacion.procesos_comerciales.service import (
    crear_proceso_comercial_para_endpoint,
    listar_procesos_comerciales,
)

router = APIRouter()

_ROLES_ESCRITURA = ("admin", "gerencia", "lider_comercial", "comercial")
_ROLES_LECTURA = ("superadmin", "admin", "gerencia", "lider_comercial", "comercial", "compras")


@router.get("/procesos-comerciales", response_model=list[ProcesoComercialResumen])
def listar_procesos_comerciales_endpoint(
    activos: bool = True,
    usuario: UsuarioPerfil = Depends(require_roles(*_ROLES_LECTURA)),
    user_client: Client = Depends(get_user_client),
) -> list[ProcesoComercialResumen]:
    return listar_procesos_comerciales(
        user_client, drogueria_id=usuario.drogueria_id, activos=activos
    )


@router.post("/procesos-comerciales", response_model=ProcesoComercialOut)
def crear_proceso_comercial_endpoint(
    body: ProcesoComercialCreate,
    usuario: UsuarioPerfil = Depends(require_roles(*_ROLES_ESCRITURA)),
) -> ProcesoComercialOut:
    return crear_proceso_comercial_para_endpoint(
        drogueria_id=usuario.drogueria_id, body=body, usuario_id=usuario.id
    )
