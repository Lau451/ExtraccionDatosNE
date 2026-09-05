from fastapi import APIRouter, Depends, status
from supabase import Client

from services.shared.auth import UsuarioPerfil, require_roles
from services.shared.database import get_user_client
from services.terceros.direcciones.models import (
    DireccionUsoCreate,
    DireccionUsoOut,
    TerceroDireccionCreate,
    TerceroDireccionOut,
    TerceroDireccionUpdate,
)
from services.terceros.direcciones.service import (
    actualizar_direccion_para_endpoint,
    asignar_uso_para_endpoint,
    crear_direccion_para_endpoint,
    eliminar_direccion_para_endpoint,
    eliminar_uso_para_endpoint,
    listar_direcciones,
    listar_usos,
    obtener_direccion,
)

router = APIRouter()

# D3/RLS (0008_terceros_modelo.sql: "idéntico para tercero_direcciones,
# direccion_usos..."): mismo set de roles que terceros_ins/terceros_upd.
_ROLES_ESCRITURA = ("admin", "gerencia", "lider_comercial", "comercial", "compras")
_ROLES_LECTURA = ("superadmin", "admin", "gerencia", "lider_comercial", "comercial", "compras")


@router.get("/terceros/{tercero_id}/direcciones", response_model=list[TerceroDireccionOut])
def listar_direcciones_endpoint(
    tercero_id: str,
    activo: bool | None = True,
    uso: str | None = None,
    usuario: UsuarioPerfil = Depends(require_roles(*_ROLES_LECTURA)),
    user_client: Client = Depends(get_user_client),
) -> list[TerceroDireccionOut]:
    return listar_direcciones(
        user_client,
        tercero_id=tercero_id,
        drogueria_id=usuario.drogueria_id,
        activo=activo,
        uso=uso,
    )


@router.post("/terceros/{tercero_id}/direcciones", response_model=TerceroDireccionOut)
def crear_direccion_endpoint(
    tercero_id: str,
    body: TerceroDireccionCreate,
    usuario: UsuarioPerfil = Depends(require_roles(*_ROLES_ESCRITURA)),
) -> TerceroDireccionOut:
    return crear_direccion_para_endpoint(
        tercero_id=tercero_id, drogueria_id=usuario.drogueria_id, body=body
    )


@router.get("/terceros/{tercero_id}/direcciones/{direccion_id}", response_model=TerceroDireccionOut)
def obtener_direccion_endpoint(
    tercero_id: str,
    direccion_id: str,
    usuario: UsuarioPerfil = Depends(require_roles(*_ROLES_LECTURA)),
    user_client: Client = Depends(get_user_client),
) -> TerceroDireccionOut:
    return obtener_direccion(user_client, direccion_id=direccion_id, drogueria_id=usuario.drogueria_id)


@router.patch("/terceros/{tercero_id}/direcciones/{direccion_id}", response_model=TerceroDireccionOut)
def actualizar_direccion_endpoint(
    tercero_id: str,
    direccion_id: str,
    body: TerceroDireccionUpdate,
    usuario: UsuarioPerfil = Depends(require_roles(*_ROLES_ESCRITURA)),
) -> TerceroDireccionOut:
    return actualizar_direccion_para_endpoint(
        direccion_id=direccion_id, drogueria_id=usuario.drogueria_id, body=body
    )


@router.delete(
    "/terceros/{tercero_id}/direcciones/{direccion_id}", status_code=status.HTTP_204_NO_CONTENT
)
def eliminar_direccion_endpoint(
    tercero_id: str,
    direccion_id: str,
    usuario: UsuarioPerfil = Depends(require_roles(*_ROLES_ESCRITURA)),
) -> None:
    eliminar_direccion_para_endpoint(direccion_id=direccion_id, drogueria_id=usuario.drogueria_id)


@router.post(
    "/terceros/{tercero_id}/direcciones/{direccion_id}/usos", response_model=DireccionUsoOut
)
def asignar_uso_endpoint(
    tercero_id: str,
    direccion_id: str,
    body: DireccionUsoCreate,
    usuario: UsuarioPerfil = Depends(require_roles(*_ROLES_ESCRITURA)),
) -> DireccionUsoOut:
    return asignar_uso_para_endpoint(
        direccion_id=direccion_id,
        tercero_id=tercero_id,
        drogueria_id=usuario.drogueria_id,
        body=body,
    )


@router.get(
    "/terceros/{tercero_id}/direcciones/{direccion_id}/usos",
    response_model=list[DireccionUsoOut],
)
def listar_usos_endpoint(
    tercero_id: str,
    direccion_id: str,
    usuario: UsuarioPerfil = Depends(require_roles(*_ROLES_LECTURA)),
    user_client: Client = Depends(get_user_client),
) -> list[DireccionUsoOut]:
    return listar_usos(user_client, direccion_id=direccion_id, drogueria_id=usuario.drogueria_id)


@router.delete(
    "/terceros/{tercero_id}/direcciones/{direccion_id}/usos/{uso}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def eliminar_uso_endpoint(
    tercero_id: str,
    direccion_id: str,
    uso: str,
    usuario: UsuarioPerfil = Depends(require_roles(*_ROLES_ESCRITURA)),
) -> None:
    eliminar_uso_para_endpoint(direccion_id=direccion_id, drogueria_id=usuario.drogueria_id, uso=uso)
