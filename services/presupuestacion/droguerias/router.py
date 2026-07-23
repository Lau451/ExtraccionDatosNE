from fastapi import APIRouter, Depends
from supabase import Client

from services.presupuestacion.core.auth import UsuarioPerfil, get_current_user, require_roles
from services.presupuestacion.core.database import get_user_client
from services.presupuestacion.core.exceptions import NotFoundError
from services.presupuestacion.droguerias.models import DrogueriaCreate, DrogueriaOut, DrogueriaUpdate
from services.presupuestacion.droguerias.service import (
    actualizar_drogueria_para_endpoint,
    crear_drogueria_para_endpoint,
    eliminar_drogueria_para_endpoint,
)

router = APIRouter()


@router.get("/droguerias", response_model=list[DrogueriaOut])
def listar_droguerias_endpoint(
    usuario: UsuarioPerfil = Depends(get_current_user),
    user_client: Client = Depends(get_user_client),
) -> list[DrogueriaOut]:
    # Sin filtro explícito: RLS (droguerias_sel) ya acota a la propia droguería
    # salvo superadmin, que ve todas.
    return user_client.table("droguerias").select("*").order("nombre").execute().data


@router.get("/droguerias/{drogueria_id}", response_model=DrogueriaOut)
def obtener_drogueria_endpoint(
    drogueria_id: str,
    usuario: UsuarioPerfil = Depends(get_current_user),
    user_client: Client = Depends(get_user_client),
) -> DrogueriaOut:
    resultado = user_client.table("droguerias").select("*").eq("id", drogueria_id).limit(1).execute()
    if not resultado.data:
        raise NotFoundError("No se encontró la droguería")
    return resultado.data[0]


@router.post("/droguerias", response_model=DrogueriaOut)
def crear_drogueria_endpoint(
    body: DrogueriaCreate, usuario: UsuarioPerfil = Depends(require_roles("superadmin"))
) -> DrogueriaOut:
    return crear_drogueria_para_endpoint(body=body)


@router.patch("/droguerias/{drogueria_id}", response_model=DrogueriaOut)
def actualizar_drogueria_endpoint(
    drogueria_id: str,
    body: DrogueriaUpdate,
    usuario: UsuarioPerfil = Depends(require_roles("superadmin")),
) -> DrogueriaOut:
    return actualizar_drogueria_para_endpoint(drogueria_id=drogueria_id, body=body)


@router.delete("/droguerias/{drogueria_id}", status_code=204)
def eliminar_drogueria_endpoint(
    drogueria_id: str,
    usuario: UsuarioPerfil = Depends(require_roles("superadmin")),
) -> None:
    eliminar_drogueria_para_endpoint(drogueria_id=drogueria_id)
