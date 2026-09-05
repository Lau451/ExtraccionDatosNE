from fastapi import APIRouter, Depends
from supabase import Client

from services.presupuestacion.clientes.models import (
    ClienteContactoCreate,
    ClienteContactoOut,
    ClienteContactoUpdate,
    ClienteCreate,
    ClienteFormatoDocumentoOut,
    ClienteFormatoDocumentoUpsert,
    ClienteObservacionCreate,
    ClienteObservacionOut,
    ClienteOut,
    ClienteUpdate,
)
from services.presupuestacion.clientes.service import (
    actualizar_cliente_para_endpoint,
    actualizar_contacto_para_endpoint,
    crear_cliente_para_endpoint,
    crear_contacto_para_endpoint,
    crear_observacion_para_endpoint,
    eliminar_cliente_para_endpoint,
    listar_clientes,
    listar_contactos,
    listar_formato_documentos,
    listar_observaciones,
    obtener_cliente,
    upsert_formato_documento_para_endpoint,
)
from services.presupuestacion.core.auth import UsuarioPerfil, require_roles
from services.presupuestacion.core.database import get_user_client
from services.terceros import api

router = APIRouter()

_ROLES_ESCRITURA = ("admin", "gerencia", "lider_comercial", "comercial")
_ROLES_ELIMINACION = ("admin", "gerencia")
_ROLES_LECTURA = ("superadmin", "admin", "gerencia", "lider_comercial", "comercial", "compras")


@router.get("/clientes", response_model=list[ClienteOut])
def listar_clientes_endpoint(
    activo: bool | None = None,
    usuario: UsuarioPerfil = Depends(require_roles(*_ROLES_LECTURA)),
    user_client: Client = Depends(get_user_client),
) -> list[ClienteOut]:
    return listar_clientes(user_client, drogueria_id=usuario.drogueria_id, activo=activo)


@router.post("/clientes", response_model=ClienteOut)
def crear_cliente_endpoint(
    body: ClienteCreate,
    usuario: UsuarioPerfil = Depends(require_roles(*_ROLES_ESCRITURA)),
) -> ClienteOut:
    return crear_cliente_para_endpoint(
        drogueria_id=usuario.drogueria_id, body=body, usuario_id=usuario.id
    )


@router.get("/clientes/{cliente_id}", response_model=ClienteOut)
def obtener_cliente_endpoint(
    cliente_id: str,
    usuario: UsuarioPerfil = Depends(require_roles(*_ROLES_LECTURA)),
    user_client: Client = Depends(get_user_client),
) -> ClienteOut:
    return obtener_cliente(user_client, cliente_id=cliente_id, drogueria_id=usuario.drogueria_id)


@router.patch("/clientes/{cliente_id}", response_model=ClienteOut)
def actualizar_cliente_endpoint(
    cliente_id: str,
    body: ClienteUpdate,
    usuario: UsuarioPerfil = Depends(require_roles(*_ROLES_ESCRITURA)),
) -> ClienteOut:
    return actualizar_cliente_para_endpoint(
        cliente_id=cliente_id, drogueria_id=usuario.drogueria_id, body=body, usuario_id=usuario.id
    )


@router.delete("/clientes/{cliente_id}", status_code=204)
def eliminar_cliente_endpoint(
    cliente_id: str,
    usuario: UsuarioPerfil = Depends(require_roles(*_ROLES_ELIMINACION)),
) -> None:
    eliminar_cliente_para_endpoint(
        cliente_id=cliente_id, drogueria_id=usuario.drogueria_id, usuario_id=usuario.id
    )


@router.get("/clientes/{cliente_id}/contactos", response_model=list[ClienteContactoOut])
def listar_contactos_endpoint(
    cliente_id: str,
    usuario: UsuarioPerfil = Depends(require_roles(*_ROLES_LECTURA)),
    user_client: Client = Depends(get_user_client),
) -> list[ClienteContactoOut]:
    drogueria_id = _obtener_drogueria_id_del_cliente(user_client, usuario, cliente_id)
    return listar_contactos(user_client, cliente_id=cliente_id, drogueria_id=drogueria_id)


@router.post("/clientes/{cliente_id}/contactos", response_model=ClienteContactoOut)
def crear_contacto_endpoint(
    cliente_id: str,
    body: ClienteContactoCreate,
    usuario: UsuarioPerfil = Depends(require_roles(*_ROLES_ESCRITURA)),
    user_client: Client = Depends(get_user_client),
) -> ClienteContactoOut:
    drogueria_id = _obtener_drogueria_id_del_cliente(user_client, usuario, cliente_id)
    return crear_contacto_para_endpoint(cliente_id=cliente_id, drogueria_id=drogueria_id, body=body)


@router.patch("/clientes/{cliente_id}/contactos/{contacto_id}", response_model=ClienteContactoOut)
def actualizar_contacto_endpoint(
    cliente_id: str,
    contacto_id: str,
    body: ClienteContactoUpdate,
    usuario: UsuarioPerfil = Depends(require_roles(*_ROLES_ESCRITURA)),
    user_client: Client = Depends(get_user_client),
) -> ClienteContactoOut:
    drogueria_id = _obtener_drogueria_id_del_cliente(user_client, usuario, cliente_id)
    return actualizar_contacto_para_endpoint(
        cliente_id=cliente_id, contacto_id=contacto_id, drogueria_id=drogueria_id, body=body
    )


def _obtener_drogueria_id_del_cliente(
    user_client: Client, usuario: UsuarioPerfil, cliente_id: str
) -> str:
    """Resuelve la droguería real del cliente vía services.terceros.api en
    vez de leer `clientes`/`terceros` directamente (design.md D5). Fase 8
    corrige acá la deuda D-CLIENTES-004 (design.md D3): el shape anterior
    devolvía `ForbiddenError` para "existe pero es de otra droguería" y
    `NotFoundError` para "no existe" -- dos excepciones para el mismo caso
    indistinguible desde afuera. `api.obtener_tercero` ya aplica el guard
    único D3 (siempre `NotFoundError`), incluyendo el bypass de superadmin."""
    tercero = api.obtener_tercero(
        user_client,
        tercero_id=cliente_id,
        drogueria_id=usuario.drogueria_id,
        es_superadmin=(usuario.rol == "superadmin"),
    )
    return tercero["drogueria_id"]


@router.get(
    "/clientes/{cliente_id}/formato-documentos",
    response_model=list[ClienteFormatoDocumentoOut],
)
def listar_formato_documentos_endpoint(
    cliente_id: str,
    usuario: UsuarioPerfil = Depends(require_roles(*_ROLES_LECTURA)),
    user_client: Client = Depends(get_user_client),
) -> list[ClienteFormatoDocumentoOut]:
    _obtener_drogueria_id_del_cliente(user_client, usuario, cliente_id)
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
    drogueria_id = _obtener_drogueria_id_del_cliente(user_client, usuario, cliente_id)
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
    _obtener_drogueria_id_del_cliente(user_client, usuario, cliente_id)
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
    drogueria_id = _obtener_drogueria_id_del_cliente(user_client, usuario, cliente_id)
    return crear_observacion_para_endpoint(
        cliente_id=cliente_id, drogueria_id=drogueria_id, body=body, usuario_id=usuario.id
    )
