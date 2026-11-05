"""tests/integracion_progress/registro/test_repository.py -- consultas PostgREST del
registro de archivos (filtros por droguería, orden, paginación y CAS por estado,
intentos y updated_at). El CAS de `reclamar` también se prueba contra Postgres real
(integración contra TEST)."""

import hashlib
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

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
        cliente,
        drogueria_id="d1",
        registro_id="r1",
        campos={"estado": "error"},
        estado_esperado="recibido",
        intentos_esperados=2,
    )

    assert _llamadas(consulta, "eq") == [
        ("id", "r1"),
        ("drogueria_id", "d1"),
        ("estado", "recibido"),
        ("intentos", 2),
    ]
    assert resultado is None


def test_actualizar_sin_cas_filtra_id_y_drogueria():
    cliente, consulta = _cliente_con([{"id": "r1"}])

    fila = repo.actualizar(cliente, drogueria_id="d1", registro_id="r1", campos={"filas": 1})

    assert _llamadas(consulta, "eq") == [("id", "r1"), ("drogueria_id", "d1")]
    assert _llamadas(consulta, "update") == [({"filas": 1},)]
    assert fila == {"id": "r1"}


def test_buscar_por_id_filtra_por_drogueria():
    cliente, consulta = _cliente_con([])

    assert repo.buscar_por_id(cliente, drogueria_id="d1", registro_id="r1") is None
    assert _llamadas(consulta, "eq") == [("id", "r1"), ("drogueria_id", "d1")]


def test_reclamar_filtra_drogueria_estado_y_updated_at():
    cliente, consulta = _cliente_con([])
    momento = datetime(2026, 11, 4, 12, 0, 0, 123456, tzinfo=timezone.utc)

    resultado = repo.reclamar(
        cliente,
        drogueria_id="d1",
        registro_id="r1",
        estado_esperado="error",
        updated_at_esperado=momento,
    )

    assert _llamadas(consulta, "update") == [({"estado": "recibido"},)]
    assert _llamadas(consulta, "eq") == [
        ("id", "r1"),
        ("drogueria_id", "d1"),
        ("estado", "error"),
        ("updated_at", "2026-11-04T12:00:00.123456+00:00"),
    ]
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


# --- integración contra TEST ---------------------------------------------------


@pytest.mark.integration
def test_reclamar_es_un_cas_sobre_updated_at_en_postgres(
    service_client, seed_drogueria, seed_usuario_sistema
):
    """R3-cas-updated-at-unproved (L11): el trigger trg_progress_archivos_updated_at
    renueva updated_at, así que un segundo reclamo con el updated_at leído antes del
    primero no actualiza nada, aunque el estado esperado coincida."""
    drogueria_id = seed_drogueria["id"]
    fila = repo.insertar(
        service_client,
        {
            "drogueria_id": drogueria_id,
            "sentido": "entrada",
            "tipo": "presupuestos",
            "nombre_archivo": "CAS_TEST.csv",
            "sha256": hashlib.sha256(uuid.uuid4().bytes).hexdigest(),
            "origen": "carpeta",
            "estado": "error",
            "usuario_id": seed_usuario_sistema["id"],
        },
    )
    try:
        leido = datetime.fromisoformat(fila["updated_at"])

        primero = repo.reclamar(
            service_client,
            drogueria_id=drogueria_id,
            registro_id=fila["id"],
            estado_esperado="error",
            updated_at_esperado=leido,
        )
        assert primero is not None
        assert primero["estado"] == "recibido"
        assert datetime.fromisoformat(primero["updated_at"]) > leido

        # Mismo estado que el reclamo ganador dejó, updated_at viejo: no actualiza.
        segundo = repo.reclamar(
            service_client,
            drogueria_id=drogueria_id,
            registro_id=fila["id"],
            estado_esperado="recibido",
            updated_at_esperado=leido,
        )
        # El reclamo perdido del otro proceso (estado 'error' ya no vigente).
        tercero = repo.reclamar(
            service_client,
            drogueria_id=drogueria_id,
            registro_id=fila["id"],
            estado_esperado="error",
            updated_at_esperado=leido,
        )
        assert segundo is None
        assert tercero is None
        actual = repo.buscar_por_id(
            service_client, drogueria_id=drogueria_id, registro_id=fila["id"]
        )
        assert actual["estado"] == "recibido"
        assert actual["updated_at"] == primero["updated_at"]
    finally:
        service_client.table("progress_archivos").delete().eq("id", fila["id"]).execute()
