"""tests/integracion_progress/registro/test_repository.py -- consultas PostgREST del
registro de archivos (filtros, orden, paginación y CAS por intentos)."""

from types import SimpleNamespace
from unittest.mock import MagicMock

from services.integracion_progress.registro import repository as repo


class _ConsultaFalsa:
    def __init__(self, filas):
        self._filas = filas
        self.llamadas: list[tuple] = []

    def __getattr__(self, nombre):
        def _registrar(*args, **kwargs):
            self.llamadas.append((nombre, args, kwargs))
            return self

        return _registrar

    def execute(self):
        return SimpleNamespace(data=self._filas)


def _cliente_con(filas):
    consulta = _ConsultaFalsa(filas)
    cliente = MagicMock()
    cliente.table.return_value = consulta
    return cliente, consulta


def _llamadas(consulta, nombre):
    return [args for n, args, _ in consulta.llamadas if n == nombre]


def test_listar_filtra_por_drogueria_sentido_estado_y_pagina():
    cliente, consulta = _cliente_con([{"id": "a"}])

    filas = repo.listar(
        cliente, drogueria_id="d1", sentido="entrada", estado="error", limit=20, offset=40
    )

    cliente.table.assert_called_once_with("progress_archivos")
    assert _llamadas(consulta, "eq") == [
        ("drogueria_id", "d1"),
        ("sentido", "entrada"),
        ("estado", "error"),
    ]
    assert _llamadas(consulta, "range") == [(40, 59)]
    assert [n for n, _, kw in consulta.llamadas if n == "order" and kw == {"desc": True}] == ["order"]
    assert filas == [{"id": "a"}]


def test_listar_sin_filtros_opcionales_solo_filtra_drogueria():
    cliente, consulta = _cliente_con([])

    repo.listar(cliente, drogueria_id="d1", sentido=None, estado=None, limit=50, offset=0)

    assert _llamadas(consulta, "eq") == [("drogueria_id", "d1")]
    assert _llamadas(consulta, "range") == [(0, 49)]


def test_actualizar_con_intentos_esperados_agrega_el_cas():
    cliente, consulta = _cliente_con([])

    resultado = repo.actualizar(
        cliente, registro_id="r1", campos={"estado": "error"}, intentos_esperados=2
    )

    assert _llamadas(consulta, "eq") == [("id", "r1"), ("intentos", 2)]
    assert resultado is None


def test_buscar_por_contenido_filtra_la_clave_unica():
    cliente, consulta = _cliente_con([{"id": "a"}])

    fila = repo.buscar_por_contenido(
        cliente, drogueria_id="d1", sentido="entrada", tipo="presupuestos", sha256="f" * 64
    )

    assert _llamadas(consulta, "eq") == [
        ("drogueria_id", "d1"),
        ("sentido", "entrada"),
        ("tipo", "presupuestos"),
        ("sha256", "f" * 64),
    ]
    assert fila == {"id": "a"}
