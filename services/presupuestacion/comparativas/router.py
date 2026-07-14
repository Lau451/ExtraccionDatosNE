from fastapi import APIRouter, Depends
from supabase import Client

from services.presupuestacion.comparativas import repository as repo
from services.presupuestacion.comparativas.models import (
    AsignarProveedorRequest,
    OfertaSinMatchear,
    RenglonGanado,
)
from services.presupuestacion.comparativas.service import asignar_proveedor_para_endpoint
from services.presupuestacion.core.auth import UsuarioPerfil, require_roles
from services.presupuestacion.core.database import get_user_client
from services.presupuestacion.core.exceptions import ForbiddenError, NotFoundError

router = APIRouter()

_ROLES_ASIGNAR = ("admin", "gerencia", "lider_comercial", "comercial")
_ROLES_LECTURA = ("superadmin", "admin", "gerencia", "lider_comercial", "comercial", "compras")


@router.get("/procesos/{proceso_id}/renglones-ganados", response_model=list[RenglonGanado])
def renglones_ganados_endpoint(
    proceso_id: str,
    usuario: UsuarioPerfil = Depends(require_roles(*_ROLES_LECTURA)),
    user_client: Client = Depends(get_user_client),
) -> list[RenglonGanado]:
    return repo.listar_renglones_ganados(user_client, proceso_comercial_id=proceso_id)


@router.get("/proveedores/sin-matchear", response_model=list[OfertaSinMatchear])
def ofertas_sin_matchear_endpoint(
    usuario: UsuarioPerfil = Depends(require_roles(*_ROLES_LECTURA)),
    user_client: Client = Depends(get_user_client),
) -> list[OfertaSinMatchear]:
    return repo.listar_ofertas_sin_matchear(user_client)


@router.post("/ofertas/{oferta_id}/asignar-proveedor")
def asignar_proveedor_endpoint(
    oferta_id: str,
    body: AsignarProveedorRequest,
    usuario: UsuarioPerfil = Depends(require_roles(*_ROLES_ASIGNAR)),
    user_client: Client = Depends(get_user_client),
) -> dict:
    resultado = (
        user_client.table("ofertas_items")
        .select("id, drogueria_id")
        .eq("id", oferta_id)
        .limit(1)
        .execute()
    )
    if not resultado.data:
        raise NotFoundError("No se encontró la oferta")

    oferta_drogueria_id = resultado.data[0]["drogueria_id"]
    if usuario.rol != "superadmin" and oferta_drogueria_id != usuario.drogueria_id:
        raise ForbiddenError("La oferta no pertenece a tu droguería")

    return asignar_proveedor_para_endpoint(oferta_item_id=oferta_id, proveedor_id=body.proveedor_id)
