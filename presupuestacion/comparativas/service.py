from typing import Any

from supabase import Client

from presupuestacion.comparativas import repository as repo
from presupuestacion.core.database import get_service_client
from presupuestacion.core.exceptions import NotFoundError, ValidationError


def asignar_proveedor(
    client: Client, *, oferta_item_id: str, proveedor_id: str
) -> dict[str, Any]:
    oferta = repo.buscar_oferta_item(client, oferta_item_id=oferta_item_id)
    if oferta is None:
        raise NotFoundError("No se encontró la oferta")

    proveedor = repo.buscar_proveedor(client, proveedor_id=proveedor_id)
    if proveedor is None:
        raise NotFoundError("No se encontró el proveedor")
    if proveedor["drogueria_id"] != oferta["drogueria_id"]:
        raise ValidationError("El proveedor no pertenece a la misma droguería que la oferta")

    return repo.actualizar_oferta_item(
        client, oferta_item_id=oferta_item_id, campos={"proveedor_id": proveedor_id}
    )


def asignar_proveedor_para_endpoint(*, oferta_item_id: str, proveedor_id: str) -> dict[str, Any]:
    """Corre con service_role: la RLS de ofertas_items no incluye 'superadmin' en UPDATE —
    mismo criterio que el resto de los módulos, el router nunca importa el service client."""
    return asignar_proveedor(
        get_service_client(), oferta_item_id=oferta_item_id, proveedor_id=proveedor_id
    )
