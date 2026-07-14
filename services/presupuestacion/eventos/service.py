import uuid
from datetime import datetime, timezone
from typing import Any

from dateutil.rrule import rrulestr
from supabase import Client

from services.presupuestacion.core.audit import registrar_cambio, registrar_cambios, registrar_evento_ciclo_vida
from services.presupuestacion.core.database import get_service_client
from services.presupuestacion.core.exceptions import NotFoundError, ValidationError
from services.presupuestacion.eventos import repository as repo
from services.presupuestacion.eventos.models import (
    EventoCreate,
    EventoRecurrenteCreate,
    EventoRecurrenteUpdate,
    EventoUpdate,
    OrigenEvento,
)

# eventos.origen usa 'automatico'; historial_cambios.origen usa 'automatizacion' (mismo
# concepto, vocabulario distinto -- ver core/audit.py OrigenCambio). dict[OrigenEvento, str]
# en vez de dict[str, str] para que agregar un valor a OrigenEvento sin agregarlo acá
# rompa el chequeo de tipos, no falle en silencio recién en runtime con un KeyError.
_ORIGEN_EVENTO_A_ORIGEN_CAMBIO: dict[OrigenEvento, str] = {
    "usuario": "usuario",
    "ia": "ia",
    "sistema": "sistema",
    "automatico": "automatizacion",
}

# -- eventos -----------------------------------------------------------------

def crear_evento(
    client: Client,
    *,
    drogueria_id: str,
    body: EventoCreate,
    usuario_id: str,
    origen: OrigenEvento = "usuario",
) -> dict[str, Any]:
    estado = "pendiente"
    if body.depende_de_id is not None:
        dependencia = repo.obtener_evento(client, evento_id=body.depende_de_id)
        if dependencia is None:
            raise ValidationError("El evento del que depende no existe")
        if dependencia["estado"] != "completado":
            estado = "bloqueado"

    evento = repo.crear_evento(
        client,
        {
            "drogueria_id": drogueria_id,
            "tipo": body.tipo,
            "titulo": body.titulo,
            "descripcion": body.descripcion,
            "prioridad": body.prioridad,
            "estado": estado,
            "origen": origen,
            "proceso_comercial_id": body.proceso_comercial_id,
            "comparativa_id": body.comparativa_id,
            "orden_compra_id": body.orden_compra_id,
            "cliente_id": body.cliente_id,
            "proveedor_id": body.proveedor_id,
            "responsable_id": body.responsable_id,
            "depende_de_id": body.depende_de_id,
            "fecha_programada": body.fecha_programada.isoformat() if body.fecha_programada else None,
            "fecha_limite": body.fecha_limite.isoformat() if body.fecha_limite else None,
            "metadata": body.metadata,
            "created_by": usuario_id,
            "updated_by": usuario_id,
        },
    )
    registrar_evento_ciclo_vida(
        client,
        entidad="evento",
        entidad_id=evento["id"],
        drogueria_id=drogueria_id,
        tipo_cambio="creacion",
        origen=_ORIGEN_EVENTO_A_ORIGEN_CAMBIO[origen],
        usuario_id=usuario_id,
    )
    return evento


def obtener_evento(client: Client, *, evento_id: str, drogueria_id: str) -> dict[str, Any]:
    evento = repo.obtener_evento(client, evento_id=evento_id)
    if evento is None or evento["drogueria_id"] != drogueria_id:
        raise NotFoundError("No se encontró el evento")
    return evento


def listar_eventos(
    client: Client,
    *,
    drogueria_id: str,
    estado: str | None = None,
    proceso_comercial_id: str | None = None,
    responsable_id: str | None = None,
) -> list[dict[str, Any]]:
    return repo.listar_eventos(
        client,
        drogueria_id=drogueria_id,
        estado=estado,
        proceso_comercial_id=proceso_comercial_id,
        responsable_id=responsable_id,
    )


def actualizar_evento(
    client: Client, *, evento_id: str, drogueria_id: str, body: EventoUpdate, usuario_id: str
) -> dict[str, Any]:
    evento = obtener_evento(client, evento_id=evento_id, drogueria_id=drogueria_id)
    campos = body.model_dump(exclude_unset=True)
    for campo in ("fecha_programada", "fecha_limite"):
        if campo in campos and campos[campo] is not None:
            campos[campo] = campos[campo].isoformat()

    cambios_reales = {
        campo: (evento.get(campo), nuevo)
        for campo, nuevo in campos.items()
        if evento.get(campo) != nuevo
    }

    campos["updated_by"] = usuario_id
    evento_actualizado = repo.actualizar_evento(client, evento_id=evento_id, campos=campos)

    if cambios_reales:
        registrar_cambios(
            client,
            entidad="evento",
            entidad_id=evento_id,
            drogueria_id=drogueria_id,
            cambios=cambios_reales,
            origen="usuario",
            usuario_id=usuario_id,
        )

    return evento_actualizado


def completar_evento(client: Client, *, evento_id: str, drogueria_id: str, usuario_id: str) -> dict[str, Any]:
    evento = obtener_evento(client, evento_id=evento_id, drogueria_id=drogueria_id)
    estado_anterior = evento["estado"]
    actualizado = repo.actualizar_evento(
        client,
        evento_id=evento_id,
        campos={
            "estado": "completado",
            "fecha_real": datetime.now(timezone.utc).isoformat(),
            "updated_by": usuario_id,
        },
    )
    registrar_cambio(
        client,
        entidad="evento",
        entidad_id=evento_id,
        drogueria_id=drogueria_id,
        campo="estado",
        valor_anterior=estado_anterior,
        valor_nuevo="completado",
        origen="usuario",
        usuario_id=usuario_id,
        batch_id=str(uuid.uuid4()),
    )

    for bloqueado in repo.listar_bloqueados_por_dependencia(client, depende_de_id=evento_id):
        repo.actualizar_evento(
            client, evento_id=bloqueado["id"], campos={"estado": "pendiente", "updated_by": usuario_id}
        )
        registrar_cambio(
            client,
            entidad="evento",
            entidad_id=bloqueado["id"],
            drogueria_id=drogueria_id,
            campo="estado",
            valor_anterior="bloqueado",
            valor_nuevo="pendiente",
            origen="usuario",
            usuario_id=usuario_id,
            batch_id=str(uuid.uuid4()),
        )

    return actualizado


def eliminar_evento(client: Client, *, evento_id: str, drogueria_id: str, usuario_id: str) -> None:
    obtener_evento(client, evento_id=evento_id, drogueria_id=drogueria_id)
    repo.soft_delete_evento(client, evento_id=evento_id, usuario_id=usuario_id)
    registrar_evento_ciclo_vida(
        client,
        entidad="evento",
        entidad_id=evento_id,
        drogueria_id=drogueria_id,
        tipo_cambio="eliminacion",
        origen="usuario",
        usuario_id=usuario_id,
    )


def obtener_bloqueo(client: Client, *, evento_id: str, drogueria_id: str) -> dict[str, Any]:
    obtener_evento(client, evento_id=evento_id, drogueria_id=drogueria_id)
    bloqueo = repo.bloqueo_de_evento(client, evento_id=evento_id)
    if bloqueo is None:
        raise NotFoundError("No se encontró el evento")
    return bloqueo


def calendario(
    client: Client, *, drogueria_id: str, desde: str | None = None, hasta: str | None = None
) -> list[dict[str, Any]]:
    return repo.calendario(client, drogueria_id=drogueria_id, desde=desde, hasta=hasta)


def crear_evento_para_endpoint(*, drogueria_id: str, body: EventoCreate, usuario_id: str) -> dict[str, Any]:
    return crear_evento(get_service_client(), drogueria_id=drogueria_id, body=body, usuario_id=usuario_id)


def actualizar_evento_para_endpoint(
    *, evento_id: str, drogueria_id: str, body: EventoUpdate, usuario_id: str
) -> dict[str, Any]:
    return actualizar_evento(
        get_service_client(), evento_id=evento_id, drogueria_id=drogueria_id, body=body, usuario_id=usuario_id
    )


def completar_evento_para_endpoint(*, evento_id: str, drogueria_id: str, usuario_id: str) -> dict[str, Any]:
    return completar_evento(
        get_service_client(), evento_id=evento_id, drogueria_id=drogueria_id, usuario_id=usuario_id
    )


def eliminar_evento_para_endpoint(*, evento_id: str, drogueria_id: str, usuario_id: str) -> None:
    eliminar_evento(get_service_client(), evento_id=evento_id, drogueria_id=drogueria_id, usuario_id=usuario_id)


# -- eventos_recurrentes -------------------------------------------------------

def crear_evento_recurrente(
    client: Client, *, drogueria_id: str, body: EventoRecurrenteCreate, usuario_id: str
) -> dict[str, Any]:
    try:
        regla = rrulestr(body.rrule, dtstart=datetime.now(timezone.utc))
        proxima = regla.after(datetime.now(timezone.utc))
    except (ValueError, TypeError) as exc:
        raise ValidationError(f"rrule inválida: {exc}") from exc

    return repo.crear_evento_recurrente(
        client,
        {
            "drogueria_id": drogueria_id,
            "tipo": body.tipo,
            "titulo": body.titulo,
            "descripcion": body.descripcion,
            "prioridad": body.prioridad,
            "responsable_id": body.responsable_id,
            "cliente_id": body.cliente_id,
            "proveedor_id": body.proveedor_id,
            "metadata": body.metadata,
            "rrule": body.rrule,
            "fecha_inicio": body.fecha_inicio.isoformat(),
            "fecha_fin": body.fecha_fin.isoformat() if body.fecha_fin else None,
            "proxima_ejecucion": proxima.isoformat() if proxima else None,
            "created_by": usuario_id,
            "updated_by": usuario_id,
        },
    )


def listar_eventos_recurrentes(
    client: Client, *, drogueria_id: str, activa: bool | None = None
) -> list[dict[str, Any]]:
    return repo.listar_eventos_recurrentes(client, drogueria_id=drogueria_id, activa=activa)


def actualizar_evento_recurrente(
    client: Client,
    *,
    evento_recurrente_id: str,
    drogueria_id: str,
    body: EventoRecurrenteUpdate,
    usuario_id: str,
) -> dict[str, Any]:
    plantilla = repo.obtener_evento_recurrente(client, evento_recurrente_id=evento_recurrente_id)
    if plantilla is None or plantilla["drogueria_id"] != drogueria_id:
        raise NotFoundError("No se encontró el evento recurrente")

    campos = body.model_dump(exclude_unset=True)
    if "fecha_fin" in campos and campos["fecha_fin"] is not None:
        campos["fecha_fin"] = campos["fecha_fin"].isoformat()
    campos["updated_by"] = usuario_id
    return repo.actualizar_evento_recurrente(
        client, evento_recurrente_id=evento_recurrente_id, campos=campos
    )


def crear_evento_recurrente_para_endpoint(
    *, drogueria_id: str, body: EventoRecurrenteCreate, usuario_id: str
) -> dict[str, Any]:
    return crear_evento_recurrente(
        get_service_client(), drogueria_id=drogueria_id, body=body, usuario_id=usuario_id
    )


def actualizar_evento_recurrente_para_endpoint(
    *, evento_recurrente_id: str, drogueria_id: str, body: EventoRecurrenteUpdate, usuario_id: str
) -> dict[str, Any]:
    return actualizar_evento_recurrente(
        get_service_client(),
        evento_recurrente_id=evento_recurrente_id,
        drogueria_id=drogueria_id,
        body=body,
        usuario_id=usuario_id,
    )


def generar_instancias_recurrentes(client: Client, *, usuario_scheduler_id: str) -> int:
    """Job periódico: materializa una instancia en 'eventos' por cada plantilla
    vencida y recalcula su próxima ejecución. Si la próxima ejecución cae después
    de fecha_fin, desactiva la plantilla en vez de seguir generando."""
    generadas = 0
    for plantilla in repo.listar_recurrentes_a_ejecutar(client):
        evento = repo.crear_evento(
            client,
            {
                "drogueria_id": plantilla["drogueria_id"],
                "tipo": plantilla["tipo"],
                "titulo": plantilla["titulo"],
                "descripcion": plantilla["descripcion"],
                "prioridad": plantilla["prioridad"],
                "estado": "pendiente",
                "origen": "sistema",
                "cliente_id": plantilla["cliente_id"],
                "proveedor_id": plantilla["proveedor_id"],
                "responsable_id": plantilla["responsable_id"],
                "evento_recurrente_id": plantilla["id"],
                "fecha_programada": plantilla["proxima_ejecucion"],
                "metadata": plantilla["metadata"],
                "created_by": usuario_scheduler_id,
                "updated_by": usuario_scheduler_id,
            },
        )
        registrar_evento_ciclo_vida(
            client,
            entidad="evento",
            entidad_id=evento["id"],
            drogueria_id=plantilla["drogueria_id"],
            tipo_cambio="creacion",
            origen="sistema",
            usuario_id=usuario_scheduler_id,
        )
        generadas += 1

        ejecutada_en = datetime.fromisoformat(plantilla["proxima_ejecucion"])
        regla = rrulestr(plantilla["rrule"], dtstart=ejecutada_en)
        proxima = regla.after(ejecutada_en)

        fecha_fin = plantilla.get("fecha_fin")
        activa = True
        if proxima is not None and fecha_fin is not None:
            limite = datetime.fromisoformat(fecha_fin).replace(tzinfo=proxima.tzinfo)
            if proxima.date() > limite.date():
                activa = False
                proxima = None
        if proxima is None and fecha_fin is not None:
            activa = False

        repo.actualizar_evento_recurrente(
            client,
            evento_recurrente_id=plantilla["id"],
            campos={
                "proxima_ejecucion": proxima.isoformat() if proxima else None,
                "ultima_generacion": datetime.now(timezone.utc).isoformat(),
                "instancias_generadas": plantilla["instancias_generadas"] + 1,
                "activa": activa,
            },
        )

    return generadas
