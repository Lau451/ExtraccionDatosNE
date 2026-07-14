from datetime import date, datetime

import pytest

from services.presupuestacion.core.audit import (
    _COLUMNA_FK_POR_ENTIDAD,
    _a_texto,
    registrar_cambios,
    registrar_evento_ciclo_vida,
)


def test_a_texto_none_es_none():
    assert _a_texto(None) is None


def test_a_texto_booleanos_en_minuscula():
    assert _a_texto(True) == "true"
    assert _a_texto(False) == "false"


def test_a_texto_datetime_usa_isoformat():
    valor = datetime(2026, 7, 13, 10, 30)
    assert _a_texto(valor) == valor.isoformat()


def test_a_texto_date_usa_isoformat():
    valor = date(2026, 7, 13)
    assert _a_texto(valor) == valor.isoformat()


def test_a_texto_numero_y_texto_usan_str():
    assert _a_texto(42) == "42"
    assert _a_texto(15000.5) == "15000.5"
    assert _a_texto("ya-texto") == "ya-texto"


def test_mapeo_entidad_columna_cubre_las_5_fks_de_historial_cambios():
    assert _COLUMNA_FK_POR_ENTIDAD == {
        "proceso_comercial": "proceso_comercial_id",
        "comparativa": "comparativa_id",
        "orden_compra": "orden_compra_id",
        "presupuesto": "presupuesto_id",
        "evento": "evento_id",
    }


@pytest.mark.integration
def test_registrar_cambios_inserta_en_historial_cambios_real(
    service_client, seed_drogueria, seed_proceso_comercial, seed_usuario_sistema
):
    batch_id = registrar_cambios(
        service_client,
        entidad="proceso_comercial",
        entidad_id=seed_proceso_comercial["id"],
        drogueria_id=seed_drogueria["id"],
        cambios={
            "estado": ("abierto", "presupuestado"),
            "monto_estimado": (None, 15000.5),
        },
        origen="sistema",
        usuario_id=seed_usuario_sistema["id"],
    )
    try:
        filas = (
            service_client.table("historial_cambios")
            .select("*")
            .eq("batch_id", batch_id)
            .execute()
            .data
        )
        por_campo = {fila["campo"]: fila for fila in filas}

        assert len(filas) == 2
        assert por_campo["estado"]["tipo_cambio"] == "estado"
        assert por_campo["estado"]["valor_anterior"] == "abierto"
        assert por_campo["estado"]["valor_nuevo"] == "presupuestado"
        assert por_campo["monto_estimado"]["tipo_cambio"] == "campo"
        assert por_campo["monto_estimado"]["valor_anterior"] is None
        assert por_campo["monto_estimado"]["valor_nuevo"] == "15000.5"
        assert all(fila["proceso_comercial_id"] == seed_proceso_comercial["id"] for fila in filas)
        assert all(fila["comparativa_id"] is None for fila in filas)
    finally:
        service_client.table("historial_cambios").delete().eq("batch_id", batch_id).execute()


@pytest.mark.integration
def test_registrar_evento_ciclo_vida_inserta_creacion_real(
    service_client, seed_drogueria, seed_proceso_comercial, seed_usuario_sistema
):
    batch_id = registrar_evento_ciclo_vida(
        service_client,
        entidad="proceso_comercial",
        entidad_id=seed_proceso_comercial["id"],
        drogueria_id=seed_drogueria["id"],
        tipo_cambio="creacion",
        origen="sistema",
        usuario_id=seed_usuario_sistema["id"],
    )
    try:
        filas = (
            service_client.table("historial_cambios")
            .select("*")
            .eq("batch_id", batch_id)
            .execute()
            .data
        )

        assert len(filas) == 1
        assert filas[0]["tipo_cambio"] == "creacion"
        assert filas[0]["campo"] is None
        assert filas[0]["proceso_comercial_id"] == seed_proceso_comercial["id"]
    finally:
        service_client.table("historial_cambios").delete().eq("batch_id", batch_id).execute()
