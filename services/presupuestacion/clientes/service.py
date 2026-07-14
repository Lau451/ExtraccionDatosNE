from typing import Any

from supabase import Client

from services.presupuestacion.clientes import repository as repo
from services.presupuestacion.clientes.models import ClienteFormatoDocumentoUpsert, ClienteObservacionCreate
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
