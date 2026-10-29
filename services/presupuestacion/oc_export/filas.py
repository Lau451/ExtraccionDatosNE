# Construcción pura (sin I/O) de las filas del CSV de Progress
# (openspec/changes/oc-export-progress, D4).
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from services.presupuestacion.oc_export.models import (
    EntregaExport,
    OcExport,
    RenglonExport,
)

ENCABEZADOS: list[str] = [
    "id_oc",
    "numero_oc",
    "version",
    "fecha_emision",
    "codigo_cliente",
    "cuit_cliente",
    "direccion_entrega",
    "numero_renglon",
    "codigo_articulo",
    "descripcion",
    "cantidad_total",
    "precio_unitario",
    "numero_entrega",
    "fecha_entrega",
    "cantidad_entrega",
]

_DOS_DECIMALES = Decimal("0.01")


def _decimal(valor: Decimal) -> str:
    redondeado = valor.quantize(_DOS_DECIMALES, rounding=ROUND_HALF_UP)
    return f"{redondeado:f}"


def _fecha(valor: date | None) -> str:
    return valor.strftime("%d/%m/%Y") if valor else ""


def _texto(valor: str | None) -> str:
    return valor.strip() if valor else ""


def construir_filas(
    oc: OcExport,
    renglones: list[RenglonExport],
    entregas: list[EntregaExport],
    *,
    codigo_cliente: str,
    cuit_cliente: str | None,
) -> list[list[str]]:
    """Una fila por renglón × entrega con cantidad planificada > 0, ordenadas por
    `numero_renglon` y luego `numero_entrega`. No incluye la fila de encabezados."""
    cabecera = [
        _texto(oc.id),
        _texto(oc.numero_oc),
        str(oc.version_numero),
        _fecha(oc.fecha_emision),
        _texto(codigo_cliente),
        _texto(cuit_cliente),
        _texto(oc.direccion_entrega),
    ]
    entregas_por_item: dict[str, list[EntregaExport]] = {}
    for entrega in entregas:
        if entrega.cantidad_planificada > 0:
            entregas_por_item.setdefault(entrega.oc_item_id, []).append(entrega)

    filas: list[list[str]] = []
    for renglon in sorted(renglones, key=lambda r: r.numero_renglon):
        datos_renglon = [
            str(renglon.numero_renglon),
            _texto(renglon.codigo_articulo),
            _texto(renglon.descripcion),
            _decimal(renglon.cantidad),
            _decimal(renglon.precio_unitario),
        ]
        for entrega in sorted(
            entregas_por_item.get(renglon.oc_item_id, []), key=lambda e: e.numero_entrega
        ):
            filas.append(
                cabecera
                + datos_renglon
                + [
                    str(entrega.numero_entrega),
                    _fecha(entrega.fecha_entrega),
                    _decimal(entrega.cantidad_planificada),
                ]
            )
    return filas
