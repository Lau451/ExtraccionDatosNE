from fastapi import APIRouter, Depends
from supabase import Client

from presupuestacion.clientes.models import (
    ClienteFormatoDocumentoOut,
    ClienteFormatoDocumentoUpsert,
    ClienteObservacionCreate,
    ClienteObservacionOut,
)
from presupuestacion.clientes.service import (
    crear_observacion_para_endpoint,
    listar_formato_documentos,
    listar_observaciones,
    upsert_formato_documento_para_endpoint,
)
from presupuestacion.core.auth import UsuarioPerfil, require_roles
from presupuestacion.core.database import get_user_client
from presupuestacion.core.exceptions import ForbiddenError, NotFoundError

router = APIRouter()

_ROLES_ESCRITURA = ("admin", "gerencia", "lider_comercial", "comercial")
_ROLES_LECTURA = ("superadmin", "admin", "gerencia", "lider_comercial", "comercial", "compras")


def _validar_cliente_y_obtener_drogueria_id(
    user_client: Client, usuario: UsuarioPerfil, cliente_id: str
) -> str:
    resultado = (
        user_client.table("clientes")
        .select("id, drogueria_id")
        .eq("id", cliente_id)
        .limit(1)
        .execute()
    )
    if not resultado.data:
        raise NotFoundError("No se encontró el cliente")

    cliente_drogueria_id = resultado.data[0]["drogueria_id"]
    if usuario.rol != "superadmin" and cliente_drogueria_id != usuario.drogueria_id:
        raise ForbiddenError("El cliente no pertenece a tu droguería")
    return cliente_drogueria_id


@router.get(
    "/clientes/{cliente_id}/formato-documentos",
    response_model=list[ClienteFormatoDocumentoOut],
)
def listar_formato_documentos_endpoint(
    cliente_id: str,
    usuario: UsuarioPerfil = Depends(require_roles(*_ROLES_LECTURA)),
    user_client: Client = Depends(get_user_client),
) -> list[ClienteFormatoDocumentoOut]:
    _validar_cliente_y_obtener_drogueria_id(user_client, usuario, cliente_id)
    return listar_formato_documentos(user_client, cliente_id=cliente_id)


@router.post(
    "/clientes/{cliente_id}/formato-documentos",
    response_model=ClienteFormatoDocumentoOut,
)
def upsert_formato_documento_endpoint(
    cliente_id: str,
    body: ClienteFormatoDocumentoUpsert,
    usuario: UsuarioPerfil = Depends(require_roles(*_ROLES_ESCRITURA)),
    user_client: Client = Depends(get_user_client),
) -> ClienteFormatoDocumentoOut:
    drogueria_id = _validar_cliente_y_obtener_drogueria_id(user_client, usuario, cliente_id)
    return upsert_formato_documento_para_endpoint(
        cliente_id=cliente_id, drogueria_id=drogueria_id, body=body, usuario_id=usuario.id
    )


@router.get(
    "/clientes/{cliente_id}/observaciones",
    response_model=list[ClienteObservacionOut],
)
def listar_observaciones_endpoint(
    cliente_id: str,
    usuario: UsuarioPerfil = Depends(require_roles(*_ROLES_LECTURA)),
    user_client: Client = Depends(get_user_client),
) -> list[ClienteObservacionOut]:
    _validar_cliente_y_obtener_drogueria_id(user_client, usuario, cliente_id)
    return listar_observaciones(user_client, cliente_id=cliente_id)


@router.post(
    "/clientes/{cliente_id}/observaciones",
    response_model=ClienteObservacionOut,
)
def crear_observacion_endpoint(
    cliente_id: str,
    body: ClienteObservacionCreate,
    usuario: UsuarioPerfil = Depends(require_roles(*_ROLES_ESCRITURA)),
    user_client: Client = Depends(get_user_client),
) -> ClienteObservacionOut:
    drogueria_id = _validar_cliente_y_obtener_drogueria_id(user_client, usuario, cliente_id)
    return crear_observacion_para_endpoint(
        cliente_id=cliente_id, drogueria_id=drogueria_id, body=body, usuario_id=usuario.id
    )
