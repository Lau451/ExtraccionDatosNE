from typing import Any

from postgrest.exceptions import APIError
from supabase import Client

from services.shared.database import get_service_client
from services.shared.exceptions import ConflictError
from services.terceros.catalogos import repository as repo
from services.terceros.catalogos.models import (
    CondicionPagoCreate,
    CondicionPagoUpdate,
    FormaPagoCreate,
    FormaPagoUpdate,
    SectorContactoCreate,
    SectorContactoUpdate,
)
from services.terceros.errors import UNIQUE_VIOLATION, asegurar_tercero_de_la_drogueria

# -- sectores_contacto --------------------------------------------------------


def crear_sector(client: Client, *, drogueria_id: str, body: SectorContactoCreate) -> dict[str, Any]:
    try:
        return repo.crear_sector(
            client,
            {
                "drogueria_id": drogueria_id,
                "nombre": body.nombre,
                "descripcion": body.descripcion,
            },
        )
    except APIError as exc:
        if exc.code == UNIQUE_VIOLATION:
            raise ConflictError(
                f"Ya existe un sector de contacto llamado '{body.nombre}' en esta droguería"
            ) from exc
        raise


def listar_sectores(
    client: Client, *, drogueria_id: str, activo: bool | None = True
) -> list[dict[str, Any]]:
    return repo.listar_sectores(client, drogueria_id=drogueria_id, activo=activo)


def obtener_sector(client: Client, *, sector_id: str, drogueria_id: str) -> dict[str, Any]:
    sector = repo.obtener_sector(client, sector_id=sector_id)
    return asegurar_tercero_de_la_drogueria(
        sector, drogueria_id=drogueria_id, entidad="el sector de contacto"
    )


def actualizar_sector(
    client: Client, *, sector_id: str, drogueria_id: str, body: SectorContactoUpdate
) -> dict[str, Any]:
    obtener_sector(client, sector_id=sector_id, drogueria_id=drogueria_id)
    campos = body.model_dump(exclude_unset=True)
    try:
        return repo.actualizar_sector(client, sector_id=sector_id, campos=campos)
    except APIError as exc:
        if exc.code == UNIQUE_VIOLATION:
            raise ConflictError(
                f"Ya existe un sector de contacto llamado '{campos.get('nombre')}' en esta droguería"
            ) from exc
        raise


# -- condiciones_pago -----------------------------------------------------------


def crear_condicion_pago(
    client: Client, *, drogueria_id: str, body: CondicionPagoCreate
) -> dict[str, Any]:
    try:
        return repo.crear_condicion_pago(
            client,
            {
                "drogueria_id": drogueria_id,
                "nombre": body.nombre,
                "plazos_dias": body.plazos_dias,
                "descripcion": body.descripcion,
            },
        )
    except APIError as exc:
        if exc.code == UNIQUE_VIOLATION:
            raise ConflictError(
                f"Ya existe una condición de pago llamada '{body.nombre}' en esta droguería"
            ) from exc
        raise


def listar_condiciones_pago(
    client: Client, *, drogueria_id: str, activo: bool | None = True
) -> list[dict[str, Any]]:
    return repo.listar_condiciones_pago(client, drogueria_id=drogueria_id, activo=activo)


def obtener_condicion_pago(client: Client, *, condicion_pago_id: str, drogueria_id: str) -> dict[str, Any]:
    condicion = repo.obtener_condicion_pago(client, condicion_pago_id=condicion_pago_id)
    return asegurar_tercero_de_la_drogueria(
        condicion, drogueria_id=drogueria_id, entidad="la condición de pago"
    )


def actualizar_condicion_pago(
    client: Client, *, condicion_pago_id: str, drogueria_id: str, body: CondicionPagoUpdate
) -> dict[str, Any]:
    obtener_condicion_pago(client, condicion_pago_id=condicion_pago_id, drogueria_id=drogueria_id)
    campos = body.model_dump(exclude_unset=True)
    try:
        return repo.actualizar_condicion_pago(
            client, condicion_pago_id=condicion_pago_id, campos=campos
        )
    except APIError as exc:
        if exc.code == UNIQUE_VIOLATION:
            raise ConflictError(
                f"Ya existe una condición de pago llamada '{campos.get('nombre')}' en esta droguería"
            ) from exc
        raise


# -- formas_pago ------------------------------------------------------------------


def crear_forma_pago(client: Client, *, drogueria_id: str, body: FormaPagoCreate) -> dict[str, Any]:
    try:
        return repo.crear_forma_pago(
            client,
            {
                "drogueria_id": drogueria_id,
                "nombre": body.nombre,
                "tipo": body.tipo,
                "descripcion": body.descripcion,
            },
        )
    except APIError as exc:
        if exc.code == UNIQUE_VIOLATION:
            raise ConflictError(
                f"Ya existe una forma de pago llamada '{body.nombre}' en esta droguería"
            ) from exc
        raise


def listar_formas_pago(
    client: Client, *, drogueria_id: str, activo: bool | None = True
) -> list[dict[str, Any]]:
    return repo.listar_formas_pago(client, drogueria_id=drogueria_id, activo=activo)


def obtener_forma_pago(client: Client, *, forma_pago_id: str, drogueria_id: str) -> dict[str, Any]:
    forma = repo.obtener_forma_pago(client, forma_pago_id=forma_pago_id)
    return asegurar_tercero_de_la_drogueria(
        forma, drogueria_id=drogueria_id, entidad="la forma de pago"
    )


def actualizar_forma_pago(
    client: Client, *, forma_pago_id: str, drogueria_id: str, body: FormaPagoUpdate
) -> dict[str, Any]:
    obtener_forma_pago(client, forma_pago_id=forma_pago_id, drogueria_id=drogueria_id)
    campos = body.model_dump(exclude_unset=True)
    try:
        return repo.actualizar_forma_pago(client, forma_pago_id=forma_pago_id, campos=campos)
    except APIError as exc:
        if exc.code == UNIQUE_VIOLATION:
            raise ConflictError(
                f"Ya existe una forma de pago llamada '{campos.get('nombre')}' en esta droguería"
            ) from exc
        raise


# -- wrappers de endpoint (service_role, mismo criterio que clientes/catalogo) ----


def crear_sector_para_endpoint(*, drogueria_id: str, body: SectorContactoCreate) -> dict[str, Any]:
    return crear_sector(get_service_client(), drogueria_id=drogueria_id, body=body)


def actualizar_sector_para_endpoint(
    *, sector_id: str, drogueria_id: str, body: SectorContactoUpdate
) -> dict[str, Any]:
    return actualizar_sector(
        get_service_client(), sector_id=sector_id, drogueria_id=drogueria_id, body=body
    )


def crear_condicion_pago_para_endpoint(
    *, drogueria_id: str, body: CondicionPagoCreate
) -> dict[str, Any]:
    return crear_condicion_pago(get_service_client(), drogueria_id=drogueria_id, body=body)


def actualizar_condicion_pago_para_endpoint(
    *, condicion_pago_id: str, drogueria_id: str, body: CondicionPagoUpdate
) -> dict[str, Any]:
    return actualizar_condicion_pago(
        get_service_client(),
        condicion_pago_id=condicion_pago_id,
        drogueria_id=drogueria_id,
        body=body,
    )


def crear_forma_pago_para_endpoint(*, drogueria_id: str, body: FormaPagoCreate) -> dict[str, Any]:
    return crear_forma_pago(get_service_client(), drogueria_id=drogueria_id, body=body)


def actualizar_forma_pago_para_endpoint(
    *, forma_pago_id: str, drogueria_id: str, body: FormaPagoUpdate
) -> dict[str, Any]:
    return actualizar_forma_pago(
        get_service_client(), forma_pago_id=forma_pago_id, drogueria_id=drogueria_id, body=body
    )
