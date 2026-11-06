"""Escaneo de la carpeta de entrada de un tipo de archivo de Progress
(odd/tasks/integracion-progress.md S4 automática, S3).

Cada archivo completo de la carpeta del tipo pasa por el mismo pipeline que la carga
manual (`service.recibir_archivo`) y después se mueve a `procesados/` (procesado o
duplicado de un registro procesado) o a `errores/` (error, duplicado de un registro
que quedó en `error`, o excepción del pipeline con el registro en `error`). Se deja
en la carpeta, para el próximo escaneo, un duplicado que otro proceso todavía está
procesando (registro en `recibido`), un archivo que no se pudo leer (bloqueado por
quien lo escribe), uno que cambió mientras se leía y uno cuyo pipeline falló sin
dejar el registro en `error` (ej. Supabase caído antes de registrarlo): así ningún
archivo sale del circuito sin que el registro lo muestre. Nunca se borra ni se pisa un archivo: ante
un nombre repetido en el destino se agrega un sufijo.

Un archivo se considera completo si tiene al lado un marcador `<nombre>.ok`, o si no
se modificó en los últimos `_EDAD_MINIMA_SEGUNDOS` y no cambia mientras se lee (el
`.ok` es opcional, ver el estándar de archivos en
docs/arquitectura/integracion-progress.md). Sin `.ok`, un escritor que se pausa más
de `_EDAD_MINIMA_SEGUNDOS` y no escribe durante la lectura no se detecta.

Apagado: `detener` (un `threading.Event`) corta el escaneo antes del próximo archivo;
los que faltan quedan en la carpeta.

Concurrencia: si dos procesos escanean la misma carpeta a la vez (varios workers de
uvicorn), el UNIQUE del registro hace que el segundo reciba un duplicado, y el
archivo que el otro ya movió se ignora (no es un error).
"""

import logging
import os
import stat
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Literal

from supabase import Client

from services.integracion_progress.recepcion.service import (
    EstadoRecepcion,
    ResultadoRecepcion,
    recibir_archivo,
)
from services.integracion_progress.registro.models import RegistroArchivo
from services.integracion_progress.registro.service import buscar_entrada

logger = logging.getLogger(__name__)

# Un archivo sin `.ok` más nuevo que esto puede seguir escribiéndose.
_EDAD_MINIMA_SEGUNDOS = 30
_SUFIJO_OK = ".ok"
_SUFIJO_TEMPORAL = ".tmp"
_PROCESADOS = "procesados"
_ERRORES = "errores"
_DESTINO_POR_ESTADO: dict[str, str] = {
    "procesado": _PROCESADOS,
    "duplicado": _PROCESADOS,
    "error": _ERRORES,
}

# Atributo "oculto" de Windows (0 en otros sistemas, donde no existe).
_ATRIBUTO_OCULTO = getattr(stat, "FILE_ATTRIBUTE_HIDDEN", 0)

Recibir = Callable[..., ResultadoRecepcion]
Buscar = Callable[..., RegistroArchivo | None]
# `pendiente`: el pipeline falló sin dejar el registro en error; queda en la carpeta.
EstadoArchivo = EstadoRecepcion | Literal["pendiente"]


@dataclass
class ResultadoArchivo:
    """Resumen de un archivo escaneado. `registro_id` es None si el pipeline lanzó
    una excepción sin dejar un registro en error; `movido_a` es None si el archivo
    ya no estaba al moverlo (otro proceso lo tomó), si no se pudo mover, si otro
    proceso todavía lo está procesando o si quedó `pendiente`."""

    nombre_archivo: str
    estado: EstadoArchivo
    registro_id: str | None
    movido_a: Path | None


def _marcador(archivo: Path) -> Path:
    return archivo.with_name(archivo.name + _SUFIJO_OK)


def _candidatos(carpeta_tipo: Path, ahora: datetime) -> list[Path]:
    """Archivos regulares directamente en la carpeta, visibles y completos, en orden
    de nombre. Uno que no se puede inspeccionar (sin permiso) se saltea."""
    candidatos: list[Path] = []
    with os.scandir(carpeta_tipo) as entradas:
        for entrada in entradas:
            nombre = entrada.name
            minuscula = nombre.lower()
            if (
                nombre.startswith(".")
                or minuscula.endswith(_SUFIJO_TEMPORAL)
                or minuscula.endswith(_SUFIJO_OK)
            ):
                continue
            try:
                if not entrada.is_file(follow_symlinks=False):
                    continue
                datos = entrada.stat(follow_symlinks=False)
                if getattr(datos, "st_file_attributes", 0) & _ATRIBUTO_OCULTO:
                    continue
                archivo = Path(entrada.path)
                if not _marcador(archivo).is_file():
                    if ahora.timestamp() - datos.st_mtime < _EDAD_MINIMA_SEGUNDOS:
                        continue
            except FileNotFoundError:
                continue
            except OSError:
                logger.warning("No se pudo inspeccionar el archivo de Progress %s", entrada.path)
                continue
            candidatos.append(archivo)
    return sorted(candidatos, key=lambda p: p.name)


def _nombres_libres(nombre: str, sufijo_tiempo: str):
    """`nombre`, después `<stem>_<yyyyMMddHHmmss><ext>`, `<stem>_<...>_2<ext>`, ..."""
    yield nombre
    ruta = Path(nombre)
    base = f"{ruta.stem}_{sufijo_tiempo}"
    yield f"{base}{ruta.suffix}"
    n = 2
    while True:
        yield f"{base}_{n}{ruta.suffix}"
        n += 1


def _mover(origen: Path, destino_dir: Path, ahora: datetime) -> Path | None:
    """Mueve `origen` (y su `.ok`, si tiene) a `destino_dir` sin pisar nada.
    Devuelve la ruta final, o None si `origen` ya no existe."""
    destino_dir.mkdir(parents=True, exist_ok=True)
    marcador = _marcador(origen)
    for nombre in _nombres_libres(origen.name, ahora.strftime("%Y%m%d%H%M%S")):
        destino = destino_dir / nombre
        if destino.exists() or _marcador(destino).exists():
            continue
        try:
            # En Windows rename falla si el destino existe (FileExistsError): nunca pisa.
            origen.rename(destino)
        except FileExistsError:
            continue
        except FileNotFoundError:
            return None
        try:
            marcador.rename(_marcador(destino))
        except FileNotFoundError:
            pass
        except OSError:
            # El archivo ya se movió: el `.ok` huérfano queda en la carpeta (se ignora).
            logger.warning(
                "No se pudo mover el marcador %s junto con el archivo de Progress",
                marcador,
                exc_info=True,
            )
        return destino


def _huella(archivo: Path) -> tuple[int, int]:
    datos = archivo.stat()
    return datos.st_size, datos.st_mtime_ns


def _leer_estable(archivo: Path) -> bytes | None:
    """Contenido del archivo, o None si cambió mientras se leía (quien lo escribe
    todavía no terminó). FileNotFoundError / OSError se propagan."""
    antes = _huella(archivo)
    contenido = archivo.read_bytes()
    despues = _huella(archivo)
    if antes != despues or len(contenido) != despues[0]:
        return None
    return contenido


def escanear_carpeta(
    client: Client,
    *,
    carpeta_tipo: Path,
    tipo: str,
    drogueria_id: str,
    usuario_id: str,
    ahora: datetime | None = None,
    recibir: Recibir = recibir_archivo,
    buscar: Buscar = buscar_entrada,
    detener: threading.Event | None = None,
) -> list[ResultadoArchivo]:
    """Recibe cada archivo completo de `carpeta_tipo` y lo mueve según el resultado.
    Un archivo que falla no corta el escaneo de los demás; `detener` sí (apagado)."""
    ahora = ahora or datetime.now(timezone.utc)
    if not carpeta_tipo.is_dir():
        logger.warning("La carpeta de entrada de Progress %s no existe", carpeta_tipo)
        return []

    resultados: list[ResultadoArchivo] = []
    for archivo in _candidatos(carpeta_tipo, ahora):
        if detener is not None and detener.is_set():
            logger.info("Escaneo de %s interrumpido por el apagado", carpeta_tipo)
            break
        try:
            contenido = _leer_estable(archivo)
        except FileNotFoundError:
            continue
        except OSError:
            # Típicamente bloqueado por quien lo escribe: se reintenta en el próximo escaneo.
            logger.warning("No se pudo leer el archivo de Progress %s", archivo, exc_info=True)
            continue
        if contenido is None:
            logger.warning(
                "El archivo de Progress %s cambió mientras se leía: queda para el próximo escaneo",
                archivo,
            )
            continue

        registro_id: str | None = None
        en_curso = False
        destino = None
        estado: EstadoArchivo
        try:
            recepcion = recibir(
                client,
                drogueria_id=drogueria_id,
                tipo=tipo,
                nombre_archivo=archivo.name,
                contenido=contenido,
                origen="carpeta",
                usuario_id=usuario_id,
            )
            estado = recepcion.estado
            registro_id = recepcion.registro.id
            en_curso = estado == "duplicado" and recepcion.registro.estado == "recibido"
            if estado == "duplicado" and recepcion.registro.estado == "error":
                # Reclamo perdido contra un registro que el ganador volvió a cerrar en
                # error: el contenido no se importó, no va a procesados/.
                destino = _ERRORES
        except Exception:
            logger.exception("Falló la recepción del archivo de Progress %s", archivo)
            registro_error = _registro_en_error(
                buscar, client, drogueria_id=drogueria_id, tipo=tipo, contenido=contenido
            )
            if registro_error is not None:
                estado, registro_id = "error", registro_error.id
            else:
                estado = "pendiente"

        movido_a: Path | None = None
        if estado == "pendiente":
            logger.warning(
                "El archivo de Progress %s queda en la carpeta para el próximo escaneo", archivo
            )
        elif en_curso:
            # Otro proceso lo está procesando: se queda en la carpeta y el próximo
            # escaneo lo mueve según cómo termine (o lo reprocesa si quedó colgado).
            logger.info("El archivo de Progress %s se está procesando en otro proceso", archivo)
        else:
            try:
                subcarpeta = destino or _DESTINO_POR_ESTADO[estado]
                movido_a = _mover(archivo, carpeta_tipo / subcarpeta, ahora)
            except OSError:
                logger.exception("No se pudo mover el archivo de Progress %s", archivo)
        resultados.append(
            ResultadoArchivo(
                nombre_archivo=archivo.name,
                estado=estado,
                registro_id=registro_id,
                movido_a=movido_a,
            )
        )
    return resultados


def _registro_en_error(
    buscar: Buscar, client: Client, *, drogueria_id: str, tipo: str, contenido: bytes
) -> RegistroArchivo | None:
    """El registro del contenido si el pipeline lo dejó en `error`; None si no hay
    registro, si quedó en otro estado o si la búsqueda también falla."""
    try:
        registro = buscar(client, drogueria_id=drogueria_id, tipo=tipo, contenido=contenido)
    except Exception:
        logger.exception("No se pudo consultar el registro del archivo de Progress")
        return None
    return registro if registro is not None and registro.estado == "error" else None
