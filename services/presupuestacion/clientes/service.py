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
from services.presupuestacion.core.exceptions import NotFoundError
from services.terceros import api

# Fase 8 (design.md D5): `services/presupuestacion/clientes/` deja de ser
# dueño de la identidad (nombre/cuit/email/...) y de los contactos del
# cliente -- ambos viven ahora en `services.terceros.api` (terceros + rol
# cliente, terceros_contactos). Este módulo importa EXCLUSIVAMENTE esa
# fachada, nunca un repository/service interno de services/terceros/.

_IDENTIDAD_CAMPOS = {
    "nombre": "razon_social",
    "cuit": "cuit",
    "email": "email",
    "telefono": "telefono",
}
_ROL_CAMPOS = ("tipo", "condicion_pago_id", "forma_pago_id", "activo")


def _combinar(tercero: dict[str, Any], rol: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": rol["id"],
        "drogueria_id": rol["drogueria_id"],
        "codigo_interno": tercero["codigo_interno"],
        "nombre": tercero["razon_social"],
        "cuit": tercero["cuit"],
        "email": tercero["email"],
        "telefono": tercero["telefono"],
        "tipo": rol["tipo"],
        "condicion_pago_id": rol["condicion_pago_id"],
        "forma_pago_id": rol["forma_pago_id"],
        "activo": rol["activo"],
    }


def _combinar_embed(fila: dict[str, Any]) -> dict[str, Any]:
    """`fila` viene de api.listar_clientes_con_tercero/obtener_cliente_con_tercero:
    la fila de `clientes` con `terceros` embebido vía PostgREST."""
    return _combinar(fila["terceros"], fila)


def _combinar_contacto(fila: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": fila["id"],
        "cliente_id": fila["tercero_id"],
        "nombre": fila["nombre"],
        "apellido": fila["apellido"],
        "sector_id": fila["sector_id"],
        "cargo": fila["cargo"],
        "email": fila["email"],
        "telefono": fila["telefono"],
        "celular": fila["celular"],
        "es_principal": fila["es_principal"],
        "notas": fila["notas"],
        "activo": fila["activo"],
    }


def _asegurar_cliente(client: Client, *, cliente_id: str, drogueria_id: str) -> None:
    """Reemplaza al viejo `_validar_cliente_de_la_drogueria` (que devolvía
    `ValidationError` en cross-tenant, deuda D-CLIENTES-004 documentada en
    design.md D3). `api.obtener_cliente_con_tercero` ya aplica el guard
    único D3: no existe y cross-tenant son indistinguibles, ambos
    `NotFoundError`."""
    api.obtener_cliente_con_tercero(client, tercero_id=cliente_id, drogueria_id=drogueria_id)


# ---------------------------------------------------------------------------
# CRUD de clientes (identidad + rol, vía services.terceros.api)
# ---------------------------------------------------------------------------


def crear_cliente(
    client: Client, *, drogueria_id: str, body: ClienteCreate, usuario_id: str
) -> dict[str, Any]:
    tercero = api.crear_tercero(
        client,
        drogueria_id=drogueria_id,
        body=api.TerceroCreate(
            codigo_interno=body.codigo_interno,
            razon_social=body.nombre,
            cuit=body.cuit,
            email=body.email,
            telefono=body.telefono,
        ),
        usuario_id=usuario_id,
    )
    rol = api.asignar_rol_cliente(
        client,
        tercero_id=tercero["id"],
        drogueria_id=drogueria_id,
        body=api.ClienteRolCreate(
            tipo=body.tipo,
            condicion_pago_id=body.condicion_pago_id,
            forma_pago_id=body.forma_pago_id,
        ),
    )
    return _combinar(tercero, rol)


def listar_clientes(
    client: Client, *, drogueria_id: str, activo: bool | None = None
) -> list[dict[str, Any]]:
    filas = api.listar_clientes_con_tercero(client, drogueria_id=drogueria_id, activo=activo)
    return [_combinar_embed(f) for f in filas]


def obtener_cliente(client: Client, *, cliente_id: str, drogueria_id: str) -> dict[str, Any]:
    fila = api.obtener_cliente_con_tercero(client, tercero_id=cliente_id, drogueria_id=drogueria_id)
    return _combinar_embed(fila)


def actualizar_cliente(
    client: Client, *, cliente_id: str, drogueria_id: str, body: ClienteUpdate, usuario_id: str
) -> dict[str, Any]:
    campos = body.model_dump(exclude_unset=True)
    identidad_campos = {v: campos[k] for k, v in _IDENTIDAD_CAMPOS.items() if k in campos}
    rol_campos = {k: campos[k] for k in _ROL_CAMPOS if k in campos}

    if identidad_campos:
        api.actualizar_tercero(
            client,
            tercero_id=cliente_id,
            drogueria_id=drogueria_id,
            body=api.TerceroUpdate(**identidad_campos),
            usuario_id=usuario_id,
        )
    if rol_campos:
        api.actualizar_rol_cliente(
            client,
            tercero_id=cliente_id,
            drogueria_id=drogueria_id,
            body=api.ClienteRolUpdate(**rol_campos),
        )
    return obtener_cliente(client, cliente_id=cliente_id, drogueria_id=drogueria_id)


def eliminar_cliente(client: Client, *, cliente_id: str, drogueria_id: str, usuario_id: str) -> None:
    """D4: ya no hay soft-delete propio de `clientes` -- desactivar el rol
    (`activo=false`) es la baja lógica correcta acá, porque el mismo
    tercero puede seguir activo como proveedor (D1 doble rol). `usuario_id`
    se conserva en la firma por compatibilidad con el router/tests aunque
    `ClienteRolUpdate` no audita quién desactivó el rol."""
    api.actualizar_rol_cliente(
        client,
        tercero_id=cliente_id,
        drogueria_id=drogueria_id,
        body=api.ClienteRolUpdate(activo=False),
    )


# ---------------------------------------------------------------------------
# Contactos (terceros_contactos, vía services.terceros.api)
# ---------------------------------------------------------------------------


def crear_contacto(
    client: Client, *, cliente_id: str, drogueria_id: str, body: ClienteContactoCreate
) -> dict[str, Any]:
    fila = api.crear_contacto(
        client,
        tercero_id=cliente_id,
        drogueria_id=drogueria_id,
        body=api.TerceroContactoCreate(**body.model_dump()),
    )
    return _combinar_contacto(fila)


def listar_contactos(client: Client, *, cliente_id: str, drogueria_id: str) -> list[dict[str, Any]]:
    filas = api.listar_contactos(client, tercero_id=cliente_id, drogueria_id=drogueria_id, activo=None)
    return [_combinar_contacto(f) for f in filas]


def actualizar_contacto(
    client: Client,
    *,
    cliente_id: str,
    contacto_id: str,
    drogueria_id: str,
    body: ClienteContactoUpdate,
) -> dict[str, Any]:
    """`api.actualizar_contacto` solo valida droguería (D3): acá se agrega
    la validación de que el contacto pertenezca a ESTE cliente (no solo a
    la misma droguería), igual que el comportamiento previo a esta
    migración (`test_actualizar_contacto_de_otro_cliente_lanza_not_found`)."""
    contacto = api.obtener_contacto(client, contacto_id=contacto_id, drogueria_id=drogueria_id)
    if contacto["tercero_id"] != cliente_id:
        raise NotFoundError("No se encontró el contacto")
    fila = api.actualizar_contacto(
        client,
        contacto_id=contacto_id,
        drogueria_id=drogueria_id,
        body=api.TerceroContactoUpdate(**body.model_dump(exclude_unset=True)),
    )
    return _combinar_contacto(fila)


# ---------------------------------------------------------------------------
# cliente_formato_documentos / cliente_observaciones (propios de presupuestación)
# ---------------------------------------------------------------------------


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
    _asegurar_cliente(client, cliente_id=cliente_id, drogueria_id=drogueria_id)

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
    _asegurar_cliente(client, cliente_id=cliente_id, drogueria_id=drogueria_id)

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


# ---------------------------------------------------------------------------
# wrappers de endpoint (service_role, mismo criterio que el resto de los módulos)
# ---------------------------------------------------------------------------


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
    *, cliente_id: str, contacto_id: str, drogueria_id: str, body: ClienteContactoUpdate
) -> dict[str, Any]:
    return actualizar_contacto(
        get_service_client(),
        cliente_id=cliente_id,
        contacto_id=contacto_id,
        drogueria_id=drogueria_id,
        body=body,
    )


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
