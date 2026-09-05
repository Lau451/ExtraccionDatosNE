from typing import Any

from postgrest.exceptions import APIError
from supabase import Client

from services.shared.database import get_service_client
from services.shared.exceptions import ConflictError, ValidationError
from services.terceros.catalogos import repository as catalogos_repo
from services.terceros.errors import UNIQUE_VIOLATION, asegurar_tercero_de_la_drogueria
from services.terceros.identidad import repository as repo
from services.terceros.identidad.models import (
    ClienteRolCreate,
    ClienteRolUpdate,
    ProveedorRolCreate,
    ProveedorRolUpdate,
    TerceroCreate,
    TerceroUpdate,
)

# -- terceros -------------------------------------------------------------------


def crear_tercero(
    client: Client, *, drogueria_id: str, body: TerceroCreate, usuario_id: str
) -> dict[str, Any]:
    try:
        return repo.crear_tercero(
            client,
            {
                "drogueria_id": drogueria_id,
                "codigo_interno": body.codigo_interno,
                "razon_social": body.razon_social,
                "nombre_fantasia": body.nombre_fantasia,
                "cuit": body.cuit,
                "email": body.email,
                "telefono": body.telefono,
                "sitio_web": body.sitio_web,
                "notas": body.notas,
                "created_by": usuario_id,
                "updated_by": usuario_id,
            },
        )
    except APIError as exc:
        if exc.code == UNIQUE_VIOLATION:
            raise ConflictError(
                f"Ya existe un tercero con el código interno '{body.codigo_interno}' en esta droguería"
            ) from exc
        raise


def _con_flags_de_rol(fila: dict[str, Any]) -> dict[str, Any]:
    # El embed de la fila trae `clientes`/`proveedores` como arrays (0 o 1 elemento,
    # nunca más porque comparten PK con `terceros`) — se resumen a booleanos para el
    # badge de rol del listado y se sacan del dict, TerceroOut no los declara.
    return {
        **{k: v for k, v in fila.items() if k not in ("clientes", "proveedores")},
        "tiene_rol_cliente": bool(fila.get("clientes")),
        "tiene_rol_proveedor": bool(fila.get("proveedores")),
    }


def listar_terceros(
    client: Client, *, drogueria_id: str, activo: bool | None = True
) -> list[dict[str, Any]]:
    filas = repo.listar_terceros(client, drogueria_id=drogueria_id, activo=activo)
    return [_con_flags_de_rol(fila) for fila in filas]


def obtener_tercero(
    client: Client, *, tercero_id: str, drogueria_id: str, es_superadmin: bool = False
) -> dict[str, Any]:
    tercero = repo.buscar_tercero(client, tercero_id=tercero_id)
    return asegurar_tercero_de_la_drogueria(
        tercero, drogueria_id=drogueria_id, es_superadmin=es_superadmin, entidad="el tercero"
    )


def actualizar_tercero(
    client: Client,
    *,
    tercero_id: str,
    drogueria_id: str,
    body: TerceroUpdate,
    usuario_id: str,
    es_superadmin: bool = False,
) -> dict[str, Any]:
    obtener_tercero(
        client, tercero_id=tercero_id, drogueria_id=drogueria_id, es_superadmin=es_superadmin
    )
    campos = body.model_dump(exclude_unset=True)
    campos["updated_by"] = usuario_id
    try:
        return repo.actualizar_tercero(client, tercero_id=tercero_id, campos=campos)
    except APIError as exc:
        if exc.code == UNIQUE_VIOLATION:
            raise ConflictError(
                f"Ya existe un tercero con el código interno '{campos.get('codigo_interno')}' "
                "en esta droguería"
            ) from exc
        raise


# -- condición / forma de pago habitual (4.10 / 4.11) --------------------------


def _validar_condicion_y_forma_pago(
    client: Client, *, drogueria_id: str, condicion_pago_id: str | None, forma_pago_id: str | None
) -> None:
    if condicion_pago_id is not None:
        condicion = catalogos_repo.obtener_condicion_pago(
            client, condicion_pago_id=condicion_pago_id
        )
        if condicion is None or condicion["drogueria_id"] != drogueria_id:
            raise ValidationError(
                "La condición de pago habitual no pertenece a esta droguería"
            )
    if forma_pago_id is not None:
        forma = catalogos_repo.obtener_forma_pago(client, forma_pago_id=forma_pago_id)
        if forma is None or forma["drogueria_id"] != drogueria_id:
            raise ValidationError("La forma de pago habitual no pertenece a esta droguería")


# -- rol cliente ------------------------------------------------------------------


def asignar_rol_cliente(
    client: Client, *, tercero_id: str, drogueria_id: str, body: ClienteRolCreate
) -> dict[str, Any]:
    obtener_tercero(client, tercero_id=tercero_id, drogueria_id=drogueria_id)
    _validar_condicion_y_forma_pago(
        client,
        drogueria_id=drogueria_id,
        condicion_pago_id=body.condicion_pago_id,
        forma_pago_id=body.forma_pago_id,
    )
    try:
        return repo.crear_rol_cliente(
            client,
            {
                "id": tercero_id,
                "drogueria_id": drogueria_id,
                "tipo": body.tipo,
                "condicion_pago_id": body.condicion_pago_id,
                "forma_pago_id": body.forma_pago_id,
            },
        )
    except APIError as exc:
        if exc.code == UNIQUE_VIOLATION:
            raise ConflictError("Este tercero ya tiene asignado el rol cliente") from exc
        raise


def obtener_rol_cliente(client: Client, *, tercero_id: str, drogueria_id: str) -> dict[str, Any]:
    rol = repo.buscar_rol_cliente(client, tercero_id=tercero_id)
    return asegurar_tercero_de_la_drogueria(
        rol, drogueria_id=drogueria_id, entidad="el rol cliente de este tercero"
    )


def actualizar_rol_cliente(
    client: Client, *, tercero_id: str, drogueria_id: str, body: ClienteRolUpdate
) -> dict[str, Any]:
    obtener_rol_cliente(client, tercero_id=tercero_id, drogueria_id=drogueria_id)
    campos = body.model_dump(exclude_unset=True)
    _validar_condicion_y_forma_pago(
        client,
        drogueria_id=drogueria_id,
        condicion_pago_id=campos.get("condicion_pago_id"),
        forma_pago_id=campos.get("forma_pago_id"),
    )
    return repo.actualizar_rol_cliente(client, tercero_id=tercero_id, campos=campos)


# -- rol proveedor ------------------------------------------------------------------


def asignar_rol_proveedor(
    client: Client, *, tercero_id: str, drogueria_id: str, body: ProveedorRolCreate
) -> dict[str, Any]:
    obtener_tercero(client, tercero_id=tercero_id, drogueria_id=drogueria_id)
    _validar_condicion_y_forma_pago(
        client,
        drogueria_id=drogueria_id,
        condicion_pago_id=body.condicion_pago_id,
        forma_pago_id=body.forma_pago_id,
    )
    try:
        return repo.crear_rol_proveedor(
            client,
            {
                "id": tercero_id,
                "drogueria_id": drogueria_id,
                "tipo": body.tipo,
                "es_competidor": body.es_competidor,
                "es_proveedor_compra": body.es_proveedor_compra,
                "condicion_pago_id": body.condicion_pago_id,
                "forma_pago_id": body.forma_pago_id,
            },
        )
    except APIError as exc:
        if exc.code == UNIQUE_VIOLATION:
            raise ConflictError("Este tercero ya tiene asignado el rol proveedor") from exc
        raise


def obtener_rol_proveedor(client: Client, *, tercero_id: str, drogueria_id: str) -> dict[str, Any]:
    rol = repo.buscar_rol_proveedor(client, tercero_id=tercero_id)
    return asegurar_tercero_de_la_drogueria(
        rol, drogueria_id=drogueria_id, entidad="el rol proveedor de este tercero"
    )


def actualizar_rol_proveedor(
    client: Client, *, tercero_id: str, drogueria_id: str, body: ProveedorRolUpdate
) -> dict[str, Any]:
    obtener_rol_proveedor(client, tercero_id=tercero_id, drogueria_id=drogueria_id)
    campos = body.model_dump(exclude_unset=True)
    _validar_condicion_y_forma_pago(
        client,
        drogueria_id=drogueria_id,
        condicion_pago_id=campos.get("condicion_pago_id"),
        forma_pago_id=campos.get("forma_pago_id"),
    )
    return repo.actualizar_rol_proveedor(client, tercero_id=tercero_id, campos=campos)


# -- rol cliente/proveedor + tercero combinados (Fase 8, consumidos por
# services.terceros.api -> services/presupuestacion/{clientes,catalogo}) --------


def listar_clientes_con_tercero(
    client: Client, *, drogueria_id: str, activo: bool | None = True
) -> list[dict[str, Any]]:
    return repo.listar_clientes_con_tercero(client, drogueria_id=drogueria_id, activo=activo)


def obtener_cliente_con_tercero(client: Client, *, tercero_id: str, drogueria_id: str) -> dict[str, Any]:
    fila = repo.buscar_cliente_con_tercero(client, tercero_id=tercero_id)
    return asegurar_tercero_de_la_drogueria(fila, drogueria_id=drogueria_id, entidad="el cliente")


def listar_proveedores_con_tercero(
    client: Client, *, drogueria_id: str, activo: bool | None = True
) -> list[dict[str, Any]]:
    return repo.listar_proveedores_con_tercero(client, drogueria_id=drogueria_id, activo=activo)


def obtener_proveedor_con_tercero(client: Client, *, tercero_id: str, drogueria_id: str) -> dict[str, Any]:
    fila = repo.buscar_proveedor_con_tercero(client, tercero_id=tercero_id)
    return asegurar_tercero_de_la_drogueria(fila, drogueria_id=drogueria_id, entidad="el proveedor")


# -- wrappers de endpoint (service_role, mismo criterio que clientes/catalogo) ----


def crear_tercero_para_endpoint(
    *, drogueria_id: str, body: TerceroCreate, usuario_id: str
) -> dict[str, Any]:
    return crear_tercero(get_service_client(), drogueria_id=drogueria_id, body=body, usuario_id=usuario_id)


def actualizar_tercero_para_endpoint(
    *, tercero_id: str, drogueria_id: str, body: TerceroUpdate, usuario_id: str, es_superadmin: bool = False
) -> dict[str, Any]:
    return actualizar_tercero(
        get_service_client(),
        tercero_id=tercero_id,
        drogueria_id=drogueria_id,
        body=body,
        usuario_id=usuario_id,
        es_superadmin=es_superadmin,
    )


def asignar_rol_cliente_para_endpoint(
    *, tercero_id: str, drogueria_id: str, body: ClienteRolCreate
) -> dict[str, Any]:
    return asignar_rol_cliente(
        get_service_client(), tercero_id=tercero_id, drogueria_id=drogueria_id, body=body
    )


def actualizar_rol_cliente_para_endpoint(
    *, tercero_id: str, drogueria_id: str, body: ClienteRolUpdate
) -> dict[str, Any]:
    return actualizar_rol_cliente(
        get_service_client(), tercero_id=tercero_id, drogueria_id=drogueria_id, body=body
    )


def asignar_rol_proveedor_para_endpoint(
    *, tercero_id: str, drogueria_id: str, body: ProveedorRolCreate
) -> dict[str, Any]:
    return asignar_rol_proveedor(
        get_service_client(), tercero_id=tercero_id, drogueria_id=drogueria_id, body=body
    )


def actualizar_rol_proveedor_para_endpoint(
    *, tercero_id: str, drogueria_id: str, body: ProveedorRolUpdate
) -> dict[str, Any]:
    return actualizar_rol_proveedor(
        get_service_client(), tercero_id=tercero_id, drogueria_id=drogueria_id, body=body
    )
