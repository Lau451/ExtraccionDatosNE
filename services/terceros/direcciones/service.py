"""Servicio de direcciones (0008_terceros_modelo.sql sección 3: tercero_direcciones +
direccion_usos).

Regla de "dirección principal" (documentada acá porque design.md deja la elección
explícitamente abierta): `uq_du_principal` es un índice único parcial sobre
`(tercero_id, uso) WHERE es_principal`, así que a lo sumo una dirección puede ser
principal para un mismo uso de un mismo tercero. Este módulo, a diferencia de
`terceros/contactos` (que *demueve* al principal anterior al crear uno nuevo),
elige **rechazar con ConflictError** la segunda asignación de uso principal para
el mismo (tercero_id, uso): el cliente debe demover explícitamente el uso
principal anterior (PATCH/DELETE sobre esa dirección_uso) antes de asignar uno
nuevo. Se prefiere sobre la democión automática porque una dirección puede
declarar varios usos a la vez (a diferencia de "un contacto es o no es el
principal"), así que decidir *cuál* asignación de uso queda demovida no tiene
una respuesta obvia sin involucrar al cliente.

"Eliminar una dirección" (5.9/spec `terceros-direcciones`) es una baja física, no
una desactivación: a diferencia de `terceros_contactos`, el requerimiento
explícito de `openspec/changes/terceros-modelo/specs/terceros-direcciones/spec.md`
("Address Edit and Removal") pide que la dirección y sus usos "dejen de existir",
y Fase 5 de tasks.md no incluye ningún test de "oculto por defecto" tipo D4 para
este submódulo (a diferencia de 3.11/4.6). `TerceroDireccionUpdate.activo` sigue
existiendo para permitir baja lógica manual si un consumidor futuro la necesita,
pero la baja física vía `eliminar_direccion` es el camino soportado por el router.
"""

from typing import Any

from postgrest.exceptions import APIError
from supabase import Client

from services.shared.database import get_service_client
from services.shared.exceptions import ConflictError
from services.terceros.direcciones import repository as repo
from services.terceros.direcciones.models import (
    DireccionUsoCreate,
    TerceroDireccionCreate,
    TerceroDireccionUpdate,
)
from services.terceros.errors import UNIQUE_VIOLATION, asegurar_tercero_de_la_drogueria
from services.terceros.identidad import repository as identidad_repo

# -- tercero_direcciones ---------------------------------------------------------


def _asegurar_tercero(client: Client, *, tercero_id: str, drogueria_id: str) -> None:
    tercero = identidad_repo.buscar_tercero(client, tercero_id=tercero_id)
    asegurar_tercero_de_la_drogueria(tercero, drogueria_id=drogueria_id, entidad="el tercero")


def crear_direccion(
    client: Client, *, tercero_id: str, drogueria_id: str, body: TerceroDireccionCreate
) -> dict[str, Any]:
    _asegurar_tercero(client, tercero_id=tercero_id, drogueria_id=drogueria_id)
    return repo.crear_direccion(
        client,
        {
            "tercero_id": tercero_id,
            "drogueria_id": drogueria_id,
            "etiqueta": body.etiqueta,
            "calle": body.calle,
            "numero": body.numero,
            "piso_depto": body.piso_depto,
            "ciudad": body.ciudad,
            "provincia": body.provincia,
            "codigo_postal": body.codigo_postal,
            "pais": body.pais,
            "observaciones": body.observaciones,
        },
    )


def listar_direcciones(
    client: Client,
    *,
    tercero_id: str,
    drogueria_id: str,
    activo: bool | None = True,
    uso: str | None = None,
) -> list[dict[str, Any]]:
    return repo.listar_direcciones(
        client, tercero_id=tercero_id, drogueria_id=drogueria_id, activo=activo, uso=uso
    )


def obtener_direccion(client: Client, *, direccion_id: str, drogueria_id: str) -> dict[str, Any]:
    direccion = repo.buscar_direccion(client, direccion_id=direccion_id)
    return asegurar_tercero_de_la_drogueria(
        direccion, drogueria_id=drogueria_id, entidad="la dirección"
    )


def actualizar_direccion(
    client: Client, *, direccion_id: str, drogueria_id: str, body: TerceroDireccionUpdate
) -> dict[str, Any]:
    obtener_direccion(client, direccion_id=direccion_id, drogueria_id=drogueria_id)
    campos = body.model_dump(exclude_unset=True)
    return repo.actualizar_direccion(client, direccion_id=direccion_id, campos=campos)


def eliminar_direccion(client: Client, *, direccion_id: str, drogueria_id: str) -> None:
    obtener_direccion(client, direccion_id=direccion_id, drogueria_id=drogueria_id)
    repo.eliminar_direccion(client, direccion_id=direccion_id)


# -- direccion_usos ----------------------------------------------------------------


def asignar_uso(
    client: Client,
    *,
    direccion_id: str,
    tercero_id: str,
    drogueria_id: str,
    body: DireccionUsoCreate,
) -> dict[str, Any]:
    obtener_direccion(client, direccion_id=direccion_id, drogueria_id=drogueria_id)
    try:
        return repo.crear_uso(
            client,
            {
                "direccion_id": direccion_id,
                "tercero_id": tercero_id,
                "drogueria_id": drogueria_id,
                "uso": body.uso,
                "es_principal": body.es_principal,
            },
        )
    except APIError as exc:
        if exc.code == UNIQUE_VIOLATION:
            mensaje = getattr(exc, "message", "") or ""
            if "uq_du_principal" in mensaje:
                raise ConflictError(
                    f"Ya existe una dirección principal para el uso '{body.uso}' de este tercero"
                ) from exc
            raise ConflictError(
                f"Esta dirección ya tiene asignado el uso '{body.uso}'"
            ) from exc
        raise


def listar_usos(client: Client, *, direccion_id: str, drogueria_id: str) -> list[dict[str, Any]]:
    obtener_direccion(client, direccion_id=direccion_id, drogueria_id=drogueria_id)
    return repo.listar_usos(client, direccion_id=direccion_id)


def eliminar_uso(client: Client, *, direccion_id: str, drogueria_id: str, uso: str) -> None:
    obtener_direccion(client, direccion_id=direccion_id, drogueria_id=drogueria_id)
    repo.eliminar_uso(client, direccion_id=direccion_id, uso=uso)


# -- wrappers de endpoint (service_role, mismo criterio que identidad/catalogos) ----


def crear_direccion_para_endpoint(
    *, tercero_id: str, drogueria_id: str, body: TerceroDireccionCreate
) -> dict[str, Any]:
    return crear_direccion(
        get_service_client(), tercero_id=tercero_id, drogueria_id=drogueria_id, body=body
    )


def actualizar_direccion_para_endpoint(
    *, direccion_id: str, drogueria_id: str, body: TerceroDireccionUpdate
) -> dict[str, Any]:
    return actualizar_direccion(
        get_service_client(), direccion_id=direccion_id, drogueria_id=drogueria_id, body=body
    )


def eliminar_direccion_para_endpoint(*, direccion_id: str, drogueria_id: str) -> None:
    eliminar_direccion(get_service_client(), direccion_id=direccion_id, drogueria_id=drogueria_id)


def asignar_uso_para_endpoint(
    *, direccion_id: str, tercero_id: str, drogueria_id: str, body: DireccionUsoCreate
) -> dict[str, Any]:
    return asignar_uso(
        get_service_client(),
        direccion_id=direccion_id,
        tercero_id=tercero_id,
        drogueria_id=drogueria_id,
        body=body,
    )


def eliminar_uso_para_endpoint(*, direccion_id: str, drogueria_id: str, uso: str) -> None:
    eliminar_uso(get_service_client(), direccion_id=direccion_id, drogueria_id=drogueria_id, uso=uso)
