"""Adaptadores concretos de `MensajeriaPort` (design.md D9).

`LoggingMensajeriaAdapter` es el default y el único adaptador que este PR
implementa: registra el intento (nivel INFO) y devuelve
`ResultadoEnvio(entregado=False, proveedor_externo="log")` sin llamar a
ningún vendor externo -- "con el adaptador default esto es un no-op
registrado, así que el módulo se entrega sin ningún vendor de mensajería"
(D9/D10). Un vendor real (email/whatsapp) es un adaptador nuevo detrás del
mismo puerto -- "el renderer/adaptador se mantiene como un cambio de una
sola clase" -- fuera de alcance de este PR (droppable, tasks.md Fase 11).

`get_mensajeria()` resuelve el adaptador desde `PCP_MENSAJERIA_ADAPTER`
(default `"log"`, `services/shared/config.py`). Un valor distinto de
`"log"` levanta `ValueError` explícito en vez de degradar silenciosamente a
logging -- todavía no existe otro adaptador que instanciar, y fallar rápido
en el arranque/primer uso es preferible a un typo de configuración que
termine mandando `entregado=False` en silencio.
"""

import logging
from collections.abc import Mapping, Sequence

from services.pcp.mensajeria.port import MensajeAdjunto, MensajeriaPort, ResultadoEnvio
from services.shared.config import get_settings

logger = logging.getLogger(__name__)


class LoggingMensajeriaAdapter:
    """Adaptador default (D9): no envía nada, solo deja constancia."""

    def enviar_email(
        self,
        *,
        destinatario: str,
        asunto: str,
        cuerpo: str,
        adjuntos: Sequence[MensajeAdjunto] = (),
    ) -> ResultadoEnvio:
        logger.info(
            "PCP mensajeria (log): email a %s -- asunto=%r, %d adjunto(s)",
            destinatario,
            asunto,
            len(adjuntos),
        )
        return ResultadoEnvio(entregado=False, proveedor_externo="log")

    def enviar_whatsapp(
        self,
        *,
        destinatario: str,
        plantilla: str,
        variables: Mapping[str, str],
        adjuntos: Sequence[MensajeAdjunto] = (),
    ) -> ResultadoEnvio:
        logger.info(
            "PCP mensajeria (log): whatsapp a %s -- plantilla=%r, %d adjunto(s)",
            destinatario,
            plantilla,
            len(adjuntos),
        )
        return ResultadoEnvio(entregado=False, proveedor_externo="log")


def get_mensajeria() -> MensajeriaPort:
    adaptador = get_settings().pcp_mensajeria_adapter
    if adaptador == "log":
        return LoggingMensajeriaAdapter()
    raise ValueError(
        f"Adaptador de mensajería PCP no soportado: '{adaptador}'. Solo 'log' está "
        "implementado en este PR (design.md D9) -- un vendor real es un adaptador "
        "nuevo detrás del mismo MensajeriaPort."
    )
