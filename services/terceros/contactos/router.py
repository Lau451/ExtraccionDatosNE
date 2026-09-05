from fastapi import APIRouter, Depends
from supabase import Client

from services.shared.auth import UsuarioPerfil, require_roles
from services.shared.database import get_user_client
from services.terceros.contactos.models import (
    TerceroContactoCreate,
    TerceroContactoOut,
    TerceroContactoUpdate,
)
from services.terceros.contactos.service import (
    actualizar_contacto_para_endpoint,
    crear_contacto_para_endpoint,
    listar_contactos,
    obtener_contacto,
)

router = APIRouter()

# D3/RLS (0008_terceros_modelo.sql: "idéntico para tercero_direcciones,
# direccion_usos, terceros_contactos..."): mismo set de roles que terceros_ins/upd.
_ROLES_ESCRITURA = ("admin", "gerencia", "lider_comercial", "comercial", "compras")
_ROLES_LECTURA = ("superadmin", "admin", "gerencia", "lider_comercial", "comercial", "compras")


@router.get("/terceros/{tercero_id}/contactos", response_model=list[TerceroContactoOut])
def listar_contactos_endpoint(
    tercero_id: str,
    activo: bool | None = True,
    usuario: UsuarioPerfil = Depends(require_roles(*_ROLES_LECTURA)),
    user_client: Client = Depends(get_user_client),
) -> list[TerceroContactoOut]:
    return listar_contactos(
        user_client, tercero_id=tercero_id, drogueria_id=usuario.drogueria_id, activo=activo
    )


@router.post("/terceros/{tercero_id}/contactos", response_model=TerceroContactoOut)
def crear_contacto_endpoint(
    tercero_id: str,
    body: TerceroContactoCreate,
    usuario: UsuarioPerfil = Depends(require_roles(*_ROLES_ESCRITURA)),
) -> TerceroContactoOut:
    return crear_contacto_para_endpoint(
        tercero_id=tercero_id, drogueria_id=usuario.drogueria_id, body=body
    )


@router.get("/terceros/{tercero_id}/contactos/{contacto_id}", response_model=TerceroContactoOut)
def obtener_contacto_endpoint(
    tercero_id: str,
    contacto_id: str,
    usuario: UsuarioPerfil = Depends(require_roles(*_ROLES_LECTURA)),
    user_client: Client = Depends(get_user_client),
) -> TerceroContactoOut:
    return obtener_contacto(user_client, contacto_id=contacto_id, drogueria_id=usuario.drogueria_id)


@router.patch("/terceros/{tercero_id}/contactos/{contacto_id}", response_model=TerceroContactoOut)
def actualizar_contacto_endpoint(
    tercero_id: str,
    contacto_id: str,
    body: TerceroContactoUpdate,
    usuario: UsuarioPerfil = Depends(require_roles(*_ROLES_ESCRITURA)),
) -> TerceroContactoOut:
    return actualizar_contacto_para_endpoint(
        contacto_id=contacto_id, drogueria_id=usuario.drogueria_id, body=body
    )
