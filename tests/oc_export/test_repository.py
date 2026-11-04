"""tests/oc_export/test_repository.py -- `listar_numeros_presupuesto` sin red: un
cliente falso registra los filtros y devuelve filas fijas por tabla."""

from services.presupuestacion.oc_export import repository as repo


class _Consulta:
    def __init__(self, cliente, tabla):
        self.cliente, self.tabla, self.filtros = cliente, tabla, []

    def select(self, columnas):
        self.filtros.append(("select", columnas))
        return self

    def in_(self, columna, valores):
        self.filtros.append(("in", columna, list(valores)))
        return self

    def eq(self, columna, valor):
        self.filtros.append(("eq", columna, valor))
        return self

    def order(self, columna, **kw):
        self.filtros.append(("order", columna))
        return self

    def execute(self):
        self.cliente.consultas.append((self.tabla, self.filtros))
        valores = next(f[2] for f in self.filtros if f[0] == "in")
        filas = [f for f in self.cliente.datos[self.tabla] if f[self.cliente.clave[self.tabla]] in valores]
        return type("R", (), {"data": filas})()


class _Cliente:
    clave = {"presupuesto_items": "id", "presupuesto_legacy_map": "presupuesto_id"}

    def __init__(self, datos):
        self.datos, self.consultas = datos, []

    def table(self, tabla):
        return _Consulta(self, tabla)


def test_mapea_cada_item_al_codigo_legacy_de_su_presupuesto():
    cliente = _Cliente(
        {
            "presupuesto_items": [
                {"id": "pi-1", "presupuesto_id": "pre-1"},
                {"id": "pi-2", "presupuesto_id": "pre-1"},
                {"id": "pi-3", "presupuesto_id": "pre-2"},
            ],
            # Ya ordenadas por importado_at (lo hace la query): gana la primera.
            "presupuesto_legacy_map": [
                {"presupuesto_id": "pre-1", "codigo_legacy": "P-100"},
                {"presupuesto_id": "pre-1", "codigo_legacy": "P-200"},
            ],
        }
    )

    numeros = repo.listar_numeros_presupuesto(
        cliente, presupuesto_item_ids=["pi-1", "pi-2", "pi-3", "pi-1"], drogueria_id="d1"
    )

    assert numeros == {"pi-1": "P-100", "pi-2": "P-100"}  # pi-3: presupuesto sin legacy map
    (items, filtros_items), (mapa, filtros_mapa) = cliente.consultas
    assert items == "presupuesto_items"
    assert ("in", "id", ["pi-1", "pi-2", "pi-3"]) in filtros_items
    assert ("eq", "drogueria_id", "d1") in filtros_items
    assert mapa == "presupuesto_legacy_map"
    assert ("in", "presupuesto_id", ["pre-1", "pre-2"]) in filtros_mapa
    assert ("eq", "drogueria_id", "d1") in filtros_mapa
    assert ("order", "importado_at") in filtros_mapa


def test_sin_items_no_consulta():
    cliente = _Cliente({"presupuesto_items": [], "presupuesto_legacy_map": []})
    assert repo.listar_numeros_presupuesto(cliente, presupuesto_item_ids=[], drogueria_id="d1") == {}
    assert cliente.consultas == []
