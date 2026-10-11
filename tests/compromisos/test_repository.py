"""tests/compromisos/test_repository.py -- filtros de la consulta a v_compromisos_entregas."""

from datetime import date
from unittest.mock import MagicMock

from services.presupuestacion.compromisos import repository as repo


def _cliente_con_cadena():
    cliente = MagicMock()
    consulta = cliente.table.return_value.select.return_value
    consulta.eq.return_value = consulta
    consulta.gte.return_value = consulta
    consulta.lte.return_value = consulta
    consulta.execute.return_value.data = [{"numero_oc": "OC-1"}]
    return cliente, consulta


def test_filtra_por_drogueria_y_tope_superior():
    cliente, consulta = _cliente_con_cadena()

    filas = repo.listar_compromisos(
        cliente, drogueria_id="d1", desde=None, hasta=date(2026, 12, 31)
    )

    cliente.table.assert_called_once_with("v_compromisos_entregas")
    consulta.eq.assert_called_once_with("drogueria_id", "d1")
    consulta.lte.assert_called_once_with("fecha_entrega_planificada", "2026-12-31")
    consulta.gte.assert_not_called()
    assert filas == [{"numero_oc": "OC-1"}]


def test_con_desde_agrega_cota_inferior():
    cliente, consulta = _cliente_con_cadena()

    repo.listar_compromisos(
        cliente, drogueria_id="d1", desde=date(2026, 11, 1), hasta=date(2026, 12, 31)
    )

    consulta.gte.assert_called_once_with("fecha_entrega_planificada", "2026-11-01")
