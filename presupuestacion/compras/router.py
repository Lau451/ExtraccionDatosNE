from fastapi import APIRouter, Depends
from supabase import Client

from presupuestacion.compras.models import (
    CrearEntregaRequest,
    CrearOrdenCompraRequest,
    ResultadoEntrega,
    ResultadoOrdenCompra,
)
from presupuestacion.compras.service import (
    confirmar_orden_compra_para_endpoint,
    crear_entrega_para_endpoint,
    crear_orden_compra_para_endpoint,
)
from presupuestacion.core.auth import UsuarioPerfil, require_roles
from presupuestacion.core.database import get_user_client
from presupuestacion.core.exceptions import ForbiddenError, NotFoundError

router = APIRouter()

_ROLES_OC = ("admin", "gerencia", "lider_comercial", "comercial")
_ROLES_ENTREGA = ("admin", "gerencia", "lider_comercial", "comercial", "compras")
_ROLES_LECTURA = ("superadmin", "admin", "gerencia", "lider_comercial", "comercial", "compras")


def _validar_oc_de_la_drogueria(
    user_client: Client, usuario: UsuarioPerfil, orden_compra_id: str
) -> None:
    resultado = (
        user_client.table("ordenes_compra")
        .select("id, drogueria_id")
        .eq("id", orden_compra_id)
        .limit(1)
        .execute()
    )
    if not resultado.data:
        raise NotFoundError("No se encontró la orden de compra")

    oc_drogueria_id = resultado.data[0]["drogueria_id"]
    if usuario.rol != "superadmin" and oc_drogueria_id != usuario.drogueria_id:
        raise ForbiddenError("La orden de compra no pertenece a tu droguería")


@router.post("/ordenes-compra", response_model=ResultadoOrdenCompra)
def crear_orden_compra_endpoint(
    body: CrearOrdenCompraRequest,
    usuario: UsuarioPerfil = Depends(require_roles(*_ROLES_OC)),
    user_client: Client = Depends(get_user_client),
) -> ResultadoOrdenCompra:
    proceso = (
        user_client.table("procesos_comerciales")
        .select("id, drogueria_id")
        .eq("id", body.proceso_comercial_id)
        .limit(1)
        .execute()
    )
    if not proceso.data:
        raise NotFoundError("No se encontró el proceso comercial")

    proceso_drogueria_id = proceso.data[0]["drogueria_id"]
    if usuario.rol != "superadmin" and proceso_drogueria_id != usuario.drogueria_id:
        raise ForbiddenError("El proceso comercial no pertenece a tu droguería")

    return crear_orden_compra_para_endpoint(
        drogueria_id=proceso_drogueria_id, usuario_id=usuario.id, body=body
    )


@router.post("/ordenes-compra/{orden_compra_id}/confirmar", response_model=ResultadoOrdenCompra)
def confirmar_orden_compra_endpoint(
    orden_compra_id: str,
    usuario: UsuarioPerfil = Depends(require_roles(*_ROLES_OC)),
    user_client: Client = Depends(get_user_client),
) -> ResultadoOrdenCompra:
    _validar_oc_de_la_drogueria(user_client, usuario, orden_compra_id)
    return confirmar_orden_compra_para_endpoint(
        orden_compra_id=orden_compra_id, usuario_id=usuario.id
    )


@router.post("/ordenes-compra/{orden_compra_id}/entregas", response_model=ResultadoEntrega)
def crear_entrega_endpoint(
    orden_compra_id: str,
    body: CrearEntregaRequest,
    usuario: UsuarioPerfil = Depends(require_roles(*_ROLES_ENTREGA)),
    user_client: Client = Depends(get_user_client),
) -> ResultadoEntrega:
    _validar_oc_de_la_drogueria(user_client, usuario, orden_compra_id)
    return crear_entrega_para_endpoint(
        orden_compra_id=orden_compra_id,
        items=body.items,
        fecha_entrega_planificada=body.fecha_entrega_planificada,
        fecha_entrega_real=body.fecha_entrega_real,
        observaciones=body.observaciones,
    )


@router.get("/entregas/pendientes")
def entregas_pendientes_endpoint(
    usuario: UsuarioPerfil = Depends(require_roles(*_ROLES_LECTURA)),
    user_client: Client = Depends(get_user_client),
) -> list[dict]:
    return user_client.table("v_entregas_pendientes").select("*").execute().data


@router.get("/compras/vs-cotizado")
def compras_vs_cotizado_endpoint(
    usuario: UsuarioPerfil = Depends(
        require_roles("superadmin", "admin", "gerencia", "compras")
    ),
    user_client: Client = Depends(get_user_client),
) -> list[dict]:
    return user_client.table("v_compras_vs_cotizado").select("*").execute().data
