from typing import Any, Literal

from pydantic import BaseModel

TipoEvento = Literal[
    "creada",
    "estado_cambiado",
    "renglon_agregado",
    "renglon_quitado",
    "consulta_enviada",
    "resultado_registrado",
    "sugerencia_aplicada",
    "notificacion_enviada",
    "importada",
]


class EventoHistorialCreate(BaseModel):
    """Entrada de `agregar_evento` (0012_pcp_extras.sql M1, design.md D6).

    `payload` es contexto libre del evento (p.ej. estado_anterior/estado_nuevo,
    proveedor, resultado) -- nunca un campo de costo (D2): quien arma este
    modelo decide qué va en el payload, este módulo no ofrece ningún atajo de
    "costo"/"precio" que lo tiente a colarlo ahí.
    """

    pcp_id: str
    tipo_evento: TipoEvento
    payload: dict[str, Any] = {}
    usuario_id: str | None = None
    pcp_renglon_id: str | None = None
    origen: str | None = None


class EventoHistorialOut(BaseModel):
    id: str
    drogueria_id: str
    pcp_id: str
    pcp_renglon_id: str | None
    tipo_evento: str
    payload: dict[str, Any]
    origen: str | None
    usuario_id: str | None
    created_at: str
