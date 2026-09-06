"""Servicio de renglones de PCP (0011_pcp_modelo.sql M2/M4, design.md
D2-D4, spec `pcp-renglones`).

Ancla en `item_proceso_id` -- nunca `presupuesto_items.id` -- porque
`presupuesto_items` se borra e inserta de nuevo en cada regeneración del
presupuesto (`pricing.service.generar_presupuesto`, RN-PRICING-008);
`item_proceso_id` sobrevive esa regeneración sin cambios, ya que
`pcp_renglones` no tiene ninguna FK hacia `presupuesto_items`
(`PcpRenglonCreate` ni siquiera ofrece ese campo -- ver models.py).

D3 (catálogo producto<->proveedor): `listar_proveedores_disponibles_renglon`
lee `services/pcp/catalogo/service.py::listar_proveedores_producto` (PR6,
tasks.md 6.5) -- ya no un placeholder `[]`. Usa el default
`solo_activos=True` de esa función: una asociación `activo=false` no debe
reaparecer como objetivo de negociación (mismo criterio documentado en
`catalogo/service.py`).
"""

from typing import Any

from supabase import Client

from services.pcp.catalogo import service as catalogo_service
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


def listar_resultados_renglon(
    client: Client, *, renglon_id: str, drogueria_id: str
) -> list[dict[str, Any]]:
    """PR11 (tasks.md 11.7) -- expone `pcp_renglon_resultados` (D4) de un
    renglón ya validado por tenant, para que otros submódulos (p.ej.
    `negociacion/service.py::cerrar_pcp`, armando el PDF de resultado de
    cierre) puedan leer "con qué proveedores se negoció y qué resultado
    tuvo cada uno" sin importar `repository` de este módulo (mismo criterio
    ya usado por `negociacion/service.py` reusando `obtener_renglon`)."""
    obtener_renglon(client, renglon_id=renglon_id, drogueria_id=drogueria_id)
    return repo.listar_resultados(client, pcp_renglon_id=renglon_id)


def listar_proveedores_disponibles_renglon(
    client: Client, *, renglon_id: str, drogueria_id: str
) -> list[dict[str, Any]]:
    """PR6 (tasks.md 6.5) -- reemplaza el placeholder `[]` de PR5 por una
    lectura real del catálogo (D3). Firma sin cambios respecto al
    placeholder: eso era un compromiso explícito del docstring anterior y
    del lanzamiento de esta tarea.

    Repite el mismo `SELECT ... WHERE id = renglon_id` que
    `obtener_detalle_renglon` ya ejecutó una vez -- considerado y
    descartado cambiar la firma para recibir el renglón ya resuelto (p.ej.
    un parámetro opcional), porque el costo real es un único lookup extra
    por PK indexado (`buscar_renglon`), y evitarlo hubiera significado
    tocar la firma pública que esta misma tarea pide no tocar. Un renglón
    sin `producto_id` (matching todavía pendiente) no tiene nada que
    catalogar: se corta antes de llamar al catálogo.
    """
    renglon = obtener_renglon(client, renglon_id=renglon_id, drogueria_id=drogueria_id)
    if renglon.get("producto_id") is None:
        return []
    return catalogo_service.listar_proveedores_producto(
        client, producto_id=renglon["producto_id"], drogueria_id=drogueria_id
    )


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
