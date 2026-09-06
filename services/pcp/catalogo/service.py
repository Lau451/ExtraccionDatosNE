"""Servicio de catálogo producto<->proveedor (0011_pcp_modelo.sql M3,
design.md D3, spec `pcp-catalogo-proveedores`).

Arranca vacío (D3, spec "Empty Catalog on Day One"): no hay seeding desde
`precios_proveedor` (eso es un log de cotizaciones, no un catálogo -- un
proveedor que nunca cotizó jamás aparecería ahí). El alta ad-hoc durante la
gestión de un PCP (spec "Ad-Hoc Supplier Addition During a PCP") es una
escritura normal contra esta misma tabla, sin pantalla de mantenimiento
separada.

`solo_activos=True` por default en `listar_proveedores_producto` -- decisión
que tasks.md 6.5 deja explícitamente a criterio de esta implementación,
documentada acá: el índice parcial `(drogueria_id, producto_id) WHERE
activo` (0011_pcp_modelo.sql M3) ya expresa que "proveedores disponibles"
es, por diseño, una consulta sobre asociaciones activas, y una asociación
desactivada no debe reaparecer como objetivo de negociación. Este mismo
default es el que consume `services/pcp/renglones/service.py::listar_proveedores_disponibles_renglon`
(PR6, wiring de esta misma tarea) para la lista "disponible para este
renglón". Un caller que necesite ver también las inactivas (p.ej. una futura
pantalla de mantenimiento del catálogo) puede pasar `solo_activos=False`
explícitamente -- el parámetro no se saca de la firma pública.

Usa `services.pcp.errors.UNIQUE_VIOLATION` (compartido) en vez de una copia
local -- a diferencia de `gestion/service.py::_UNIQUE_VIOLATION` (que es
anterior a la existencia de `services/pcp/errors.py`, PR5), este submódulo
es posterior a ese archivo y es exactamente el motivo por el que existe
(design.md D1, File Changes; ver docstring de `errors.py`).
"""

from typing import Any

from postgrest.exceptions import APIError
from supabase import Client

from services.pcp.catalogo import repository as repo
from services.pcp.catalogo.models import ProductoProveedorCreate
from services.pcp.errors import UNIQUE_VIOLATION
from services.productos import service as productos_service
from services.shared.database import get_service_client
from services.shared.exceptions import ConflictError
from services.terceros.api import obtener_proveedor_con_tercero


def listar_proveedores_producto(
    client: Client, *, producto_id: str, drogueria_id: str, solo_activos: bool = True
) -> list[dict[str, Any]]:
    return repo.listar_asociaciones(
        client, producto_id=producto_id, drogueria_id=drogueria_id, solo_activos=solo_activos
    )


def agregar_proveedor(
    client: Client,
    *,
    drogueria_id: str,
    producto_id: str,
    body: ProductoProveedorCreate,
    usuario_id: str,
) -> dict[str, Any]:
    # Valida que ambos extremos de la asociación existan y sean del tenant
    # antes de escribir -- mismo criterio que
    # services/pcp/renglones/service.py::crear_renglon con item_proceso_id.
    # `productos.service` y `services.terceros.api` son ambos imports
    # permitidos por D1 (design.md). Import directo de la función (no del
    # módulo `services.terceros.api` como alias) -- `tests/pcp/test_dependencias.py`
    # matchea el `ast.ImportFrom.module` exacto contra
    # `_PERMITIDOS_EXACTOS = {"services.terceros.api", ...}`; un
    # `from services.terceros import api` registra "services.terceros" (sin
    # el `.api`), que el guard no reconoce.
    productos_service.obtener_producto(client, producto_id=producto_id, drogueria_id=drogueria_id)
    obtener_proveedor_con_tercero(client, tercero_id=body.proveedor_id, drogueria_id=drogueria_id)

    fila = {
        "drogueria_id": drogueria_id,
        "producto_id": producto_id,
        "proveedor_id": body.proveedor_id,
        "codigo_proveedor": body.codigo_proveedor,
        "preferido": body.preferido,
        "notas": body.notas,
        "created_by": usuario_id,
        "updated_by": usuario_id,
    }
    try:
        return repo.crear_asociacion(client, fila)
    except APIError as exc:
        if exc.code == UNIQUE_VIOLATION:
            raise ConflictError(
                f"El proveedor '{body.proveedor_id}' ya está asociado al producto '{producto_id}'"
            ) from exc
        raise


# -- wrappers de endpoint (service_role, mismo criterio que
# services/pcp/renglones/service.py::*_para_endpoint) -----------------------


def listar_proveedores_producto_para_endpoint(
    *, producto_id: str, drogueria_id: str, solo_activos: bool = True
) -> list[dict[str, Any]]:
    return listar_proveedores_producto(
        get_service_client(),
        producto_id=producto_id,
        drogueria_id=drogueria_id,
        solo_activos=solo_activos,
    )


def agregar_proveedor_para_endpoint(
    *, drogueria_id: str, producto_id: str, body: ProductoProveedorCreate, usuario_id: str
) -> dict[str, Any]:
    return agregar_proveedor(
        get_service_client(),
        drogueria_id=drogueria_id,
        producto_id=producto_id,
        body=body,
        usuario_id=usuario_id,
    )
