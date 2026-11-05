# Escritura atómica de los CSV que salen hacia Progress
# (openspec/changes/oc-export-progress, D5; docs/arquitectura/integracion-progress.md).
# Es la única pieza que conoce la carpeta, el nombre y el encoding de los archivos.
import csv
import errno
import os
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from services.shared.exceptions import ConflictError

_ZONA = ZoneInfo("America/Argentina/Buenos_Aires")
_NO_VALIDO = re.compile(r"[^A-Za-z0-9-]")


def _sanear(valor: str) -> str:
    return _NO_VALIDO.sub("-", valor.strip())


def carpeta_oc(progress_docs_dir: str) -> Path:
    return Path(progress_docs_dir) / "oc"


def construir_nombre(
    codigo_cliente: str,
    numero_oc: str,
    version: int,
    *,
    ahora: datetime | None = None,
) -> str:
    """`OC_{codigo_cliente}_{numero_oc}_v{version}_{yyyyMMddHHmmss}.csv`, en hora de
    Buenos Aires. `ahora` es inyectable para tests."""
    momento = (ahora or datetime.now(_ZONA)).astimezone(_ZONA)
    return (
        f"OC_{_sanear(codigo_cliente)}_{_sanear(numero_oc)}_v{version}_"
        f"{momento:%Y%m%d%H%M%S}.csv"
    )


# Errores de os.link que significan "el sistema de archivos no tiene hard links".
_SIN_HARD_LINKS = {errno.EPERM, errno.EXDEV, errno.EMLINK, getattr(errno, "ENOTSUP", -1)}


def _publicar(temporal: Path, destino: Path) -> None:
    """Renombra `temporal` a `destino` de forma atómica sin pisarlo nunca: si
    `destino` ya existe lanza FileExistsError. En Windows `os.rename` ya falla si el
    destino existe; en POSIX se usa un hard link (falla si existe) y se borra el
    temporal. Sin hard links queda el chequeo previo + `os.replace`."""
    if os.name == "nt":
        os.rename(temporal, destino)
        return
    try:
        os.link(temporal, destino)
    except FileExistsError:
        raise
    except OSError as exc:
        if exc.errno not in _SIN_HARD_LINKS:
            raise
        if destino.exists():
            raise FileExistsError(errno.EEXIST, "destino existente", str(destino)) from None
        os.replace(temporal, destino)
        return
    temporal.unlink()


def escribir_csv(
    encabezados: list[str],
    filas: list[list[str]],
    *,
    carpeta: Path,
    nombre: str,
    encoding: str,
) -> Path:
    """Escribe `encabezados` + `filas` en un temporal de la misma carpeta y lo renombra
    de forma atómica. Un carácter no representable en `encoding` sale como `?`.
    Nunca pisa un archivo existente (`ConflictError`), tampoco uno que aparece mientras
    escribe; ante una falla borra el temporal."""
    carpeta.mkdir(parents=True, exist_ok=True)
    destino = carpeta / nombre
    if destino.exists():
        raise ConflictError(f"Ya existe el archivo {nombre}")

    temporal = carpeta / f".{nombre}.tmp"
    try:
        with open(temporal, "w", encoding=encoding, errors="replace", newline="") as f:
            escritor = csv.writer(
                f, delimiter=";", quoting=csv.QUOTE_MINIMAL, lineterminator="\r\n"
            )
            escritor.writerow(encabezados)
            escritor.writerows(filas)
        _publicar(temporal, destino)
    except FileExistsError:
        temporal.unlink(missing_ok=True)
        raise ConflictError(f"Ya existe el archivo {nombre}") from None
    except BaseException:
        temporal.unlink(missing_ok=True)
        raise
    return destino


def borrar_archivo(ruta: Path) -> None:
    """Compensación: borra un archivo ya escrito. No falla si ya no existe."""
    ruta.unlink(missing_ok=True)
