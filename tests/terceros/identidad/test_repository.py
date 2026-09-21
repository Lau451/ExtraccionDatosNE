"""Unit tests (sin red, sin fixture `service_client`) para el paginado de
`listar_terceros`. El fake client simula el límite por defecto de PostgREST
(1000 filas cuando no se pide `.range()` explícito) para reproducir el bug
real: sin paginación, una droguería con más de 1000 terceros pierde en
silencio todo lo que queda alfabéticamente después de la fila 1000."""

from typing import Any

from services.terceros.identidad import repository as repo

_LIMITE_POSTGREST_POR_DEFECTO = 1000


class _FakeResultado:
    def __init__(self, data: list[dict[str, Any]], count: int | None = None) -> None:
        self.data = data
        self.count = count


class _FakeQuery:
    def __init__(self, dataset: list[dict[str, Any]]) -> None:
        self._dataset = dataset
        self._eq: dict[str, Any] = {}
        self._is: dict[str, Any] = {}
        self._orden: str | None = None
        self._rango: tuple[int, int] | None = None
        self._or: str | None = None
        self._count: str | None = None
        self._embeds_inner: set[str] = set()

    def select(self, *args: Any, count: str | None = None, **_kwargs: Any) -> "_FakeQuery":
        # Emula lo suficiente de la sintaxis de embeds de PostgREST para probar
        # el filtro de rol 100% server-side: `clientes!inner(id)` en el string
        # de columnas fuerza INNER JOIN -- solo pasan filas con al menos una
        # fila relacionada, igual que hace PostgREST de verdad.
        self._count = count
        for columnas in args:
            for parte in columnas.split(","):
                parte = parte.strip()
                if "!inner" in parte:
                    self._embeds_inner.add(parte.split("!inner")[0].strip())
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

    def or_(self, filtro: str) -> "_FakeQuery":
        # Emula el formato PostgREST "col.ilike.%term%,col2.ilike.%term%,...":
        # alcanza para probar que el repository arma y aplica el filtro bien,
        # sin depender de la red.
        self._or = filtro
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
            # Solo se exige presencia para embeds que el dataset de test modela
            # de verdad (clave presente, aunque sea lista vacía) -- otros
            # fakes de este mismo archivo (ej. listar_clientes_con_tercero)
            # usan `!inner` con datasets planos que ni siquiera declaran esa
            # clave, y no están probando semántica de embed.
            and all(bool(f[embed]) for embed in self._embeds_inner if embed in f)
            and self._coincide_or(f)
        ]
        if self._orden:
            filas = sorted(filas, key=lambda f: f[self._orden])

        total = len(filas) if self._count == "exact" else None

        if self._rango is not None:
            inicio, fin = self._rango
            filas = filas[inicio : fin + 1]
        else:
            # Comportamiento real de PostgREST/Supabase: sin `.range()` explícito,
            # el server igual corta al max-rows configurado (1000 por defecto).
            filas = filas[:_LIMITE_POSTGREST_POR_DEFECTO]

        return _FakeResultado(filas, total)


class _FakeClient:
    def __init__(self, dataset: list[dict[str, Any]]) -> None:
        self._dataset = dataset
        self.llamadas_table = 0

    def table(self, _nombre: str) -> _FakeQuery:
        # Contador de round-trips: repo.listar_terceros (viejo, loop de a 1000)
        # llama `.table()` en cada vuelta del `while True`; el nuevo
        # `listar_terceros_paginado` server-side debe llamarlo una sola vez por
        # invocación -- ver test_listar_terceros_paginado_no_acumula_todo_antes_de_paginar.
        self.llamadas_table += 1
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


def test_listar_terceros_filtra_por_q_en_razon_social_cuit_o_codigo_interno():
    dataset = [
        {
            "id": "id-1",
            "drogueria_id": "drog-1",
            "razon_social": "Hospital Provincial Rosario",
            "cuit": "33685444459",
            "codigo_interno": "C996",
            "activo": True,
            "deleted_at": None,
            "clientes": [],
            "proveedores": [],
        },
        {
            "id": "id-2",
            "drogueria_id": "drog-1",
            "razon_social": "Farmacia del Centro",
            "cuit": "20111111112",
            "codigo_interno": "C100",
            "activo": True,
            "deleted_at": None,
            "clientes": [],
            "proveedores": [],
        },
    ]
    client = _FakeClient(dataset)

    por_codigo = repo.listar_terceros(client, drogueria_id="drog-1", activo=None, q="c996")
    por_razon_social = repo.listar_terceros(
        client, drogueria_id="drog-1", activo=None, q="hospital"
    )
    sin_match = repo.listar_terceros(client, drogueria_id="drog-1", activo=None, q="inexistente")

    assert [f["id"] for f in por_codigo] == ["id-1"]
    assert [f["id"] for f in por_razon_social] == ["id-1"]
    assert sin_match == []


# ---------------------------------------------------------------------------
# listar_terceros_paginado -- paginación y filtro de rol 100% server-side
# (odd/tasks/terceros-listado-paginacion-y-rol.md: bug de acumulación en
# Python -- sección 2 -- más la investigación de la sección 3 sobre si el
# filtro de rol también podía volverse server-side).
# ---------------------------------------------------------------------------


def _dataset_terceros_roles(
    cantidad: int,
    *,
    drogueria_id: str = "drog-1",
    con_cliente: set[int] = frozenset(),
    con_proveedor: set[int] = frozenset(),
) -> list[dict[str, Any]]:
    return [
        {
            "id": f"id-{i:05d}",
            "drogueria_id": drogueria_id,
            "razon_social": f"Tercero {i:05d}",
            "activo": True,
            "deleted_at": None,
            "clientes": [{"id": f"id-{i:05d}"}] if i in con_cliente else [],
            "proveedores": [{"id": f"id-{i:05d}"}] if i in con_proveedor else [],
        }
        for i in range(cantidad)
    ]


def test_listar_terceros_paginado_no_acumula_todo_antes_de_paginar():
    # RED original (tarea 3 del odd task): antes de este fix, esta función ni
    # existía en el repository -- el service traía TODO vía listar_terceros
    # (loop interno de a 1000) y recién ahí recortaba en Python. Con más
    # terceros que una página, esto tiene que hacer UNA sola consulta con
    # `.range()` + `count="exact"`, nunca acumular todo antes.
    dataset = _dataset_terceros_roles(120)
    client = _FakeClient(dataset)

    filas, total = repo.listar_terceros_paginado(
        client, drogueria_id="drog-1", activo=None, filtro_rol="todos", page=1, page_size=50
    )

    assert client.llamadas_table == 1
    assert total == 120
    assert len(filas) == 50
    assert [f["id"] for f in filas] == [f"id-{i:05d}" for i in range(50)]


def test_listar_terceros_paginado_pagina_intermedia_con_todos_los_roles():
    dataset = _dataset_terceros_roles(120)
    client = _FakeClient(dataset)

    filas, total = repo.listar_terceros_paginado(
        client, drogueria_id="drog-1", activo=None, filtro_rol="todos", page=3, page_size=50
    )

    assert client.llamadas_table == 1
    assert total == 120
    assert [f["id"] for f in filas] == [f"id-{i:05d}" for i in range(100, 120)]


def test_listar_terceros_paginado_filtra_por_q_server_side():
    dataset = [
        {
            "id": "id-1",
            "drogueria_id": "drog-1",
            "razon_social": "Hospital Provincial Rosario",
            "cuit": "33685444459",
            "codigo_interno": "C996",
            "activo": True,
            "deleted_at": None,
            "clientes": [],
            "proveedores": [],
        },
        {
            "id": "id-2",
            "drogueria_id": "drog-1",
            "razon_social": "Farmacia del Centro",
            "cuit": "20111111112",
            "codigo_interno": "C100",
            "activo": True,
            "deleted_at": None,
            "clientes": [],
            "proveedores": [],
        },
    ]
    client = _FakeClient(dataset)

    filas, total = repo.listar_terceros_paginado(client, drogueria_id="drog-1", activo=None, q="c996")

    assert client.llamadas_table == 1
    assert total == 1
    assert filas[0]["id"] == "id-1"


# -- filtro de rol server-side (sección 3 investigada: viable con `!inner` una
# vez que el filtro pasó a ser inclusivo -- ver comentario en repository.py) --


def test_listar_terceros_paginado_filtro_rol_clientes_incluye_los_que_tambien_son_proveedores():
    dataset = _dataset_terceros_roles(5, con_cliente={0, 2}, con_proveedor={2, 4})
    client = _FakeClient(dataset)

    filas, total = repo.listar_terceros_paginado(
        client, drogueria_id="drog-1", activo=None, filtro_rol="clientes", page=1, page_size=10
    )

    assert client.llamadas_table == 1
    assert total == 2
    assert {f["id"] for f in filas} == {"id-00000", "id-00002"}


def test_listar_terceros_paginado_filtro_rol_proveedores_incluye_los_que_tambien_son_clientes():
    dataset = _dataset_terceros_roles(5, con_cliente={0, 2}, con_proveedor={2, 4})
    client = _FakeClient(dataset)

    filas, total = repo.listar_terceros_paginado(
        client, drogueria_id="drog-1", activo=None, filtro_rol="proveedores", page=1, page_size=10
    )

    assert client.llamadas_table == 1
    assert total == 2
    assert {f["id"] for f in filas} == {"id-00002", "id-00004"}


def test_listar_terceros_paginado_filtro_rol_ambos_es_interseccion():
    dataset = _dataset_terceros_roles(5, con_cliente={0, 2}, con_proveedor={2, 4})
    client = _FakeClient(dataset)

    filas, total = repo.listar_terceros_paginado(
        client, drogueria_id="drog-1", activo=None, filtro_rol="ambos", page=1, page_size=10
    )

    assert client.llamadas_table == 1
    assert total == 1
    assert [f["id"] for f in filas] == ["id-00002"]


def test_listar_terceros_paginado_filtro_rol_se_pagina_server_side_tambien():
    # No solo filtra: pagina en el mismo request -- con más matches que
    # page_size, sigue sin acumular todo antes (misma query, un solo range()).
    dataset = _dataset_terceros_roles(60, con_cliente=set(range(60)))
    client = _FakeClient(dataset)

    filas, total = repo.listar_terceros_paginado(
        client, drogueria_id="drog-1", activo=None, filtro_rol="clientes", page=2, page_size=20
    )

    assert client.llamadas_table == 1
    assert total == 60
    assert [f["id"] for f in filas] == [f"id-{i:05d}" for i in range(20, 40)]
