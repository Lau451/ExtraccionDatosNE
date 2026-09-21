"""Unit tests (sin red) para services.terceros.identidad.service.listar_terceros_paginado.

Desde el fix de paginación/rol 100% server-side (odd/tasks/
terceros-listado-paginacion-y-rol.md), esta función es un wrapper fino sobre
repo.listar_terceros_paginado -- esa función arma la query real contra
PostgREST y ahí es donde vive la lógica de paginado y filtro de rol (probada
sin red en tests/terceros/identidad/test_repository.py, y contra Postgres
real en tests/terceros/identidad/test_service.py). Acá solo se prueba que el
service reenvía los parámetros correctos al repository y aplica
`_con_flags_de_rol` sobre lo que devuelve."""

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
def repo_listar_terceros_paginado_mock(monkeypatch: pytest.MonkeyPatch):
    llamadas: list[dict[str, Any]] = []

    def _fake(
        client,
        *,
        drogueria_id,
        activo=None,
        q=None,
        filtro_rol="todos",
        page=1,
        page_size=50,
    ):
        llamadas.append(
            {
                "drogueria_id": drogueria_id,
                "activo": activo,
                "q": q,
                "filtro_rol": filtro_rol,
                "page": page,
                "page_size": page_size,
            }
        )
        return _fake.filas, _fake.total

    _fake.filas = []
    _fake.total = 0
    monkeypatch.setattr(service.repo, "listar_terceros_paginado", _fake)
    return _fake, llamadas


def test_reenvia_todos_los_parametros_al_repository(repo_listar_terceros_paginado_mock):
    fake, llamadas = repo_listar_terceros_paginado_mock
    fake.filas = []
    fake.total = 0

    service.listar_terceros_paginado(
        client=object(),
        drogueria_id="drog-1",
        activo=False,
        q="hospital",
        filtro_rol="clientes",
        page=2,
        page_size=10,
    )

    assert llamadas == [
        {
            "drogueria_id": "drog-1",
            "activo": False,
            "q": "hospital",
            "filtro_rol": "clientes",
            "page": 2,
            "page_size": 10,
        }
    ]


def test_usa_los_defaults_esperados_cuando_no_se_pasan_parametros(
    repo_listar_terceros_paginado_mock,
):
    fake, llamadas = repo_listar_terceros_paginado_mock

    service.listar_terceros_paginado(client=object(), drogueria_id="drog-1")

    assert llamadas == [
        {
            "drogueria_id": "drog-1",
            "activo": True,
            "q": None,
            "filtro_rol": "todos",
            "page": 1,
            "page_size": 50,
        }
    ]


def test_devuelve_el_total_tal_como_lo_da_el_repository(repo_listar_terceros_paginado_mock):
    fake, _ = repo_listar_terceros_paginado_mock
    fake.filas = [_tercero("id-1")]
    fake.total = 5541

    _, total = service.listar_terceros_paginado(client=object(), drogueria_id="drog-1")

    assert total == 5541


def test_items_devueltos_incluyen_flags_de_rol_y_no_los_arrays_crudos(
    repo_listar_terceros_paginado_mock,
):
    fake, _ = repo_listar_terceros_paginado_mock
    fake.filas = [_tercero("id-1", cliente=True, proveedor=True)]
    fake.total = 1

    items, _ = service.listar_terceros_paginado(client=object(), drogueria_id="drog-1")

    assert items[0]["tiene_rol_cliente"] is True
    assert items[0]["tiene_rol_proveedor"] is True
    assert "clientes" not in items[0]
    assert "proveedores" not in items[0]


def test_items_sin_ningun_rol_traen_flags_en_false(repo_listar_terceros_paginado_mock):
    fake, _ = repo_listar_terceros_paginado_mock
    fake.filas = [_tercero("id-1")]
    fake.total = 1

    items, _ = service.listar_terceros_paginado(client=object(), drogueria_id="drog-1")

    assert items[0]["tiene_rol_cliente"] is False
    assert items[0]["tiene_rol_proveedor"] is False
