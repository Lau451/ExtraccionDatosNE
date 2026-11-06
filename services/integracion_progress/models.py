from datetime import datetime

from pydantic import BaseModel

from services.integracion_progress.recepcion.service import EstadoRecepcion
from services.integracion_progress.registro.models import ErrorLinea
from services.presupuestacion.presupuestos.api import ImportPresupuestoLegacyResultado


class RecepcionPresupuestosOut(BaseModel):
    """Respuesta de la carga manual del archivo de presupuestos (S4 manual, S5).

    - `procesado`: `resultados` trae un resultado por presupuesto, igual que
      POST /pcp/imports/presupuestos-legacy.
    - `duplicado`: el mismo contenido ya se había recibido; no se importó nada.
      Si el registro original terminó en error, `errores` trae esos errores y el
      archivo se puede volver a cargar para reintentar.
      `procesado_at` es cuándo se procesó (None si sigue en curso).
    - `error`: `errores` trae los errores por línea; no se importó nada.
    """

    estado: EstadoRecepcion
    registro_id: str
    nombre_archivo: str
    procesado_at: datetime | None = None
    errores: list[ErrorLinea]
    resultados: list[ImportPresupuestoLegacyResultado]
