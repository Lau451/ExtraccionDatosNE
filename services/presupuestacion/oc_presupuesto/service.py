from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from rapidfuzz import fuzz, process
from supabase import Client

from services.presupuestacion.core.database import get_service_client
from services.presupuestacion.core.exceptions import NotFoundError, ValidationError
from services.presupuestacion.core.texto import normalizar_descripcion
from services.presupuestacion.oc_presupuesto import repository as repo
from services.presupuestacion.oc_presupuesto.models import (
    CandidatoPresupuesto,
    CandidatoVinculo,
    EstadoVinculo,
    MatchingOut,
    PresupuestosCandidatosOut,
    RenglonOrdenCompra,
    RenglonPresupuesto,
)
from services.presupuestacion.presupuestos import repository as presupuestos_repo
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


# =============================================================================
# Phase 3 -- vinculación renglón a renglón (D4-D9, D12). Funciones puras
# primero (testeables sin mock de Supabase), después la orquestación
# (obtener_matching / confirmar_vinculo / deshacer_vinculo / descartar_renglon).
# =============================================================================


def _ordenar_por_similitud(
    descripcion_oc: str, candidatos: dict[str, str]
) -> list[tuple[str, Decimal | None]]:
    """D7: ordena candidatos al mismo precio por fuzz.WRatio sobre
    normalizar_descripcion(...) -- reusa la misma maquinaria que
    matching/service.py::_generar_candidatos, sin _UMBRAL_SUGERIDO ni _TOP_K:
    el precio ya hizo la selección, la similitud solo ordena, NUNCA filtra.
    `candidatos`: presupuesto_item_id -> descripción (de items_proceso, C5).

    Con un solo candidato no hay nada que desempatar: similitud=None (D7).
    """
    if len(candidatos) <= 1:
        return [(pid, None) for pid in candidatos]

    choices = {pid: normalizar_descripcion(desc) for pid, desc in candidatos.items()}
    resultados = process.extract(
        normalizar_descripcion(descripcion_oc), choices, scorer=fuzz.WRatio, limit=None
    )
    return [(pid, Decimal(str(round(score, 2)))) for _, score, pid in resultados]


def _heredar_producto_id(
    presupuesto_item: dict[str, Any], item_proceso: dict[str, Any] | None
) -> str | None:
    """D6: COALESCE(presupuesto_items.producto_id, items_proceso.producto_id).
    Los 4 casos (ambos, solo presupuesto, solo item_proceso, ninguno) resuelven
    acá sin excepción: `None` es un resultado normal, nunca un error."""
    producto_presupuesto = presupuesto_item.get("producto_id")
    producto_item_proceso = item_proceso.get("producto_id") if item_proceso else None
    return producto_presupuesto or producto_item_proceso


def _debe_revertir_producto_id(
    producto_id_actual: str | None, producto_id_heredado_ahora: str | None
) -> bool:
    """D9: al deshacer/descartar, `oc_items.producto_id` vuelve a NULL SOLO si
    sigue siendo EXACTAMENTE el valor que el vínculo dio (recalculado en el
    momento). Si es `None` ya no hay nada que revertir (no-op); si es distinto,
    alguien lo cambió por otro camino después y se respeta intacto."""
    return producto_id_actual is not None and producto_id_actual == producto_id_heredado_ahora


def _derivar_estado(presupuesto_item_id: str | None, vinculo_descartado: bool) -> EstadoVinculo:
    """D4: el estado de 3 valores se DERIVA de (presupuesto_item_id,
    vinculo_descartado), nunca se guarda -- el 4to caso (ambos "activos" a la
    vez) es estructuralmente imposible por ck_oci_vinculo_excluyente."""
    if presupuesto_item_id is not None:
        return "confirmado"
    if vinculo_descartado:
        return "sin_presupuesto"
    return "pendiente"


def _agregar_aviso_n1(
    oc_items_vinculados: list[dict[str, Any]], *, orden_compra_id: str
) -> dict[str, dict[str, Any]]:
    """D5: cuenta, por presupuesto_item_id, cuántos oc_items de TODA la
    droguería apuntan a él (incluye otras OC del mismo cliente en compras
    parciales -- el riesgo real no se detiene en el borde de una OC)."""
    conteo: dict[str, dict[str, Any]] = {}
    for oci in oc_items_vinculados:
        pid = oci["presupuesto_item_id"]
        entrada = conteo.setdefault(pid, {"total": 0, "otras_oc": 0, "cantidad": Decimal("0")})
        entrada["total"] += 1
        if oci["orden_compra_id"] != orden_compra_id:
            entrada["otras_oc"] += 1
        entrada["cantidad"] += Decimal(str(oci["cantidad"]))
    return conteo


def _candidatos_para_renglon(
    precio_oc: Decimal,
    descripcion_oc: str,
    presupuesto_items_activos: list[dict[str, Any]],
    descripciones_por_item_proceso: dict[str, str],
) -> list[CandidatoVinculo]:
    """D7: candidatos = presupuesto_items del presupuesto elegido cuyo precio
    coincide EXACTO con este renglón de OC, ordenados por similitud."""
    coincidencias = [
        pi
        for pi in presupuesto_items_activos
        if pi.get("precio_unitario") is not None and _q2(pi["precio_unitario"]) == precio_oc
    ]
    if not coincidencias:
        return []

    candidatos_desc = {
        pi["id"]: descripciones_por_item_proceso.get(pi["item_proceso_id"], "")
        for pi in coincidencias
    }
    ordenados = _ordenar_por_similitud(descripcion_oc, candidatos_desc)
    return [CandidatoVinculo(presupuesto_item_id=pid, similitud=score) for pid, score in ordenados]


def _top_presupuesto_sugerido(
    client: Client, *, drogueria_id: str, cliente_id: str, oc_items: list[dict[str, Any]]
) -> tuple[int, str | None]:
    """Mismo cálculo que `rankear_presupuestos_candidatos`, sin la
    enriquecimiento de etiquetas (D2.1) ni el lookup de `razon_social` -- acá
    solo hace falta el top del ranking para resolver D8.3. Devuelve
    (presupuestos_del_cliente, presupuesto_id_sugerido_o_None)."""
    precios_oc = [_q2(item["precio_unitario"]) for item in oc_items]
    procesos = repo.listar_procesos_comerciales_del_cliente(
        client, drogueria_id=drogueria_id, cliente_id=cliente_id
    )
    presupuestos = repo.listar_presupuestos_de_procesos(
        client, proceso_comercial_ids=[proceso["id"] for proceso in procesos]
    )
    if not presupuestos:
        return 0, None

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
        return len(presupuestos), None
    return len(presupuestos), puntuados[0][0]["id"]


def _presupuesto_de_vinculos_confirmados(
    client: Client, *, presupuesto_item_ids: list[str]
) -> str:
    """D8, invariante duro: TODOS los vínculos confirmados de una misma OC
    pertenecen al MISMO presupuesto. Se verifica acá, no se asume -- tanto al
    leer (obtener_matching) como antes de escribir (confirmar_vinculo)."""
    presupuesto_items = repo.listar_presupuesto_items_por_ids(
        client, presupuesto_item_ids=list(dict.fromkeys(presupuesto_item_ids))
    )
    distintos = {pi["presupuesto_id"] for pi in presupuesto_items}
    if len(distintos) != 1:
        raise ValidationError(
            "Los vínculos confirmados de esta orden de compra apuntan a más de un "
            "presupuesto -- estado inconsistente, requiere intervención manual"
        )
    return next(iter(distintos))


def _resolver_presupuesto_activo(
    client: Client,
    *,
    drogueria_id: str,
    cliente_id: str,
    oc_items: list[dict[str, Any]],
    presupuesto_id_query: str | None,
) -> tuple[str | None, str | None]:
    """D8: vínculos confirmados de la OC > query param > sugerido del ranking.
    Devuelve (presupuesto_id_o_None, advertencia_o_None)."""
    ids_confirmados = [
        item["presupuesto_item_id"] for item in oc_items if item.get("presupuesto_item_id")
    ]
    if ids_confirmados:
        return _presupuesto_de_vinculos_confirmados(client, presupuesto_item_ids=ids_confirmados), None

    if presupuesto_id_query is not None:
        return presupuesto_id_query, None

    presupuestos_del_cliente, presupuesto_id = _top_presupuesto_sugerido(
        client, drogueria_id=drogueria_id, cliente_id=cliente_id, oc_items=oc_items
    )
    if presupuesto_id is not None:
        return presupuesto_id, None
    if presupuestos_del_cliente == 0:
        return None, "El cliente no tiene presupuestos cargados para elegir uno."
    return None, (
        f"El cliente tiene {presupuestos_del_cliente} presupuesto(s) cargado(s), pero "
        "ninguno coincide en precio con esta orden de compra."
    )


def _armar_renglon_oc(
    item: dict[str, Any],
    presupuesto_items_activos: list[dict[str, Any]],
    descripciones_por_item_proceso: dict[str, str],
) -> RenglonOrdenCompra:
    estado = _derivar_estado(item.get("presupuesto_item_id"), bool(item.get("vinculo_descartado")))
    # candidatos solo aplica a pendiente (D4/design.md § RenglonOrdenCompra):
    # un renglón ya confirmado o descartado no necesita sugerencias.
    candidatos: list[CandidatoVinculo] = []
    if estado == "pendiente":
        candidatos = _candidatos_para_renglon(
            _q2(item["precio_unitario"]),
            item["descripcion"],
            presupuesto_items_activos,
            descripciones_por_item_proceso,
        )
    return RenglonOrdenCompra(
        oc_item_id=item["id"],
        numero_renglon=item["numero_renglon"],
        descripcion=item["descripcion"],
        cantidad=item["cantidad"],
        precio_unitario=item["precio_unitario"],
        producto_id=item.get("producto_id"),
        estado=estado,
        presupuesto_item_id=item.get("presupuesto_item_id"),
        vinculo_origen=item.get("vinculo_origen"),
        candidatos=candidatos,
    )


def obtener_matching(
    client: Client, *, orden_compra_id: str, drogueria_id: str, presupuesto_id: str | None
) -> MatchingOut:
    """Estado completo de la pantalla (D13). `presupuesto_id` None -> se
    resuelve por D8. Calcula sugerencias y avisos en cada llamada; NO
    persiste ninguna (D4: "nada se escribe sin un click")."""
    oc = repo.buscar_orden_compra(client, orden_compra_id=orden_compra_id)
    if oc is None:
        raise NotFoundError("No se encontró la orden de compra")

    cliente_id = oc.get("cliente_id")
    if cliente_id is None:
        raise ValidationError(
            "La orden de compra está anclada por proceso comercial, sin cliente resuelto: "
            "el matching contra presupuesto no aplica"
        )

    oc_items = repo.listar_oc_items_completos(client, orden_compra_id=orden_compra_id)

    presupuesto_activo_id, advertencia = _resolver_presupuesto_activo(
        client,
        drogueria_id=drogueria_id,
        cliente_id=cliente_id,
        oc_items=oc_items,
        presupuesto_id_query=presupuesto_id,
    )

    if presupuesto_activo_id is None:
        return MatchingOut(
            orden_compra_id=orden_compra_id,
            numero_oc=oc["numero_oc"],
            cliente_id=cliente_id,
            presupuesto_id=None,
            renglones_presupuesto=[],
            renglones_oc=[
                _armar_renglon_oc(item, [], {}) for item in oc_items
            ],
            advertencias=[advertencia] if advertencia else [],
        )

    presupuesto_items = presupuestos_repo.listar_items_presupuesto(
        client, presupuesto_id=presupuesto_activo_id
    )
    presupuesto_items_activos = [pi for pi in presupuesto_items if not pi.get("excluido")]

    item_proceso_ids = [pi["item_proceso_id"] for pi in presupuesto_items_activos]
    items_proceso = repo.listar_items_proceso_por_ids(client, item_proceso_ids=item_proceso_ids)
    descripciones = {ip["id"]: ip["descripcion"] for ip in items_proceso}
    numero_renglon_por_item_proceso = {ip["id"]: ip["numero_renglon"] for ip in items_proceso}
    producto_respaldo_por_item_proceso = {ip["id"]: ip.get("producto_id") for ip in items_proceso}

    oc_items_vinculados = repo.listar_oc_items_por_presupuesto_item_ids(
        client,
        drogueria_id=drogueria_id,
        presupuesto_item_ids=[pi["id"] for pi in presupuesto_items_activos],
    )
    aviso_n1 = _agregar_aviso_n1(oc_items_vinculados, orden_compra_id=orden_compra_id)

    renglones_presupuesto = [
        RenglonPresupuesto(
            presupuesto_item_id=pi["id"],
            item_proceso_id=pi["item_proceso_id"],
            numero_renglon=numero_renglon_por_item_proceso.get(pi["item_proceso_id"], 0),
            descripcion=descripciones.get(pi["item_proceso_id"], ""),
            cantidad_ofertada=pi.get("cantidad_ofertada"),
            precio_unitario=pi["precio_unitario"],
            producto_id=pi.get("producto_id")
            or producto_respaldo_por_item_proceso.get(pi["item_proceso_id"]),
            renglones_oc_vinculados=aviso_n1.get(pi["id"], {}).get("total", 0),
            renglones_oc_vinculados_otras_oc=aviso_n1.get(pi["id"], {}).get("otras_oc", 0),
            cantidad_vinculada=aviso_n1.get(pi["id"], {}).get("cantidad", Decimal("0")),
        )
        for pi in presupuesto_items_activos
    ]

    renglones_oc = [
        _armar_renglon_oc(item, presupuesto_items_activos, descripciones) for item in oc_items
    ]

    return MatchingOut(
        orden_compra_id=orden_compra_id,
        numero_oc=oc["numero_oc"],
        cliente_id=cliente_id,
        presupuesto_id=presupuesto_activo_id,
        renglones_presupuesto=renglones_presupuesto,
        renglones_oc=renglones_oc,
        advertencias=[advertencia] if advertencia else [],
    )


def confirmar_vinculo(
    client: Client,
    *,
    orden_compra_id: str,
    oc_item_id: str,
    presupuesto_item_id: str,
    drogueria_id: str,
    usuario_id: str,
) -> MatchingOut:
    """Escribe el vínculo y hereda producto_id (D6). UN solo UPDATE, después
    de TODAS las validaciones de pertenencia (D12). Acepta vínculos cuyo
    precio no coincide, marcándolos vinculo_origen='manual' -- el precio
    sugiere, no autoriza (D4). Re-confirmar un renglón ya confirmado
    reemplaza el vínculo sin error (D13, idempotente)."""
    oc = repo.buscar_orden_compra(client, orden_compra_id=orden_compra_id)
    if oc is None:
        raise NotFoundError("No se encontró la orden de compra")

    cliente_id = oc.get("cliente_id")
    if cliente_id is None:
        raise ValidationError(
            "La orden de compra está anclada por proceso comercial, sin cliente resuelto: "
            "el matching contra presupuesto no aplica"
        )

    oc_item = repo.buscar_oc_item(client, oc_item_id=oc_item_id)
    if oc_item is None or oc_item["orden_compra_id"] != orden_compra_id:
        raise NotFoundError("El renglón no pertenece a esta orden de compra")

    presupuesto_item = repo.buscar_presupuesto_item_con_drogueria(
        client, presupuesto_item_id=presupuesto_item_id, drogueria_id=drogueria_id
    )
    if presupuesto_item is None:
        raise NotFoundError("No se encontró el renglón de presupuesto")
    if presupuesto_item.get("excluido"):
        raise ValidationError(
            "El renglón de presupuesto está excluido: nunca se cotizó al cliente"
        )

    # presupuesto_item ∈ presupuesto elegido ∈ cliente de la OC (D12), antes
    # del primer write: el presupuesto tiene que pertenecer a un proceso
    # comercial de ESTE cliente, no solo a la misma droguería.
    procesos_del_cliente = repo.listar_procesos_comerciales_del_cliente(
        client, drogueria_id=drogueria_id, cliente_id=cliente_id
    )
    proceso_ids_del_cliente = {proceso["id"] for proceso in procesos_del_cliente}
    presupuesto = presupuestos_repo.buscar_presupuesto(
        client, presupuesto_id=presupuesto_item["presupuesto_id"]
    )
    if presupuesto is None or presupuesto["proceso_comercial_id"] not in proceso_ids_del_cliente:
        raise NotFoundError("No se encontró el renglón de presupuesto")

    # D8, invariante duro: verificado ANTES de escribir, no solo al leer.
    oc_items = repo.listar_oc_items_completos(client, orden_compra_id=orden_compra_id)
    ids_confirmados_de_otros_renglones = [
        item["presupuesto_item_id"]
        for item in oc_items
        if item.get("presupuesto_item_id") and item["id"] != oc_item_id
    ]
    if ids_confirmados_de_otros_renglones:
        presupuesto_activo_id = _presupuesto_de_vinculos_confirmados(
            client, presupuesto_item_ids=ids_confirmados_de_otros_renglones
        )
        if presupuesto_item["presupuesto_id"] != presupuesto_activo_id:
            raise ValidationError(
                f"Esta orden de compra ya tiene vínculos confirmados contra el presupuesto "
                f"{presupuesto_activo_id}. Para usar un presupuesto distinto, deshacé esos "
                "vínculos primero."
            )

    items_proceso = repo.listar_items_proceso_por_ids(
        client, item_proceso_ids=[presupuesto_item["item_proceso_id"]]
    )
    item_proceso = items_proceso[0] if items_proceso else None
    producto_heredado = _heredar_producto_id(presupuesto_item, item_proceso)

    precio_coincide = presupuesto_item.get("precio_unitario") is not None and _q2(
        presupuesto_item["precio_unitario"]
    ) == _q2(oc_item["precio_unitario"])

    repo.actualizar_oc_item(
        client,
        oc_item_id=oc_item_id,
        campos={
            "presupuesto_item_id": presupuesto_item_id,
            "vinculo_descartado": False,
            "vinculo_origen": "precio_exacto" if precio_coincide else "manual",
            "vinculo_confirmado_por": usuario_id,
            "vinculo_confirmado_at": datetime.now(timezone.utc).isoformat(),
            "producto_id": producto_heredado,
        },
    )

    return obtener_matching(
        client,
        orden_compra_id=orden_compra_id,
        drogueria_id=drogueria_id,
        presupuesto_id=presupuesto_item["presupuesto_id"],
    )


def _producto_heredado_del_vinculo(
    client: Client, *, presupuesto_item_id: str, drogueria_id: str
) -> str | None:
    presupuesto_item = repo.buscar_presupuesto_item_con_drogueria(
        client, presupuesto_item_id=presupuesto_item_id, drogueria_id=drogueria_id
    )
    if presupuesto_item is None:
        return None
    items_proceso = repo.listar_items_proceso_por_ids(
        client, item_proceso_ids=[presupuesto_item["item_proceso_id"]]
    )
    item_proceso = items_proceso[0] if items_proceso else None
    return _heredar_producto_id(presupuesto_item, item_proceso)


def _campos_para_liberar_vinculo(
    client: Client, *, oc_item: dict[str, Any], drogueria_id: str, vinculo_descartado: bool
) -> dict[str, Any]:
    """Comunes a deshacer_vinculo (D9) y descartar_renglon (D4): limpian el
    vínculo. Sobre producto_id aplica el mismo criterio de D9 en ambos casos
    -- ck_oci_vinculo_excluyente exige limpiar presupuesto_item_id incluso al
    descartar un renglón que estaba confirmado, y dejar un producto heredado
    sin el vínculo que lo sostiene sería el mismo dato huérfano que D9 evita."""
    campos: dict[str, Any] = {
        "presupuesto_item_id": None,
        "vinculo_descartado": vinculo_descartado,
        "vinculo_origen": None,
        "vinculo_confirmado_por": None,
        "vinculo_confirmado_at": None,
    }

    presupuesto_item_id_actual = oc_item.get("presupuesto_item_id")
    if presupuesto_item_id_actual is not None and oc_item.get("producto_id") is not None:
        producto_heredado_ahora = _producto_heredado_del_vinculo(
            client, presupuesto_item_id=presupuesto_item_id_actual, drogueria_id=drogueria_id
        )
        if _debe_revertir_producto_id(oc_item["producto_id"], producto_heredado_ahora):
            campos["producto_id"] = None

    return campos


def deshacer_vinculo(
    client: Client, *, orden_compra_id: str, oc_item_id: str, drogueria_id: str
) -> MatchingOut:
    """D9: vuelve el renglón a `pendiente`, sirva para deshacer un
    `confirmado` o un `sin_presupuesto` -- `pendiente` es el estado cero."""
    oc = repo.buscar_orden_compra(client, orden_compra_id=orden_compra_id)
    if oc is None:
        raise NotFoundError("No se encontró la orden de compra")

    oc_item = repo.buscar_oc_item(client, oc_item_id=oc_item_id)
    if oc_item is None or oc_item["orden_compra_id"] != orden_compra_id:
        raise NotFoundError("El renglón no pertenece a esta orden de compra")

    campos = _campos_para_liberar_vinculo(
        client, oc_item=oc_item, drogueria_id=drogueria_id, vinculo_descartado=False
    )
    repo.actualizar_oc_item(client, oc_item_id=oc_item_id, campos=campos)

    return obtener_matching(
        client, orden_compra_id=orden_compra_id, drogueria_id=drogueria_id, presupuesto_id=None
    )


def descartar_renglon(
    client: Client, *, orden_compra_id: str, oc_item_id: str, drogueria_id: str
) -> MatchingOut:
    """D4: marca vinculo_descartado=True -- el humano afirma que este renglón
    NO está en el presupuesto elegido. Distinto de `pendiente` ("todavía no lo
    miré" vs. "lo miré y no está")."""
    oc = repo.buscar_orden_compra(client, orden_compra_id=orden_compra_id)
    if oc is None:
        raise NotFoundError("No se encontró la orden de compra")

    oc_item = repo.buscar_oc_item(client, oc_item_id=oc_item_id)
    if oc_item is None or oc_item["orden_compra_id"] != orden_compra_id:
        raise NotFoundError("El renglón no pertenece a esta orden de compra")

    campos = _campos_para_liberar_vinculo(
        client, oc_item=oc_item, drogueria_id=drogueria_id, vinculo_descartado=True
    )
    repo.actualizar_oc_item(client, oc_item_id=oc_item_id, campos=campos)

    return obtener_matching(
        client, orden_compra_id=orden_compra_id, drogueria_id=drogueria_id, presupuesto_id=None
    )
