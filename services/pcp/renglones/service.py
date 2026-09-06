"""Servicio de renglones de PCP (0011_pcp_modelo.sql M2/M4, design.md
D2-D4, spec `pcp-renglones`).

Ancla en `item_proceso_id` -- nunca `presupuesto_items.id` -- porque
`presupuesto_items` se borra e inserta de nuevo en cada regeneración del
presupuesto (`pricing.service.generar_presupuesto`, RN-PRICING-008);
`item_proceso_id` sobrevive esa regeneración sin cambios, ya que
`pcp_renglones` no tiene ninguna FK hacia `presupuesto_items`
(`PcpRenglonCreate` ni siquiera ofrece ese campo -- ver models.py).

D3 (catálogo producto<->proveedor) todavía no existe como servicio -- llega
en PR6 (`services/pcp/catalogo/`, tasks.md 6.1-6.5). Aunque la tabla
`producto_proveedores` ya existe desde 0011 (M3), `listar_proveedores_disponibles_renglon`
degrada deliberadamente a `[]` en este PR en vez de leerla directamente: la
tarea 6.5 es explícitamente la que "wire[a] into
services/pcp/renglones/service.py for the 'available suppliers' list" --
adelantar esa lectura ahora anticiparía decisiones de PR6 (p.ej. filtros por
`activo`/`preferido`) que todavía no están tomadas, y crearía una dependencia
implícita sobre una forma de esa función que PR6 podría necesitar cambiar.
"""

from typing import Any

from supabase import Client

from services.pcp.gestion import service as gestion_service
from services.pcp.renglones import repository as repo
from services.pcp.renglones.models import PcpRenglonCreate
from services.productos import service as productos_service
from services.shared.database import get_service_client
from services.shared.exceptions import NotFoundError, ValidationError


def crear_renglon(
    client: Client, *, drogueria_id: str, pcp_id: str, body: PcpRenglonCreate, usuario_id: str
) -> dict[str, Any]:
    # 5.2 -- valida que el pcp exista y sea del tenant (reusa gestion, mismo
    # criterio que gestion/service.py reusando historial: ambos son
    # submódulos internos de services/pcp/, fuera del alcance del guard D1).
    pcp = gestion_service.obtener_pcp(client, pcp_id=pcp_id, drogueria_id=drogueria_id)

    item = repo.buscar_item_proceso(client, item_proceso_id=body.item_proceso_id)
    if item is None or item["drogueria_id"] != drogueria_id:
        raise NotFoundError(f"No se encontró el ítem de proceso '{body.item_proceso_id}'")

    fila = {
        "drogueria_id": drogueria_id,
        "pcp_id": pcp["id"],
        "item_proceso_id": item["id"],
        "producto_id": item.get("producto_id"),
        "cantidad": item.get("cantidad"),
        "origen": body.origen,
        "regla_pcp_id": body.regla_pcp_id,
        "created_by": usuario_id,
        "updated_by": usuario_id,
    }
    return repo.crear_renglon(client, fila)


def obtener_renglon(client: Client, *, renglon_id: str, drogueria_id: str) -> dict[str, Any]:
    fila = repo.buscar_renglon(client, renglon_id=renglon_id)
    if fila is None or fila["drogueria_id"] != drogueria_id:
        raise NotFoundError(f"No se encontró el renglón '{renglon_id}'")
    return fila


def listar_renglones(client: Client, *, pcp_id: str, drogueria_id: str) -> list[dict[str, Any]]:
    return repo.listar_renglones(client, pcp_id=pcp_id, drogueria_id=drogueria_id)


def listar_proveedores_disponibles_renglon(
    client: Client, *, renglon_id: str, drogueria_id: str
) -> list[dict[str, Any]]:
    """Placeholder deliberado -- ver docstring del módulo. PR6 (tasks.md 6.5)
    reemplaza esta implementación para leer `producto_proveedores` a través
    de `services/pcp/catalogo/`, sin cambiar la firma."""
    obtener_renglon(client, renglon_id=renglon_id, drogueria_id=drogueria_id)
    return []


def obtener_detalle_renglon(client: Client, *, renglon_id: str, drogueria_id: str) -> dict[str, Any]:
    renglon = obtener_renglon(client, renglon_id=renglon_id, drogueria_id=drogueria_id)
    producto = None
    if renglon.get("producto_id"):
        producto = productos_service.obtener_producto(
            client, producto_id=renglon["producto_id"], drogueria_id=drogueria_id
        )
    proveedores = listar_proveedores_disponibles_renglon(
        client, renglon_id=renglon_id, drogueria_id=drogueria_id
    )
    return {"renglon": renglon, "producto": producto, "proveedores_catalogados": proveedores}


def seleccionar_proveedores(
    client: Client, *, renglon_id: str, drogueria_id: str, proveedor_ids: list[str]
) -> list[dict[str, Any]]:
    """5.4 -- selecciona uno, varios, o todos los proveedores disponibles
    como objetivo de negociación para un renglón.

    No se crea una tabla nueva de "selección": cada proveedor elegido es una
    fila `pcp_renglon_resultados` (D4, ya viva desde PR1) con
    `resultado='sin_respuesta'` -- el estado inicial/pendiente que
    `ck_ppr_resultado_val` ya admite. PR7 (`pcp-negociacion`) actualiza esa
    misma fila a `precio_obtenido`/`no_cotiza` sin necesitar ningún cambio de
    esquema, exactamente el "shape que le permite a PR7 adjuntar resultados
    por proveedor seleccionado sin un cambio de esquema" que pide la tarea
    5.4. "Seleccionar todos los disponibles" no es lógica especial de este
    servicio: el caller resuelve la lista completa de ids (hoy, manualmente;
    desde PR6, vía el catálogo) y la pasa igual que una selección de uno
    solo -- `seleccionar_proveedores` no distingue los dos casos.
    """
    if not proveedor_ids:
        raise ValidationError("Debe seleccionarse al menos un proveedor")

    renglon = obtener_renglon(client, renglon_id=renglon_id, drogueria_id=drogueria_id)
    filas = [
        {
            "drogueria_id": drogueria_id,
            "pcp_renglon_id": renglon["id"],
            "proveedor_id": proveedor_id,
            "resultado": "sin_respuesta",
        }
        for proveedor_id in proveedor_ids
    ]
    return repo.crear_resultados_seleccion(client, filas)


# -- wrappers de endpoint (service_role, mismo criterio que
# services/pcp/gestion/service.py) -----------------------------------------


def crear_renglon_para_endpoint(
    *, drogueria_id: str, pcp_id: str, body: PcpRenglonCreate, usuario_id: str
) -> dict[str, Any]:
    return crear_renglon(
        get_service_client(), drogueria_id=drogueria_id, pcp_id=pcp_id, body=body, usuario_id=usuario_id
    )


def listar_renglones_para_endpoint(*, pcp_id: str, drogueria_id: str) -> list[dict[str, Any]]:
    return listar_renglones(get_service_client(), pcp_id=pcp_id, drogueria_id=drogueria_id)


def obtener_detalle_renglon_para_endpoint(*, renglon_id: str, drogueria_id: str) -> dict[str, Any]:
    return obtener_detalle_renglon(get_service_client(), renglon_id=renglon_id, drogueria_id=drogueria_id)


def seleccionar_proveedores_para_endpoint(
    *, renglon_id: str, drogueria_id: str, proveedor_ids: list[str]
) -> list[dict[str, Any]]:
    return seleccionar_proveedores(
        get_service_client(),
        renglon_id=renglon_id,
        drogueria_id=drogueria_id,
        proveedor_ids=proveedor_ids,
    )
