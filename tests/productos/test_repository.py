"""Unit tests (sin red) para services.productos.repository.listar_productos_paginado.
Mismo criterio que tests/terceros/identidad/test_repository.py: un fake client
que emula lo suficiente de PostgREST (filtros, `.or_()`, `.range()` y el
`count="exact"` que pide `select(..., count=...)`) para probar que el
repository arma la query y pagina bien, sin pegarle a la red."""

from typing import Any

from services.productos import repository as repo


class _FakeResultado:
    def __init__(self, data: list[dict[str, Any]], count: int | None) -> None:
        self.data = data
        self.count = count


class _FakeQuery:
    def __init__(self, dataset: list[dict[str, Any]]) -> None:
        self._dataset = dataset
        self._eq: dict[str, Any] = {}
        self._is: dict[str, Any] = {}
        self._or: str | None = None
        self._orden: str | None = None
        self._rango: tuple[int, int] | None = None
        self._count: str | None = None

    def select(self, *_args: Any, count: str | None = None, **_kwargs: Any) -> "_FakeQuery":
        self._count = count
        return self

    def eq(self, campo: str, valor: Any) -> "_FakeQuery":
        self._eq[campo] = valor
        return self

    def is_(self, campo: str, valor: Any) -> "_FakeQuery":
        self._is[campo] = valor
        return self

    def or_(self, filtro: str) -> "_FakeQuery":
        self._or = filtro
        return self

    def order(self, campo: str) -> "_FakeQuery":
        self._orden = campo
        return self

    def range(self, inicio: int, fin: int) -> "_FakeQuery":
        self._rango = (inicio, fin)
        return self

    def _coincide_or(self, fila: dict[str, Any]) -> bool:
        if self._or is None:
            return True
        for condicion in self._or.split(","):
            campo, _, resto = condicion.partition(".ilike.")
            termino = resto.strip("%").lower()
            valor = str(fila.get(campo) or "").lower()
            if termino in valor:
                return True
        return False

    def execute(self) -> _FakeResultado:
        filas = [
            f
            for f in self._dataset
            if all(f.get(k) == v for k, v in self._eq.items())
            and all(f.get(k) is v for k, v in self._is.items())
            and self._coincide_or(f)
        ]
        if self._orden:
            filas = sorted(filas, key=lambda f: f[self._orden])
        total = len(filas) if self._count == "exact" else None
        if self._rango is not None:
            inicio, fin = self._rango
            filas = filas[inicio : fin + 1]
        return _FakeResultado(filas, total)


class _FakeClient:
    def __init__(self, dataset: list[dict[str, Any]]) -> None:
        self._dataset = dataset

    def table(self, _nombre: str) -> _FakeQuery:
        return _FakeQuery(self._dataset)


def _dataset_productos(cantidad: int, *, drogueria_id: str = "drog-1") -> list[dict[str, Any]]:
    return [
        {
            "id": f"id-{i:05d}",
            "drogueria_id": drogueria_id,
            "nombre": f"Producto {i:05d}",
            "codigo_interno": f"COD{i:05d}",
            "activo": True,
            "deleted_at": None,
            "categoria_id": None,
            "clasificacion": None,
        }
        for i in range(cantidad)
    ]


def test_listar_productos_paginado_devuelve_total_exacto_y_una_pagina():
    dataset = _dataset_productos(7144)
    client = _FakeClient(dataset)

    items, total = repo.listar_productos_paginado(
        client, drogueria_id="drog-1", page=1, page_size=50
    )

    assert total == 7144
    assert len(items) == 50
    assert items[0]["id"] == "id-00000"


def test_listar_productos_paginado_pagina_intermedia():
    dataset = _dataset_productos(120)
    client = _FakeClient(dataset)

    items, total = repo.listar_productos_paginado(
        client, drogueria_id="drog-1", page=3, page_size=50
    )

    assert total == 120
    assert [i["id"] for i in items] == [f"id-{n:05d}" for n in range(100, 120)]


def test_listar_productos_paginado_filtra_por_q_y_el_total_refleja_el_filtro():
    dataset = _dataset_productos(10)
    dataset[3]["nombre"] = "Amoxicilina 500mg"
    client = _FakeClient(dataset)

    items, total = repo.listar_productos_paginado(
        client, drogueria_id="drog-1", q="amoxicilina", page=1, page_size=50
    )

    assert total == 1
    assert items[0]["nombre"] == "Amoxicilina 500mg"


def test_listar_productos_paginado_respeta_categoria_y_clasificacion():
    dataset = _dataset_productos(5)
    dataset[0]["categoria_id"] = "cat-1"
    dataset[0]["clasificacion"] = "medicamento"
    client = _FakeClient(dataset)

    items, total = repo.listar_productos_paginado(
        client, drogueria_id="drog-1", categoria_id="cat-1", clasificacion="medicamento"
    )

    assert total == 1
    assert items[0]["id"] == "id-00000"
