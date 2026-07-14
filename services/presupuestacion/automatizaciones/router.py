from fastapi import APIRouter, Depends
from supabase import Client

from services.presupuestacion.automatizaciones.models import (
    MetricaAutomatizacionOut,
    ReglaAutomatizacionCreate,
    ReglaAutomatizacionOut,
    ReglaAutomatizacionUpdate,
)
from services.presupuestacion.automatizaciones.service import (
    actualizar_regla_para_endpoint,
    crear_regla_para_endpoint,
    listar_reglas,
    metricas,
)
from services.presupuestacion.core.auth import UsuarioPerfil, require_roles
from services.presupuestacion.core.database import get_user_client

router = APIRouter()

_ROLES = ("admin", "gerencia")


@router.get("/automatizaciones/reglas", response_model=list[ReglaAutomatizacionOut])
def listar_reglas_endpoint(
    activa: bool | None = None,
    usuario: UsuarioPerfil = Depends(require_roles(*_ROLES)),
    user_client: Client = Depends(get_user_client),
) -> list[ReglaAutomatizacionOut]:
    return listar_reglas(user_client, drogueria_id=usuario.drogueria_id, activa=activa)


@router.post("/automatizaciones/reglas", response_model=ReglaAutomatizacionOut)
def crear_regla_endpoint(
    body: ReglaAutomatizacionCreate, usuario: UsuarioPerfil = Depends(require_roles(*_ROLES))
) -> ReglaAutomatizacionOut:
    return crear_regla_para_endpoint(drogueria_id=usuario.drogueria_id, body=body, usuario_id=usuario.id)


@router.patch("/automatizaciones/reglas/{regla_id}", response_model=ReglaAutomatizacionOut)
def actualizar_regla_endpoint(
    regla_id: str, body: ReglaAutomatizacionUpdate, usuario: UsuarioPerfil = Depends(require_roles(*_ROLES))
) -> ReglaAutomatizacionOut:
    return actualizar_regla_para_endpoint(
        regla_id=regla_id, drogueria_id=usuario.drogueria_id, body=body, usuario_id=usuario.id
    )


@router.get("/automatizaciones/metricas", response_model=list[MetricaAutomatizacionOut])
def metricas_endpoint(
    usuario: UsuarioPerfil = Depends(require_roles(*_ROLES)),
    user_client: Client = Depends(get_user_client),
) -> list[MetricaAutomatizacionOut]:
    return metricas(user_client, drogueria_id=usuario.drogueria_id)
