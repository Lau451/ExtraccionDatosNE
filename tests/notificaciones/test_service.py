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


@pytest.mark.integration
def test_rls_bloquea_lectura_de_notificaciones_ajenas_aunque_el_codigo_no_filtre(
    service_client, seed_drogueria, crear_usuario_autenticado, limpiar_notificaciones
):
    """No alcanza con que listar_no_leidas() filtre por destinatario_id en Python --
    esto confirma que si ESE filtro se rompiera (se borrara el .eq de repository.py),
    RLS solo ya deja pasar cero filas ajenas. Por eso acá NO se llama a
    listar_no_leidas(): se consulta la tabla directa, sin ningún filtro de
    destinatario_id, simulando el código roto."""
    _, cliente_a = crear_usuario_autenticado(rol="comercial", drogueria_id=seed_drogueria["id"])
    usuario_b, cliente_b = crear_usuario_autenticado(rol="comercial", drogueria_id=seed_drogueria["id"])

    notificacion_de_b = crear_notificacion(
        service_client,
        drogueria_id=seed_drogueria["id"],
        destinatario_id=usuario_b,
        tipo="sistema",
        titulo="Solo para B",
    )

    # cliente_a consulta SIN filtrar por destinatario_id -- si el código de
    # aplicación fuera la única defensa, esto traería la notificación de B.
    vistas_por_a = cliente_a.table("notificaciones").select("*").execute().data
    ids_vistos_por_a = {n["id"] for n in vistas_por_a}
    assert notificacion_de_b["id"] not in ids_vistos_por_a

    # Confirma que la policy es "solo la propia", no "nadie ve nada": B sí la ve.
    vistas_por_b = cliente_b.table("notificaciones").select("*").execute().data
    assert notificacion_de_b["id"] in {n["id"] for n in vistas_por_b}


@pytest.mark.integration
def test_rls_bloquea_update_de_preferencia_ajena_aunque_el_codigo_no_filtre(
    service_client, seed_drogueria, crear_usuario_autenticado, limpiar_notificaciones
):
    """Mismo criterio que el test de lectura, pero sobre UPDATE: sin el .eq("usuario_id", ...)
    del código, la policy np_upd (usuario_id = auth.uid() OR es_superadmin()) tiene que
    ser la que bloquee la escritura sobre la fila de otro usuario."""
    _, cliente_a = crear_usuario_autenticado(rol="comercial", drogueria_id=seed_drogueria["id"])
    usuario_b, cliente_b = crear_usuario_autenticado(rol="comercial", drogueria_id=seed_drogueria["id"])

    preferencia_de_b = upsert_preferencia(
        service_client,
        usuario_id=usuario_b,
        drogueria_id=seed_drogueria["id"],
        body=NotificacionPreferenciaUpsert(tipo="evento_vencido", canal="web", habilitada=True),
    )

    # cliente_a intenta actualizar la fila de B por id, SIN filtrar por usuario_id --
    # si el código fuera la única defensa, esto la deshabilitaría igual.
    resultado = (
        cliente_a.table("notificacion_preferencias")
        .update({"habilitada": False})
        .eq("id", preferencia_de_b["id"])
        .execute()
    )
    assert resultado.data == []

    fila_real = (
        service_client.table("notificacion_preferencias")
        .select("habilitada")
        .eq("id", preferencia_de_b["id"])
        .execute()
        .data[0]
    )
    assert fila_real["habilitada"] is True

    # Confirma que la policy discrimina por identidad, no que bloquea todo: B sí
    # puede actualizar su propia fila por el mismo camino (sin filtrar por usuario_id).
    resultado_b = (
        cliente_b.table("notificacion_preferencias")
        .update({"habilitada": False})
        .eq("id", preferencia_de_b["id"])
        .execute()
    )
    assert len(resultado_b.data) == 1
    assert resultado_b.data[0]["habilitada"] is False
