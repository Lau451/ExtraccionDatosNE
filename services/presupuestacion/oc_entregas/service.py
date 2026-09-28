"""Servicio del módulo oc_entregas (odd/tasks/oc-entregas-planificacion.md,
T3): planificar la división en entregas de una OC ya con matching resuelto
(design.md D1/D8 del cambio orden-compra, aplicados DESPUÉS de matching en vez
de al confirmar la OC -- ver el § Why de la tarea).

Reusa deliberadamente piezas de otros módulos en vez de reinventarlas:
- `repartir_cantidad` (extraccion/service.py, D8) para el reparto parejo.
- `crear_entrega_oc` / `insertar_entregas_oc_items` (extraccion/repository.py)
  para los inserts -- son el único lugar del código que ya sabía escribir
  estas dos tablas.
- `_derivar_estado` (oc_presupuesto/service.py, D4) para pendiente/
  confirmado/sin_presupuesto -- el estado de un renglón NUNCA se recalcula
  con un criterio propio acá, siempre el mismo que ve la pantalla de
  matching.

NUNCA importa ni llama nada de `core/stock.py` (invariante duro: "planificar
entregas no mueve stock", igual que "confirmar una OC no mueve stock").
"""

from datetime import date
from decimal import Decimal
from typing import Any

from supabase import Client

from services.presupuestacion.core.exceptions import ConflictError, NotFoundError, ValidationError
from services.presupuestacion.extraccion import repository as extraccion_repo
from services.presupuestacion.extraccion.service import repartir_cantidad
from services.presupuestacion.oc_entregas import repository as repo
from services.presupuestacion.oc_entregas.models import (
    AdvertenciaDivisibilidad,
    EntregaItemPlanOut,
    EntregaPlanIn,
    EntregaPlanOut,
    PlanificacionEntregasOut,
    PlanificarEntregasOut,
    PlanSugeridoRenglon,
    RenglonPlanificacion,
)
from services.presupuestacion.oc_presupuesto.service import _derivar_estado


def sugerir_plan_renglon(
    cantidad: Decimal, unidades_por_presentacion: int | None, entregas: int
) -> list[Decimal]:
    """Sugerencia de reparto para UN renglón confirmado (GET §
    plan_sugerido). Índice i == entrega i+1.

    Con tamaño de pack conocido (`unidades_por_presentacion`, migración 0031):
    - `packs = cantidad // u` -- cuántos packs ENTEROS entran en `cantidad`.
    - esos packs se reparten lo más parejo posible entre las N entregas con
      `repartir_cantidad` (D8: las primeras reciben un pack de más cuando
      `packs` no es múltiplo de `entregas`), y cada parte se multiplica por
      `u` para volver a unidades.
    - el resto (`cantidad - packs*u`, lo que no llega a formar un pack
      completo) se suma a la ÚLTIMA entrega -- mismo criterio que el caso
      decimal de D8 (`repartir_cantidad`): un resto de redondeo/ajuste va al
      final, nunca se reparte, para no arrastrar el error.

    Ejemplos (design.md D8 + tasks.md T3): (100, 25, 3) -> [50, 25, 25];
    (110, 25, 3) -> [50, 25, 35].

    Sin tamaño de pack conocido (`u` None o <= 0): reparto liso con
    `repartir_cantidad` tal cual, sin ninguna noción de pack.

    Invariante: `sum(resultado) == cantidad`, siempre -- hereda el invariante
    de `repartir_cantidad` (D8) más la reconciliación del resto acá.
    """
    if not unidades_por_presentacion or unidades_por_presentacion <= 0:
        return repartir_cantidad(cantidad, entregas)

    u = Decimal(unidades_por_presentacion)
    packs = int(cantidad // u)
    resto = cantidad - (Decimal(packs) * u)

    cantidades = [parte * u for parte in repartir_cantidad(Decimal(packs), entregas)]
    cantidades[-1] += resto
    return cantidades


def _clasificar_renglones(
    oc_items: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], int, int]:
    """D4: la MISMA derivación que usa la pantalla de matching
    (oc_presupuesto.service._derivar_estado) -- nunca un criterio propio.
    Devuelve (confirmados, cantidad_pendientes, cantidad_descartados)."""
    confirmados: list[dict[str, Any]] = []
    pendientes = 0
    descartados = 0
    for item in oc_items:
        estado = _derivar_estado(item.get("presupuesto_item_id"), bool(item.get("vinculo_descartado")))
        if estado == "confirmado":
            confirmados.append(item)
        elif estado == "pendiente":
            pendientes += 1
        else:
            descartados += 1
    return confirmados, pendientes, descartados


def _productos_por_id(client: Client, oc_items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    producto_ids = [item["producto_id"] for item in oc_items if item.get("producto_id")]
    return {p["id"]: p for p in repo.listar_productos_por_ids(client, producto_ids=producto_ids)}


def _armar_plan_actual(
    client: Client, entregas_existentes: list[dict[str, Any]]
) -> list[EntregaPlanOut]:
    if not entregas_existentes:
        return []
    items = repo.listar_entregas_oc_items(
        client, entrega_oc_ids=[entrega["id"] for entrega in entregas_existentes]
    )
    items_por_entrega: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        items_por_entrega.setdefault(item["entrega_oc_id"], []).append(item)
    return [
        EntregaPlanOut(
            numero_entrega=entrega["numero_entrega"],
            fecha_entrega_planificada=entrega.get("fecha_entrega_planificada"),
            estado=entrega["estado"],
            items=[
                EntregaItemPlanOut(
                    oc_item_id=item["oc_item_id"],
                    cantidad_planificada=item["cantidad_planificada"],
                )
                for item in items_por_entrega.get(entrega["id"], [])
            ],
        )
        for entrega in entregas_existentes
    ]


def obtener_planificacion(
    client: Client, *, orden_compra_id: str, drogueria_id: str
) -> PlanificacionEntregasOut:
    """Contexto completo de la pantalla de planificación (GET). No escribe
    nada -- mismo criterio que oc_presupuesto.obtener_matching (D4: "nada se
    escribe sin un click")."""
    oc = repo.buscar_orden_compra(client, orden_compra_id=orden_compra_id)
    if oc is None or oc["drogueria_id"] != drogueria_id:
        raise NotFoundError("No se encontró la orden de compra")

    oc_items = repo.listar_oc_items(client, orden_compra_id=orden_compra_id)
    confirmados, pendientes, descartados = _clasificar_renglones(oc_items)
    productos = _productos_por_id(client, confirmados)

    renglones = [
        RenglonPlanificacion(
            oc_item_id=item["id"],
            numero_renglon=item["numero_renglon"],
            numero_renglon_documento=item.get("numero_renglon_documento"),
            descripcion=item["descripcion"],
            cantidad=item["cantidad"],
            producto_id=item.get("producto_id"),
            producto_nombre=productos.get(item.get("producto_id"), {}).get("nombre"),
            unidades_por_presentacion=productos.get(item.get("producto_id"), {}).get(
                "unidades_por_presentacion"
            ),
        )
        for item in confirmados
    ]

    entregas_existentes = repo.listar_entregas_oc(client, orden_compra_id=orden_compra_id)
    plan_bloqueado = any(entrega["estado"] != "pendiente" for entrega in entregas_existentes)

    if pendientes > 0:
        puede_planificar = False
        motivo = (
            f"Hay {pendientes} renglón(es) pendiente(s) de matching -- resolvelos antes de "
            "planificar las entregas."
        )
    elif not confirmados:
        puede_planificar = False
        motivo = "La orden de compra no tiene renglones confirmados para planificar."
    elif plan_bloqueado:
        puede_planificar = False
        motivo = (
            "El plan ya tiene una entrega que dejó de estar 'pendiente' -- no se puede "
            "replanificar."
        )
    else:
        puede_planificar = True
        motivo = None

    cantidad_entregas_sugerida = oc.get("cantidad_entregas") or 1
    plan_sugerido = (
        [
            PlanSugeridoRenglon(
                oc_item_id=item["id"],
                cantidades=sugerir_plan_renglon(
                    Decimal(str(item["cantidad"])),
                    productos.get(item.get("producto_id"), {}).get("unidades_por_presentacion"),
                    cantidad_entregas_sugerida,
                ),
            )
            for item in confirmados
        ]
        if puede_planificar
        else []
    )

    return PlanificacionEntregasOut(
        orden_compra_id=orden_compra_id,
        numero_oc=oc["numero_oc"],
        cantidad_entregas_sugerida=cantidad_entregas_sugerida,
        renglones=renglones,
        pendientes=pendientes,
        descartados=descartados,
        puede_planificar=puede_planificar,
        motivo=motivo,
        plan_sugerido=plan_sugerido,
        plan_actual=_armar_plan_actual(client, entregas_existentes),
    )


def _validar_numeracion(entregas: list[EntregaPlanIn]) -> None:
    n = len(entregas)
    numeros = sorted(entrega.numero_entrega for entrega in entregas)
    if numeros != list(range(1, n + 1)):
        raise ValidationError(
            f"Los números de entrega deben ser exactamente 1..{n}, consecutivos y sin repetir "
            f"(recibido: {sorted(entrega.numero_entrega for entrega in entregas)})"
        )


def _validar_renglones_y_cantidades(
    entregas: list[EntregaPlanIn], confirmados: dict[str, dict[str, Any]]
) -> None:
    for entrega in entregas:
        for item in entrega.items:
            if item.oc_item_id not in confirmados:
                raise ValidationError(
                    f"El renglón {item.oc_item_id} de la entrega {entrega.numero_entrega} no está "
                    "confirmado por matching o no pertenece a esta orden de compra"
                )
            if item.cantidad < 0:
                raise ValidationError(
                    f"La cantidad del renglón {item.oc_item_id} en la entrega "
                    f"{entrega.numero_entrega} no puede ser negativa"
                )
        if all(item.cantidad == 0 for item in entrega.items):
            raise ValidationError(
                f"La entrega {entrega.numero_entrega} no puede tener todas las cantidades en cero"
            )


def _validar_sumas_por_renglon(
    entregas: list[EntregaPlanIn], confirmados: dict[str, dict[str, Any]]
) -> None:
    sumas: dict[str, Decimal] = {oc_item_id: Decimal("0") for oc_item_id in confirmados}
    for entrega in entregas:
        for item in entrega.items:
            sumas[item.oc_item_id] += item.cantidad

    errores: list[str] = []
    for oc_item_id, item in confirmados.items():
        cantidad_renglon = Decimal(str(item["cantidad"]))
        if sumas[oc_item_id] != cantidad_renglon:
            etiqueta = item.get("numero_renglon_documento") or str(item["numero_renglon"])
            errores.append(
                f"renglón {etiqueta}: la suma planificada ({sumas[oc_item_id]}) no coincide con "
                f"la cantidad del renglón ({cantidad_renglon})"
            )
    if errores:
        detalle = "; ".join(errores[:10])
        extra = f" (y {len(errores) - 10} más)" if len(errores) > 10 else ""
        raise ValidationError(
            f"La planificación no coincide con la cantidad de cada renglón — {detalle}{extra}"
        )


def _unidades_por_oc_item(
    client: Client, confirmados: dict[str, dict[str, Any]]
) -> dict[str, int]:
    productos = _productos_por_id(client, list(confirmados.values()))
    resultado: dict[str, int] = {}
    for oc_item_id, item in confirmados.items():
        producto = productos.get(item.get("producto_id"))
        u = producto.get("unidades_por_presentacion") if producto else None
        if u:
            resultado[oc_item_id] = u
    return resultado


def _advertencias_divisibilidad(
    entregas: list[EntregaPlanIn], unidades_por_id: dict[str, int]
) -> list[AdvertenciaDivisibilidad]:
    """Advertencias NUNCA bloqueantes (T3 acceptance criteria): se calculan
    DESPUÉS de que el plan ya pasó todas las validaciones -- por definición no
    pueden impedir la creación del plan."""
    advertencias: list[AdvertenciaDivisibilidad] = []
    for entrega in entregas:
        for item in entrega.items:
            u = unidades_por_id.get(item.oc_item_id)
            if not u or item.cantidad % Decimal(u) == 0:
                continue
            sugerida = (item.cantidad // Decimal(u)) * Decimal(u)
            if sugerida == 0:
                sugerida = Decimal(u)
            advertencias.append(
                AdvertenciaDivisibilidad(
                    oc_item_id=item.oc_item_id,
                    numero_entrega=entrega.numero_entrega,
                    cantidad=item.cantidad,
                    unidades_por_presentacion=u,
                    cantidad_sugerida=sugerida,
                )
            )
    return advertencias


def _fecha_iso(fecha: date | None) -> str | None:
    return fecha.isoformat() if fecha else None


def planificar_entregas(
    client: Client,
    *,
    orden_compra_id: str,
    drogueria_id: str,
    usuario_id: str,
    entregas: list[EntregaPlanIn],
) -> PlanificarEntregasOut:
    """Crea o reemplaza el plan de entregas de una OC (PUT). Gate + todas las
    validaciones corren ANTES del primer write (mismo criterio que
    `_validar_orden_compra_override`, extraccion/service.py, D7)."""
    oc = repo.buscar_orden_compra(client, orden_compra_id=orden_compra_id)
    if oc is None or oc["drogueria_id"] != drogueria_id:
        raise NotFoundError("No se encontró la orden de compra")

    if not entregas:
        raise ValidationError("El plan debe tener al menos una entrega")

    oc_items = repo.listar_oc_items(client, orden_compra_id=orden_compra_id)
    confirmados_lista, pendientes, _descartados = _clasificar_renglones(oc_items)
    if pendientes:
        raise ConflictError(
            f"Hay {pendientes} renglón(es) pendiente(s) de matching -- resolvelos antes de "
            "planificar las entregas."
        )
    if not confirmados_lista:
        raise ConflictError("La orden de compra no tiene renglones confirmados para planificar.")
    confirmados = {item["id"]: item for item in confirmados_lista}

    entregas_existentes = repo.listar_entregas_oc(client, orden_compra_id=orden_compra_id)
    if any(entrega["estado"] != "pendiente" for entrega in entregas_existentes):
        raise ConflictError(
            "El plan está bloqueado: ya hay una entrega que dejó de estar 'pendiente'."
        )

    entregas_ordenadas = sorted(entregas, key=lambda entrega: entrega.numero_entrega)
    _validar_numeracion(entregas_ordenadas)
    _validar_renglones_y_cantidades(entregas_ordenadas, confirmados)
    _validar_sumas_por_renglon(entregas_ordenadas, confirmados)

    # Reemplazo (D4 § PUT "solo mientras esté pendiente"): se borra el plan
    # anterior (siempre 'pendiente', ya verificado arriba) ANTES de insertar
    # el nuevo. Bug de no atomicidad (idéntico al de
    # extraccion/service.py::_materializar_orden_compra, ver su comentario):
    # PostgREST no ofrece una transacción real entre estos deletes/inserts. Si
    # el insert de más abajo falla a mitad de camino, la OC queda SIN plan
    # (compensación manual, catch de abajo) en vez de con un plan mixto
    # viejo+nuevo -- un estado más seguro para reintentar.
    if entregas_existentes:
        repo.borrar_entregas_oc(client, orden_compra_id=orden_compra_id)

    unidades_por_id = _unidades_por_oc_item(client, confirmados)
    entregas_out: list[EntregaPlanOut] = []
    algo_insertado = False
    try:
        for entrega in entregas_ordenadas:
            items_no_cero = [item for item in entrega.items if item.cantidad > 0]
            entrega_creada = extraccion_repo.crear_entrega_oc(
                client,
                {
                    "orden_compra_id": orden_compra_id,
                    "drogueria_id": drogueria_id,
                    "numero_entrega": entrega.numero_entrega,
                    "fecha_entrega_planificada": _fecha_iso(entrega.fecha_entrega_planificada),
                    "cantidad_items": len(items_no_cero),
                    "estado": "pendiente",
                },
            )
            algo_insertado = True
            extraccion_repo.insertar_entregas_oc_items(
                client,
                [
                    {
                        "entrega_oc_id": entrega_creada["id"],
                        "drogueria_id": drogueria_id,
                        "oc_item_id": item.oc_item_id,
                        "cantidad_planificada": str(item.cantidad),
                        "cantidad_entregada": "0",
                    }
                    for item in items_no_cero
                ],
            )
            entregas_out.append(
                EntregaPlanOut(
                    numero_entrega=entrega.numero_entrega,
                    fecha_entrega_planificada=entrega.fecha_entrega_planificada,
                    estado="pendiente",
                    items=[
                        EntregaItemPlanOut(
                            oc_item_id=item.oc_item_id, cantidad_planificada=item.cantidad
                        )
                        for item in items_no_cero
                    ],
                )
            )

        repo.actualizar_cantidad_entregas(
            client, orden_compra_id=orden_compra_id, cantidad_entregas=len(entregas_ordenadas)
        )
    except Exception:
        # Compensación manual: el DELETE de entregas_oc se lleva sus
        # entregas_oc_items por CASCADE (fk_eoci_ent), un solo delete alcanza.
        if algo_insertado:
            repo.borrar_entregas_oc(client, orden_compra_id=orden_compra_id)
        raise

    advertencias = _advertencias_divisibilidad(entregas_ordenadas, unidades_por_id)

    return PlanificarEntregasOut(
        orden_compra_id=orden_compra_id, entregas=entregas_out, advertencias=advertencias
    )
