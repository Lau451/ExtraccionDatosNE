from typing import Any

from fastapi import APIRouter, Depends, Query
from supabase import Client

from services.presupuestacion.core.auth import UsuarioPerfil, require_roles
from services.presupuestacion.core.database import get_user_client
from services.presupuestacion.core.exceptions import ForbiddenError, NotFoundError
from services.presupuestacion.extraccion.models import (
    ExtraccionResumen,
    FilasExtraccionOut,
    ResultadoValidarExtraccion,
    ValidarExtraccionRequest,
)
from services.presupuestacion.extraccion.service import (
    leer_filas_extraccion,
    listar_extracciones,
    validar_extraccion_para_endpoint,
)

router = APIRouter()

_ROLES_VALIDAR = ("admin", "gerencia", "lider_comercial", "comercial")
_ROLES_LECTURA = ("superadmin", "admin", "gerencia", "lider_comercial", "comercial", "compras")


def _verificar_pertenencia(
    user_client: Client,
    *,
    usuario: UsuarioPerfil,
    extraction_id: str,
    select: str = "id, drogueria_id",
) -> dict[str, Any]:
    """Mismo chequeo de pertenencia para todos los endpoints que operan sobre una
    extracción puntual (§8.2 -- GET .../filas replica esto tal cual desde POST
    .../validar). superadmin (drogueria_id NULL) queda exento a propósito."""
    resultado = (
        user_client.table("extraction_results")
        .select(select)
        .eq("id", extraction_id)
        .limit(1)
        .execute()
    )
    if not resultado.data:
        raise NotFoundError("No se encontró la extracción")

    extraccion = resultado.data[0]
    if usuario.rol != "superadmin" and extraccion["drogueria_id"] != usuario.drogueria_id:
        raise ForbiddenError("La extracción no pertenece a tu droguería")
    return extraccion


@router.get("/extracciones", response_model=list[ExtraccionResumen])
def listar_extracciones_endpoint(
    validado: bool | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    usuario: UsuarioPerfil = Depends(require_roles(*_ROLES_LECTURA)),
    user_client: Client = Depends(get_user_client),
) -> list[ExtraccionResumen]:
    return listar_extracciones(user_client, validado=validado, limit=limit, offset=offset)


@router.get("/extracciones/{extraction_id}/filas", response_model=FilasExtraccionOut)
def obtener_filas_extraccion_endpoint(
    extraction_id: str,
    usuario: UsuarioPerfil = Depends(require_roles(*_ROLES_VALIDAR)),
    user_client: Client = Depends(get_user_client),
) -> FilasExtraccionOut:
    extraccion = _verificar_pertenencia(
        user_client,
        usuario=usuario,
        extraction_id=extraction_id,
        select="id, drogueria_id, document_type, csv_disk_path, row_count",
    )
    return leer_filas_extraccion(extraccion)


@router.post("/extracciones/{extraction_id}/validar", response_model=ResultadoValidarExtraccion)
def validar_extraccion_endpoint(
    extraction_id: str,
    body: ValidarExtraccionRequest,
    usuario: UsuarioPerfil = Depends(require_roles(*_ROLES_VALIDAR)),
    user_client: Client = Depends(get_user_client),
) -> ResultadoValidarExtraccion:
    _verificar_pertenencia(user_client, usuario=usuario, extraction_id=extraction_id)

    # D2 -- el override entra como dicts planos, misma forma que las filas del CSV
    # (`_leer_filas_csv` también devuelve `list[dict[str, str]]`).
    filas_override = (
        [fila.model_dump() for fila in body.filas] if body.filas is not None else None
    )

    return validar_extraccion_para_endpoint(
        extraction_id=extraction_id,
        usuario_id=usuario.id,
        proceso_comercial_id=body.proceso_comercial_id,
        filas_override=filas_override,
    )
