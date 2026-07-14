import pytest

from services.presupuestacion.automatizaciones.models import ReglaAutomatizacionCreate, ReglaAutomatizacionUpdate
from services.presupuestacion.automatizaciones.service import (
    actualizar_regla,
    crear_regla,
    disparar_reglas,
    listar_reglas,
    metricas,
    procesar_acciones_pendientes,
)


def _regla(**overrides) -> ReglaAutomatizacionCreate:
    base = {
        "nombre": "Regla de test",
        "evento_disparador": "completado",
        "entidad_objetivo": "proceso_comercial",
        "tipo_accion": "enviar_notificacion",
        "modo_ejecucion": "cola",
    }
    base.update(overrides)
    return ReglaAutomatizacionCreate(**base)


@pytest.mark.integration
def test_crear_y_listar_regla(
    service_client, seed_drogueria, seed_usuario_sistema, limpiar_automatizaciones
):
    creada = crear_regla(
        service_client, drogueria_id=seed_drogueria["id"], body=_regla(),
        usuario_id=seed_usuario_sistema["id"],
    )
    assert creada["activa"] is True

    todas = listar_reglas(service_client, drogueria_id=seed_drogueria["id"])
    assert [r["id"] for r in todas] == [creada["id"]]


@pytest.mark.integration
def test_actualizar_regla_solo_pisa_campos_enviados(
    service_client, seed_drogueria, seed_usuario_sistema, limpiar_automatizaciones
):
    creada = crear_regla(
        service_client, drogueria_id=seed_drogueria["id"], body=_regla(prioridad=5),
        usuario_id=seed_usuario_sistema["id"],
    )

    resultado = actualizar_regla(
        service_client, regla_id=creada["id"], drogueria_id=seed_drogueria["id"],
        body=ReglaAutomatizacionUpdate(activa=False), usuario_id=seed_usuario_sistema["id"],
    )
    assert resultado["activa"] is False
    assert resultado["prioridad"] == 5


@pytest.mark.integration
def test_disparar_reglas_condicion_no_matchea_no_ejecuta(
    service_client, seed_drogueria, seed_proceso_comercial, seed_usuario_sistema, limpiar_automatizaciones
):
    crear_regla(
        service_client, drogueria_id=seed_drogueria["id"],
        body=_regla(condicion={"campo": "clase", "valor": "licitacion"}),
        usuario_id=seed_usuario_sistema["id"],
    )

    resultados = disparar_reglas(
        service_client, drogueria_id=seed_drogueria["id"], entidad_objetivo="proceso_comercial",
        evento_disparador="completado", entidad_id=seed_proceso_comercial["id"],
        datos={"clase": "cotizacion"}, usuario_id=seed_usuario_sistema["id"],
    )
    assert resultados == []


@pytest.mark.integration
def test_disparar_reglas_modo_inmediato_crea_evento_sincronicamente(
    service_client, seed_drogueria, seed_proceso_comercial, seed_usuario_sistema, limpiar_automatizaciones
):
    crear_regla(
        service_client, drogueria_id=seed_drogueria["id"],
        body=_regla(
            tipo_accion="crear_evento", modo_ejecucion="inmediato",
            parametros_accion={"tipo": "seguimiento", "titulo": "Seguimiento automático"},
        ),
        usuario_id=seed_usuario_sistema["id"],
    )

    resultados = disparar_reglas(
        service_client, drogueria_id=seed_drogueria["id"], entidad_objetivo="proceso_comercial",
        evento_disparador="completado", entidad_id=seed_proceso_comercial["id"],
        datos={}, usuario_id=seed_usuario_sistema["id"],
    )

    assert len(resultados) == 1
    assert resultados[0]["estado"] == "completada"
    evento_id = resultados[0]["resultado"]["evento_id"]
    evento = service_client.table("eventos").select("*").eq("id", evento_id).execute().data[0]
    assert evento["titulo"] == "Seguimiento automático"
    assert evento["origen"] == "automatico"
    assert evento["proceso_comercial_id"] == seed_proceso_comercial["id"]


@pytest.mark.integration
def test_disparar_reglas_modo_cola_encola_pendiente(
    service_client, seed_drogueria, seed_proceso_comercial, seed_usuario_sistema, limpiar_automatizaciones
):
    crear_regla(
        service_client, drogueria_id=seed_drogueria["id"],
        body=_regla(
            tipo_accion="enviar_notificacion", modo_ejecucion="cola",
            parametros_accion={
                "destinatario_id": seed_usuario_sistema["id"], "tipo": "sistema", "titulo": "Aviso",
            },
        ),
        usuario_id=seed_usuario_sistema["id"],
    )

    resultados = disparar_reglas(
        service_client, drogueria_id=seed_drogueria["id"], entidad_objetivo="proceso_comercial",
        evento_disparador="completado", entidad_id=seed_proceso_comercial["id"],
        datos={}, usuario_id=seed_usuario_sistema["id"],
    )

    assert len(resultados) == 1
    assert resultados[0]["estado"] == "pendiente"


@pytest.mark.integration
def test_procesar_acciones_pendientes_ejecuta_y_completa(
    service_client, seed_drogueria, seed_proceso_comercial, seed_usuario_sistema, limpiar_automatizaciones
):
    crear_regla(
        service_client, drogueria_id=seed_drogueria["id"],
        body=_regla(
            tipo_accion="enviar_notificacion", modo_ejecucion="cola",
            parametros_accion={
                "destinatario_id": seed_usuario_sistema["id"], "tipo": "sistema", "titulo": "Aviso",
            },
        ),
        usuario_id=seed_usuario_sistema["id"],
    )
    disparar_reglas(
        service_client, drogueria_id=seed_drogueria["id"], entidad_objetivo="proceso_comercial",
        evento_disparador="completado", entidad_id=seed_proceso_comercial["id"],
        datos={}, usuario_id=seed_usuario_sistema["id"],
    )

    procesadas = procesar_acciones_pendientes(service_client, usuario_scheduler_id=seed_usuario_sistema["id"])
    assert procesadas == 1

    acciones = (
        service_client.table("acciones_ejecutadas")
        .select("*").eq("drogueria_id", seed_drogueria["id"]).execute().data
    )
    assert acciones[0]["estado"] == "completada"


@pytest.mark.integration
def test_procesar_acciones_pendientes_reintenta_con_backoff_si_falla(
    service_client, seed_drogueria, seed_proceso_comercial, seed_usuario_sistema, limpiar_automatizaciones
):
    crear_regla(
        service_client, drogueria_id=seed_drogueria["id"],
        body=_regla(tipo_accion="enviar_email", modo_ejecucion="cola", max_reintentos=3),
        usuario_id=seed_usuario_sistema["id"],
    )
    disparar_reglas(
        service_client, drogueria_id=seed_drogueria["id"], entidad_objetivo="proceso_comercial",
        evento_disparador="completado", entidad_id=seed_proceso_comercial["id"],
        datos={}, usuario_id=seed_usuario_sistema["id"],
    )

    procesar_acciones_pendientes(service_client, usuario_scheduler_id=seed_usuario_sistema["id"])

    accion = (
        service_client.table("acciones_ejecutadas")
        .select("*").eq("drogueria_id", seed_drogueria["id"]).execute().data[0]
    )
    assert accion["estado"] == "pendiente"
    assert accion["intentos"] == 1
    assert accion["proximo_intento_at"] is not None
    assert "no implementado" in accion["error_msg"]


@pytest.mark.integration
def test_procesar_acciones_pendientes_marca_fallida_al_agotar_reintentos(
    service_client, seed_drogueria, seed_proceso_comercial, seed_usuario_sistema, limpiar_automatizaciones
):
    crear_regla(
        service_client, drogueria_id=seed_drogueria["id"],
        body=_regla(tipo_accion="enviar_email", modo_ejecucion="cola", max_reintentos=2),
        usuario_id=seed_usuario_sistema["id"],
    )
    disparar_reglas(
        service_client, drogueria_id=seed_drogueria["id"], entidad_objetivo="proceso_comercial",
        evento_disparador="completado", entidad_id=seed_proceso_comercial["id"],
        datos={}, usuario_id=seed_usuario_sistema["id"],
    )

    procesar_acciones_pendientes(service_client, usuario_scheduler_id=seed_usuario_sistema["id"])

    accion_id = (
        service_client.table("acciones_ejecutadas")
        .select("id").eq("drogueria_id", seed_drogueria["id"]).execute().data[0]["id"]
    )
    # Forzamos que el próximo intento ya esté vencido para que el segundo pase lo levante.
    service_client.table("acciones_ejecutadas").update({"proximo_intento_at": "2020-01-01T00:00:00Z"}).eq(
        "id", accion_id
    ).execute()

    procesar_acciones_pendientes(service_client, usuario_scheduler_id=seed_usuario_sistema["id"])

    accion = service_client.table("acciones_ejecutadas").select("*").eq("id", accion_id).execute().data[0]
    assert accion["estado"] == "fallida"
    assert accion["intentos"] == 2


@pytest.mark.integration
def test_metricas(service_client, seed_drogueria, seed_proceso_comercial, seed_usuario_sistema, limpiar_automatizaciones):
    crear_regla(
        service_client, drogueria_id=seed_drogueria["id"],
        body=_regla(
            tipo_accion="enviar_notificacion", modo_ejecucion="inmediato",
            parametros_accion={
                "destinatario_id": seed_usuario_sistema["id"], "tipo": "sistema", "titulo": "Aviso",
            },
        ),
        usuario_id=seed_usuario_sistema["id"],
    )
    disparar_reglas(
        service_client, drogueria_id=seed_drogueria["id"], entidad_objetivo="proceso_comercial",
        evento_disparador="completado", entidad_id=seed_proceso_comercial["id"],
        datos={}, usuario_id=seed_usuario_sistema["id"],
    )

    resultado = metricas(service_client, drogueria_id=seed_drogueria["id"])
    assert len(resultado) == 1
    assert resultado[0]["ejecuciones"] == 1
    assert resultado[0]["exitosas"] == 1
