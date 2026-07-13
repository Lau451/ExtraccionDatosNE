import threading
from decimal import Decimal

import pytest

from presupuestacion.core.exceptions import ConflictError
from presupuestacion.presupuestos import repository as repo
from presupuestacion.presupuestos import stock


@pytest.mark.integration
def test_comprometer_stock_producto_un_solo_deposito(
    service_client, seed_drogueria, seed_producto, seed_stock_factory
):
    seed_stock_factory(seed_producto["id"], disponible="10")

    compromisos = stock.comprometer_stock_producto(
        service_client,
        producto_id=seed_producto["id"],
        drogueria_id=seed_drogueria["id"],
        cantidad=Decimal("6"),
    )

    assert sum((m for _, m in compromisos), Decimal("0")) == Decimal("6")
    fila = (
        service_client.table("stock_productos")
        .select("cantidad_comprometida")
        .eq("producto_id", seed_producto["id"])
        .execute()
        .data[0]
    )
    assert Decimal(str(fila["cantidad_comprometida"])) == Decimal("6")


@pytest.mark.integration
def test_comprometer_stock_producto_reparte_entre_depositos(
    service_client, seed_drogueria, seed_producto, seed_stock_factory
):
    fila_a = seed_stock_factory(seed_producto["id"], disponible="4", deposito="deposito-a")
    fila_b = seed_stock_factory(seed_producto["id"], disponible="5", deposito="deposito-b")

    compromisos = stock.comprometer_stock_producto(
        service_client,
        producto_id=seed_producto["id"],
        drogueria_id=seed_drogueria["id"],
        cantidad=Decimal("7"),
    )

    assert sum((m for _, m in compromisos), Decimal("0")) == Decimal("7")
    fila_ids_comprometidos = {fila_id for fila_id, _ in compromisos}
    assert fila_ids_comprometidos == {fila_a["id"], fila_b["id"]}


@pytest.mark.integration
def test_comprometer_stock_producto_insuficiente_revierte_todo(
    service_client, seed_drogueria, seed_producto, seed_stock_factory
):
    fila = seed_stock_factory(seed_producto["id"], disponible="4")

    with pytest.raises(ConflictError):
        stock.comprometer_stock_producto(
            service_client,
            producto_id=seed_producto["id"],
            drogueria_id=seed_drogueria["id"],
            cantidad=Decimal("10"),
        )

    fila_final = (
        service_client.table("stock_productos")
        .select("cantidad_comprometida")
        .eq("id", fila["id"])
        .execute()
        .data[0]
    )
    assert Decimal(str(fila_final["cantidad_comprometida"])) == Decimal("0")


@pytest.mark.integration
def test_comprometer_stock_producto_revierte_deposito_a_si_deposito_b_agota_reintentos(
    service_client, seed_drogueria, seed_producto, seed_stock_factory, mocker
):
    """Depósito A tiene más libre que B, así que el reparto greedy lo intenta primero y
    comprometer ahí un monto real. Depósito B se fuerza (via mock) a perder SIEMPRE la
    carrera optimista, agotando sus reintentos y levantando ConflictError desde adentro
    de _comprometer_hasta -- el camino que ningún test anterior ejercitaba. El compromiso
    ya aplicado en A no puede quedar colgado: tiene que revertirse a 0 igual que en el
    camino de 'stock insuficiente'."""
    fila_a = seed_stock_factory(seed_producto["id"], disponible="6", deposito="deposito-a")
    fila_b = seed_stock_factory(seed_producto["id"], disponible="5", deposito="deposito-b")

    original = repo.actualizar_comprometida_si_no_cambio

    def _perder_siempre_en_b(client, *, fila_id, valor_esperado, nuevo_valor):
        if fila_id == fila_b["id"]:
            return None
        return original(client, fila_id=fila_id, valor_esperado=valor_esperado, nuevo_valor=nuevo_valor)

    mocker.patch(
        "presupuestacion.presupuestos.stock.repo.actualizar_comprometida_si_no_cambio",
        side_effect=_perder_siempre_en_b,
    )
    mocker.patch("presupuestacion.presupuestos.stock.time.sleep", lambda _: None)

    with pytest.raises(ConflictError):
        stock.comprometer_stock_producto(
            service_client,
            producto_id=seed_producto["id"],
            drogueria_id=seed_drogueria["id"],
            cantidad=Decimal("9"),
        )

    fila_a_final = (
        service_client.table("stock_productos")
        .select("cantidad_comprometida")
        .eq("id", fila_a["id"])
        .execute()
        .data[0]
    )
    fila_b_final = (
        service_client.table("stock_productos")
        .select("cantidad_comprometida")
        .eq("id", fila_b["id"])
        .execute()
        .data[0]
    )
    assert Decimal(str(fila_a_final["cantidad_comprometida"])) == Decimal("0"), (
        "el compromiso real en Depósito A quedó sin revertir tras el fallo en B"
    )
    assert Decimal(str(fila_b_final["cantidad_comprometida"])) == Decimal("0")


@pytest.mark.integration
def test_comprometer_stock_producto_si_la_reversion_tambien_falla_no_pierde_el_motivo_original(
    service_client, seed_drogueria, seed_producto, seed_stock_factory, mocker
):
    """Caso límite: B agota reintentos al comprometer (motivo original) Y, al intentar
    revertir el compromiso real ya aplicado en A, ESA reversión también agota reintentos
    (ej. otra carrera concurrente justo al liberar). No pedimos que esto se resuelva solo
    -- pedimos que el error final no oculte ninguno de los dos motivos y deje claro qué
    fila quedó sin reconciliar, para que un humano lo arregle a mano."""
    fila_a = seed_stock_factory(seed_producto["id"], disponible="6", deposito="deposito-a")
    fila_b = seed_stock_factory(seed_producto["id"], disponible="5", deposito="deposito-b")

    original = repo.actualizar_comprometida_si_no_cambio

    def _falla_b_al_comprometer_y_a_al_liberar(client, *, fila_id, valor_esperado, nuevo_valor):
        if fila_id == fila_b["id"]:
            return None
        if fila_id == fila_a["id"] and Decimal(nuevo_valor) < Decimal(valor_esperado):
            return None  # intento de LIBERAR (bajar el valor): forzado a perder la carrera
        return original(client, fila_id=fila_id, valor_esperado=valor_esperado, nuevo_valor=nuevo_valor)

    mocker.patch(
        "presupuestacion.presupuestos.stock.repo.actualizar_comprometida_si_no_cambio",
        side_effect=_falla_b_al_comprometer_y_a_al_liberar,
    )
    mocker.patch("presupuestacion.presupuestos.stock.time.sleep", lambda _: None)

    with pytest.raises(ConflictError) as excinfo:
        stock.comprometer_stock_producto(
            service_client,
            producto_id=seed_producto["id"],
            drogueria_id=seed_drogueria["id"],
            cantidad=Decimal("9"),
        )

    mensaje = str(excinfo.value)
    assert "reconciliación manual" in mensaje
    assert fila_a["id"] in mensaje
    assert "6" in mensaje
    assert excinfo.value.__cause__ is not None, (
        "el motivo original (por qué se intentaba comprometer) debe quedar encadenado, "
        "no reemplazado en silencio por el error de la reversión"
    )
    assert "El stock cambió" in str(excinfo.value.__cause__)

    fila_a_final = (
        service_client.table("stock_productos")
        .select("cantidad_comprometida")
        .eq("id", fila_a["id"])
        .execute()
        .data[0]
    )
    assert Decimal(str(fila_a_final["cantidad_comprometida"])) == Decimal("6"), (
        "en este escenario forzado la reversión de A también falla -- el compromiso real "
        "queda tal cual, que es justamente lo que el mensaje de error tiene que reflejar"
    )


@pytest.mark.integration
def test_liberar_compromisos_resta_lo_comprometido(
    service_client, seed_drogueria, seed_producto, seed_stock_factory
):
    fila = seed_stock_factory(seed_producto["id"], disponible="10")
    compromisos = stock.comprometer_stock_producto(
        service_client,
        producto_id=seed_producto["id"],
        drogueria_id=seed_drogueria["id"],
        cantidad=Decimal("6"),
    )

    stock.liberar_compromisos(service_client, compromisos)

    fila_final = (
        service_client.table("stock_productos")
        .select("cantidad_comprometida")
        .eq("id", fila["id"])
        .execute()
        .data[0]
    )
    assert Decimal(str(fila_final["cantidad_comprometida"])) == Decimal("0")


@pytest.mark.integration
def test_comprometer_stock_producto_concurrencia_no_sobrecompromete(
    service_client, seed_drogueria, seed_producto, seed_stock_factory
):
    """Dos requests simultáneos piden 6 unidades cada uno contra un stock de 10 libres
    (demanda total 12 > 10 disponibles). Solo uno debe lograr comprometer sus 6 unidades
    completas; el otro debe fallar limpio con ConflictError y dejar cantidad_comprometida
    sin pisar lo del ganador (nunca > 10, nunca corrupto)."""
    seed_stock_factory(seed_producto["id"], disponible="10")
    barrera = threading.Barrier(2)
    resultados: dict[str, Decimal] = {}
    errores: dict[str, Exception] = {}

    def _intentar(nombre: str) -> None:
        barrera.wait()
        try:
            compromisos = stock.comprometer_stock_producto(
                service_client,
                producto_id=seed_producto["id"],
                drogueria_id=seed_drogueria["id"],
                cantidad=Decimal("6"),
            )
            resultados[nombre] = sum((m for _, m in compromisos), Decimal("0"))
        except ConflictError as exc:
            errores[nombre] = exc

    hilos = [threading.Thread(target=_intentar, args=(nombre,)) for nombre in ("A", "B")]
    for hilo in hilos:
        hilo.start()
    for hilo in hilos:
        hilo.join()

    assert len(resultados) == 1, f"esperaba que solo uno de los dos comprometa: {resultados}"
    assert len(errores) == 1, f"esperaba que el otro falle por stock insuficiente: {errores}"
    assert next(iter(resultados.values())) == Decimal("6")

    fila_final = (
        service_client.table("stock_productos")
        .select("cantidad_comprometida")
        .eq("producto_id", seed_producto["id"])
        .execute()
        .data[0]
    )
    assert Decimal(str(fila_final["cantidad_comprometida"])) == Decimal("6")


@pytest.mark.integration
def test_comprometer_stock_producto_concurrencia_con_stock_suficiente_ambos_ganan(
    service_client, seed_drogueria, seed_producto, seed_stock_factory
):
    """Con stock de sobra para ambos pedidos concurrentes, ninguno debe fallar y el total
    comprometido debe ser exactamente la suma de los dos."""
    seed_stock_factory(seed_producto["id"], disponible="20")
    barrera = threading.Barrier(2)
    resultados: dict[str, Decimal] = {}
    errores: dict[str, Exception] = {}

    def _intentar(nombre: str) -> None:
        barrera.wait()
        try:
            compromisos = stock.comprometer_stock_producto(
                service_client,
                producto_id=seed_producto["id"],
                drogueria_id=seed_drogueria["id"],
                cantidad=Decimal("6"),
            )
            resultados[nombre] = sum((m for _, m in compromisos), Decimal("0"))
        except ConflictError as exc:
            errores[nombre] = exc

    hilos = [threading.Thread(target=_intentar, args=(nombre,)) for nombre in ("A", "B")]
    for hilo in hilos:
        hilo.start()
    for hilo in hilos:
        hilo.join()

    assert errores == {}
    assert len(resultados) == 2
    assert sum(resultados.values()) == Decimal("12")

    fila_final = (
        service_client.table("stock_productos")
        .select("cantidad_comprometida")
        .eq("producto_id", seed_producto["id"])
        .execute()
        .data[0]
    )
    assert Decimal(str(fila_final["cantidad_comprometida"])) == Decimal("12")
