from typing import Any

from postgrest.exceptions import APIError
from supabase import Client

from services.presupuestacion.core.database import get_service_client
from services.presupuestacion.core.exceptions import ConflictError, NotFoundError
from services.presupuestacion.droguerias import repository as repo
from services.presupuestacion.droguerias.models import DrogueriaCreate, DrogueriaUpdate


def crear_drogueria(client: Client, *, body: DrogueriaCreate) -> dict[str, Any]:
    return repo.crear_drogueria(client, body.model_dump())


def actualizar_drogueria(
    client: Client, *, drogueria_id: str, body: DrogueriaUpdate
) -> dict[str, Any]:
    existente = repo.obtener_drogueria(client, drogueria_id=drogueria_id)
    if existente is None:
        raise NotFoundError("No se encontró la droguería")

    campos = body.model_dump(exclude_unset=True)
    return repo.actualizar_drogueria(client, drogueria_id=drogueria_id, campos=campos)


def eliminar_drogueria(client: Client, *, drogueria_id: str) -> None:
    existente = repo.obtener_drogueria(client, drogueria_id=drogueria_id)
    if existente is None:
        raise NotFoundError("No se encontró la droguería")

    try:
        repo.eliminar_drogueria(client, drogueria_id=drogueria_id)
    except APIError as exc:
        raise ConflictError(
            "No se puede eliminar: la empresa tiene datos asociados (usuarios, clientes, "
            "procesos comerciales, etc.)."
        ) from exc


def crear_drogueria_para_endpoint(*, body: DrogueriaCreate) -> dict[str, Any]:
    return crear_drogueria(get_service_client(), body=body)


def actualizar_drogueria_para_endpoint(*, drogueria_id: str, body: DrogueriaUpdate) -> dict[str, Any]:
    return actualizar_drogueria(get_service_client(), drogueria_id=drogueria_id, body=body)


def eliminar_drogueria_para_endpoint(*, drogueria_id: str) -> None:
    eliminar_drogueria(get_service_client(), drogueria_id=drogueria_id)
