import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from supabase import Client

from services.presupuestacion.automatizaciones import repository as repo
from services.presupuestacion.automatizaciones.models import (
    ReglaAutomatizacionCreate,
    ReglaAutomatizacionUpdate,
)
from services.presupuestacion.core.database import get_service_client
from services.presupuestacion.core.exceptions import NotFoundError
from services.presupuestacion.eventos.models import EventoCreate
from services.presupuestacion.eventos.service import crear_evento
from services.presupuestacion.notificaciones.service import crear_notificacion

logger = logging.getLogger(__name__)

_ACCIONES_INMEDIATAS_SOPORTADAS = {"crear_evento", "enviar_notificacion"}


def crear_regla(client: Client, *, drogueria_id: str, body: ReglaAutomatizacionCreate, usuario_id: str) -> dict[str, Any]:
    return repo.crear_regla(
        client,
        {
            "drogueria_id": drogueria_id,
            "nombre": body.nombre,
            "descripcion": body.descripcion,
            "evento_disparador": body.evento_disparador,
            "entidad_objetivo": body.entidad_objetivo,
            "condicion": body.condicion,
            "tipo_accion": body.tipo_accion,
            "parametros_accion": body.parametros_accion,
            "modo_ejecucion": body.modo_ejecucion,
            "max_reintentos": body.max_reintentos,
            "prioridad": body.prioridad,
            "created_by": usuario_id,
            "updated_by": usuario_id,
        },
    )


def listar_reglas(client: Client, *, drogueria_id: str, activa: bool | None = None) -> list[dict[str, Any]]:
    return repo.listar_reglas(client, drogueria_id=drogueria_id, activa=activa)


def actualizar_regla(
    client: Client, *, regla_id: str, drogueria_id: str, body: ReglaAutomatizacionUpdate, usuario_id: str
) -> dict[str, Any]:
    regla = repo.obtener_regla(client, regla_id=regla_id)
    if regla is None or regla["drogueria_id"] != drogueria_id:
        raise NotFoundError("No se encontró la regla")
    campos = body.model_dump(exclude_unset=True)
    campos["updated_by"] = usuario_id
    return repo.actualizar_regla(client, regla_id=regla_id, campos=campos)


def metricas(client: Client, *, drogueria_id: str) -> list[dict[str, Any]]:
    return repo.metricas(client, drogueria_id=drogueria_id)


def crear_regla_para_endpoint(*, drogueria_id: str, body: ReglaAutomatizacionCreate, usuario_id: str) -> dict[str, Any]:
    return crear_regla(get_service_client(), drogueria_id=drogueria_id, body=body, usuario_id=usuario_id)


def actualizar_regla_para_endpoint(
    *, regla_id: str, drogueria_id: str, body: ReglaAutomatizacionUpdate, usuario_id: str
) -> dict[str, Any]:
    return actualizar_regla(
        get_service_client(), regla_id=regla_id, drogueria_id=drogueria_id, body=body, usuario_id=usuario_id
    )


# -- motor -------------------------------------------------------------------

def _evaluar_condicion(condicion: dict | None, datos: dict[str, Any]) -> bool:
    """condicion=None es comodín (siempre matchea). Formato soportado (deliberadamente
    simple, según el spec): {"campo": "...", "valor": ...} → datos.get(campo) == valor."""
    if not condicion:
        return True
    campo = condicion.get("campo")
    valor = condicion.get("valor")
    return datos.get(campo) == valor


def _ejecutar_accion(
    client: Client,
    *,
    regla: dict[str, Any],
    entidad_objetivo: str,
    entidad_id: str,
    drogueria_id: str,
    usuario_id: str,
) -> tuple[bool, Any]:
    parametros = regla.get("parametros_accion") or {}
    columna_fk = repo.COLUMNA_FK_POR_ENTIDAD.get(entidad_objetivo)

    if regla["tipo_accion"] == "crear_evento":
        campos_evento = dict(parametros)
        if columna_fk:
            campos_evento[columna_fk] = entidad_id
        try:
            body = EventoCreate(**campos_evento)
        except Exception as exc:  # parametros_accion mal formados
            return False, f"parametros_accion inválidos para crear_evento: {exc}"
        evento = crear_evento(
            client, drogueria_id=drogueria_id, body=body, usuario_id=usuario_id, origen="automatico"
        )
        return True, {"evento_id": evento["id"]}

    if regla["tipo_accion"] == "enviar_notificacion":
        relaciones = {columna_fk: entidad_id} if columna_fk else {}
        try:
            notificacion = crear_notificacion(
                client,
                drogueria_id=drogueria_id,
                destinatario_id=parametros["destinatario_id"],
                tipo=parametros["tipo"],
                titulo=parametros["titulo"],
                mensaje=parametros.get("mensaje"),
                prioridad=parametros.get("prioridad", "media"),
                url_destino=parametros.get("url_destino"),
                origen="automatizacion",
                relaciones=relaciones,
            )
        except (KeyError, TypeError) as exc:
            return False, f"parametros_accion inválidos para enviar_notificacion: {exc}"
        return True, {"notificacion_id": notificacion["id"]}

    return False, f"tipo_accion '{regla['tipo_accion']}' no implementado aún"


def disparar_reglas(
    client: Client,
    *,
    drogueria_id: str,
    entidad_objetivo: str,
    evento_disparador: str,
    entidad_id: str,
    datos: dict[str, Any],
    usuario_id: str,
) -> list[dict[str, Any]]:
    """Busca reglas activas que matcheen entidad_objetivo+evento_disparador, evalúa
    su condición y ejecuta (inmediato) o encola (cola) la acción. Devuelve las
    acciones_ejecutadas creadas/actualizadas.

    Nota de alcance: esta función y `procesar_acciones_pendientes()` están completas y
    testeadas, pero HOY nada en el código las llama fuera de los tests -- ningún flujo de
    negocio (confirmar una OC, adjudicar una licitación, etc.) dispara `disparar_reglas()`,
    y no existe un worker/cron real que corra `procesar_acciones_pendientes()` ni el
    scheduler de `eventos.generar_instancias_recurrentes()` periódicamente. Es exactamente
    el "motor mínimo, sin conectar a los eventos de negocio todavía" que pedía el spec para
    esta ronda -- conectarlo es la próxima ronda, no una omisión de esta."""
    resultados = []
    for regla in repo.reglas_activas_para(
        client, drogueria_id=drogueria_id, entidad_objetivo=entidad_objetivo, evento_disparador=evento_disparador
    ):
        if not _evaluar_condicion(regla["condicion"], datos):
            continue

        columna_fk = repo.COLUMNA_FK_POR_ENTIDAD.get(entidad_objetivo)
        if columna_fk is None:
            logger.warning(
                "disparar_reglas: entidad_objetivo=%s no tiene columna en acciones_ejecutadas "
                "(gap de schema: ck_ae_una_entidad no cubre extraction_result/entrega) — se omite regla %s",
                entidad_objetivo, regla["id"],
            )
            continue

        if regla["modo_ejecucion"] == "inmediato":
            inicio = datetime.now(timezone.utc)
            exito, resultado = _ejecutar_accion(
                client, regla=regla, entidad_objetivo=entidad_objetivo, entidad_id=entidad_id,
                drogueria_id=drogueria_id, usuario_id=usuario_id,
            )
            fin = datetime.now(timezone.utc)
            accion = repo.crear_accion_ejecutada(
                client,
                {
                    "drogueria_id": drogueria_id,
                    "regla_id": regla["id"],
                    columna_fk: entidad_id,
                    "tipo_accion": regla["tipo_accion"],
                    "estado": "completada" if exito else "fallida",
                    "resultado": resultado if exito else None,
                    "error_msg": None if exito else str(resultado),
                    "intentos": 1,
                    "iniciado_at": inicio.isoformat(),
                    "finalizado_at": fin.isoformat(),
                    "duracion_ms": int((fin - inicio).total_seconds() * 1000),
                    "ejecutado_at": fin.isoformat(),
                },
            )
        else:
            accion = repo.crear_accion_ejecutada(
                client,
                {
                    "drogueria_id": drogueria_id,
                    "regla_id": regla["id"],
                    columna_fk: entidad_id,
                    "tipo_accion": regla["tipo_accion"],
                    "estado": "pendiente",
                },
            )
        resultados.append(accion)

    return resultados


def procesar_acciones_pendientes(client: Client, *, usuario_scheduler_id: str) -> int:
    """Worker de la cola: toma pendientes con proximo_intento_at <= NOW() (o nunca
    intentadas), ejecuta la acción de su regla y actualiza métricas/estado. Si falla
    y no agotó max_reintentos, reprograma con backoff exponencial (2**intentos min)."""
    procesadas = 0
    for accion in repo.listar_acciones_pendientes(client):
        regla = repo.obtener_regla(client, regla_id=accion["regla_id"]) if accion["regla_id"] else None
        if regla is None:
            repo.actualizar_accion_ejecutada(
                client, accion_id=accion["id"],
                campos={"estado": "fallida", "error_msg": "La regla asociada ya no existe"},
            )
            procesadas += 1
            continue

        entidad_objetivo = regla["entidad_objetivo"]
        columna_fk = repo.COLUMNA_FK_POR_ENTIDAD.get(entidad_objetivo)
        entidad_id = accion.get(columna_fk) if columna_fk else None

        inicio = datetime.now(timezone.utc)
        exito, resultado = _ejecutar_accion(
            client, regla=regla, entidad_objetivo=entidad_objetivo, entidad_id=entidad_id,
            drogueria_id=accion["drogueria_id"], usuario_id=usuario_scheduler_id,
        )
        fin = datetime.now(timezone.utc)
        intentos = accion["intentos"] + 1

        if exito:
            repo.actualizar_accion_ejecutada(
                client, accion_id=accion["id"],
                campos={
                    "estado": "completada", "resultado": resultado, "intentos": intentos,
                    "iniciado_at": inicio.isoformat(), "finalizado_at": fin.isoformat(),
                    "duracion_ms": int((fin - inicio).total_seconds() * 1000),
                    "ejecutado_at": fin.isoformat(),
                },
            )
        elif intentos < regla["max_reintentos"]:
            proximo = fin + timedelta(minutes=2 ** intentos)
            repo.actualizar_accion_ejecutada(
                client, accion_id=accion["id"],
                campos={
                    "estado": "pendiente", "error_msg": str(resultado), "intentos": intentos,
                    "proximo_intento_at": proximo.isoformat(),
                },
            )
        else:
            repo.actualizar_accion_ejecutada(
                client, accion_id=accion["id"],
                campos={
                    "estado": "fallida", "error_msg": str(resultado), "intentos": intentos,
                    "finalizado_at": fin.isoformat(),
                },
            )
        procesadas += 1

    return procesadas
