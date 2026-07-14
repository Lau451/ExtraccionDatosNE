from typing import Any

from supabase import Client

from services.presupuestacion.clientes import repository as repo
from services.presupuestacion.clientes.models import (
    ClienteContactoCreate,
    ClienteContactoUpdate,
    ClienteCreate,
    ClienteFormatoDocumentoUpsert,
    ClienteObservacionCreate,
    ClienteUpdate,
)
from services.presupuestacion.core.database import get_service_client
from services.presupuestacion.core.exceptions import NotFoundError, ValidationError


def _validar_cliente_de_la_drogueria(
    client: Client, *, cliente_id: str, drogueria_id: str
) -> dict[str, Any]:
    cliente = repo.buscar_cliente(client, cliente_id=cliente_id)
    if cliente is None:
        raise NotFoundError("No se encontró el cliente")
    if cliente["drogueria_id"] != drogueria_id:
        raise ValidationError("El cliente no pertenece a esta droguería")
    return cliente


def upsert_formato_documento(
    client: Client,
    *,
    cliente_id: str,
    drogueria_id: str,
    body: ClienteFormatoDocumentoUpsert,
    usuario_id: str,
) -> dict[str, Any]:
    """UNIQUE(cliente_id, doc_type): si ya hay un formato cargado para este
    cliente+doc_type lo actualiza, si no lo crea."""
    _validar_cliente_de_la_drogueria(client, cliente_id=cliente_id, drogueria_id=drogueria_id)

    campos = {
        "descripcion_estructura": body.descripcion_estructura,
        "instrucciones_prompt": body.instrucciones_prompt,
        "archivo_ejemplo_path": body.archivo_ejemplo_path,
        "archivo_ejemplo_nombre": body.archivo_ejemplo_nombre,
        "activo": body.activo,
        "actualizado_por": usuario_id,
    }

    existente = repo.buscar_formato_documento(
        client, cliente_id=cliente_id, doc_type=body.doc_type
    )
    if existente is not None:
        return repo.actualizar_formato_documento(
            client, formato_id=existente["id"], campos=campos
        )

    return repo.crear_formato_documento(
        client,
        {
            "cliente_id": cliente_id,
            "drogueria_id": drogueria_id,
            "doc_type": body.doc_type,
            **campos,
        },
    )


def listar_formato_documentos(client: Client, *, cliente_id: str) -> list[dict[str, Any]]:
    return repo.listar_formato_documentos(client, cliente_id=cliente_id)


def crear_observacion(
    client: Client,
    *,
    cliente_id: str,
    drogueria_id: str,
    body: ClienteObservacionCreate,
    usuario_id: str,
) -> dict[str, Any]:
    _validar_cliente_de_la_drogueria(client, cliente_id=cliente_id, drogueria_id=drogueria_id)

    return repo.crear_observacion(
        client,
        {
            "cliente_id": cliente_id,
            "drogueria_id": drogueria_id,
            "categoria": body.categoria,
            "observacion": body.observacion,
            "creado_por": usuario_id,
        },
    )


def listar_observaciones(client: Client, *, cliente_id: str) -> list[dict[str, Any]]:
    return repo.listar_observaciones(client, cliente_id=cliente_id)


def crear_cliente(
    client: Client, *, drogueria_id: str, body: ClienteCreate, usuario_id: str
) -> dict[str, Any]:
    return repo.crear_cliente(
        client,
        {
            "drogueria_id": drogueria_id,
            "nombre": body.nombre,
            "tipo": body.tipo,
            "direccion": body.direccion,
            "ciudad": body.ciudad,
            "provincia": body.provincia,
            "codigo_postal": body.codigo_postal,
            "plazo_pago_dias": body.plazo_pago_dias,
            "condiciones_pago": body.condiciones_pago,
            "created_by": usuario_id,
            "updated_by": usuario_id,
        },
    )


def listar_clientes(
    client: Client, *, drogueria_id: str, activo: bool | None = None
) -> list[dict[str, Any]]:
    return repo.listar_clientes(client, drogueria_id=drogueria_id, activo=activo)


def obtener_cliente(client: Client, *, cliente_id: str, drogueria_id: str) -> dict[str, Any]:
    cliente = repo.obtener_cliente(client, cliente_id=cliente_id)
    if cliente is None or cliente["drogueria_id"] != drogueria_id:
        raise NotFoundError("No se encontró el cliente")
    return cliente


def actualizar_cliente(
    client: Client, *, cliente_id: str, drogueria_id: str, body: ClienteUpdate, usuario_id: str
) -> dict[str, Any]:
    obtener_cliente(client, cliente_id=cliente_id, drogueria_id=drogueria_id)
    campos = {k: v for k, v in body.model_dump(exclude_unset=True).items()}
    campos["updated_by"] = usuario_id
    return repo.actualizar_cliente(client, cliente_id=cliente_id, campos=campos)


def eliminar_cliente(client: Client, *, cliente_id: str, drogueria_id: str, usuario_id: str) -> None:
    obtener_cliente(client, cliente_id=cliente_id, drogueria_id=drogueria_id)
    repo.soft_delete_cliente(client, cliente_id=cliente_id, usuario_id=usuario_id)


def crear_contacto(
    client: Client, *, cliente_id: str, drogueria_id: str, body: ClienteContactoCreate
) -> dict[str, Any]:
    _validar_cliente_de_la_drogueria(client, cliente_id=cliente_id, drogueria_id=drogueria_id)
    return repo.crear_contacto(
        client,
        {
            "cliente_id": cliente_id,
            "drogueria_id": drogueria_id,
            "nombre": body.nombre,
            "cargo": body.cargo,
            "email": body.email,
            "telefono": body.telefono,
            "es_principal": body.es_principal,
            "notas": body.notas,
        },
    )


def listar_contactos(client: Client, *, cliente_id: str) -> list[dict[str, Any]]:
    return repo.listar_contactos(client, cliente_id=cliente_id)


def actualizar_contacto(
    client: Client, *, cliente_id: str, contacto_id: str, body: ClienteContactoUpdate
) -> dict[str, Any]:
    contacto = repo.buscar_contacto(client, contacto_id=contacto_id)
    if contacto is None or contacto["cliente_id"] != cliente_id:
        raise NotFoundError("No se encontró el contacto")
    campos = body.model_dump(exclude_unset=True)
    return repo.actualizar_contacto(client, contacto_id=contacto_id, campos=campos)


def crear_cliente_para_endpoint(*, drogueria_id: str, body: ClienteCreate, usuario_id: str) -> dict[str, Any]:
    return crear_cliente(get_service_client(), drogueria_id=drogueria_id, body=body, usuario_id=usuario_id)


def actualizar_cliente_para_endpoint(
    *, cliente_id: str, drogueria_id: str, body: ClienteUpdate, usuario_id: str
) -> dict[str, Any]:
    return actualizar_cliente(
        get_service_client(), cliente_id=cliente_id, drogueria_id=drogueria_id, body=body, usuario_id=usuario_id
    )


def eliminar_cliente_para_endpoint(*, cliente_id: str, drogueria_id: str, usuario_id: str) -> None:
    eliminar_cliente(get_service_client(), cliente_id=cliente_id, drogueria_id=drogueria_id, usuario_id=usuario_id)


def crear_contacto_para_endpoint(
    *, cliente_id: str, drogueria_id: str, body: ClienteContactoCreate
) -> dict[str, Any]:
    return crear_contacto(get_service_client(), cliente_id=cliente_id, drogueria_id=drogueria_id, body=body)


def actualizar_contacto_para_endpoint(
    *, cliente_id: str, contacto_id: str, body: ClienteContactoUpdate
) -> dict[str, Any]:
    return actualizar_contacto(get_service_client(), cliente_id=cliente_id, contacto_id=contacto_id, body=body)


def upsert_formato_documento_para_endpoint(
    *, cliente_id: str, drogueria_id: str, body: ClienteFormatoDocumentoUpsert, usuario_id: str
) -> dict[str, Any]:
    """Corre con service_role: la RLS de cliente_formato_documentos no incluye
    'superadmin' en INSERT/UPDATE — mismo criterio que el resto de los módulos."""
    return upsert_formato_documento(
        get_service_client(),
        cliente_id=cliente_id,
        drogueria_id=drogueria_id,
        body=body,
        usuario_id=usuario_id,
    )


def crear_observacion_para_endpoint(
    *, cliente_id: str, drogueria_id: str, body: ClienteObservacionCreate, usuario_id: str
) -> dict[str, Any]:
    return crear_observacion(
        get_service_client(),
        cliente_id=cliente_id,
        drogueria_id=drogueria_id,
        body=body,
        usuario_id=usuario_id,
    )
