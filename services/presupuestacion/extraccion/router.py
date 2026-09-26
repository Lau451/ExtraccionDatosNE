from typing import Any

from fastapi import APIRouter, Depends, Query
from supabase import Client

from services.presupuestacion.core.auth import UsuarioPerfil, require_roles
from services.presupuestacion.core.database import get_user_client
from services.presupuestacion.core.exceptions import ForbiddenError, NotFoundError
from services.presupuestacion.extraccion.models import (
    AgruparExtraccionesRequest,
    CandidatoClienteOut,
    ExtraccionResumen,
    FilasExtraccionOut,
    ResultadoValidarExtraccion,
    ValidarExtraccionRequest,
)
from services.presupuestacion.extraccion.service import (
    agrupar_extracciones_para_endpoint,
    desagrupar_extracciones_para_endpoint,
    leer_filas_extraccion,
    listar_extracciones,
    obtener_cliente_candidato,
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
        select="id, drogueria_id, document_type, csv_disk_path, row_count, grupo_id, "
        "source_filename, validado",
    )
    return leer_filas_extraccion(extraccion, client=user_client)


@router.get(
    "/extracciones/{extraction_id}/cliente-candidato", response_model=CandidatoClienteOut
)
def obtener_cliente_candidato_endpoint(
    extraction_id: str,
    usuario: UsuarioPerfil = Depends(require_roles(*_ROLES_VALIDAR)),
    user_client: Client = Depends(get_user_client),
) -> CandidatoClienteOut:
    extraccion = _verificar_pertenencia(
        user_client,
        usuario=usuario,
        extraction_id=extraction_id,
        select="id, drogueria_id, csv_disk_path",
    )
    return obtener_cliente_candidato(user_client, extraccion)


@router.post("/extracciones/agrupar")
def agrupar_extracciones_endpoint(
    body: AgruparExtraccionesRequest,
    usuario: UsuarioPerfil = Depends(require_roles(*_ROLES_VALIDAR)),
    user_client: Client = Depends(get_user_client),
) -> dict[str, str]:
    # D13 § Agrupar después -- _verificar_pertenencia POR CADA id con el user
    # client (RLS real) antes de tocar nada con el service client, mismo
    # patrón que el resto de los endpoints *_para_endpoint.
    for extraction_id in body.extraction_ids:
        _verificar_pertenencia(user_client, usuario=usuario, extraction_id=extraction_id)

    grupo_id = agrupar_extracciones_para_endpoint(
        extraction_ids=body.extraction_ids, drogueria_id=usuario.drogueria_id
    )
    return {"grupo_id": grupo_id}


@router.post("/extracciones/desagrupar", status_code=204)
def desagrupar_extracciones_endpoint(
    body: AgruparExtraccionesRequest,
    usuario: UsuarioPerfil = Depends(require_roles(*_ROLES_VALIDAR)),
    user_client: Client = Depends(get_user_client),
) -> None:
    for extraction_id in body.extraction_ids:
        _verificar_pertenencia(user_client, usuario=usuario, extraction_id=extraction_id)

    desagrupar_extracciones_para_endpoint(
        extraction_ids=body.extraction_ids, drogueria_id=usuario.drogueria_id
    )


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
        orden_compra=body.orden_compra,
    )
