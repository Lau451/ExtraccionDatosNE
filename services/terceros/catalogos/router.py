from fastapi import APIRouter, Depends
from supabase import Client

from services.shared.auth import UsuarioPerfil, require_roles
from services.shared.database import get_user_client
from services.terceros.catalogos.models import (
    CondicionPagoCreate,
    CondicionPagoOut,
    CondicionPagoUpdate,
    FormaPagoCreate,
    FormaPagoOut,
    FormaPagoUpdate,
    SectorContactoCreate,
    SectorContactoOut,
    SectorContactoUpdate,
)
from services.terceros.catalogos.service import (
    actualizar_condicion_pago_para_endpoint,
    actualizar_forma_pago_para_endpoint,
    actualizar_sector_para_endpoint,
    crear_condicion_pago_para_endpoint,
    crear_forma_pago_para_endpoint,
    crear_sector_para_endpoint,
    listar_condiciones_pago,
    listar_formas_pago,
    listar_sectores,
    obtener_condicion_pago,
    obtener_forma_pago,
    obtener_sector,
)

router = APIRouter()

# RLS (0008_terceros_modelo.sql: sec_ins/cp_ins/fp_ins): los catálogos
# comerciales solo se escriben desde admin/gerencia, más restrictivo que
# terceros_ins/terceros_upd.
_ROLES_ESCRITURA = ("admin", "gerencia")
_ROLES_LECTURA = ("superadmin", "admin", "gerencia", "lider_comercial", "comercial", "compras")


@router.get("/sectores-contacto", response_model=list[SectorContactoOut])
def listar_sectores_endpoint(
    activo: bool | None = True,
    usuario: UsuarioPerfil = Depends(require_roles(*_ROLES_LECTURA)),
    user_client: Client = Depends(get_user_client),
) -> list[SectorContactoOut]:
    return listar_sectores(user_client, drogueria_id=usuario.drogueria_id, activo=activo)


@router.post("/sectores-contacto", response_model=SectorContactoOut)
def crear_sector_endpoint(
    body: SectorContactoCreate,
    usuario: UsuarioPerfil = Depends(require_roles(*_ROLES_ESCRITURA)),
) -> SectorContactoOut:
    return crear_sector_para_endpoint(drogueria_id=usuario.drogueria_id, body=body)


@router.get("/sectores-contacto/{sector_id}", response_model=SectorContactoOut)
def obtener_sector_endpoint(
    sector_id: str,
    usuario: UsuarioPerfil = Depends(require_roles(*_ROLES_LECTURA)),
    user_client: Client = Depends(get_user_client),
) -> SectorContactoOut:
    return obtener_sector(user_client, sector_id=sector_id, drogueria_id=usuario.drogueria_id)


@router.patch("/sectores-contacto/{sector_id}", response_model=SectorContactoOut)
def actualizar_sector_endpoint(
    sector_id: str,
    body: SectorContactoUpdate,
    usuario: UsuarioPerfil = Depends(require_roles(*_ROLES_ESCRITURA)),
) -> SectorContactoOut:
    return actualizar_sector_para_endpoint(
        sector_id=sector_id, drogueria_id=usuario.drogueria_id, body=body
    )


@router.get("/condiciones-pago", response_model=list[CondicionPagoOut])
def listar_condiciones_pago_endpoint(
    activo: bool | None = True,
    usuario: UsuarioPerfil = Depends(require_roles(*_ROLES_LECTURA)),
    user_client: Client = Depends(get_user_client),
) -> list[CondicionPagoOut]:
    return listar_condiciones_pago(user_client, drogueria_id=usuario.drogueria_id, activo=activo)


@router.post("/condiciones-pago", response_model=CondicionPagoOut)
def crear_condicion_pago_endpoint(
    body: CondicionPagoCreate,
    usuario: UsuarioPerfil = Depends(require_roles(*_ROLES_ESCRITURA)),
) -> CondicionPagoOut:
    return crear_condicion_pago_para_endpoint(drogueria_id=usuario.drogueria_id, body=body)


@router.get("/condiciones-pago/{condicion_pago_id}", response_model=CondicionPagoOut)
def obtener_condicion_pago_endpoint(
    condicion_pago_id: str,
    usuario: UsuarioPerfil = Depends(require_roles(*_ROLES_LECTURA)),
    user_client: Client = Depends(get_user_client),
) -> CondicionPagoOut:
    return obtener_condicion_pago(
        user_client, condicion_pago_id=condicion_pago_id, drogueria_id=usuario.drogueria_id
    )


@router.patch("/condiciones-pago/{condicion_pago_id}", response_model=CondicionPagoOut)
def actualizar_condicion_pago_endpoint(
    condicion_pago_id: str,
    body: CondicionPagoUpdate,
    usuario: UsuarioPerfil = Depends(require_roles(*_ROLES_ESCRITURA)),
) -> CondicionPagoOut:
    return actualizar_condicion_pago_para_endpoint(
        condicion_pago_id=condicion_pago_id, drogueria_id=usuario.drogueria_id, body=body
    )


@router.get("/formas-pago", response_model=list[FormaPagoOut])
def listar_formas_pago_endpoint(
    activo: bool | None = True,
    usuario: UsuarioPerfil = Depends(require_roles(*_ROLES_LECTURA)),
    user_client: Client = Depends(get_user_client),
) -> list[FormaPagoOut]:
    return listar_formas_pago(user_client, drogueria_id=usuario.drogueria_id, activo=activo)


@router.post("/formas-pago", response_model=FormaPagoOut)
def crear_forma_pago_endpoint(
    body: FormaPagoCreate,
    usuario: UsuarioPerfil = Depends(require_roles(*_ROLES_ESCRITURA)),
) -> FormaPagoOut:
    return crear_forma_pago_para_endpoint(drogueria_id=usuario.drogueria_id, body=body)


@router.get("/formas-pago/{forma_pago_id}", response_model=FormaPagoOut)
def obtener_forma_pago_endpoint(
    forma_pago_id: str,
    usuario: UsuarioPerfil = Depends(require_roles(*_ROLES_LECTURA)),
    user_client: Client = Depends(get_user_client),
) -> FormaPagoOut:
    return obtener_forma_pago(
        user_client, forma_pago_id=forma_pago_id, drogueria_id=usuario.drogueria_id
    )


@router.patch("/formas-pago/{forma_pago_id}", response_model=FormaPagoOut)
def actualizar_forma_pago_endpoint(
    forma_pago_id: str,
    body: FormaPagoUpdate,
    usuario: UsuarioPerfil = Depends(require_roles(*_ROLES_ESCRITURA)),
) -> FormaPagoOut:
    return actualizar_forma_pago_para_endpoint(
        forma_pago_id=forma_pago_id, drogueria_id=usuario.drogueria_id, body=body
    )
