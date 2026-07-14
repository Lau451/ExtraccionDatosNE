import pytest

from services.presupuestacion.core.exceptions import ForbiddenError
from services.presupuestacion.notificaciones.models import NotificacionPreferenciaUpsert
from services.presupuestacion.notificaciones.service import (
    crear_notificacion,
    listar_no_leidas,
    listar_preferencias,
    marcar_archivada,
    marcar_leida,
    upsert_preferencia,
)


@pytest.mark.integration
def test_crear_notificacion_sin_preferencia_usa_canal_web_default(
    service_client, seed_drogueria, seed_usuario_sistema, limpiar_notificaciones
):
    notificacion = crear_notificacion(
        service_client,
        drogueria_id=seed_drogueria["id"],
        destinatario_id=seed_usuario_sistema["id"],
        tipo="sistema",
        titulo="Aviso de prueba",
    )

    entregas = (
        service_client.table("notificacion_entregas")
        .select("*")
        .eq("notificacion_id", notificacion["id"])
        .execute()
        .data
    )
    assert len(entregas) == 1
    assert entregas[0]["canal"] == "web"
    assert entregas[0]["estado"] == "pendiente"


@pytest.mark.integration
def test_crear_notificacion_respeta_preferencias_habilitadas(
    service_client, seed_drogueria, seed_usuario_sistema, limpiar_notificaciones
):
    upsert_preferencia(
        service_client,
        usuario_id=seed_usuario_sistema["id"],
        drogueria_id=seed_drogueria["id"],
        body=NotificacionPreferenciaUpsert(tipo="oc_creada", canal="web", habilitada=True),
    )
    upsert_preferencia(
        service_client,
        usuario_id=seed_usuario_sistema["id"],
        drogueria_id=seed_drogueria["id"],
        body=NotificacionPreferenciaUpsert(tipo="oc_creada", canal="email", habilitada=False),
    )

    notificacion = crear_notificacion(
        service_client,
        drogueria_id=seed_drogueria["id"],
        destinatario_id=seed_usuario_sistema["id"],
        tipo="oc_creada",
        titulo="Nueva OC",
    )

    entregas = (
        service_client.table("notificacion_entregas")
        .select("canal")
        .eq("notificacion_id", notificacion["id"])
        .execute()
        .data
    )
    assert [e["canal"] for e in entregas] == ["web"]


@pytest.mark.integration
def test_listar_no_leidas_excluye_leidas_y_archivadas(
    service_client, seed_drogueria, seed_usuario_sistema, limpiar_notificaciones
):
    a = crear_notificacion(
        service_client, drogueria_id=seed_drogueria["id"], destinatario_id=seed_usuario_sistema["id"],
        tipo="sistema", titulo="A",
    )
    b = crear_notificacion(
        service_client, drogueria_id=seed_drogueria["id"], destinatario_id=seed_usuario_sistema["id"],
        tipo="sistema", titulo="B",
    )
    marcar_leida(service_client, notificacion_id=a["id"], usuario_id=seed_usuario_sistema["id"])

    no_leidas = listar_no_leidas(service_client, destinatario_id=seed_usuario_sistema["id"])
    assert [n["id"] for n in no_leidas] == [b["id"]]


@pytest.mark.integration
def test_marcar_leida_de_otro_destinatario_lanza_forbidden(
    service_client, seed_drogueria, seed_usuario_sistema, limpiar_notificaciones
):
    notificacion = crear_notificacion(
        service_client, drogueria_id=seed_drogueria["id"], destinatario_id=seed_usuario_sistema["id"],
        tipo="sistema", titulo="A",
    )
    with pytest.raises(ForbiddenError):
        marcar_leida(service_client, notificacion_id=notificacion["id"], usuario_id="otro-usuario")


@pytest.mark.integration
def test_marcar_archivada(service_client, seed_drogueria, seed_usuario_sistema, limpiar_notificaciones):
    notificacion = crear_notificacion(
        service_client, drogueria_id=seed_drogueria["id"], destinatario_id=seed_usuario_sistema["id"],
        tipo="sistema", titulo="A",
    )
    resultado = marcar_archivada(
        service_client, notificacion_id=notificacion["id"], usuario_id=seed_usuario_sistema["id"]
    )
    assert resultado["archivada_at"] is not None

    no_leidas = listar_no_leidas(service_client, destinatario_id=seed_usuario_sistema["id"])
    assert no_leidas == []


@pytest.mark.integration
def test_upsert_preferencia_es_idempotente_por_usuario_tipo_canal(
    service_client, seed_drogueria, seed_usuario_sistema, limpiar_notificaciones
):
    upsert_preferencia(
        service_client, usuario_id=seed_usuario_sistema["id"], drogueria_id=seed_drogueria["id"],
        body=NotificacionPreferenciaUpsert(tipo="evento_vencido", canal="web", habilitada=True),
    )
    upsert_preferencia(
        service_client, usuario_id=seed_usuario_sistema["id"], drogueria_id=seed_drogueria["id"],
        body=NotificacionPreferenciaUpsert(tipo="evento_vencido", canal="web", habilitada=False),
    )

    preferencias = listar_preferencias(service_client, usuario_id=seed_usuario_sistema["id"])
    coincidencias = [p for p in preferencias if p["tipo"] == "evento_vencido" and p["canal"] == "web"]
    assert len(coincidencias) == 1
    assert coincidencias[0]["habilitada"] is False
