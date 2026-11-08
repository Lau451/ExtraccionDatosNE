"""Import legado de presupuestos (Progress; engram #647, agreed design
2026-09-24, odd/tasks/presupuestos-legacy-import.md T1).

Movido desde `services/pcp/imports/service.py` (odd/tasks/
procesos-comerciales-dueno.md S1): `comercial` es el único dueño de
`procesos_comerciales`, `items_proceso`, `presupuestos`, `presupuesto_items` y
`presupuesto_legacy_map`. El proceso se crea con
`procesos_comerciales.service.crear_proceso_comercial` (S2): queda con
`created_by` = el usuario que importa y su evento de auditoría 'creacion', como
cualquier proceso.

Import order es mandatorio (design agreed): presupuesto PRIMERO, PCP DESPUÉS
(el import de PCP, en `services/pcp/imports`, busca las líneas ya existentes
vía `presupuesto_legacy_map`, nunca las crea).
"""

import logging
from collections import OrderedDict
from typing import Any

from supabase import Client

from services.presupuestacion.core.database import get_service_client
from services.presupuestacion.core.exceptions import NotFoundError
from services.presupuestacion.presupuestos import importacion_legacy_repository as repo
from services.presupuestacion.presupuestos.importacion_legacy_models import (
    FilaImportPresupuestoLegacy,
)
from services.presupuestacion.procesos_comerciales.models import ProcesoComercialCreate
from services.presupuestacion.procesos_comerciales.service import (
    crear_proceso_comercial,
    deshacer_creacion_proceso_comercial,
)

logger = logging.getLogger(__name__)

# "1" = cotización directa / "2" = licitación; ausente -> default `licitacion`
# (decisión confirmada por el usuario, no `cotizacion`).
_CLASE_POR_PROCESO_COMERCIAL: dict[str, str] = {"1": "cotizacion", "2": "licitacion"}
_CLASE_DEFAULT = "licitacion"


def _resolver_cliente_id(client: Client, *, drogueria_id: str, codigo_cliente: str) -> str:
    """`cliente_id` se resuelve por `terceros.codigo_interno` (`UNIQUE
    (drogueria_id, codigo_interno)`, 0008_terceros_modelo.sql), sin pasar por
    `terceros_legacy_map`. El tercero encontrado debe tener además una fila de
    rol `clientes` (`procesos_comerciales.cliente_id` referencia `clientes(id)`,
    no `terceros(id)` directamente)."""
    tercero = repo.buscar_tercero_por_codigo(
        client, drogueria_id=drogueria_id, codigo_interno=codigo_cliente
    )
    if tercero is None:
        raise NotFoundError(
            f"No se encontró ningún tercero con código interno '{codigo_cliente}' en esta droguería"
        )
    cliente = repo.buscar_rol_cliente(client, tercero_id=tercero["id"])
    if cliente is None:
        raise NotFoundError(
            f"El tercero con código interno '{codigo_cliente}' no tiene rol de cliente"
        )
    return cliente["id"]


def _resolver_producto_id(
    client: Client, *, drogueria_id: str, codigo_producto: str | None
) -> str | None:
    """`codigo_producto` es opcional y puede no matchear ningún
    `productos.codigo_interno` de la droguería -- en ambos casos resuelve a
    `None` sin bloquear la fila (agreed design: "NULL if missing or not
    found")."""
    if not codigo_producto:
        return None
    producto = repo.buscar_producto_por_codigo(
        client, drogueria_id=drogueria_id, codigo_interno=codigo_producto
    )
    return producto["id"] if producto else None


def _crear_presupuesto_legacy(
    client: Client,
    *,
    drogueria_id: str,
    header: FilaImportPresupuestoLegacy,
    filas_grupo: list[FilaImportPresupuestoLegacy],
    usuario_id: str,
) -> tuple[dict[str, Any], int]:
    """Primer import de un `numero_presupuesto`: crea `procesos_comerciales`
    (con `crear_proceso_comercial`, a nombre de `usuario_id`) + `presupuestos`,
    y dentro de un bloque compensado `presupuesto_legacy_map` (el ancla de
    idempotencia) + `items_proceso`/`presupuesto_items` por renglón.

    Compensación manual (no hay transacción real vía PostgREST -- mismo
    criterio que `services/presupuestacion/extraccion/service.py::
    _materializar_orden_compra`): ante cualquier excepción tras crear
    `presupuestos`, se borra esa fila (cascadea `presupuesto_items` +
    `presupuesto_legacy_map`) y luego el proceso con
    `deshacer_creacion_proceso_comercial` (borra su evento de creación y
    cascadea `items_proceso`, ya liberado de la referencia RESTRICT de
    `presupuesto_items`) -- ese orden es obligatorio. Un reintento posterior con
    el mismo `numero_presupuesto` no encuentra ningún huérfano y arranca de
    cero."""
    cliente_id = _resolver_cliente_id(
        client, drogueria_id=drogueria_id, codigo_cliente=header.codigo_cliente
    )
    clase = _CLASE_POR_PROCESO_COMERCIAL.get(header.proceso_comercial or "", _CLASE_DEFAULT)

    proceso = crear_proceso_comercial(
        client,
        drogueria_id=drogueria_id,
        body=ProcesoComercialCreate(
            cliente_id=cliente_id,
            clase=clase,
            nombre=(
                f"Import legado — {header.razon_social_cliente} "
                f"(presupuesto {header.numero_presupuesto})"
            ),
        ),
        usuario_id=usuario_id,
    )

    renglones_sin_precio = sum(1 for fila in filas_grupo if fila.precio_producto is None)
    fila_presupuesto: dict[str, Any] = {
        "proceso_comercial_id": proceso["id"],
        "drogueria_id": drogueria_id,
        "estado": "generado",
        "monto_total": str(header.importe_total) if header.importe_total is not None else None,
        "cantidad_items": len(filas_grupo),
        "items_sin_precio": renglones_sin_precio,
    }
    if header.fecha_generacion is not None:
        fila_presupuesto["generado_at"] = header.fecha_generacion

    presupuesto: dict[str, Any] | None = None
    try:
        presupuesto = repo.crear_presupuesto(client, fila_presupuesto)

        # El ancla de idempotencia: se guardan las filas CRUDAS del grupo
        # completo (no solo la cabecera, a diferencia de pcp_legacy_map) para
        # trazabilidad archival del presupuesto entero (agreed design).
        repo.crear_mapa_legacy_presupuesto(
            client,
            {
                "presupuesto_id": presupuesto["id"],
                "drogueria_id": drogueria_id,
                "codigo_legacy": header.numero_presupuesto,
                "datos_legacy": [fila.model_dump(mode="json") for fila in filas_grupo],
            },
        )

        renglones_sin_producto = 0
        for fila in filas_grupo:
            producto_id = _resolver_producto_id(
                client, drogueria_id=drogueria_id, codigo_producto=fila.codigo_producto
            )
            if producto_id is None:
                renglones_sin_producto += 1

            item = repo.crear_item_proceso(
                client,
                {
                    "proceso_comercial_id": proceso["id"],
                    "drogueria_id": drogueria_id,
                    "numero_renglon": fila.renglon,
                    "descripcion": fila.descripcion_producto,
                    "cantidad": str(fila.cantidad_producto),
                    "producto_id": producto_id,
                },
            )
            repo.crear_presupuesto_item(
                client,
                {
                    "presupuesto_id": presupuesto["id"],
                    "drogueria_id": drogueria_id,
                    "item_proceso_id": item["id"],
                    "producto_id": producto_id,
                    "precio_unitario": (
                        str(fila.precio_producto) if fila.precio_producto is not None else None
                    ),
                    "cantidad_ofertada": str(fila.cantidad_producto),
                    # Decisión confirmada por el usuario (2026-09-24): 'manual'
                    # siempre, incluso sin precio -- no 'sin_precio' pese a que
                    # ck_pi_metodo lo permite.
                    "metodo_precio": "manual",
                },
            )
    except Exception:
        # T1b(d): cada paso de la compensación queda guardado por separado --
        # si `borrar_presupuesto` también falla (p.ej. un problema de red
        # aparte del error que disparó esta compensación), NO debe pisar el
        # error ORIGINAL que se re-lanza al final, y el borrado del proceso
        # debe seguir corriendo igual (mismo criterio para su propio fallo).
        if presupuesto is not None:
            try:
                repo.borrar_presupuesto(client, presupuesto_id=presupuesto["id"])
            except Exception:
                logger.exception(
                    "Compensación de importar_presupuesto_legacy falló al "
                    "borrar presupuesto %s (numero_presupuesto=%s)",
                    presupuesto["id"],
                    header.numero_presupuesto,
                )
        try:
            deshacer_creacion_proceso_comercial(client, proceso_comercial_id=proceso["id"])
        except Exception:
            logger.exception(
                "Compensación de importar_presupuesto_legacy falló al "
                "borrar proceso_comercial %s (numero_presupuesto=%s)",
                proceso["id"],
                header.numero_presupuesto,
            )
        raise

    return presupuesto, renglones_sin_producto


def importar_presupuesto_legacy(
    client: Client, *, drogueria_id: str, filas: list[FilaImportPresupuestoLegacy], usuario_id: str
) -> list[dict[str, Any]]:
    """Agrupa las filas planas por `numero_presupuesto` (los campos de
    cabecera se repiten por fila, mismo criterio que el import de PCP).
    Devuelve una fila de resultado por cada `numero_presupuesto` distinto en
    el lote, con `accion` = "creado" | "existente" (agreed design: un
    reimport nunca duplica nada -- a diferencia del import de PCP, que sí
    reprocesa renglones en cada corrida). `usuario_id` queda como
    `created_by` del proceso: el usuario logueado en la carga manual, el usuario
    del sistema en la recepción automática."""
    por_presupuesto: "OrderedDict[str, list[FilaImportPresupuestoLegacy]]" = OrderedDict()
    for fila in filas:
        por_presupuesto.setdefault(fila.numero_presupuesto, []).append(fila)

    resultados: list[dict[str, Any]] = []
    for numero_presupuesto, filas_grupo in por_presupuesto.items():
        header = filas_grupo[0]
        mapa = repo.buscar_mapa_legacy_presupuesto(
            client, drogueria_id=drogueria_id, codigo_legacy=numero_presupuesto
        )

        if mapa is None:
            presupuesto, renglones_sin_producto = _crear_presupuesto_legacy(
                client,
                drogueria_id=drogueria_id,
                header=header,
                filas_grupo=filas_grupo,
                usuario_id=usuario_id,
            )
            resultados.append(
                {
                    "codigo_legacy": numero_presupuesto,
                    "presupuesto_id": presupuesto["id"],
                    "accion": "creado",
                    "renglones_procesados": len(filas_grupo),
                    "renglones_sin_producto": renglones_sin_producto,
                }
            )
        else:
            # Reimport: nunca vuelve a tocar procesos_comerciales/presupuestos/
            # items_proceso/presupuesto_items (agreed design, "reimport never
            # duplicates") -- se informan los conteos ya persistidos.
            presupuesto = repo.buscar_presupuesto(client, presupuesto_id=mapa["presupuesto_id"])
            if presupuesto is None:
                raise NotFoundError(
                    f"El presupuesto mapeado para '{numero_presupuesto}' ya no existe"
                )
            # T1b(a): misma métrica que el primer import (renglones sin
            # producto_id resuelto) -- `items_sin_precio` es un campo
            # distinto (renglones sin precio) que solo coincidía por
            # casualidad cuando ninguna fila traía precio ni código.
            renglones_sin_producto = repo.contar_presupuesto_items_sin_producto(
                client, presupuesto_id=presupuesto["id"]
            )
            resultados.append(
                {
                    "codigo_legacy": numero_presupuesto,
                    "presupuesto_id": presupuesto["id"],
                    "accion": "existente",
                    "renglones_procesados": presupuesto["cantidad_items"],
                    "renglones_sin_producto": renglones_sin_producto,
                }
            )

    return resultados


def importar_presupuesto_legacy_para_endpoint(
    *, drogueria_id: str, filas: list[FilaImportPresupuestoLegacy], usuario_id: str
) -> list[dict[str, Any]]:
    return importar_presupuesto_legacy(
        get_service_client(), drogueria_id=drogueria_id, filas=filas, usuario_id=usuario_id
    )
