"""tests/oc_resumen/test_service.py -- resumen de solo lectura de una OC
(odd/tasks/oc-resumen.md, T1). Unit tests con el repository mockeado."""

from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from services.presupuestacion.core.exceptions import NotFoundError
from services.presupuestacion.oc_resumen import repository as repo
from services.presupuestacion.oc_resumen import service


OC_ID = "11111111-1111-1111-1111-111111111111"


def _oc(**overrides) -> dict:
    base = {
        "id": "oc-1",
        "drogueria_id": "d1",
        "cliente_id": "cli-1",
        "numero_oc": "OC-1",
        "fecha_emision": "2026-10-01",
        "fecha_entrega_estimada": "2026-11-01",
        "direccion_entrega": "Calle 123",
        "notas": "Entregar por la tarde",
        "estado": "confirmada",
        "version_numero": 2,
        "monto_total": "150.00",
        "exportado_at": None,
        "exportado_por": None,
        "archivo_exportado": None,
        "usuarios": None,
        "clientes": {"terceros": {"razon_social": "Hospital Test", "cuit": "30712345678"}},
    }
    base.update(overrides)
    return base


def _item(id_: str, numero_renglon: int, **overrides) -> dict:
    base = {
        "id": id_,
        "numero_renglon": numero_renglon,
        "numero_renglon_documento": None,
        "descripcion": f"Renglón {numero_renglon}",
        "cantidad": "10",
        "precio_unitario": "5.00",
        "monto_total": "50.00",
        "producto_id": None,
        "presupuesto_item_id": None,
        "vinculo_descartado": False,
    }
    base.update(overrides)
    return base


def _parchar(monkeypatch, *, oc, items=(), productos=(), entregas=(), entregas_items=()):
    monkeypatch.setattr(repo, "buscar_orden_compra", lambda client, **kw: oc)
    monkeypatch.setattr(repo, "listar_oc_items", lambda client, **kw: list(items))
    monkeypatch.setattr(repo, "listar_productos_por_ids", lambda client, **kw: list(productos))
    monkeypatch.setattr(repo, "listar_entregas_oc", lambda client, **kw: list(entregas))
    monkeypatch.setattr(repo, "listar_entregas_oc_items", lambda client, **kw: list(entregas_items))


def _resumen(**kw):
    return service.obtener_resumen(MagicMock(), orden_compra_id=OC_ID, drogueria_id="d1", **kw)


def test_camino_feliz_arma_cabecera_cliente_renglones_entregas_y_exportacion(monkeypatch):
    oc = _oc(
        exportado_at="2026-10-05T12:00:00+00:00",
        exportado_por="11111111-1111-1111-1111-111111111111",
        archivo_exportado="oc-1.txt",
        usuarios={"nombre": "Ana", "apellido": "Pérez"},
    )
    items = [
        _item("i1", 1, numero_renglon_documento="10", producto_id="p1", presupuesto_item_id="pi-1"),
        _item("i2", 2, vinculo_descartado=True),
        _item("i3", 3),
    ]
    _parchar(
        monkeypatch,
        oc=oc,
        items=items,
        productos=[{"id": "p1", "codigo_interno": "COD-1", "nombre": "Producto Uno"}],
        entregas=[
            {"id": "e1", "numero_entrega": 1, "fecha_entrega_planificada": "2026-11-01", "estado": "pendiente"},
            {"id": "e2", "numero_entrega": 2, "fecha_entrega_planificada": None, "estado": "pendiente"},
        ],
        entregas_items=[
            {"entrega_oc_id": "e1", "oc_item_id": "i1", "cantidad_planificada": "6"},
            {"entrega_oc_id": "e2", "oc_item_id": "i1", "cantidad_planificada": "4"},
        ],
    )

    r = _resumen()

    assert r.orden_compra_id == "oc-1"
    assert r.numero_oc == "OC-1"
    assert r.cliente.razon_social == "Hospital Test"
    assert r.cliente.cuit == "30712345678"
    assert r.estado == "confirmada"
    assert r.version_numero == 2
    assert r.monto_total == Decimal("150.00")
    assert r.direccion_entrega == "Calle 123"
    assert r.notas == "Entregar por la tarde"
    assert [x.numero_renglon for x in r.renglones] == [1, 2, 3]
    assert [x.estado_vinculo for x in r.renglones] == ["confirmado", "sin_presupuesto", "pendiente"]
    primero = r.renglones[0]
    assert primero.producto.codigo_interno == "COD-1"
    assert primero.producto.nombre == "Producto Uno"
    assert primero.numero_renglon_documento == "10"
    assert primero.cantidad == Decimal("10")
    assert primero.precio_unitario == Decimal("5.00")
    assert primero.monto_total == Decimal("50.00")
    assert r.renglones[1].producto is None
    assert [e.numero_entrega for e in r.entregas] == [1, 2]
    assert [(i.oc_item_id, i.cantidad_planificada) for i in r.entregas[0].items] == [("i1", Decimal("6"))]
    assert r.entregas[1].fecha_entrega_planificada is None
    assert r.exportacion.exportado_por_nombre == "Ana Pérez"
    assert r.exportacion.archivo_exportado == "oc-1.txt"


def test_oc_sin_cliente_devuelve_cliente_none(monkeypatch):
    _parchar(monkeypatch, oc=_oc(cliente_id=None, clientes=None))

    r = _resumen()

    assert r.cliente is None
    assert r.exportacion is None


def test_oc_sin_entregas_devuelve_lista_vacia(monkeypatch):
    _parchar(monkeypatch, oc=_oc(), items=[_item("i1", 1)])

    r = _resumen()

    assert r.entregas == []
    assert len(r.renglones) == 1


def test_oc_inexistente_da_not_found(monkeypatch):
    _parchar(monkeypatch, oc=None)
    with pytest.raises(NotFoundError):
        _resumen()


def test_oc_de_otra_drogueria_da_not_found(monkeypatch):
    _parchar(monkeypatch, oc=_oc(drogueria_id="otra"))
    with pytest.raises(NotFoundError):
        _resumen()


@pytest.mark.parametrize("id_invalido", ["oc-1", "", "123", "no-es-uuid"])
def test_id_no_uuid_da_not_found_sin_consultar_la_base(monkeypatch, id_invalido):
    # Postgres rechaza el cast a uuid con un 500: se corta antes de tocar el repository.
    buscar = MagicMock()
    monkeypatch.setattr(repo, "buscar_orden_compra", buscar)

    with pytest.raises(NotFoundError, match="No se encontró la orden de compra"):
        service.obtener_resumen(MagicMock(), orden_compra_id=id_invalido, drogueria_id="d1")

    buscar.assert_not_called()
