import uuid
from datetime import date, datetime
from typing import Any, Literal

from supabase import Client

EntidadAuditable = Literal[
    "proceso_comercial", "comparativa", "orden_compra", "presupuesto", "evento"
]
OrigenCambio = Literal["usuario", "ia", "automatizacion", "webhook", "api", "sistema"]

_COLUMNA_FK_POR_ENTIDAD: dict[EntidadAuditable, str] = {
    "proceso_comercial": "proceso_comercial_id",
    "comparativa": "comparativa_id",
    "orden_compra": "orden_compra_id",
    "presupuesto": "presupuesto_id",
    "evento": "evento_id",
}


def _a_texto(valor: Any) -> str | None:
    if valor is None:
        return None
    if isinstance(valor, bool):
        return "true" if valor else "false"
    if isinstance(valor, (datetime, date)):
        return valor.isoformat()
    return str(valor)


def registrar_cambio(
    client: Client,
    *,
    entidad: EntidadAuditable,
    entidad_id: str,
    drogueria_id: str,
    campo: str,
    valor_anterior: Any,
    valor_nuevo: Any,
    origen: OrigenCambio,
    usuario_id: str,
    batch_id: str,
) -> None:
    fila = {
        "drogueria_id": drogueria_id,
        _COLUMNA_FK_POR_ENTIDAD[entidad]: entidad_id,
        "batch_id": batch_id,
        "tipo_cambio": "estado" if campo == "estado" else "campo",
        "campo": campo,
        "valor_anterior": _a_texto(valor_anterior),
        "valor_nuevo": _a_texto(valor_nuevo),
        "origen": origen,
        "usuario_id": usuario_id,
    }
    client.table("historial_cambios").insert(fila).execute()


def registrar_cambios(
    client: Client,
    *,
    entidad: EntidadAuditable,
    entidad_id: str,
    drogueria_id: str,
    cambios: dict[str, tuple[Any, Any]],
    origen: OrigenCambio,
    usuario_id: str,
    batch_id: str | None = None,
) -> str:
    batch_id = batch_id or str(uuid.uuid4())
    for campo, (valor_anterior, valor_nuevo) in cambios.items():
        registrar_cambio(
            client,
            entidad=entidad,
            entidad_id=entidad_id,
            drogueria_id=drogueria_id,
            campo=campo,
            valor_anterior=valor_anterior,
            valor_nuevo=valor_nuevo,
            origen=origen,
            usuario_id=usuario_id,
            batch_id=batch_id,
        )
    return batch_id


def registrar_evento_ciclo_vida(
    client: Client,
    *,
    entidad: EntidadAuditable,
    entidad_id: str,
    drogueria_id: str,
    tipo_cambio: Literal["creacion", "eliminacion", "restauracion"],
    origen: OrigenCambio,
    usuario_id: str,
    batch_id: str | None = None,
) -> str:
    batch_id = batch_id or str(uuid.uuid4())
    fila = {
        "drogueria_id": drogueria_id,
        _COLUMNA_FK_POR_ENTIDAD[entidad]: entidad_id,
        "batch_id": batch_id,
        "tipo_cambio": tipo_cambio,
        "origen": origen,
        "usuario_id": usuario_id,
    }
    client.table("historial_cambios").insert(fila).execute()
    return batch_id
