"""tests/compromisos/test_service.py -- rango y orden de GET /compromisos-entregas
(openspec/changes/oc-export-progress, D9/D10). Unitarios con el repository mockeado;
"hoy" se inyecta para no depender del reloj."""

from datetime import date
from unittest.mock import MagicMock

import pytest

from services.presupuestacion.compromisos import repository as repo
from services.presupuestacion.compromisos import service
from services.presupuestacion.core.exceptions import ValidationError

HOY = date(2026, 10, 11)
DROGUERIA = "drogueria-1"


def _fila(situacion, fecha, numero_oc="OC-1", entrega=1, renglon=1):
    return {
        "situacion": situacion,
        "fecha_entrega_planificada": fecha,
        "numero_oc": numero_oc,
        "numero_entrega": entrega,
        "numero_renglon": renglon,
    }


@pytest.fixture
def listar(monkeypatch):
    mock = MagicMock(return_value=[])
    monkeypatch.setattr(repo, "listar_compromisos", mock)
    return mock


def test_sin_desde_ni_hasta_trae_todo_lo_vencido_y_seis_meses_hacia_adelante(listar):
    service.listar_compromisos(MagicMock(), drogueria_id=DROGUERIA, hoy=HOY)

    kwargs = listar.call_args.kwargs
    assert kwargs["drogueria_id"] == DROGUERIA
    assert kwargs["desde"] is None
    assert kwargs["hasta"] == date(2027, 4, 11)


def test_seis_meses_desde_fin_de_mes_se_ajusta_al_ultimo_dia(listar):
    service.listar_compromisos(MagicMock(), drogueria_id=DROGUERIA, hoy=date(2026, 8, 31))

    assert listar.call_args.kwargs["hasta"] == date(2027, 2, 28)


def test_con_desde_y_hasta_filtra_ese_rango(listar):
    service.listar_compromisos(
        MagicMock(),
        drogueria_id=DROGUERIA,
        desde=date(2026, 11, 1),
        hasta=date(2026, 11, 30),
        hoy=HOY,
    )

    kwargs = listar.call_args.kwargs
    assert kwargs["desde"] == date(2026, 11, 1)
    assert kwargs["hasta"] == date(2026, 11, 30)


def test_solo_desde_usa_seis_meses_desde_esa_fecha(listar):
    service.listar_compromisos(
        MagicMock(), drogueria_id=DROGUERIA, desde=date(2026, 12, 1), hoy=HOY
    )

    assert listar.call_args.kwargs["hasta"] == date(2027, 6, 1)


def test_solo_hasta_mantiene_las_vencidas(listar):
    service.listar_compromisos(
        MagicMock(), drogueria_id=DROGUERIA, hasta=date(2026, 12, 31), hoy=HOY
    )

    kwargs = listar.call_args.kwargs
    assert kwargs["desde"] is None
    assert kwargs["hasta"] == date(2026, 12, 31)


def test_hasta_anterior_a_desde_es_validation_error(listar):
    with pytest.raises(ValidationError):
        service.listar_compromisos(
            MagicMock(),
            drogueria_id=DROGUERIA,
            desde=date(2026, 12, 1),
            hasta=date(2026, 11, 30),
            hoy=HOY,
        )
    listar.assert_not_called()


def test_rango_de_exactamente_24_meses_es_valido(listar):
    service.listar_compromisos(
        MagicMock(),
        drogueria_id=DROGUERIA,
        desde=date(2026, 1, 1),
        hasta=date(2028, 1, 1),
        hoy=HOY,
    )

    listar.assert_called_once()


def test_rango_de_mas_de_24_meses_es_validation_error(listar):
    with pytest.raises(ValidationError):
        service.listar_compromisos(
            MagicMock(),
            drogueria_id=DROGUERIA,
            desde=date(2026, 1, 1),
            hasta=date(2028, 1, 2),
            hoy=HOY,
        )
    listar.assert_not_called()


def test_solo_hasta_a_mas_de_24_meses_de_hoy_es_validation_error(listar):
    with pytest.raises(ValidationError):
        service.listar_compromisos(
            MagicMock(), drogueria_id=DROGUERIA, hasta=date(2028, 10, 12), hoy=HOY
        )


def test_ordena_vencidas_primero_y_luego_fecha_oc_entrega_renglon(listar):
    listar.return_value = [
        _fila("futura", "2026-10-20", "OC-1", 1, 1),
        _fila("vencida", "2026-10-05", "OC-2", 1, 2),
        _fila("vencida", "2026-10-05", "OC-2", 1, 1),
        _fila("vencida", "2026-09-01", "OC-9", 2, 1),
        _fila("futura", "2026-10-20", "OC-1", 2, 1),
        _fila("vencida", "2026-10-05", "OC-1", 3, 1),
        _fila("futura", "2026-10-12", "OC-3", 1, 1),
    ]

    filas = service.listar_compromisos(MagicMock(), drogueria_id=DROGUERIA, hoy=HOY)

    assert [
        (f["situacion"], f["fecha_entrega_planificada"], f["numero_oc"], f["numero_entrega"], f["numero_renglon"])
        for f in filas
    ] == [
        ("vencida", "2026-09-01", "OC-9", 2, 1),
        ("vencida", "2026-10-05", "OC-1", 3, 1),
        ("vencida", "2026-10-05", "OC-2", 1, 1),
        ("vencida", "2026-10-05", "OC-2", 1, 2),
        ("futura", "2026-10-12", "OC-3", 1, 1),
        ("futura", "2026-10-20", "OC-1", 1, 1),
        ("futura", "2026-10-20", "OC-1", 2, 1),
    ]


def test_hoy_por_defecto_es_la_fecha_de_buenos_aires(listar, monkeypatch):
    monkeypatch.setattr(service, "_hoy_buenos_aires", lambda: date(2026, 1, 31))

    service.listar_compromisos(MagicMock(), drogueria_id=DROGUERIA)

    assert listar.call_args.kwargs["hasta"] == date(2026, 7, 31)
