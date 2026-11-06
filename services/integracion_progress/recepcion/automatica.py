"""Recepción automática desde la carpeta de entrada de Progress
(odd/tasks/integracion-progress.md S4 automática, L6).

Se enciende solo cuando están configurados la carpeta (`progress_entrada_dir`) y el
tenant (`progress_drogueria_id`). Cada tipo de archivo se lee de su subcarpeta
(`<progress_entrada_dir>/presupuestos`) con el usuario de sistema y origen 'carpeta'.

El lifespan de la app de presupuestación corre `recepcion_periodica` como tarea de
fondo: escanea al arrancar y después cada `progress_escaneo_intervalo_segundos`. El
escaneo hace IO bloqueante y llamadas sincrónicas a Supabase, así que corre en un
thread (`asyncio.to_thread`) para no frenar el event loop. Ese thread no se puede
cancelar: al apagar, la tarea le pide que pare (`detener`) y el escaneo termina
después del archivo en curso en lugar de recorrer toda la carpeta.
"""

import asyncio
import logging
import threading
from pathlib import Path
from typing import Awaitable, Callable

from supabase import Client

from services.integracion_progress.recepcion import carpeta
from services.integracion_progress.recepcion.carpeta import ResultadoArchivo
from services.shared.config import Settings
from services.shared.database import get_service_client

logger = logging.getLogger(__name__)

# Tipos que se reciben desde la carpeta; cada uno en su subcarpeta.
_TIPOS = ("presupuestos",)


def motivo_apagada(settings: Settings) -> str | None:
    """Por qué la recepción automática está apagada, o None si está encendida."""
    faltantes = [
        variable
        for variable, valor in (
            ("PROGRESS_ENTRADA_DIR", settings.progress_entrada_dir),
            ("PROGRESS_DROGUERIA_ID", settings.progress_drogueria_id),
        )
        if not valor
    ]
    if faltantes:
        return f"falta configurar {' y '.join(faltantes)}"
    return None


def escanear_si_configurado(
    settings: Settings,
    *,
    detener: threading.Event | None = None,
    client_factory: Callable[[], Client] = get_service_client,
    escanear: Callable[..., list[ResultadoArchivo]] = carpeta.escanear_carpeta,
) -> list[ResultadoArchivo]:
    """Un escaneo de todas las carpetas de tipo. Apagada: no hace nada (el motivo lo
    loguea `recepcion_periodica` una sola vez al arrancar)."""
    if motivo_apagada(settings) is not None:
        return []
    entrada = Path(settings.progress_entrada_dir)
    client = client_factory()
    resultados: list[ResultadoArchivo] = []
    for tipo in _TIPOS:
        resultados.extend(
            escanear(
                client,
                carpeta_tipo=entrada / tipo,
                tipo=tipo,
                drogueria_id=settings.progress_drogueria_id,
                usuario_id=settings.usuario_sistema_id,
                detener=detener,
            )
        )
    return resultados


async def recepcion_periodica(
    settings: Settings,
    *,
    escanear: Callable[..., object] = escanear_si_configurado,
    dormir: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> None:
    """Escanea al arrancar y después cada intervalo, hasta que se cancele la tarea.
    Apagada: loguea el motivo una vez y termina.

    Tolerante a fallos: una excepción en una iteración (ej. Supabase caído) se loguea
    y el loop sigue en la próxima. Al cancelarse le pide al escaneo en curso que pare."""
    motivo = motivo_apagada(settings)
    if motivo is not None:
        logger.info("Recepción automática de archivos de Progress apagada: %s", motivo)
        return
    intervalo = settings.progress_escaneo_intervalo_segundos
    logger.info(
        "Recepción automática de archivos de Progress encendida: %s cada %ds",
        settings.progress_entrada_dir,
        intervalo,
    )
    detener = threading.Event()
    try:
        while True:
            try:
                await asyncio.to_thread(escanear, settings, detener=detener)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception(
                    "Falló un escaneo de la carpeta de Progress, se reintenta en %ds", intervalo
                )
            await dormir(intervalo)
    finally:
        detener.set()
