import pytest

from services.presupuestacion.core.exceptions import ValidationError
from services.presupuestacion.procesos_comerciales.models import ProcesoComercialCreate
from services.presupuestacion.procesos_comerciales.service import (
    crear_proceso_comercial,
    listar_procesos_comerciales,
)


def _borrar_proceso(service_client, proceso_id: str) -> None:
    service_client.table("historial_cambios").delete().eq(
        "proceso_comercial_id", proceso_id
    ).execute()
    service_client.table("procesos_comerciales").delete().eq("id", proceso_id).execute()


@pytest.mark.integration
def test_crear_cotizacion_valida_sin_campos_seguimiento(
    service_client, seed_drogueria, seed_usuario_sistema
):
    proceso = crear_proceso_comercial(
        service_client,
        drogueria_id=seed_drogueria["id"],
        body=ProcesoComercialCreate(nombre="Cotización de test", clase="cotizacion"),
        usuario_id=seed_usuario_sistema["id"],
    )
    try:
        assert proceso["clase"] == "cotizacion"
        assert proceso["estado"] == "abierto"
        assert proceso["apertura"] is None
        assert proceso["modalidad"] is None
        assert proceso["comparativa_pedida"] is False
    finally:
        _borrar_proceso(service_client, proceso["id"])


@pytest.mark.integration
def test_crear_cotizacion_con_apertura_rechaza_con_validation_error(
    service_client, seed_drogueria, seed_usuario_sistema
):
    """La tabla tiene el CHECK ck_proc_cotizacion_sin_seguimiento (ver
    docs/schema/extractor_final.sql): una cotización no admite apertura,
    vencimiento, modalidad, tipo_gestion ni comparativa_pedida. Esto valida que
    el service la rechace ANTES de pegarle a la BD, con un error de negocio
    legible (422), no con el 500 crudo de Postgres."""
    with pytest.raises(ValidationError):
        crear_proceso_comercial(
            service_client,
            drogueria_id=seed_drogueria["id"],
            body=ProcesoComercialCreate(
                nombre="Cotización inválida",
                clase="cotizacion",
                apertura="2026-08-01",
            ),
            usuario_id=seed_usuario_sistema["id"],
        )


@pytest.mark.integration
def test_crear_licitacion_con_apertura_y_modalidad_ok(
    service_client, seed_drogueria, seed_usuario_sistema
):
    proceso = crear_proceso_comercial(
        service_client,
        drogueria_id=seed_drogueria["id"],
        body=ProcesoComercialCreate(
            nombre="Licitación de test",
            clase="licitacion",
            apertura="2026-08-01",
            modalidad="pliego",
        ),
        usuario_id=seed_usuario_sistema["id"],
    )
    try:
        assert proceso["clase"] == "licitacion"
        assert proceso["apertura"] == "2026-08-01"
        assert proceso["modalidad"] == "pliego"
    finally:
        _borrar_proceso(service_client, proceso["id"])


@pytest.mark.integration
def test_listar_activos_excluye_estados_terminales(
    service_client, seed_drogueria, seed_proceso_comercial_factory
):
    abierto = seed_proceso_comercial_factory(nombre="Abierto de test")
    cerrado = seed_proceso_comercial_factory(nombre="Cerrado de test")
    service_client.table("procesos_comerciales").update({"estado": "cerrado"}).eq(
        "id", cerrado["id"]
    ).execute()

    activos = listar_procesos_comerciales(
        service_client, drogueria_id=seed_drogueria["id"], activos=True
    )
    nombres_activos = {p["nombre"] for p in activos}
    assert abierto["nombre"] in nombres_activos
    assert cerrado["nombre"] not in nombres_activos

    todos = listar_procesos_comerciales(
        service_client, drogueria_id=seed_drogueria["id"], activos=False
    )
    nombres_todos = {p["nombre"] for p in todos}
    assert abierto["nombre"] in nombres_todos
    assert cerrado["nombre"] in nombres_todos
