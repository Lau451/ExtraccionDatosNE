"""Servicio de gestión de PCP (0011_pcp_modelo.sql M1, design.md D2, spec
`pcp-gestion`).

Máquina de estados como mapa explícito de transiciones permitidas
(`_TRANSICIONES_PERMITIDAS`), no if/else ad-hoc por par de estados -- para
que PR7 (pcp-negociacion) y PR11 (cierre/feedback loop) puedan razonar sobre
el gráfico entero, y agregar una transición nueva sea un cambio de datos, no
de lógica.
"""

from typing import Any

from postgrest.exceptions import APIError
from supabase import Client

from services.pcp.gestion import repository as repo
from services.pcp.gestion.models import EstadoPcp, PcpCreate
from services.pcp.historial import service as historial_service
from services.shared.database import get_service_client
from services.shared.exceptions import ConflictError, NotFoundError, ValidationError

# Código Postgres de unique_violation -- traduce uq_pcp_presupuesto_abierto
# (0011_pcp_modelo.sql M1) a ConflictError. Copia local intencional: cada
# submódulo de services/pcp/ define la suya (D1 evita importar el repository
# o un helper de otro módulo), mismo criterio que
# services/terceros/errors.py::UNIQUE_VIOLATION.
_UNIQUE_VIOLATION = "23505"

# D2/spec pcp-gestion "PCP State Machine": secuencia fija
# nueva -> en_gestion -> esperando_respuesta -> cerrada, sin saltos ni
# retrocesos. `cerrada` no tiene transiciones salientes en este PR (el cierre
# real -- con envío de resultado y notificación -- lo implementa
# negociacion/service.py::cerrar_pcp en PR11, D10).
_TRANSICIONES_PERMITIDAS: dict[str, frozenset[str]] = {
    "nueva": frozenset({"en_gestion"}),
    "en_gestion": frozenset({"esperando_respuesta"}),
    "esperando_respuesta": frozenset({"cerrada"}),
    "cerrada": frozenset(),
}


def crear_pcp(client: Client, *, drogueria_id: str, body: PcpCreate, usuario_id: str) -> dict[str, Any]:
    presupuesto = repo.buscar_presupuesto(client, presupuesto_id=body.presupuesto_id)
    if presupuesto is None or presupuesto["drogueria_id"] != drogueria_id:
        raise NotFoundError(f"No se encontró el presupuesto '{body.presupuesto_id}'")

    fila = {
        "drogueria_id": presupuesto["drogueria_id"],
        "presupuesto_id": presupuesto["id"],
        "proceso_comercial_id": presupuesto["proceso_comercial_id"],
        "fecha_entrega_solicitada": body.fecha_entrega_solicitada,
        "solicitante_id": body.solicitante_id,
        "sector_id": body.sector_id,
        "origen": body.origen,
        "notas": body.notas,
        "created_by": usuario_id,
        "updated_by": usuario_id,
    }
    try:
        return repo.crear_pcp(client, fila)
    except APIError as exc:
        if exc.code == _UNIQUE_VIOLATION:
            raise ConflictError(
                f"El presupuesto '{body.presupuesto_id}' ya tiene un PCP abierto"
            ) from exc
        raise


def obtener_pcp(
    client: Client, *, pcp_id: str, drogueria_id: str, es_superadmin: bool = False
) -> dict[str, Any]:
    fila = repo.buscar_pcp(client, pcp_id=pcp_id)
    if fila is None or (fila["drogueria_id"] != drogueria_id and not es_superadmin):
        raise NotFoundError(f"No se encontró el PCP '{pcp_id}'")
    return fila


def listar_pcp(
    client: Client,
    *,
    drogueria_id: str,
    estado: str | None = None,
    fecha_desde: str | None = None,
    fecha_hasta: str | None = None,
) -> list[dict[str, Any]]:
    return repo.listar_pcp(
        client,
        drogueria_id=drogueria_id,
        estado=estado,
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
    )


def cambiar_estado(
    client: Client,
    *,
    pcp_id: str,
    drogueria_id: str,
    estado_nuevo: EstadoPcp,
    usuario_id: str,
    es_superadmin: bool = False,
) -> dict[str, Any]:
    pcp = obtener_pcp(client, pcp_id=pcp_id, drogueria_id=drogueria_id, es_superadmin=es_superadmin)
    estado_actual = pcp["estado"]
    permitidos = _TRANSICIONES_PERMITIDAS.get(estado_actual, frozenset())
    if estado_nuevo not in permitidos:
        raise ValidationError(
            f"Transición de PCP inválida: '{estado_actual}' -> '{estado_nuevo}'"
        )

    actualizado = repo.actualizar_pcp(
        client, pcp_id=pcp_id, campos={"estado": estado_nuevo, "updated_by": usuario_id}
    )

    # 4.7: toda transición de estado escribe un evento en pcp_historial
    # (append-only, PR3) con estado anterior/nuevo y usuario -- nunca un
    # campo de costo (D2/D6).
    historial_service.agregar_evento(
        client,
        drogueria_id=drogueria_id,
        pcp_id=pcp_id,
        tipo_evento="estado_cambiado",
        payload={"estado_anterior": estado_actual, "estado_nuevo": estado_nuevo},
        usuario_id=usuario_id,
    )

    return actualizado


# -- wrappers de endpoint (service_role, mismo criterio que
# services/terceros/identidad/service.py::*_para_endpoint) --------------------


def crear_pcp_para_endpoint(*, drogueria_id: str, body: PcpCreate, usuario_id: str) -> dict[str, Any]:
    return crear_pcp(get_service_client(), drogueria_id=drogueria_id, body=body, usuario_id=usuario_id)


def cambiar_estado_para_endpoint(
    *,
    pcp_id: str,
    drogueria_id: str,
    estado_nuevo: EstadoPcp,
    usuario_id: str,
    es_superadmin: bool = False,
) -> dict[str, Any]:
    return cambiar_estado(
        get_service_client(),
        pcp_id=pcp_id,
        drogueria_id=drogueria_id,
        estado_nuevo=estado_nuevo,
        usuario_id=usuario_id,
        es_superadmin=es_superadmin,
    )
