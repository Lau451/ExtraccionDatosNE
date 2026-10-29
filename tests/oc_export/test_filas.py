from datetime import date
from decimal import Decimal

from services.presupuestacion.oc_export.filas import ENCABEZADOS, construir_filas
from services.presupuestacion.oc_export.models import (
    EntregaExport,
    OcExport,
    RenglonExport,
)


def _oc(**kw):
    base = dict(
        id="oc-1",
        numero_oc="4500-1",
        version_numero=3,
        fecha_emision=date(2026, 10, 5),
        direccion_entrega="  Calle 1, CABA ",
    )
    base.update(kw)
    return OcExport(**base)


def _renglon(n, item="i1", **kw):
    base = dict(
        oc_item_id=item,
        numero_renglon=n,
        codigo_articulo="ART1",
        descripcion="  Ibuprofeno 400mg, caja x 20 ",
        cantidad=Decimal("1520.5"),
        precio_unitario=Decimal("1234.5"),
    )
    base.update(kw)
    return RenglonExport(**base)


def _entrega(n, item="i1", cant="10", f=date(2026, 10, 15)):
    return EntregaExport(
        oc_item_id=item, numero_entrega=n, fecha_entrega=f, cantidad_planificada=Decimal(cant)
    )


def _filas(oc=None, renglones=None, entregas=None, cuit="30-1"):
    return construir_filas(
        oc or _oc(),
        renglones or [_renglon(1)],
        entregas or [_entrega(1)],
        codigo_cliente="C01",
        cuit_cliente=cuit,
    )


def test_encabezados_son_los_15_acordados():
    assert len(ENCABEZADOS) == 15
    assert ENCABEZADOS[0] == "id_oc" and ENCABEZADOS[-1] == "cantidad_entrega"


def test_formato_de_valores():
    (fila,) = _filas()
    assert fila == [
        "oc-1", "4500-1", "3", "05/10/2026", "C01", "30-1", "Calle 1, CABA",
        "1", "ART1", "Ibuprofeno 400mg, caja x 20", "1520.50", "1234.50",
        "1", "15/10/2026", "10.00",
    ]


def test_sin_separador_de_miles():
    (fila,) = _filas(renglones=[_renglon(1, precio_unitario=Decimal("1234567.891"))])
    assert fila[11] == "1234567.89"


def test_orden_por_renglon_y_luego_entrega():
    renglones = [_renglon(2, "i2"), _renglon(1, "i1")]
    entregas = [_entrega(2, "i1"), _entrega(1, "i2"), _entrega(1, "i1"), _entrega(2, "i2")]
    filas = _filas(renglones=renglones, entregas=entregas)
    assert [(f[7], f[12]) for f in filas] == [("1", "1"), ("1", "2"), ("2", "1"), ("2", "2")]


def test_entrega_con_cantidad_cero_se_omite():
    filas = _filas(entregas=[_entrega(1, cant="0"), _entrega(2, cant="5")])
    assert len(filas) == 1 and filas[0][12] == "2"


def test_cabecera_repetida_en_cada_fila():
    filas = _filas(entregas=[_entrega(1), _entrega(2)])
    assert len(filas) == 2 and filas[0][:7] == filas[1][:7]


def test_opcionales_null_quedan_vacios():
    oc = _oc(fecha_emision=None, direccion_entrega=None)
    (fila,) = _filas(oc=oc, cuit=None)
    assert fila[3] == "" and fila[5] == "" and fila[6] == ""


def test_sin_entregas_no_hay_filas():
    assert construir_filas(
        _oc(), [_renglon(1)], [], codigo_cliente="C01", cuit_cliente=None
    ) == []


def test_redondeo_half_up_no_bancario():
    # 0.125 y 0.135 son exactos en Decimal: HALF_UP da 0.13 / 0.14; el redondeo
    # bancario (HALF_EVEN) daría 0.12 / 0.14, así que 0.125 distingue ambos modos.
    (fila,) = _filas(
        renglones=[_renglon(1, cantidad=Decimal("0.125"), precio_unitario=Decimal("2.675"))]
    )
    assert fila[10] == "0.13"
    assert fila[11] == "2.68"
