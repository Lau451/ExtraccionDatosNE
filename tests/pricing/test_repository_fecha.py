"""La vigencia de precios se mide con la fecha de Argentina, no la del servidor.

El reloj queda a las 22:30 del 8/11 en Buenos Aires (`reloj_noche_argentina`):
un precio que vence el 8/11 sigue vigente y la ventana de mercado arranca desde
el 8/11.
"""

from decimal import Decimal

from services.presupuestacion.pricing import repository


class _Consulta:
    def __init__(self, filtros: list[tuple[str, str, object]]):
        self._filtros = filtros

    def gte(self, columna, valor):
        self._filtros.append(("gte", columna, valor))
        return self

    def __getattr__(self, _nombre):
        return lambda *args, **kwargs: self

    def execute(self):
        return type("Resultado", (), {"data": []})()


class _Cliente:
    def __init__(self):
        self.filtros: list[tuple[str, str, object]] = []

    def table(self, _nombre):
        return _Consulta(self.filtros)


def test_precio_especial_puntual_usa_la_fecha_de_argentina(reloj_noche_argentina):
    cliente = _Cliente()

    repository.buscar_precio_especial_puntual(cliente, item_proceso_id="i", cantidad=Decimal("1"))

    assert cliente.filtros == [("gte", "mantenimiento_hasta", "2026-11-08")]


def test_precio_especial_general_usa_la_fecha_de_argentina(reloj_noche_argentina):
    cliente = _Cliente()

    repository.buscar_precio_especial_general(
        cliente, producto_id="p", drogueria_id="d", cantidad=Decimal("1")
    )

    assert cliente.filtros == [("gte", "mantenimiento_hasta", "2026-11-08")]


def test_ventana_de_precio_mercado_arranca_desde_la_fecha_de_argentina(reloj_noche_argentina):
    cliente = _Cliente()

    repository.buscar_precio_mercado(cliente, producto_id="p", drogueria_id="d", meses_ventana=6)

    assert cliente.filtros == [("gte", "ultima_muestra", "2026-05-08")]
