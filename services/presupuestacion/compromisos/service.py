import calendar
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from supabase import Client

from services.presupuestacion.compromisos import repository as repo
from services.presupuestacion.core.exceptions import ValidationError

_ZONA_ARGENTINA = ZoneInfo("America/Argentina/Buenos_Aires")
_MESES_POR_DEFECTO = 6
_MESES_MAXIMOS = 24
_ORDEN_SITUACION = {"vencida": 0, "futura": 1}


def _hoy_buenos_aires() -> date:
    # Misma referencia que la vista (0032): date.today() usaría la zona del servidor.
    return datetime.now(_ZONA_ARGENTINA).date()


def _sumar_meses(fecha: date, meses: int) -> date:
    indice = fecha.year * 12 + (fecha.month - 1) + meses
    anio, mes = divmod(indice, 12)
    mes += 1
    return date(anio, mes, min(fecha.day, calendar.monthrange(anio, mes)[1]))


def _clave_orden(fila: dict[str, Any]) -> tuple:
    return (
        _ORDEN_SITUACION.get(fila["situacion"], len(_ORDEN_SITUACION)),
        fila["fecha_entrega_planificada"] or "",
        fila["numero_oc"],
        fila["numero_entrega"],
        fila["numero_renglon"] or 0,
    )


def _exigir_drogueria(drogueria_id: str | None) -> None:
    if drogueria_id is None:
        # superadmin: sin droguería, `.eq("drogueria_id", None)` revienta como uuid inválido.
        raise ValidationError("La agenda de compromisos es por droguería: el usuario no tiene una asignada")


def listar_compromisos(
    client: Client,
    *,
    drogueria_id: str | None,
    desde: date | None = None,
    hasta: date | None = None,
    hoy: date | None = None,
) -> list[dict[str, Any]]:
    """Sin `desde`: todo lo vencido más lo futuro hasta `hasta` (por defecto hoy + 6 meses).
    Con `desde`: solo las filas dentro de [desde, hasta], con `hasta` por defecto desde + 6
    meses. El rango no puede superar 24 meses."""
    _exigir_drogueria(drogueria_id)
    hoy = hoy or _hoy_buenos_aires()
    base = desde or hoy
    if hasta is None:
        hasta = _sumar_meses(base, _MESES_POR_DEFECTO)
    if desde is not None and hasta < desde:
        raise ValidationError("'hasta' no puede ser anterior a 'desde'")
    if hasta > _sumar_meses(base, _MESES_MAXIMOS):
        raise ValidationError(f"El rango no puede superar {_MESES_MAXIMOS} meses")

    filas = repo.listar_compromisos(client, drogueria_id=drogueria_id, desde=desde, hasta=hasta)
    return sorted(filas, key=_clave_orden)


def proxima_fecha(client: Client, *, drogueria_id: str | None, despues_de: date) -> date | None:
    """Próxima fecha con compromisos después de `despues_de` (el CTA del mes vacío en la
    agenda). Sin límite de rango: busca en todo lo que tenga la droguería."""
    _exigir_drogueria(drogueria_id)
    return repo.proxima_fecha(client, drogueria_id=drogueria_id, despues_de=despues_de)
