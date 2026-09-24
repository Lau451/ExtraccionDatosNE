"""Servicio de import legado de PCP (0012_pcp_extras.sql M3, design.md D8,
spec `pcp-legacy-import`).

**Resolución del bloqueo original del design** (D8): el primer borrador
asumía que `items_proceso` ya existía y que el import solo necesitaba
*matchear* `pcp_renglones.item_proceso_id` contra filas preexistentes. Eso no
vale para este dataset -- el sistema legado no tiene presupuestador, así que
`procesos_comerciales`/`presupuestos`/`items_proceso` no existen todavía para
estos PCP. `pcp.presupuesto_id`/`proceso_comercial_id` siguen siendo FKs
`NOT NULL` (el usuario rechazó relajarlas), así que este servicio genera
placeholders la primera vez que ve un "número de PCP", y los reusa tal cual
en cada reimport -- toda la idempotencia vive en el par `pcp`/`pcp_legacy_map`
(D8, sin tabla nueva; una `presupuestos_legacy_map` fue propuesta y
rechazada por el usuario como sobre-ingeniería).

**Deviation documentada**: D8 dibuja un RPC `upsert_pcp_legacy` (ya creado en
`0012_pcp_extras.sql` M8), pero su propio texto marca que ese RPC predata la
expansión de alcance a find-or-create y "necesitará revisarse en el propio
`sdd-design` de PR8". Ninguna tarea de esta fase (tasks.md 8.1-8.8) pide una
migración nueva ni tocar la 0012 -- así que este run implementa el flujo
find-or-create acá, a nivel de servicio/Python, igual que el resto de
`services/pcp/**` (ningún otro submódulo -- gestion/renglones/catalogo/
negociacion -- enruta una escritura por un RPC; todos hacen INSERT/UPDATE
directos vía su propio `repository.py`). El RPC queda sin uso, documentado
acá en vez de borrado silenciosamente (una migración `DROP FUNCTION` está
fuera del alcance de esta fase, que no incluye ninguna migración).
"""

from collections import OrderedDict
from typing import Any

from supabase import Client

from services.pcp.historial import service as historial_service
from services.pcp.imports import repository as repo
from services.pcp.imports.models import FilaImportPcpLegacy, FilaImportPresupuestoLegacy
from services.shared.database import get_service_client
from services.shared.exceptions import NotFoundError

# D8: "1" = cotización directa / "2" = licitación; ausente -> default
# `licitacion` (decisión confirmada por el usuario, no `cotizacion`).
_CLASE_POR_PROCESO_COMERCIAL: dict[str, str] = {"1": "cotizacion", "2": "licitacion"}
_CLASE_DEFAULT = "licitacion"


def _resolver_cliente_id(client: Client, *, drogueria_id: str, codigo_cliente: str) -> str:
    """D8: "cliente_id resolves via the already-existing terceros.codigo_interno
    legacy code path" -- `terceros.codigo_interno` ya es `UNIQUE
    (drogueria_id, codigo_interno)` (0008_terceros_modelo.sql), sin
    necesidad de pasar por `terceros_legacy_map`. El tercero encontrado debe
    tener además una fila de rol `clientes` (`procesos_comerciales.cliente_id`
    referencia `clientes(id)`, no `terceros(id)` directamente)."""
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


def _crear_pcp_placeholder(
    client: Client,
    *,
    drogueria_id: str,
    header: FilaImportPcpLegacy,
    cantidad_renglones: int,
    usuario_id: str,
) -> dict[str, Any]:
    """Primer import de un "número de PCP" (D8): genera los placeholders de
    `procesos_comerciales`/`presupuestos` una única vez -- un reimport nunca
    vuelve a pasar por acá (ver `importar_pcp_legacy`)."""
    cliente_id = _resolver_cliente_id(
        client, drogueria_id=drogueria_id, codigo_cliente=header.codigo_cliente
    )
    clase = _CLASE_POR_PROCESO_COMERCIAL.get(header.proceso_comercial or "", _CLASE_DEFAULT)

    proceso = repo.crear_proceso_comercial(
        client,
        {
            "drogueria_id": drogueria_id,
            "cliente_id": cliente_id,
            "clase": clase,
            # El export legado no trae nombre de proceso -- se sintetiza
            # (D8: "nombre (NOT NULL) es sintetizado").
            "nombre": f"Import legado — {header.razon_social_cliente} (PCP {header.numero_pcp})",
        },
    )
    presupuesto = repo.crear_presupuesto(
        client,
        {
            "proceso_comercial_id": proceso["id"],
            "drogueria_id": drogueria_id,
            "monto_total": str(header.importe_total) if header.importe_total is not None else None,
            "cantidad_items": cantidad_renglones,
        },
    )
    return repo.crear_pcp(
        client,
        {
            "drogueria_id": drogueria_id,
            "presupuesto_id": presupuesto["id"],
            "proceso_comercial_id": proceso["id"],
            "fecha_entrega_solicitada": header.fecha_respuesta_esperada,
            "origen": "import_legado",
            "created_by": usuario_id,
            "updated_by": usuario_id,
        },
    )


def _importar_renglon(
    client: Client,
    *,
    drogueria_id: str,
    pcp: dict[str, Any],
    fila: FilaImportPcpLegacy,
    usuario_id: str,
) -> dict[str, Any]:
    """8.2/8.4/8.6: `items_proceso` find-or-create por
    `(proceso_comercial_id, numero_renglon)`; `pcp_renglones` find-or-create
    por `(pcp_id, item_proceso_id)` -- un reimport nunca duplica ninguno de
    los dos, y todo renglón creado por este camino queda `origen =
    'import_legado'` (8.6, nunca `'manual'`/`'regla'`)."""
    item = repo.buscar_item_proceso_por_renglon(
        client, proceso_comercial_id=pcp["proceso_comercial_id"], numero_renglon=fila.renglon
    )
    if item is None:
        item = repo.crear_item_proceso(
            client,
            {
                "proceso_comercial_id": pcp["proceso_comercial_id"],
                "drogueria_id": drogueria_id,
                "numero_renglon": fila.renglon,
                "descripcion": fila.descripcion_producto,
                "cantidad": str(fila.cantidad_producto),
            },
        )

    renglon_existente = repo.buscar_renglon_por_item(
        client, pcp_id=pcp["id"], item_proceso_id=item["id"]
    )
    if renglon_existente is not None:
        return renglon_existente

    return repo.crear_renglon(
        client,
        {
            "drogueria_id": drogueria_id,
            "pcp_id": pcp["id"],
            "item_proceso_id": item["id"],
            "producto_id": item.get("producto_id"),
            "cantidad": item.get("cantidad"),
            "precio_referencia": (
                str(fila.precio_producto) if fila.precio_producto is not None else None
            ),
            "origen": "import_legado",
            "created_by": usuario_id,
            "updated_by": usuario_id,
        },
    )


def importar_pcp_legacy(
    client: Client, *, drogueria_id: str, filas: list[FilaImportPcpLegacy], usuario_id: str
) -> list[dict[str, Any]]:
    """8.1-8.8: agrupa las filas planas por "número de PCP" (D8: los campos
    de cabecera se repiten por fila; el header-level resolution se hace una
    sola vez por grupo). Devuelve una fila de resultado por cada "número de
    PCP" distinto en el lote, con `accion` = "creado" | "actualizado"."""
    por_pcp: "OrderedDict[str, list[FilaImportPcpLegacy]]" = OrderedDict()
    for fila in filas:
        por_pcp.setdefault(fila.numero_pcp, []).append(fila)

    resultados: list[dict[str, Any]] = []
    for numero_pcp, filas_pcp in por_pcp.items():
        header = filas_pcp[0]
        mapa = repo.buscar_mapa_legacy(client, drogueria_id=drogueria_id, codigo_legacy=numero_pcp)

        if mapa is None:
            # 8.1/8.2/8.5: primer import -- crea el pcp (con sus placeholders)
            # y la fila de idempotencia en pcp_legacy_map.
            pcp = _crear_pcp_placeholder(
                client,
                drogueria_id=drogueria_id,
                header=header,
                cantidad_renglones=len(filas_pcp),
                usuario_id=usuario_id,
            )
            repo.crear_mapa_legacy(
                client,
                {
                    "pcp_id": pcp["id"],
                    "drogueria_id": drogueria_id,
                    "codigo_legacy": numero_pcp,
                    # "número de presupuesto" es archival-only (D8): entra
                    # acá, nunca como clave de lookup/resolución.
                    "datos_legacy": header.model_dump(mode="json"),
                },
            )
            accion = "creado"
        else:
            # 8.3/8.7/8.7a: reimport -- reusa el pcp ya existente (nativo o
            # de un import anterior) tal cual; procesos_comerciales/
            # presupuestos NUNCA se tocan de nuevo.
            pcp = repo.buscar_pcp(client, pcp_id=mapa["pcp_id"])
            if pcp is None:
                raise NotFoundError(f"El PCP mapeado para '{numero_pcp}' ya no existe")
            accion = "actualizado"

        renglones = [
            _importar_renglon(
                client, drogueria_id=drogueria_id, pcp=pcp, fila=fila, usuario_id=usuario_id
            )
            for fila in filas_pcp
        ]

        # 8.8: evento de historial 'importada' por cada corrida de import
        # sobre este PCP (append-only, D6) -- nunca un campo de costo en el
        # payload (D2).
        historial_service.agregar_evento(
            client,
            drogueria_id=drogueria_id,
            pcp_id=pcp["id"],
            tipo_evento="importada",
            payload={"codigo_legacy": numero_pcp, "renglones_procesados": len(renglones)},
            usuario_id=usuario_id,
            origen="import_legado",
        )

        resultados.append(
            {
                "codigo_legacy": numero_pcp,
                "pcp_id": pcp["id"],
                "accion": accion,
                "renglones_procesados": len(renglones),
            }
        )

    return resultados


def importar_pcp_legacy_para_endpoint(
    *, drogueria_id: str, filas: list[FilaImportPcpLegacy], usuario_id: str
) -> list[dict[str, Any]]:
    return importar_pcp_legacy(
        get_service_client(), drogueria_id=drogueria_id, filas=filas, usuario_id=usuario_id
    )


# =============================================================================
# Import legado de presupuestos (Progress; engram #647, agreed design
# 2026-09-24, odd/tasks/presupuestos-legacy-import.md T1)
#
# Import order es mandatorio (design agreed): presupuesto PRIMERO, PCP
# DESPUÉS (T2 busca líneas ya existentes vía `presupuesto_legacy_map`, nunca
# las crea). Reusa acá mismo `_resolver_cliente_id` y
# `_CLASE_POR_PROCESO_COMERCIAL`/`_CLASE_DEFAULT` -- mismo criterio de
# resolución de cliente y de clase que el import de PCP, sin duplicar esa
# lógica (ambos import viven en el mismo módulo `services/pcp/imports`).
# =============================================================================


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
    """Primer import de un `numero_presupuesto`: crea `procesos_comerciales` +
    `presupuestos`, y dentro de un bloque compensado `presupuesto_legacy_map`
    (el ancla de idempotencia) + `items_proceso`/`presupuesto_items` por
    renglón.

    Compensación manual (no hay transacción real vía PostgREST -- mismo
    criterio que `services/presupuestacion/extraccion/service.py::
    _materializar_orden_compra`): ante cualquier excepción tras crear
    `presupuestos`, se borra esa fila (cascadea `presupuesto_items` +
    `presupuesto_legacy_map`) y luego `procesos_comerciales` (cascadea
    `items_proceso`, ya liberado de la referencia RESTRICT de
    `presupuesto_items`) -- ese orden es obligatorio, ver
    `repo.borrar_proceso_comercial`. Un reintento posterior con el mismo
    `numero_presupuesto` no encuentra ningún huérfano y arranca de cero."""
    cliente_id = _resolver_cliente_id(
        client, drogueria_id=drogueria_id, codigo_cliente=header.codigo_cliente
    )
    clase = _CLASE_POR_PROCESO_COMERCIAL.get(header.proceso_comercial or "", _CLASE_DEFAULT)

    proceso = repo.crear_proceso_comercial(
        client,
        {
            "drogueria_id": drogueria_id,
            "cliente_id": cliente_id,
            "clase": clase,
            "nombre": (
                f"Import legado — {header.razon_social_cliente} "
                f"(presupuesto {header.numero_presupuesto})"
            ),
        },
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
        if presupuesto is not None:
            repo.borrar_presupuesto(client, presupuesto_id=presupuesto["id"])
        repo.borrar_proceso_comercial(client, proceso_comercial_id=proceso["id"])
        raise

    return presupuesto, renglones_sin_producto


def importar_presupuesto_legacy(
    client: Client, *, drogueria_id: str, filas: list[FilaImportPresupuestoLegacy], usuario_id: str
) -> list[dict[str, Any]]:
    """Agrupa las filas planas por `numero_presupuesto` (los campos de
    cabecera se repiten por fila, mismo criterio que `importar_pcp_legacy`).
    Devuelve una fila de resultado por cada `numero_presupuesto` distinto en
    el lote, con `accion` = "creado" | "existente" (agreed design: un
    reimport nunca duplica nada -- a diferencia del import de PCP, que sí
    reprocesa renglones en cada corrida)."""
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
            resultados.append(
                {
                    "codigo_legacy": numero_presupuesto,
                    "presupuesto_id": presupuesto["id"],
                    "accion": "existente",
                    "renglones_procesados": presupuesto["cantidad_items"],
                    "renglones_sin_producto": presupuesto["items_sin_precio"],
                }
            )

    return resultados


def importar_presupuesto_legacy_para_endpoint(
    *, drogueria_id: str, filas: list[FilaImportPresupuestoLegacy], usuario_id: str
) -> list[dict[str, Any]]:
    return importar_presupuesto_legacy(
        get_service_client(), drogueria_id=drogueria_id, filas=filas, usuario_id=usuario_id
    )
