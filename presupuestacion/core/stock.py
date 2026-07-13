import time
from decimal import Decimal
from typing import Any

from supabase import Client

from presupuestacion.core.exceptions import ConflictError

_MAX_REINTENTOS = 5
_BACKOFF_BASE_SEGUNDOS = 0.05


def listar_stock_por_producto(
    client: Client, *, producto_id: str, drogueria_id: str
) -> list[dict[str, Any]]:
    return (
        client.table("stock_productos")
        .select("*")
        .eq("producto_id", producto_id)
        .eq("drogueria_id", drogueria_id)
        .execute()
        .data
    )


def buscar_fila_stock(client: Client, *, fila_id: str) -> dict[str, Any] | None:
    resultado = client.table("stock_productos").select("*").eq("id", fila_id).limit(1).execute()
    return resultado.data[0] if resultado.data else None


def actualizar_comprometida_si_no_cambio(
    client: Client, *, fila_id: str, valor_esperado: str, nuevo_valor: str
) -> dict[str, Any] | None:
    resultado = (
        client.table("stock_productos")
        .update({"cantidad_comprometida": nuevo_valor})
        .eq("id", fila_id)
        .eq("cantidad_comprometida", valor_esperado)
        .execute()
    )
    return resultado.data[0] if resultado.data else None


def actualizar_disponible_si_no_cambio(
    client: Client, *, fila_id: str, valor_esperado: str, nuevo_valor: str
) -> dict[str, Any] | None:
    resultado = (
        client.table("stock_productos")
        .update({"cantidad_disponible": nuevo_valor})
        .eq("id", fila_id)
        .eq("cantidad_disponible", valor_esperado)
        .execute()
    )
    return resultado.data[0] if resultado.data else None


def _comprometer_hasta(client: Client, *, fila_id: str, monto_deseado: Decimal) -> Decimal:
    """Compromete hasta `monto_deseado` en una fila de stock, acotado a lo libre disponible
    en el momento del intento.

    Optimistic locking: cada intento relee la fila y solo aplica el UPDATE si
    cantidad_comprometida sigue siendo igual a lo que se leyó (WHERE cantidad_comprometida =
    valor_leido). Postgres garantiza 0 filas afectadas si hubo una escritura concurrente
    entre la lectura y el UPDATE — nunca hay overwrite silencioso, a diferencia de un
    read-modify-write sin guard. Devuelve el monto realmente comprometido (puede ser 0 si
    no queda lugar en la fila).
    """
    for intento in range(_MAX_REINTENTOS):
        fila = buscar_fila_stock(client, fila_id=fila_id)
        if fila is None:
            return Decimal("0")

        comprometida_actual = Decimal(str(fila["cantidad_comprometida"]))
        disponible = Decimal(str(fila["cantidad_disponible"]))
        libre = disponible - comprometida_actual
        monto = min(monto_deseado, libre)
        if monto <= 0:
            return Decimal("0")

        nuevo_valor = comprometida_actual + monto
        actualizado = actualizar_comprometida_si_no_cambio(
            client,
            fila_id=fila_id,
            valor_esperado=str(fila["cantidad_comprometida"]),
            nuevo_valor=str(nuevo_valor),
        )
        if actualizado is not None:
            return monto

        time.sleep(_BACKOFF_BASE_SEGUNDOS * (intento + 1))

    raise ConflictError("El stock cambió mientras se procesaba, reintentá la operación")


def _liberar_monto(client: Client, *, fila_id: str, monto: Decimal) -> None:
    """Resta `monto` de cantidad_comprometida (piso en 0), con la misma técnica de
    optimistic locking que `_comprometer_hasta`."""
    if monto <= 0:
        return

    for intento in range(_MAX_REINTENTOS):
        fila = buscar_fila_stock(client, fila_id=fila_id)
        if fila is None:
            return

        comprometida_actual = Decimal(str(fila["cantidad_comprometida"]))
        nuevo_valor = max(comprometida_actual - monto, Decimal("0"))
        actualizado = actualizar_comprometida_si_no_cambio(
            client,
            fila_id=fila_id,
            valor_esperado=str(fila["cantidad_comprometida"]),
            nuevo_valor=str(nuevo_valor),
        )
        if actualizado is not None:
            return

        time.sleep(_BACKOFF_BASE_SEGUNDOS * (intento + 1))

    raise ConflictError(
        "No se pudo liberar el stock comprometido tras un error, reintentá la operación"
    )


def comprometer_stock_producto(
    client: Client, *, producto_id: str, drogueria_id: str, cantidad: Decimal
) -> list[tuple[str, Decimal]]:
    """Compromete `cantidad` unidades de un producto, repartiendo entre depósitos si un
    solo depósito no alcanza (mayor libre primero). Si al recorrer todos los depósitos
    queda un remanente sin cubrir, revierte lo parcialmente comprometido en ESTA llamada
    y levanta ConflictError.

    Devuelve la lista de (fila_id, monto) efectivamente comprometidos. El llamador
    (presentar_presupuesto) es responsable de acumular estos compromisos entre ítems y
    revertir TODOS si otro ítem del mismo presupuesto falla más adelante — este helper
    solo garantiza atomicidad para el producto que le toca.
    """
    filas = listar_stock_por_producto(client, producto_id=producto_id, drogueria_id=drogueria_id)
    filas_ordenadas = sorted(
        filas,
        key=lambda f: Decimal(str(f["cantidad_disponible"])) - Decimal(str(f["cantidad_comprometida"])),
        reverse=True,
    )

    restante = cantidad
    compromisos: list[tuple[str, Decimal]] = []
    try:
        for fila in filas_ordenadas:
            if restante <= 0:
                break
            comprometido = _comprometer_hasta(client, fila_id=fila["id"], monto_deseado=restante)
            if comprometido > 0:
                compromisos.append((fila["id"], comprometido))
                restante -= comprometido
    except ConflictError as motivo_original:
        # Si _comprometer_hasta agotó reintentos en ALGUNA fila (contención real, no
        # simple falta de stock), lo que ya se comprometió en filas anteriores de este
        # mismo producto queda a medio camino si no se revierte acá explícitamente —
        # el `if restante > 0` de abajo nunca se alcanza porque la excepción corta el loop.
        liberar_o_reportar(client, compromisos, motivo_original)
        raise

    if restante > 0:
        motivo_original = ConflictError(
            f"Stock insuficiente para comprometer {cantidad} unidades del producto "
            f"{producto_id}: faltan {restante}"
        )
        liberar_o_reportar(client, compromisos, motivo_original)
        raise motivo_original

    return compromisos


def liberar_o_reportar(
    client: Client, compromisos: list[tuple[str, Decimal]], motivo_original: ConflictError
) -> None:
    """Revierte `compromisos` y, si la reversión misma falla, no deja que el error de
    limpieza reemplace en silencio el motivo original: encadena ambos (`raise ... from`)
    y el mensaje final detalla exactamente qué filas/montos quedaron sin revertir, para
    que se puedan reconciliar a mano en stock_productos."""
    try:
        liberar_compromisos(client, compromisos)
    except ConflictError as motivo_liberacion:
        raise ConflictError(
            f"{motivo_liberacion} — ocurrió revirtiendo compromisos tras el error original: "
            f"{motivo_original}"
        ) from motivo_original


def liberar_compromisos(client: Client, compromisos: list[tuple[str, Decimal]]) -> None:
    """Revierte cada compromiso de forma independiente: si revertir una fila falla (p. ej.
    otra carrera concurrente justo al liberar), sigue con el resto en vez de abortar todo.
    Si algo queda sin revertir, levanta ConflictError con el detalle exacto de qué filas y
    montos requieren reconciliación manual."""
    fallidos: list[tuple[str, Decimal]] = []
    for fila_id, monto in reversed(compromisos):
        try:
            _liberar_monto(client, fila_id=fila_id, monto=Decimal(str(monto)))
        except ConflictError:
            fallidos.append((fila_id, monto))

    if fallidos:
        detalle = "; ".join(
            f"stock_productos.id={fila_id} ({monto} unidades sin liberar)" for fila_id, monto in fallidos
        )
        raise ConflictError(
            f"No se pudo revertir todo el stock comprometido — requiere reconciliación "
            f"manual: {detalle}"
        )


def _liberar_hasta(client: Client, *, fila_id: str, monto_deseado: Decimal) -> Decimal:
    """Libera (resta de cantidad_comprometida) hasta `monto_deseado` en una fila, acotado a
    lo que esa fila tenga comprometido. Mismo optimistic locking que `_comprometer_hasta`,
    en sentido inverso. Devuelve el monto realmente liberado (puede ser 0)."""
    for intento in range(_MAX_REINTENTOS):
        fila = buscar_fila_stock(client, fila_id=fila_id)
        if fila is None:
            return Decimal("0")

        comprometida_actual = Decimal(str(fila["cantidad_comprometida"]))
        monto = min(monto_deseado, comprometida_actual)
        if monto <= 0:
            return Decimal("0")

        nuevo_valor = comprometida_actual - monto
        actualizado = actualizar_comprometida_si_no_cambio(
            client,
            fila_id=fila_id,
            valor_esperado=str(fila["cantidad_comprometida"]),
            nuevo_valor=str(nuevo_valor),
        )
        if actualizado is not None:
            return monto

        time.sleep(_BACKOFF_BASE_SEGUNDOS * (intento + 1))

    raise ConflictError(
        "No se pudo liberar el stock comprometido tras un error, reintentá la operación"
    )


def _descontar_disponible_hasta(client: Client, *, fila_id: str, monto_deseado: Decimal) -> Decimal:
    """Descuenta hasta `monto_deseado` de cantidad_disponible en una fila, acotado a lo
    disponible. Columna independiente de cantidad_comprometida — mismo optimistic locking.
    Devuelve el monto realmente descontado (puede ser 0)."""
    for intento in range(_MAX_REINTENTOS):
        fila = buscar_fila_stock(client, fila_id=fila_id)
        if fila is None:
            return Decimal("0")

        disponible_actual = Decimal(str(fila["cantidad_disponible"]))
        monto = min(monto_deseado, disponible_actual)
        if monto <= 0:
            return Decimal("0")

        nuevo_valor = disponible_actual - monto
        actualizado = actualizar_disponible_si_no_cambio(
            client,
            fila_id=fila_id,
            valor_esperado=str(fila["cantidad_disponible"]),
            nuevo_valor=str(nuevo_valor),
        )
        if actualizado is not None:
            return monto

        time.sleep(_BACKOFF_BASE_SEGUNDOS * (intento + 1))

    raise ConflictError(
        "No se pudo descontar el stock disponible tras un error, reintentá la operación"
    )


def entregar_stock_producto(
    client: Client,
    *,
    producto_id: str,
    drogueria_id: str,
    cantidad_entregada: Decimal,
    cantidad_rechazada: Decimal = Decimal("0"),
) -> tuple[Decimal, Decimal]:
    """Al confirmar una entrega de OC (§6): libera cantidad_comprometida por el TOTAL
    entregado (`cantidad_entregada` — la promesa al cliente queda resuelta, sea aceptada o
    rechazada) y descuenta cantidad_disponible SOLO por lo aceptado
    (`cantidad_entregada - cantidad_rechazada` — lo rechazado nunca entró al stock
    vendible).

    Los dos ajustes se calculan y reparten de forma INDEPENDIENTE entre los depósitos del
    producto (mayor cantidad_comprometida primero para liberar; mayor cantidad_disponible
    primero para descontar) porque no hay registro de en qué fila exacta se comprometió o
    tiene stock cada unidad — misma aproximación de pool agregado que ya usa
    `comprometer_stock_producto`, solo que ahora en dos pasadas porque los montos a mover
    en cada columna pueden ser distintos y no hay por qué caer en las mismas filas.

    No revierte nada si no alcanza en alguna columna (no existe "liberar/descontar de
    más": cada pasada topea en lo que haya). Devuelve (liberado_total, descontado_total)
    para que el llamador detecte discrepancias.
    """
    cantidad_aceptada = cantidad_entregada - cantidad_rechazada
    filas = listar_stock_por_producto(client, producto_id=producto_id, drogueria_id=drogueria_id)

    filas_por_comprometida = sorted(
        filas, key=lambda f: Decimal(str(f["cantidad_comprometida"])), reverse=True
    )
    restante_liberar = cantidad_entregada
    liberado_total = Decimal("0")
    for fila in filas_por_comprometida:
        if restante_liberar <= 0:
            break
        liberado = _liberar_hasta(client, fila_id=fila["id"], monto_deseado=restante_liberar)
        liberado_total += liberado
        restante_liberar -= liberado

    filas_por_disponible = sorted(
        filas, key=lambda f: Decimal(str(f["cantidad_disponible"])), reverse=True
    )
    restante_descontar = cantidad_aceptada
    descontado_total = Decimal("0")
    for fila in filas_por_disponible:
        if restante_descontar <= 0:
            break
        descontado = _descontar_disponible_hasta(client, fila_id=fila["id"], monto_deseado=restante_descontar)
        descontado_total += descontado
        restante_descontar -= descontado

    return liberado_total, descontado_total
