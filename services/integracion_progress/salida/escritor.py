# Escritura atómica de los CSV que salen hacia Progress
# (openspec/changes/oc-export-progress, D5; docs/arquitectura/integracion-progress.md).
# Es la única pieza que conoce la carpeta, el nombre y el encoding de los archivos.
import csv
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
    Nunca pisa un archivo existente (`ConflictError`); ante una falla borra el temporal."""
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
        os.replace(temporal, destino)
    except BaseException:
        temporal.unlink(missing_ok=True)
        raise
    return destino


def borrar_archivo(ruta: Path) -> None:
    """Compensación: borra un archivo ya escrito. No falla si ya no existe."""
    ruta.unlink(missing_ok=True)
