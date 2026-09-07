"""Puerto de mensajería saliente de PCP (design.md D9, spec
`pcp-consultas-agrupadas` "Outbound Delivery via Configured Channel(s)").

`MensajeriaPort` define `enviar_email` y `enviar_whatsapp` -- copiado
verbatim del bloque "Interfaces / Contracts" de design.md D9. Ningún vendor
se nombra en este archivo ni en ningún default de configuración (D9: "No
vendor is named anywhere in code or config defaults"): el adaptador
concreto (`services/pcp/mensajeria/adapters.py`) es lo único que decide
cómo -- o si -- se entrega un mensaje de verdad.

Los destinatarios siempre se resuelven server-side desde `terceros_contactos`
/ `usuarios` dentro del tenant -- nunca desde un valor provisto por el
cliente (design.md D9/Interfaces) -- así que ningún adaptador puede apuntar
a una dirección arbitraria.
"""

from collections.abc import Mapping, Sequence
from typing import Protocol

from pydantic import BaseModel


class MensajeAdjunto(BaseModel):
    nombre: str
    contenido: bytes
    content_type: str = "application/pdf"


class ResultadoEnvio(BaseModel):
    entregado: bool
    proveedor_externo: str  # id del adaptador; "log" cuando no se envió nada
    referencia_externa: str | None = None
    error: str | None = None


class MensajeriaPort(Protocol):
    def enviar_email(
        self,
        *,
        destinatario: str,
        asunto: str,
        cuerpo: str,
        adjuntos: Sequence[MensajeAdjunto] = (),
    ) -> ResultadoEnvio: ...

    def enviar_whatsapp(
        self,
        *,
        destinatario: str,
        plantilla: str,
        variables: Mapping[str, str],
        adjuntos: Sequence[MensajeAdjunto] = (),
    ) -> ResultadoEnvio: ...
