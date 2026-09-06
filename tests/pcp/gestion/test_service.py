"""4.2-4.7 (openspec/changes/gestor-pcp/tasks.md Fase 4) -- pcp-gestion:
alta de PCP scopeada al presupuesto origen, máquina de estados explícita,
listado/filtro por fecha de entrega y estado, aislamiento por tenant y
escritura de `pcp_historial` en cada transición (vía
services.pcp.historial.service.agregar_evento, PR3).

RED hasta que 4.8 cree services/pcp/gestion/{models,repository,service}.py.
"""

import pytest

from services.pcp.gestion.models import PcpCreate
from services.pcp.gestion.service import cambiar_estado, crear_pcp, listar_pcp, obtener_pcp
from services.shared.exceptions import ConflictError, NotFoundError, ValidationError

# ---------------------------------------------------------------------------
# 4.2 -- crear un PCP para un presupuesto elegible queda scopeado a su drogueria_id
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_crear_pcp_para_presupuesto_elegible_queda_scopeado_a_su_drogueria(
    service_client, seed_drogueria, seed_presupuesto_factory, seed_usuario_sistema
):
    presupuesto = seed_presupuesto_factory()

    pcp = crear_pcp(
        service_client,
        drogueria_id=seed_drogueria["id"],
        body=PcpCreate(presupuesto_id=presupuesto["id"], fecha_entrega_solicitada="2026-10-01"),
        usuario_id=seed_usuario_sistema["id"],
    )
    try:
        assert pcp["presupuesto_id"] == presupuesto["id"]
        assert pcp["drogueria_id"] == seed_drogueria["id"]
        assert pcp["proceso_comercial_id"] == presupuesto["proceso_comercial_id"]
        assert pcp["estado"] == "nueva"

        en_bd = service_client.table("pcp").select("id").eq("id", pcp["id"]).execute().data
        assert len(en_bd) == 1
    finally:
        service_client.table("pcp").delete().eq("id", pcp["id"]).execute()


# ---------------------------------------------------------------------------
# 4.3 -- segunda creación para el mismo presupuesto con un PCP ya abierto -> ConflictError
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_crear_pcp_para_presupuesto_con_pcp_abierto_lanza_conflicto(
    service_client, seed_drogueria, seed_presupuesto_factory, seed_usuario_sistema
):
    presupuesto = seed_presupuesto_factory()
    primero = crear_pcp(
        service_client,
        drogueria_id=seed_drogueria["id"],
        body=PcpCreate(presupuesto_id=presupuesto["id"]),
        usuario_id=seed_usuario_sistema["id"],
    )
    try:
        with pytest.raises(ConflictError):
            crear_pcp(
                service_client,
                drogueria_id=seed_drogueria["id"],
                body=PcpCreate(presupuesto_id=presupuesto["id"]),
                usuario_id=seed_usuario_sistema["id"],
            )

        solo_uno = (
            service_client.table("pcp")
            .select("id")
            .eq("presupuesto_id", presupuesto["id"])
            .execute()
            .data
        )
        assert len(solo_uno) == 1
    finally:
        service_client.table("pcp").delete().eq("id", primero["id"]).execute()


# ---------------------------------------------------------------------------
# 4.4 -- máquina de estados: transición válida, rechazo de salto y de retroceso
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_cambiar_estado_nueva_a_en_gestion_es_una_transicion_valida(
    service_client, seed_drogueria, seed_pcp_factory, seed_usuario_sistema
):
    pcp = seed_pcp_factory()

    actualizado = cambiar_estado(
        service_client,
        pcp_id=pcp["id"],
        drogueria_id=seed_drogueria["id"],
        estado_nuevo="en_gestion",
        usuario_id=seed_usuario_sistema["id"],
    )

    assert actualizado["estado"] == "en_gestion"


@pytest.mark.integration
def test_cambiar_estado_de_nueva_a_cerrada_salta_el_intermedio_y_se_rechaza(
    service_client, seed_drogueria, seed_pcp_factory, seed_usuario_sistema
):
    pcp = seed_pcp_factory()

    with pytest.raises(ValidationError):
        cambiar_estado(
            service_client,
            pcp_id=pcp["id"],
            drogueria_id=seed_drogueria["id"],
            estado_nuevo="cerrada",
            usuario_id=seed_usuario_sistema["id"],
        )

    en_bd = service_client.table("pcp").select("estado").eq("id", pcp["id"]).execute().data[0]
    assert en_bd["estado"] == "nueva"


@pytest.mark.integration
def test_cambiar_estado_de_esperando_respuesta_a_en_gestion_retrocede_y_se_rechaza(
    service_client, seed_drogueria, seed_pcp_factory, seed_usuario_sistema
):
    pcp = seed_pcp_factory(estado="esperando_respuesta")

    with pytest.raises(ValidationError):
        cambiar_estado(
            service_client,
            pcp_id=pcp["id"],
            drogueria_id=seed_drogueria["id"],
            estado_nuevo="en_gestion",
            usuario_id=seed_usuario_sistema["id"],
        )

    en_bd = service_client.table("pcp").select("estado").eq("id", pcp["id"]).execute().data[0]
    assert en_bd["estado"] == "esperando_respuesta"


# ---------------------------------------------------------------------------
# 4.5 -- listado filtra por rango de fecha de entrega solicitada y por estado
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_listar_pcp_filtra_por_rango_de_fecha_de_entrega_solicitada(
    service_client, seed_drogueria, seed_pcp_factory
):
    cercano = seed_pcp_factory(fecha_entrega_solicitada="2026-10-05")
    lejano = seed_pcp_factory(fecha_entrega_solicitada="2026-12-20")

    resultado = listar_pcp(
        service_client,
        drogueria_id=seed_drogueria["id"],
        fecha_desde="2026-10-01",
        fecha_hasta="2026-10-31",
    )

    ids = {p["id"] for p in resultado}
    assert cercano["id"] in ids
    assert lejano["id"] not in ids


@pytest.mark.integration
def test_listar_pcp_filtra_por_estado(service_client, seed_drogueria, seed_pcp_factory):
    en_gestion = seed_pcp_factory(estado="en_gestion")
    nueva = seed_pcp_factory(estado="nueva")

    resultado = listar_pcp(service_client, drogueria_id=seed_drogueria["id"], estado="en_gestion")

    ids = {p["id"] for p in resultado}
    assert en_gestion["id"] in ids
    assert nueva["id"] not in ids


# ---------------------------------------------------------------------------
# 4.6 -- acceso cross-tenant a un PCP -> NotFoundError
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_obtener_pcp_de_otra_drogueria_lanza_not_found(
    service_client, seed_drogueria, seed_pcp_factory
):
    pcp = seed_pcp_factory()
    otra_drogueria_id = "00000000-0000-0000-0000-000000000000"

    with pytest.raises(NotFoundError):
        obtener_pcp(service_client, pcp_id=pcp["id"], drogueria_id=otra_drogueria_id)


# ---------------------------------------------------------------------------
# 4.7 -- un cambio de estado escribe un evento en pcp_historial (old/new/usuario)
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_cambiar_estado_escribe_evento_estado_cambiado_en_pcp_historial(
    service_client, seed_drogueria, seed_pcp_factory, seed_usuario_sistema
):
    pcp = seed_pcp_factory()

    cambiar_estado(
        service_client,
        pcp_id=pcp["id"],
        drogueria_id=seed_drogueria["id"],
        estado_nuevo="en_gestion",
        usuario_id=seed_usuario_sistema["id"],
    )

    eventos = (
        service_client.table("pcp_historial")
        .select("*")
        .eq("pcp_id", pcp["id"])
        .eq("tipo_evento", "estado_cambiado")
        .execute()
        .data
    )
    assert len(eventos) == 1
    evento = eventos[0]
    assert evento["payload"]["estado_anterior"] == "nueva"
    assert evento["payload"]["estado_nuevo"] == "en_gestion"
    assert evento["usuario_id"] == seed_usuario_sistema["id"]
    assert evento["created_at"] is not None
