"""Servicio de contactos (0008_terceros_modelo.sql sección 4: terceros_contactos).

Regla de "contacto principal" (design.md deja la elección abierta, documentada
acá): `uq_tc_principal` es un índice único parcial sobre `tercero_id WHERE
es_principal AND activo`, así que a lo sumo un contacto activo por tercero puede
ser principal. A diferencia de `terceros/direcciones` (que rechaza con
ConflictError), acá se **demociona automáticamente** al principal anterior antes
de insertar/actualizar el nuevo: un tercero tiene un único punto de contacto
"principal" con sentido claro de qué reemplaza a qué, así que la democión
automática es una operación no ambigua (a diferencia de direcciones, donde un
mismo tercero puede tener varios usos simultáneos y no hay una única dirección
"la principal" sin calificar por uso).

Dar de baja al contacto principal (`activo=false`) NO promueve a otro
contacto automáticamente: `uq_tc_principal` exige `activo`, así que desactivar
libera el lugar a nivel de base, pero ningún otro contacto se vuelve principal
sin una acción explícita del cliente.
"""

from typing import Any

from supabase import Client

from services.shared.database import get_service_client
from services.shared.exceptions import ValidationError
from services.terceros.catalogos import repository as catalogos_repo
from services.terceros.contactos import repository as repo
from services.terceros.contactos.models import TerceroContactoCreate, TerceroContactoUpdate
from services.terceros.errors import asegurar_tercero_de_la_drogueria
from services.terceros.identidad import repository as identidad_repo


def _asegurar_tercero(client: Client, *, tercero_id: str, drogueria_id: str) -> None:
    tercero = identidad_repo.buscar_tercero(client, tercero_id=tercero_id)
    asegurar_tercero_de_la_drogueria(tercero, drogueria_id=drogueria_id, entidad="el tercero")


def _validar_sector(client: Client, *, drogueria_id: str, sector_id: str | None) -> None:
    if sector_id is None:
        return
    sector = catalogos_repo.obtener_sector(client, sector_id=sector_id)
    if sector is None or sector["drogueria_id"] != drogueria_id:
        raise ValidationError("El sector de contacto no pertenece a esta droguería")


def _democionar_principal_anterior(
    client: Client, *, tercero_id: str, excluir_id: str | None = None
) -> None:
    anterior = repo.buscar_principal_activo(client, tercero_id=tercero_id, excluir_id=excluir_id)
    if anterior is not None:
        repo.actualizar_contacto(client, contacto_id=anterior["id"], campos={"es_principal": False})


def crear_contacto(
    client: Client, *, tercero_id: str, drogueria_id: str, body: TerceroContactoCreate
) -> dict[str, Any]:
    _asegurar_tercero(client, tercero_id=tercero_id, drogueria_id=drogueria_id)
    _validar_sector(client, drogueria_id=drogueria_id, sector_id=body.sector_id)
    if body.es_principal:
        _democionar_principal_anterior(client, tercero_id=tercero_id)
    return repo.crear_contacto(
        client,
        {
            "tercero_id": tercero_id,
            "drogueria_id": drogueria_id,
            "nombre": body.nombre,
            "apellido": body.apellido,
            "sector_id": body.sector_id,
            "cargo": body.cargo,
            "email": body.email,
            "telefono": body.telefono,
            "celular": body.celular,
            "es_principal": body.es_principal,
            "notas": body.notas,
        },
    )


def listar_contactos(
    client: Client, *, tercero_id: str, drogueria_id: str, activo: bool | None = True
) -> list[dict[str, Any]]:
    return repo.listar_contactos(
        client, tercero_id=tercero_id, drogueria_id=drogueria_id, activo=activo
    )


def obtener_contacto(client: Client, *, contacto_id: str, drogueria_id: str) -> dict[str, Any]:
    contacto = repo.buscar_contacto(client, contacto_id=contacto_id)
    return asegurar_tercero_de_la_drogueria(
        contacto, drogueria_id=drogueria_id, entidad="el contacto"
    )


def actualizar_contacto(
    client: Client, *, contacto_id: str, drogueria_id: str, body: TerceroContactoUpdate
) -> dict[str, Any]:
    contacto = obtener_contacto(client, contacto_id=contacto_id, drogueria_id=drogueria_id)
    campos = body.model_dump(exclude_unset=True)
    if "sector_id" in campos:
        _validar_sector(client, drogueria_id=drogueria_id, sector_id=campos["sector_id"])
    if campos.get("es_principal") is True:
        _democionar_principal_anterior(
            client, tercero_id=contacto["tercero_id"], excluir_id=contacto_id
        )
    return repo.actualizar_contacto(client, contacto_id=contacto_id, campos=campos)


# -- wrappers de endpoint (service_role, mismo criterio que identidad/catalogos) ----


def crear_contacto_para_endpoint(
    *, tercero_id: str, drogueria_id: str, body: TerceroContactoCreate
) -> dict[str, Any]:
    return crear_contacto(
        get_service_client(), tercero_id=tercero_id, drogueria_id=drogueria_id, body=body
    )


def actualizar_contacto_para_endpoint(
    *, contacto_id: str, drogueria_id: str, body: TerceroContactoUpdate
) -> dict[str, Any]:
    return actualizar_contacto(
        get_service_client(), contacto_id=contacto_id, drogueria_id=drogueria_id, body=body
    )
