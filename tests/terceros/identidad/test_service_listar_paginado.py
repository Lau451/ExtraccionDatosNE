"""Unit tests (sin red) para services.terceros.identidad.service.listar_terceros_paginado:
paginado y filtro de rol son lógica pura de Python sobre lo que ya trajo el
repository, así que se prueban con un `repo.listar_terceros` mockeado en vez
de pegarle a la DB real (esa parte -- el filtro `q` contra Postgres -- ya la
cubren los tests de integración de test_service.py)."""

from typing import Any

import pytest

from services.terceros.identidad import service


def _tercero(id_: str, *, cliente: bool = False, proveedor: bool = False) -> dict[str, Any]:
    return {
        "id": id_,
        "razon_social": f"Tercero {id_}",
        "clientes": [{"id": id_}] if cliente else [],
        "proveedores": [{"id": id_}] if proveedor else [],
    }


@pytest.fixture
def repo_listar_terceros_mock(monkeypatch: pytest.MonkeyPatch):
    llamadas: list[dict[str, Any]] = []

    def _fake(client, *, drogueria_id, activo=None, q=None):
        llamadas.append({"drogueria_id": drogueria_id, "activo": activo, "q": q})
        return _fake.filas

    _fake.filas = []
    monkeypatch.setattr(service.repo, "listar_terceros", _fake)
    return _fake, llamadas


def test_pagina_el_resultado_ya_traido_del_repository(repo_listar_terceros_mock):
    fake, _ = repo_listar_terceros_mock
    fake.filas = [_tercero(f"id-{i}") for i in range(25)]

    items, total = service.listar_terceros_paginado(
        client=object(), drogueria_id="drog-1", page=2, page_size=10
    )

    assert total == 25
    assert [i["id"] for i in items] == [f"id-{i}" for i in range(10, 20)]


def test_ultima_pagina_parcial_no_rompe(repo_listar_terceros_mock):
    fake, _ = repo_listar_terceros_mock
    fake.filas = [_tercero(f"id-{i}") for i in range(25)]

    items, total = service.listar_terceros_paginado(
        client=object(), drogueria_id="drog-1", page=3, page_size=10
    )

    assert total == 25
    assert [i["id"] for i in items] == [f"id-{i}" for i in range(20, 25)]


def test_pagina_fuera_de_rango_devuelve_vacio_no_error(repo_listar_terceros_mock):
    fake, _ = repo_listar_terceros_mock
    fake.filas = [_tercero(f"id-{i}") for i in range(5)]

    items, total = service.listar_terceros_paginado(
        client=object(), drogueria_id="drog-1", page=99, page_size=10
    )

    assert total == 5
    assert items == []


def test_filtro_rol_clientes_excluye_los_que_tambien_son_proveedores(repo_listar_terceros_mock):
    fake, _ = repo_listar_terceros_mock
    fake.filas = [
        _tercero("solo-cliente", cliente=True),
        _tercero("solo-proveedor", proveedor=True),
        _tercero("ambos", cliente=True, proveedor=True),
        _tercero("sin-rol"),
    ]

    items, total = service.listar_terceros_paginado(
        client=object(), drogueria_id="drog-1", filtro_rol="clientes", page=1, page_size=10
    )

    assert total == 1
    assert [i["id"] for i in items] == ["solo-cliente"]


def test_filtro_rol_ambos_solo_deja_los_que_tienen_los_dos_roles(repo_listar_terceros_mock):
    fake, _ = repo_listar_terceros_mock
    fake.filas = [
        _tercero("solo-cliente", cliente=True),
        _tercero("ambos", cliente=True, proveedor=True),
    ]

    items, total = service.listar_terceros_paginado(
        client=object(), drogueria_id="drog-1", filtro_rol="ambos", page=1, page_size=10
    )

    assert total == 1
    assert [i["id"] for i in items] == ["ambos"]


def test_total_refleja_el_filtro_de_rol_no_el_total_sin_filtrar(repo_listar_terceros_mock):
    fake, _ = repo_listar_terceros_mock
    fake.filas = [_tercero(f"id-{i}", cliente=(i % 2 == 0)) for i in range(10)]

    _, total = service.listar_terceros_paginado(
        client=object(), drogueria_id="drog-1", filtro_rol="clientes", page=1, page_size=3
    )

    assert total == 5


def test_reenvia_q_y_activo_al_repository(repo_listar_terceros_mock):
    fake, llamadas = repo_listar_terceros_mock
    fake.filas = []

    service.listar_terceros_paginado(
        client=object(), drogueria_id="drog-1", activo=False, q="hospital", page=1, page_size=10
    )

    assert llamadas == [{"drogueria_id": "drog-1", "activo": False, "q": "hospital"}]


def test_items_devueltos_incluyen_flags_de_rol(repo_listar_terceros_mock):
    fake, _ = repo_listar_terceros_mock
    fake.filas = [_tercero("id-1", cliente=True, proveedor=True)]

    items, _ = service.listar_terceros_paginado(client=object(), drogueria_id="drog-1")

    assert items[0]["tiene_rol_cliente"] is True
    assert items[0]["tiene_rol_proveedor"] is True
    assert "clientes" not in items[0]
    assert "proveedores" not in items[0]
