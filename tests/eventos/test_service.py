from datetime import date, datetime, timedelta, timezone

import pytest

from services.presupuestacion.core.exceptions import NotFoundError
from services.presupuestacion.eventos.models import EventoCreate, EventoRecurrenteCreate, EventoUpdate
from services.presupuestacion.eventos.service import (
    actualizar_evento,
    calendario,
    completar_evento,
    crear_evento,
    crear_evento_recurrente,
    eliminar_evento,
    generar_instancias_recurrentes,
    listar_eventos_recurrentes,
    obtener_bloqueo,
    obtener_evento,
)


@pytest.mark.integration
def test_crear_evento_sin_dependencia_queda_pendiente(
    service_client, seed_drogueria, seed_usuario_sistema, limpiar_eventos
):
    resultado = crear_evento(
        service_client,
        drogueria_id=seed_drogueria["id"],
        body=EventoCreate(tipo="llamada", titulo="Llamar al cliente"),
        usuario_id=seed_usuario_sistema["id"],
    )
    assert resultado["estado"] == "pendiente"


@pytest.mark.integration
def test_crear_evento_con_dependencia_no_completada_queda_bloqueado(
    service_client, seed_drogueria, seed_usuario_sistema, limpiar_eventos
):
    previo = crear_evento(
        service_client,
        drogueria_id=seed_drogueria["id"],
        body=EventoCreate(tipo="compra", titulo="Generar OC"),
        usuario_id=seed_usuario_sistema["id"],
    )

    dependiente = crear_evento(
        service_client,
        drogueria_id=seed_drogueria["id"],
        body=EventoCreate(tipo="recepcion", titulo="Recibir mercadería", depende_de_id=previo["id"]),
        usuario_id=seed_usuario_sistema["id"],
    )

    assert dependiente["estado"] == "bloqueado"


@pytest.mark.integration
def test_completar_evento_desbloquea_dependientes(
    service_client, seed_drogueria, seed_usuario_sistema, limpiar_eventos
):
    previo = crear_evento(
        service_client,
        drogueria_id=seed_drogueria["id"],
        body=EventoCreate(tipo="compra", titulo="Generar OC"),
        usuario_id=seed_usuario_sistema["id"],
    )
    dependiente = crear_evento(
        service_client,
        drogueria_id=seed_drogueria["id"],
        body=EventoCreate(tipo="recepcion", titulo="Recibir mercadería", depende_de_id=previo["id"]),
        usuario_id=seed_usuario_sistema["id"],
    )
    assert dependiente["estado"] == "bloqueado"

    resultado = completar_evento(
        service_client, evento_id=previo["id"], drogueria_id=seed_drogueria["id"],
        usuario_id=seed_usuario_sistema["id"],
    )
    assert resultado["estado"] == "completado"
    assert resultado["fecha_real"] is not None

    actualizado = obtener_evento(service_client, evento_id=dependiente["id"], drogueria_id=seed_drogueria["id"])
    assert actualizado["estado"] == "pendiente"


@pytest.mark.integration
def test_obtener_bloqueo_puede_avanzar(
    service_client, seed_drogueria, seed_usuario_sistema, limpiar_eventos
):
    evento = crear_evento(
        service_client,
        drogueria_id=seed_drogueria["id"],
        body=EventoCreate(tipo="llamada", titulo="Sin dependencia"),
        usuario_id=seed_usuario_sistema["id"],
    )
    bloqueo = obtener_bloqueo(service_client, evento_id=evento["id"], drogueria_id=seed_drogueria["id"])
    assert bloqueo["puede_avanzar"] is True


@pytest.mark.integration
def test_actualizar_evento_solo_pisa_campos_enviados(
    service_client, seed_drogueria, seed_usuario_sistema, limpiar_eventos
):
    evento = crear_evento(
        service_client,
        drogueria_id=seed_drogueria["id"],
        body=EventoCreate(tipo="llamada", titulo="Original", descripcion="desc original"),
        usuario_id=seed_usuario_sistema["id"],
    )

    resultado = actualizar_evento(
        service_client,
        evento_id=evento["id"],
        drogueria_id=seed_drogueria["id"],
        body=EventoUpdate(prioridad="alta"),
        usuario_id=seed_usuario_sistema["id"],
    )

    assert resultado["prioridad"] == "alta"
    assert resultado["titulo"] == "Original"
    assert resultado["descripcion"] == "desc original"


@pytest.mark.integration
def test_eliminar_evento_soft_delete(
    service_client, seed_drogueria, seed_usuario_sistema, limpiar_eventos
):
    evento = crear_evento(
        service_client,
        drogueria_id=seed_drogueria["id"],
        body=EventoCreate(tipo="llamada", titulo="A borrar"),
        usuario_id=seed_usuario_sistema["id"],
    )

    eliminar_evento(
        service_client, evento_id=evento["id"], drogueria_id=seed_drogueria["id"],
        usuario_id=seed_usuario_sistema["id"],
    )

    # eventos filtra deleted_at automáticamente por RLS, pero obtener_evento lee
    # directo de la tabla sin ese filtro adicional del backend -- confirmamos que
    # la fila quedó marcada.
    fila = (
        service_client.table("eventos").select("deleted_at,deleted_by")
        .eq("id", evento["id"]).execute().data[0]
    )
    assert fila["deleted_at"] is not None
    assert fila["deleted_by"] == seed_usuario_sistema["id"]


@pytest.mark.integration
def test_calendario_filtra_por_rango_de_fechas(
    service_client, seed_drogueria, seed_usuario_sistema, limpiar_eventos
):
    dentro = crear_evento(
        service_client,
        drogueria_id=seed_drogueria["id"],
        body=EventoCreate(
            tipo="llamada", titulo="Dentro de rango",
            fecha_programada=datetime(2026, 6, 15, tzinfo=timezone.utc),
        ),
        usuario_id=seed_usuario_sistema["id"],
    )
    crear_evento(
        service_client,
        drogueria_id=seed_drogueria["id"],
        body=EventoCreate(
            tipo="llamada", titulo="Fuera de rango",
            fecha_programada=datetime(2027, 1, 1, tzinfo=timezone.utc),
        ),
        usuario_id=seed_usuario_sistema["id"],
    )

    resultado = calendario(
        service_client, drogueria_id=seed_drogueria["id"], desde="2026-06-01", hasta="2026-06-30"
    )
    assert [r["evento_id"] for r in resultado] == [dentro["id"]]


# ---------------------------------------------------------------------------
# eventos_recurrentes
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_crear_evento_recurrente_calcula_proxima_ejecucion(
    service_client, seed_drogueria, seed_usuario_sistema, limpiar_eventos
):
    resultado = crear_evento_recurrente(
        service_client,
        drogueria_id=seed_drogueria["id"],
        body=EventoRecurrenteCreate(
            tipo="seguimiento", titulo="Revisar stock",
            rrule="FREQ=WEEKLY;BYDAY=MO", fecha_inicio=date(2026, 1, 1),
        ),
        usuario_id=seed_usuario_sistema["id"],
    )
    assert resultado["proxima_ejecucion"] is not None


@pytest.mark.integration
def test_generar_instancias_recurrentes_materializa_y_recalcula(
    service_client, seed_drogueria, seed_usuario_sistema, limpiar_eventos
):
    plantilla = crear_evento_recurrente(
        service_client,
        drogueria_id=seed_drogueria["id"],
        body=EventoRecurrenteCreate(
            tipo="seguimiento", titulo="Revisar stock semanal",
            rrule="FREQ=DAILY", fecha_inicio=date(2020, 1, 1),
        ),
        usuario_id=seed_usuario_sistema["id"],
    )
    # Forzamos proxima_ejecucion al pasado para que el scheduler la levante ahora.
    service_client.table("eventos_recurrentes").update(
        {"proxima_ejecucion": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()}
    ).eq("id", plantilla["id"]).execute()

    generadas = generar_instancias_recurrentes(service_client, usuario_scheduler_id=seed_usuario_sistema["id"])
    assert generadas == 1

    instancias = (
        service_client.table("eventos")
        .select("*")
        .eq("evento_recurrente_id", plantilla["id"])
        .execute()
        .data
    )
    assert len(instancias) == 1
    assert instancias[0]["origen"] == "sistema"

    actualizada = listar_eventos_recurrentes(service_client, drogueria_id=seed_drogueria["id"])
    fila = next(p for p in actualizada if p["id"] == plantilla["id"])
    assert fila["instancias_generadas"] == 1
    assert fila["proxima_ejecucion"] is not None


@pytest.mark.integration
def test_generar_instancias_recurrentes_desactiva_al_superar_fecha_fin(
    service_client, seed_drogueria, seed_usuario_sistema, limpiar_eventos
):
    ayer = (datetime.now(timezone.utc) - timedelta(days=1)).date()
    plantilla = crear_evento_recurrente(
        service_client,
        drogueria_id=seed_drogueria["id"],
        body=EventoRecurrenteCreate(
            tipo="seguimiento", titulo="Única vez",
            rrule="FREQ=DAILY;COUNT=1", fecha_inicio=date(2020, 1, 1), fecha_fin=ayer,
        ),
        usuario_id=seed_usuario_sistema["id"],
    )
    service_client.table("eventos_recurrentes").update(
        {"proxima_ejecucion": (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()}
    ).eq("id", plantilla["id"]).execute()

    generar_instancias_recurrentes(service_client, usuario_scheduler_id=seed_usuario_sistema["id"])

    actualizada = listar_eventos_recurrentes(service_client, drogueria_id=seed_drogueria["id"], activa=False)
    assert any(p["id"] == plantilla["id"] for p in actualizada)
