"""Unit tests (sin red, sin fixture `service_client`) para el paginado de
`listar_terceros`. El fake client simula el límite por defecto de PostgREST
(1000 filas cuando no se pide `.range()` explícito) para reproducir el bug
real: sin paginación, una droguería con más de 1000 terceros pierde en
silencio todo lo que queda alfabéticamente después de la fila 1000."""

from typing import Any

from services.terceros.identidad import repository as repo

_LIMITE_POSTGREST_POR_DEFECTO = 1000


class _FakeResultado:
    def __init__(self, data: list[dict[str, Any]]) -> None:
        self.data = data


class _FakeQuery:
    def __init__(self, dataset: list[dict[str, Any]]) -> None:
        self._dataset = dataset
        self._eq: dict[str, Any] = {}
        self._is: dict[str, Any] = {}
        self._orden: str | None = None
        self._rango: tuple[int, int] | None = None

    def select(self, *_args: Any, **_kwargs: Any) -> "_FakeQuery":
        return self

    def eq(self, campo: str, valor: Any) -> "_FakeQuery":
        self._eq[campo] = valor
        return self

    def is_(self, campo: str, valor: Any) -> "_FakeQuery":
        self._is[campo] = valor
        return self

    def order(self, campo: str) -> "_FakeQuery":
        self._orden = campo
        return self

    def range(self, inicio: int, fin: int) -> "_FakeQuery":
        self._rango = (inicio, fin)
        return self

    def execute(self) -> _FakeResultado:
        filas = [
            f
            for f in self._dataset
            if all(f.get(k) == v for k, v in self._eq.items())
            and all(f.get(k) is v for k, v in self._is.items())
        ]
        if self._orden:
            filas = sorted(filas, key=lambda f: f[self._orden])

        if self._rango is not None:
            inicio, fin = self._rango
            filas = filas[inicio : fin + 1]
        else:
            # Comportamiento real de PostgREST/Supabase: sin `.range()` explícito,
            # el server igual corta al max-rows configurado (1000 por defecto).
            filas = filas[:_LIMITE_POSTGREST_POR_DEFECTO]

        return _FakeResultado(filas)


class _FakeClient:
    def __init__(self, dataset: list[dict[str, Any]]) -> None:
        self._dataset = dataset

    def table(self, _nombre: str) -> _FakeQuery:
        return _FakeQuery(self._dataset)


def _dataset_terceros(cantidad: int, *, drogueria_id: str = "drog-1") -> list[dict[str, Any]]:
    return [
        {
            "id": f"id-{i:05d}",
            "drogueria_id": drogueria_id,
            "razon_social": f"Tercero {i:05d}",
            "activo": True,
            "deleted_at": None,
            "clientes": [],
            "proveedores": [],
        }
        for i in range(cantidad)
    ]


def test_listar_terceros_no_trunca_droguerias_con_mas_de_mil_terceros():
    dataset = _dataset_terceros(1500)
    client = _FakeClient(dataset)

    filas = repo.listar_terceros(client, drogueria_id="drog-1", activo=None)

    assert len(filas) == 1500
    assert {f["id"] for f in filas} == {f["id"] for f in dataset}


def test_listar_terceros_respeta_el_filtro_de_drogueria_al_paginar():
    dataset = _dataset_terceros(1200, drogueria_id="drog-1") + _dataset_terceros(
        5, drogueria_id="drog-2"
    )
    client = _FakeClient(dataset)

    filas = repo.listar_terceros(client, drogueria_id="drog-1", activo=None)

    assert len(filas) == 1200
    assert all(f["drogueria_id"] == "drog-1" for f in filas)


def test_listar_terceros_con_menos_de_una_pagina_no_hace_de_mas():
    dataset = _dataset_terceros(3)
    client = _FakeClient(dataset)

    filas = repo.listar_terceros(client, drogueria_id="drog-1", activo=None)

    assert len(filas) == 3


def _dataset_roles(cantidad: int, *, drogueria_id: str = "drog-1") -> list[dict[str, Any]]:
    # Mismo problema real: services/presupuestacion/clientes usa
    # listar_clientes_con_tercero, así que una droguería con >1000 clientes
    # (ej. Nueva Era, con 2308) pierde exactamente el mismo tramo alfabético.
    return [
        {"id": f"id-{i:05d}", "drogueria_id": drogueria_id, "activo": True}
        for i in range(cantidad)
    ]


def test_listar_clientes_con_tercero_no_trunca_droguerias_con_mas_de_mil_clientes():
    dataset = _dataset_roles(2308)
    client = _FakeClient(dataset)

    filas = repo.listar_clientes_con_tercero(client, drogueria_id="drog-1", activo=None)

    assert len(filas) == 2308


def test_listar_proveedores_con_tercero_no_trunca_droguerias_con_mas_de_mil_proveedores():
    dataset = _dataset_roles(1800)
    client = _FakeClient(dataset)

    filas = repo.listar_proveedores_con_tercero(client, drogueria_id="drog-1", activo=None)

    assert len(filas) == 1800
