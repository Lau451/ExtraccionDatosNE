"""La ventana de PCPs por vencer arranca en la fecha de Argentina, no la del
servidor (`reloj_noche_argentina`: 22:30 del 8/11 en Buenos Aires)."""

from services.pcp.sugerencias import repository


class _Consulta:
    def __init__(self, filtros: list[tuple[str, str, object]]):
        self._filtros = filtros

    def gte(self, columna, valor):
        self._filtros.append(("gte", columna, valor))
        return self

    def lte(self, columna, valor):
        self._filtros.append(("lte", columna, valor))
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


def test_pcp_por_vencer_usa_la_fecha_de_argentina(reloj_noche_argentina):
    cliente = _Cliente()

    repository.listar_pcp_abiertos_por_vencer(cliente, drogueria_id="d", dias=7)

    assert cliente.filtros == [
        ("gte", "fecha_entrega_solicitada", "2026-11-08"),
        ("lte", "fecha_entrega_solicitada", "2026-11-15"),
    ]
