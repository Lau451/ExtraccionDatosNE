from datetime import datetime
from typing import Literal

from pydantic import BaseModel

# Valores de los CHECK de progress_archivos (0043: ck_parch_sentido,
# ck_parch_origen, ck_parch_estado).
Sentido = Literal["entrada", "salida"]
Origen = Literal["carpeta", "manual"]
EstadoArchivo = Literal["recibido", "procesado", "error"]


class ErrorLinea(BaseModel):
    """Un error de validación de una línea del archivo (progress_archivos.errores)."""

    linea: int
    mensaje: str


class RegistroArchivo(BaseModel):
    """Una fila de progress_archivos (S3). `origen` es NULL en las salidas."""

    id: str
    drogueria_id: str
    sentido: Sentido
    tipo: str
    nombre_archivo: str
    sha256: str
    origen: Origen | None = None
    estado: EstadoArchivo
    filas: int | None = None
    errores: list[ErrorLinea] | None = None
    usuario_id: str
    intentos: int
    procesado_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
