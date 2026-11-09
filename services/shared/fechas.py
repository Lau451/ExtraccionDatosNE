"""Fecha de hoy del negocio: la de Argentina, no la del servidor ni la UTC.

`date.today()` usa la zona del servidor y `CURRENT_DATE` en Supabase es UTC:
entre las 21:00 y las 24:00 los dos ya dan mañana. Las vistas y los defaults
de la base usan el mismo criterio (migraciones 0045 y 0046).
"""

from datetime import date, datetime
from zoneinfo import ZoneInfo

ZONA_ARGENTINA = ZoneInfo("America/Argentina/Buenos_Aires")


def hoy_argentina() -> date:
    return datetime.now(ZONA_ARGENTINA).date()
