"""tests/compromisos/test_repository.py -- filtros de la consulta a v_compromisos_entregas."""

from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock

from services.presupuestacion.compromisos import repository as repo


class _ConsultaFalsa:
    """Query builder falso: registra filtros/orden y sirve `filas` por ventanas de `.range()`."""

    def __init__(self, filas):
        self._filas = filas
        self.eq_calls, self.gte_calls, self.lte_calls, self.order_calls = [], [], [], []
        self.ranges = []
        self._rango = None

    def select(self, *_):
        return self

    def eq(self, *args):
        self.eq_calls.append(args)
        return self

    def gte(self, *args):
        self.gte_calls.append(args)
        return self

    def lte(self, *args):
        self.lte_calls.append(args)
        return self

    def order(self, *args, **kwargs):
        self.order_calls.append(args)
        return self

    def range(self, inicio, fin):
        self.ranges.append((inicio, fin))
        self._rango = (inicio, fin)
        return self

    def execute(self):
        inicio, fin = self._rango
        return SimpleNamespace(data=self._filas[inicio : fin + 1])


def _cliente_con(filas):
    consulta = _ConsultaFalsa(filas)
    cliente = MagicMock()
    cliente.table.return_value = consulta
    return cliente, consulta


def test_filtra_por_drogueria_y_tope_superior():
    cliente, consulta = _cliente_con([{"numero_oc": "OC-1"}])

    filas = repo.listar_compromisos(
        cliente, drogueria_id="d1", desde=None, hasta=date(2026, 12, 31)
    )

    cliente.table.assert_called_once_with("v_compromisos_entregas")
    assert consulta.eq_calls == [("drogueria_id", "d1")]
    assert consulta.lte_calls == [("fecha_entrega_planificada", "2026-12-31")]
    assert consulta.gte_calls == []
    assert filas == [{"numero_oc": "OC-1"}]


def test_con_desde_agrega_cota_inferior():
    cliente, consulta = _cliente_con([])

    repo.listar_compromisos(
        cliente, drogueria_id="d1", desde=date(2026, 11, 1), hasta=date(2026, 12, 31)
    )

    assert consulta.gte_calls == [("fecha_entrega_planificada", "2026-11-01")]


def test_ordena_por_clave_estable_en_la_query():
    cliente, consulta = _cliente_con([])

    repo.listar_compromisos(cliente, drogueria_id="d1", desde=None, hasta=date(2026, 12, 31))

    assert [c[0] for c in consulta.order_calls] == [
        "fecha_entrega_planificada",
        "orden_compra_id",
        "numero_entrega",
        "numero_renglon",
    ]


def test_pagina_hasta_una_pagina_corta(monkeypatch):
    monkeypatch.setattr(repo, "_TAMANO_PAGINA", 2)
    filas = [{"n": i} for i in range(5)]
    cliente, consulta = _cliente_con(filas)

    resultado = repo.listar_compromisos(
        cliente, drogueria_id="d1", desde=None, hasta=date(2026, 12, 31)
    )

    assert resultado == filas
    assert consulta.ranges == [(0, 1), (2, 3), (4, 5)]


def test_pagina_exacta_pide_una_mas_y_corta_en_vacia(monkeypatch):
    monkeypatch.setattr(repo, "_TAMANO_PAGINA", 2)
    filas = [{"n": i} for i in range(4)]
    cliente, consulta = _cliente_con(filas)

    resultado = repo.listar_compromisos(
        cliente, drogueria_id="d1", desde=None, hasta=date(2026, 12, 31)
    )

    assert resultado == filas
    assert consulta.ranges == [(0, 1), (2, 3), (4, 5)]
