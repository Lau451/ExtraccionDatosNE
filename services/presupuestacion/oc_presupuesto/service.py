from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from supabase import Client

from services.presupuestacion.core.database import get_service_client
from services.presupuestacion.core.exceptions import NotFoundError, ValidationError
from services.presupuestacion.oc_presupuesto import repository as repo
from services.presupuestacion.oc_presupuesto.models import (
    CandidatoPresupuesto,
    PresupuestosCandidatosOut,
)
from services.terceros import api as terceros_api

# D2: tope de candidatos devueltos, aplicado DESPUÉS de ordenar -- nunca
# esconde al mejor. Ver design.md D2 § Alternatives (c).
_TOPE_CANDIDATOS = 5


def _q2(valor: Any) -> Decimal:
    """Normaliza escala de precio a 2 decimales (D3): ambas columnas son
    NUMERIC(15,2), pero el in_() de PostgREST compara texto -- "109.750" y
    "109.75" tienen que producir la MISMA cadena, o el filtro de precio
    exacto los trata como valores distintos. Comparación siempre sobre
    Decimal, nunca sobre float."""
    return Decimal(str(valor)).quantize(Decimal("0.01"))


def _epoch_ordenable(generado_at: Any) -> float:
    """Convierte `generado_at` (datetime, str ISO, o None) a un float
    comparable para el desempate de D2. None se ordena como el más antiguo
    posible -- no debería pasar (NOT NULL DEFAULT NOW()), pero el ranking no
    tiene por qué reventar si pasa."""
    if generado_at is None:
        return float("-inf")
    if isinstance(generado_at, datetime):
        dt = generado_at
    else:
        dt = datetime.fromisoformat(str(generado_at).replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


def _rankear_presupuestos(
    presupuestos: list[dict[str, Any]],
    presupuesto_items: list[dict[str, Any]],
    precios_oc: list[Decimal],
) -> list[tuple[dict[str, Any], int]]:
    """Puntúa y ordena `presupuestos` (D2). Función pura: sin cliente
    Supabase, sin tope de 5 (el tope se aplica después, en el caller).

    Puntaje = cantidad de renglones de LA OC (`precios_oc`, con repeticiones)
    cuyo precio coincide con AL MENOS UN presupuesto_item de ESE presupuesto
    -- no la cantidad de presupuesto_items que matchean, que sobre-cuenta si
    el presupuesto repite el mismo precio en varios renglones.

    `precio_unitario is None` en un presupuesto_item (C4, columna nullable)
    queda fuera del conjunto de precios sin lanzar excepción: ese renglón
    nunca puede ser el origen de un match exacto.
    """
    precios_por_presupuesto: dict[str, set[Decimal]] = {}
    for item in presupuesto_items:
        precio = item.get("precio_unitario")
        if precio is None:
            continue
        precios_por_presupuesto.setdefault(item["presupuesto_id"], set()).add(_q2(precio))

    puntuados = [
        (
            presupuesto,
            sum(
                1
                for precio in precios_oc
                if precio in precios_por_presupuesto.get(presupuesto["id"], set())
            ),
        )
        for presupuesto in presupuestos
    ]
    puntuados.sort(
        key=lambda par: (-par[1], -_epoch_ordenable(par[0].get("generado_at")), par[0]["id"])
    )
    return puntuados


def rankear_presupuestos_candidatos(
    client: Client, *, orden_compra_id: str, drogueria_id: str
) -> PresupuestosCandidatosOut:
    """Puntúa los presupuestos del cliente de la OC por coincidencia EXACTA de
    precio unitario (D2). No escribe nada. No filtra por estado ni por fecha.

    Raises:
        NotFoundError:   la OC no existe o es de otra droguería (RLS).
        ValidationError: la OC está anclada por proceso comercial (cliente_id NULL).
    """
    oc = repo.buscar_orden_compra(client, orden_compra_id=orden_compra_id)
    if oc is None:
        raise NotFoundError("No se encontró la orden de compra")

    cliente_id = oc.get("cliente_id")
    if cliente_id is None:
        raise ValidationError(
            "La orden de compra está anclada por proceso comercial, sin cliente resuelto: "
            "el matching contra presupuesto no aplica"
        )

    razon_social_cliente = terceros_api.obtener_tercero(
        client, tercero_id=cliente_id, drogueria_id=drogueria_id
    )["razon_social"]

    oc_items = repo.listar_oc_items_precios(client, orden_compra_id=orden_compra_id)
    precios_oc = [_q2(item["precio_unitario"]) for item in oc_items]

    procesos = repo.listar_procesos_comerciales_del_cliente(
        client, drogueria_id=drogueria_id, cliente_id=cliente_id
    )
    presupuestos = repo.listar_presupuestos_de_procesos(
        client, proceso_comercial_ids=[proceso["id"] for proceso in procesos]
    )
    presupuestos_del_cliente = len(presupuestos)

    if not presupuestos:
        return PresupuestosCandidatosOut(
            orden_compra_id=orden_compra_id,
            cliente_id=cliente_id,
            razon_social_cliente=razon_social_cliente,
            presupuestos_del_cliente=0,
            candidatos=[],
            presupuesto_sugerido_id=None,
            advertencias=["El cliente no tiene presupuestos cargados."],
        )

    nombre_por_proceso = {proceso["id"]: proceso["nombre"] for proceso in procesos}
    precios_distintos = sorted({str(precio) for precio in precios_oc})
    presupuesto_items = (
        repo.listar_presupuesto_items_por_precio(
            client,
            presupuesto_ids=[presupuesto["id"] for presupuesto in presupuestos],
            precios=precios_distintos,
        )
        if precios_distintos
        else []
    )

    puntuados = _rankear_presupuestos(presupuestos, presupuesto_items, precios_oc)

    if not puntuados or puntuados[0][1] == 0:
        # D2 § Semántica de casos vacíos: presupuestos_del_cliente > 0 pero
        # NINGUNO coincide en precio -- candidatos=[] con advertencia propia,
        # distinta de "sin presupuestos cargados". Esto NO contradice el
        # Scenario "Ningún renglón... coincide en precio" del spec
        # (oc-presupuesto-candidato): ese escenario describe un presupuesto
        # con HERMANOS que sí puntúan -- sigue en la lista con score 0 (ver
        # la rama de abajo, `top` incluye cola con score 0). Acá es el caso
        # distinto: NI UNO SOLO puntúa, y ahí la lista completa se colapsa a
        # vacía con una advertencia dedicada (tasks.md 2.3).
        return PresupuestosCandidatosOut(
            orden_compra_id=orden_compra_id,
            cliente_id=cliente_id,
            razon_social_cliente=razon_social_cliente,
            presupuestos_del_cliente=presupuestos_del_cliente,
            candidatos=[],
            presupuesto_sugerido_id=None,
            advertencias=[
                f"El cliente tiene {presupuestos_del_cliente} presupuesto(s) cargado(s), "
                "pero ninguno coincide en precio con esta orden de compra."
            ],
        )

    top = puntuados[:_TOPE_CANDIDATOS]
    numeros_legacy = repo.buscar_numeros_presupuesto_legacy(
        get_service_client(), presupuesto_ids=[presupuesto["id"] for presupuesto, _ in top]
    )

    candidatos = [
        CandidatoPresupuesto(
            presupuesto_id=presupuesto["id"],
            proceso_comercial_id=presupuesto["proceso_comercial_id"],
            nombre_proceso=nombre_por_proceso.get(presupuesto["proceso_comercial_id"], ""),
            numero_presupuesto=numeros_legacy.get(presupuesto["id"]),
            estado=presupuesto["estado"],
            generado_at=presupuesto["generado_at"],
            cantidad_items=presupuesto["cantidad_items"],
            renglones_oc_con_coincidencia=score,
            renglones_oc_totales=len(oc_items),
        )
        for presupuesto, score in top
    ]

    return PresupuestosCandidatosOut(
        orden_compra_id=orden_compra_id,
        cliente_id=cliente_id,
        razon_social_cliente=razon_social_cliente,
        presupuestos_del_cliente=presupuestos_del_cliente,
        candidatos=candidatos,
        presupuesto_sugerido_id=candidatos[0].presupuesto_id,
        advertencias=[],
    )
