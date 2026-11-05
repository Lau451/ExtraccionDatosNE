"""Recepción de archivos de Progress (odd/tasks/integracion-progress.md S3, S4, S5).

Pipeline genérico, compartido por la carga manual y la recepción automática desde la
carpeta: registrar → descartar duplicados → parsear con el parser del tipo → entregar
el lote a la fachada del dueño → cerrar el registro como procesado o con error.

El archivo se acepta o se rechaza entero: con un solo error de parseo no se entrega
ninguna fila (mismo criterio que la pantalla de import, que no enviaba nada si el
parseo tenía errores).

`client` es el SERVICE client: progress_archivos no tiene políticas de escritura para
authenticated, y la fachada de PCP también escribe con service client.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Literal

from supabase import Client

from services.integracion_progress.registro import service as registro
from services.integracion_progress.registro.models import ErrorLinea, Origen, RegistroArchivo
from services.integracion_progress.tipos import tipo_entrada
from services.shared.exceptions import DomainError

logger = logging.getLogger(__name__)

EstadoRecepcion = Literal["procesado", "duplicado", "error"]

# Línea de los errores de entrega, que no son de una línea del archivo.
_LINEA_ARCHIVO = 0
_MENSAJE_INESPERADO = "Error inesperado al entregar el archivo"
_MENSAJE_LECTURA_INESPERADA = "Error inesperado al leer el archivo"
_MENSAJE_SIN_FILAS = "El archivo no tiene filas para importar"


@dataclass
class ResultadoRecepcion:
    estado: EstadoRecepcion
    registro: RegistroArchivo
    errores: list[ErrorLinea] = field(default_factory=list)
    resultados: list[dict[str, Any]] = field(default_factory=list)


def _rechazar(
    client: Client, registro_archivo: RegistroArchivo, errores: list[ErrorLinea]
) -> ResultadoRecepcion:
    marcado = registro.marcar_error(
        client,
        drogueria_id=registro_archivo.drogueria_id,
        registro_id=registro_archivo.id,
        errores=errores,
    )
    return ResultadoRecepcion(estado="error", registro=marcado, errores=errores)


def recibir_archivo(
    client: Client,
    *,
    drogueria_id: str,
    tipo: str,
    nombre_archivo: str,
    contenido: bytes,
    origen: Origen,
    usuario_id: str,
) -> ResultadoRecepcion:
    """Procesa un archivo recibido de Progress.

    - Mismo contenido ya recibido o procesado: `duplicado`, no entrega nada.
    - Errores de parseo: `error` con los errores por línea, no entrega nada. Una
      excepción inesperada del parser también es `error` (línea 0): el registro nunca
      queda en `recibido` por un fallo de este proceso.
    - Si la entrega falla, el registro queda en `error` (reprocesable) y la
      excepción se propaga para que el endpoint responda con el mismo status y
      mensaje que el import directo de PCP.
    """
    parser, destino = tipo_entrada(tipo)

    registro_archivo, es_duplicado = registro.registrar_entrada(
        client,
        drogueria_id=drogueria_id,
        tipo=tipo,
        nombre_archivo=nombre_archivo,
        contenido=contenido,
        origen=origen,
        usuario_id=usuario_id,
    )
    if es_duplicado:
        return ResultadoRecepcion(estado="duplicado", registro=registro_archivo)

    try:
        parseo = parser.parsear(contenido)
    except Exception:
        logger.exception(
            "Falló la lectura del archivo %s (registro %s)", nombre_archivo, registro_archivo.id
        )
        return _rechazar(
            client,
            registro_archivo,
            [ErrorLinea(linea=_LINEA_ARCHIVO, mensaje=_MENSAJE_LECTURA_INESPERADA)],
        )
    if parseo.errores:
        return _rechazar(
            client, registro_archivo, [ErrorLinea.model_validate(e) for e in parseo.errores]
        )
    if not parseo.filas:
        return _rechazar(
            client,
            registro_archivo,
            # Línea 1, igual que "El archivo está vacío" del parser.
            [ErrorLinea(linea=1, mensaje=_MENSAJE_SIN_FILAS)],
        )

    try:
        resultados = destino.entregar(
            client, drogueria_id=drogueria_id, filas=parseo.filas, usuario_id=usuario_id
        )
    except Exception as exc:
        # El mensaje de un error de dominio es para el usuario; el de cualquier otro
        # puede traer detalles internos y solo va al log.
        mensaje = exc.message if isinstance(exc, DomainError) else _MENSAJE_INESPERADO
        if not isinstance(exc, DomainError):
            logger.exception(
                "Falló la entrega del archivo %s (registro %s)", nombre_archivo, registro_archivo.id
            )
        registro.marcar_error(
            client,
            drogueria_id=drogueria_id,
            registro_id=registro_archivo.id,
            errores=[ErrorLinea(linea=_LINEA_ARCHIVO, mensaje=mensaje)],
        )
        raise

    procesado = registro.marcar_procesado(
        client, drogueria_id=drogueria_id, registro_id=registro_archivo.id, filas=len(parseo.filas)
    )
    return ResultadoRecepcion(estado="procesado", registro=procesado, resultados=resultados)
