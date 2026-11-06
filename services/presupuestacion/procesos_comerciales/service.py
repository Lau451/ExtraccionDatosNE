from typing import Any

from supabase import Client

from services.presupuestacion.core.audit import registrar_evento_ciclo_vida
from services.presupuestacion.core.database import get_service_client
from services.presupuestacion.core.exceptions import ValidationError
from services.presupuestacion.procesos_comerciales import repository as repo
from services.presupuestacion.procesos_comerciales.models import ProcesoComercialCreate


def _validar_campos_de_seguimiento(body: ProcesoComercialCreate) -> None:
    # Constraint real de la tabla (ck_proc_cotizacion_sin_seguimiento, no versionada
    # como migración en el repo -- confirmada empíricamente contra la BD de test):
    # una cotización no puede tener ninguno de los campos de seguimiento formal de
    # una licitación (apertura, vencimiento, modalidad, tipo_gestion, comparativa_pedida).
    if body.clase != "cotizacion":
        return
    campos_seteados = [
        campo
        for campo, valor in (
            ("apertura", body.apertura),
            ("vencimiento", body.vencimiento),
            ("modalidad", body.modalidad),
            ("tipo_gestion", body.tipo_gestion),
            ("comparativa_pedida", body.comparativa_pedida or None),
        )
        if valor
    ]
    if campos_seteados:
        raise ValidationError(
            "Una cotización no admite campos de seguimiento de licitación: "
            + ", ".join(campos_seteados)
        )


def crear_proceso_comercial(
    client: Client, *, drogueria_id: str, body: ProcesoComercialCreate, usuario_id: str
) -> dict[str, Any]:
    _validar_campos_de_seguimiento(body)
    proceso = repo.crear_proceso_comercial(
        client,
        {
            "drogueria_id": drogueria_id,
            "cliente_id": body.cliente_id,
            "clase": body.clase,
            "nombre": body.nombre,
            "categoria_id": body.categoria_id,
            "monto_estimado": str(body.monto_estimado) if body.monto_estimado is not None else None,
            "notas": body.notas,
            "apertura": body.apertura.isoformat() if body.apertura else None,
            "vencimiento": body.vencimiento.isoformat() if body.vencimiento else None,
            "tipo_gestion": body.tipo_gestion,
            "modalidad": body.modalidad,
            "comparativa_pedida": body.comparativa_pedida,
            "created_by": usuario_id,
            "updated_by": usuario_id,
        },
    )
    registrar_evento_ciclo_vida(
        client,
        entidad="proceso_comercial",
        entidad_id=proceso["id"],
        drogueria_id=drogueria_id,
        tipo_cambio="creacion",
        origen="usuario",
        usuario_id=usuario_id,
    )
    return proceso


def crear_proceso_comercial_para_endpoint(
    *, drogueria_id: str, body: ProcesoComercialCreate, usuario_id: str
) -> dict[str, Any]:
    return crear_proceso_comercial(
        get_service_client(), drogueria_id=drogueria_id, body=body, usuario_id=usuario_id
    )


def deshacer_creacion_proceso_comercial(client: Client, *, proceso_comercial_id: str) -> None:
    """Compensación de quien creó el proceso con `crear_proceso_comercial` en la
    misma operación y no pudo completarla (p.ej. el import legado de
    presupuestos): borra el proceso junto con su evento de creación. El llamador
    debe haber borrado antes lo que referencie al proceso sin CASCADE
    (`presupuestos`, `presupuesto_items`)."""
    repo.borrar_proceso_comercial_recien_creado(client, proceso_comercial_id=proceso_comercial_id)


def listar_procesos_comerciales(
    client: Client, *, drogueria_id: str, activos: bool = True
) -> list[dict[str, Any]]:
    return repo.listar_procesos_comerciales(client, drogueria_id=drogueria_id, activos=activos)
