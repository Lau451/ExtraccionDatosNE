# Exportación de una OC a Progress (openspec/changes/oc-export-progress, D2/D3/D6/D8).
# Orden de efectos (D6): validar -> escribir archivo -> UPDATE CAS -> auditar.
import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from supabase import Client

from services.presupuestacion.core.audit import registrar_cambio
from services.presupuestacion.oc_entregas.service import _clasificar_renglones
from services.presupuestacion.oc_presupuesto.service import _derivar_estado
from services.presupuestacion.oc_export import repository as repo
from services.presupuestacion.oc_export.escritor import (
    carpeta_oc,
    construir_nombre,
    escribir_csv,
)
from services.presupuestacion.oc_export.filas import construir_filas
from services.presupuestacion.oc_export.models import (
    EntregaExport,
    OcExport,
    RenglonExport,
    ResultadoExportacion,
)
from services.shared.config import Settings
from services.shared.exceptions import (
    ConflictError,
    IntegracionNoConfigurada,
    NotFoundError,
    ValidationError,
)

logger = logging.getLogger(__name__)

_ZONA = ZoneInfo("America/Argentina/Buenos_Aires")
_MAX_LISTADO = 10


def _lista(valores: list[Any]) -> str:
    texto = ", ".join(str(v) for v in valores[:_MAX_LISTADO])
    if len(valores) > _MAX_LISTADO:
        texto += f" (y {len(valores) - _MAX_LISTADO} más)"
    return texto


def _conflicto_ya_exportada(client: Client, oc: dict[str, Any]) -> ConflictError:
    fecha = datetime.fromisoformat(str(oc["exportado_at"])).astimezone(_ZONA)
    usuario = None
    if oc.get("exportado_por"):
        usuario = repo.buscar_nombre_usuario(client, usuario_id=oc["exportado_por"])
    quien = usuario or oc.get("exportado_por") or "un usuario desconocido"
    return ConflictError(
        f"La orden de compra ya fue exportada a Progress el {fecha:%d/%m/%Y %H:%M} por {quien}"
        f" (archivo {oc.get('archivo_exportado')})"
    )


def _quedo_marcada_con(
    client: Client, orden_compra_id: str, drogueria_id: str, archivo: str
) -> bool:
    try:
        oc = repo.buscar_orden_compra(
            client, orden_compra_id=orden_compra_id, drogueria_id=drogueria_id
        )
    except Exception:
        logger.exception("No se pudo releer la OC %s tras el fallo de la marca", orden_compra_id)
        return False
    return bool(oc and oc.get("exportado_at") and oc.get("archivo_exportado") == archivo)


def _error_de_marca(estado: str) -> Exception:
    if estado == "ya_exportada":
        return ConflictError("La orden de compra ya fue exportada por otro usuario")
    if estado == "plan_cambiado":
        return ConflictError(
            "El plan cambió mientras se exportaba, volvé a intentar"
        )
    if estado == "no_encontrada":
        return NotFoundError("No se encontró la orden de compra")
    return RuntimeError(f"Respuesta inesperada de marcar_oc_exportada: {estado!r}")


def _errores_cabecera(oc: dict[str, Any]) -> list[str]:
    errores: list[str] = []
    if oc["estado"] == "cancelada":
        errores.append("la orden de compra está cancelada")
    if oc.get("deleted_at"):
        errores.append("la orden de compra está eliminada")
    if not oc.get("es_vigente"):
        errores.append("la orden de compra no es la versión vigente")
    if not oc.get("cliente_id"):
        errores.append("la orden de compra no tiene cliente asignado")
    return errores


def _resolver_cliente(
    client: Client, oc: dict[str, Any], drogueria_id: str, errores: list[str]
) -> tuple[str | None, str | None]:
    """D3: exactamente un código `cliente` en `terceros_legacy_map`; si hay 0 o más de
    uno no se elige ninguno."""
    if not oc.get("cliente_id"):
        return None, None
    codigos = repo.listar_codigos_cliente(
        client, tercero_id=oc["cliente_id"], drogueria_id=drogueria_id
    )
    if len(codigos) != 1:
        if not codigos:
            errores.append("el cliente no tiene código de cliente en el sistema Progress")
        else:
            errores.append(
                f"el código de cliente es ambiguo, hay {len(codigos)} códigos: {_lista(codigos)}"
            )
        return None, None
    cuit = repo.buscar_cuit_tercero(client, tercero_id=oc["cliente_id"], drogueria_id=drogueria_id)
    return codigos[0], cuit


def _armar_renglones(
    client: Client, items: list[dict[str, Any]], drogueria_id: str, errores: list[str]
) -> list[RenglonExport]:
    # Misma clasificación que la planificación (oc_entregas): solo los confirmados se
    # exportan, los descartados quedan afuera y los pendientes bloquean.
    pendientes = [
        i["numero_renglon"]
        for i in items
        if _derivar_estado(i.get("presupuesto_item_id"), bool(i.get("vinculo_descartado")))
        == "pendiente"
    ]
    items, _, _ = _clasificar_renglones(items)
    if pendientes:
        errores.append(f"renglones pendientes de matching: {_lista(pendientes)}")
    if not items:
        if not pendientes:
            errores.append("la orden de compra no tiene renglones confirmados")
        return []
    sin_producto = [i["numero_renglon"] for i in items if not i.get("producto_id")]
    if sin_producto:
        errores.append(f"renglones sin producto vinculado: {_lista(sin_producto)}")
    codigos = repo.listar_codigos_productos(
        client,
        producto_ids=[i["producto_id"] for i in items if i.get("producto_id")],
        drogueria_id=drogueria_id,
    )
    sin_codigo = [
        i["numero_renglon"] for i in items if i.get("producto_id") and not codigos.get(i["producto_id"])
    ]
    if sin_codigo:
        errores.append(f"renglones cuyo producto no tiene código de artículo: {_lista(sin_codigo)}")
    return [
        RenglonExport(
            oc_item_id=i["id"],
            numero_renglon=i["numero_renglon"],
            codigo_articulo=codigos.get(i.get("producto_id")),
            descripcion=i["descripcion"],
            cantidad=Decimal(str(i["cantidad"])),
            precio_unitario=Decimal(str(i["precio_unitario"])),
        )
        for i in items
    ]


def _armar_entregas(
    client: Client,
    entregas: list[dict[str, Any]],
    renglones: list[RenglonExport],
    drogueria_id: str,
    errores: list[str],
) -> list[EntregaExport]:
    if not entregas:
        errores.append("la orden de compra no tiene entregas planificadas")
        return []
    sin_fecha = [e["numero_entrega"] for e in entregas if not e.get("fecha_entrega_planificada")]
    if sin_fecha:
        errores.append(f"entregas sin fecha planificada: {_lista(sin_fecha)}")

    items = repo.listar_entregas_items(
        client, entrega_oc_ids=[e["id"] for e in entregas], drogueria_id=drogueria_id
    )
    por_id = {e["id"]: e for e in entregas}
    ids_renglones = {r.oc_item_id for r in renglones}

    # Un item de entrega cuyo renglón no es de esta OC se rechaza en vez de descartarse
    # en silencio: la suma por renglón no lo vería y el CSV saldría sin esa cantidad.
    huerfanos = [i["oc_item_id"] for i in items if i["oc_item_id"] not in ids_renglones]
    if huerfanos:
        errores.append(
            f"items de entrega que no corresponden a ningún renglón de la orden: {_lista(huerfanos)}"
        )

    sumas: dict[str, Decimal] = {r.oc_item_id: Decimal("0") for r in renglones}
    for i in items:
        if i["oc_item_id"] in sumas:
            sumas[i["oc_item_id"]] += Decimal(str(i["cantidad_planificada"]))
    no_cierran = [
        f"{r.numero_renglon} (planificado {sumas[r.oc_item_id]}, cantidad {r.cantidad})"
        for r in sorted(renglones, key=lambda r: r.numero_renglon)
        if sumas[r.oc_item_id] != r.cantidad
    ]
    if no_cierran:
        errores.append(
            f"la suma planificada no coincide con la cantidad del renglón {_lista(no_cierran)}"
        )

    return [
        EntregaExport(
            oc_item_id=i["oc_item_id"],
            numero_entrega=por_id[i["entrega_oc_id"]]["numero_entrega"],
            fecha_entrega=por_id[i["entrega_oc_id"]]["fecha_entrega_planificada"],
            cantidad_planificada=Decimal(str(i["cantidad_planificada"])),
        )
        for i in items
        if i["oc_item_id"] in ids_renglones
        and i["entrega_oc_id"] in por_id
        and por_id[i["entrega_oc_id"]].get("fecha_entrega_planificada")
    ]


def exportar_orden_compra(
    client: Client,
    *,
    orden_compra_id: str,
    drogueria_id: str,
    usuario_id: str,
    settings: Settings,
) -> ResultadoExportacion:
    if not settings.progress_docs_dir:
        raise IntegracionNoConfigurada(
            "La exportación a Progress no está configurada (falta PROGRESS_DOCS_DIR)"
        )

    oc = repo.buscar_orden_compra(
        client, orden_compra_id=orden_compra_id, drogueria_id=drogueria_id
    )
    if oc is None:
        raise NotFoundError("No se encontró la orden de compra")
    if oc.get("exportado_at"):
        raise _conflicto_ya_exportada(client, oc)
    # El hash se lee ANTES que las filas del plan: si el plan cambia entre esta lectura y la
    # de las filas, el hash queda desactualizado y el RPC responde `plan_cambiado` (falso
    # positivo seguro). Al revés, un cambio quedaría tapado.
    plan_hash = repo.hash_plan(client, orden_compra_id=orden_compra_id)

    # D2: se validan TODAS las precondiciones y se reportan juntas.
    errores = _errores_cabecera(oc)
    codigo_cliente, cuit_cliente = _resolver_cliente(client, oc, drogueria_id, errores)
    items = repo.listar_oc_items(client, orden_compra_id=orden_compra_id, drogueria_id=drogueria_id)
    renglones = _armar_renglones(client, items, drogueria_id, errores)
    entregas_csv = _armar_entregas(
        client,
        repo.listar_entregas(client, orden_compra_id=orden_compra_id, drogueria_id=drogueria_id),
        renglones,
        drogueria_id,
        errores,
    )
    if errores:
        raise ValidationError(
            "No se puede exportar la orden de compra a Progress: " + "; ".join(errores)
        )

    filas = construir_filas(
        OcExport(
            id=oc["id"],
            numero_oc=oc["numero_oc"],
            version_numero=oc["version_numero"],
            fecha_emision=oc.get("fecha_emision"),
            direccion_entrega=oc.get("direccion_entrega"),
        ),
        renglones,
        entregas_csv,
        codigo_cliente=codigo_cliente,
        cuit_cliente=cuit_cliente,
    )
    if not filas:
        raise ValidationError(
            "No se puede exportar la orden de compra a Progress: no hay cantidades planificadas"
        )

    nombre = construir_nombre(codigo_cliente, oc["numero_oc"], oc["version_numero"])
    ruta = escribir_csv(
        filas,
        carpeta=carpeta_oc(settings.progress_docs_dir),
        nombre=nombre,
        encoding=settings.oc_export_encoding,
    )

    exportado_at = datetime.now(timezone.utc)
    try:
        estado = repo.marcar_exportada(
            client,
            orden_compra_id=orden_compra_id,
            drogueria_id=drogueria_id,
            usuario_id=usuario_id,
            archivo_exportado=nombre,
            plan_hash=plan_hash,
        )
    except Exception:
        # Fallo ambiguo: el RPC pudo haberse aplicado y haberse perdido solo la respuesta.
        # Se relee la OC: si quedó marcada con ESTE archivo, el archivo se conserva.
        if _quedo_marcada_con(client, orden_compra_id, drogueria_id, nombre):
            logger.warning(
                "La marca de exportación de la OC %s se aplicó aunque la llamada falló",
                orden_compra_id,
            )
        else:
            # Compensación manual (D6, mismo criterio que oc_entregas.planificar_entregas).
            ruta.unlink(missing_ok=True)
            raise
    else:
        if estado != "ok":
            ruta.unlink(missing_ok=True)
            raise _error_de_marca(estado)

    try:
        registrar_cambio(
            client,
            entidad="orden_compra",
            entidad_id=orden_compra_id,
            drogueria_id=drogueria_id,
            campo="exportado_at",
            valor_anterior=None,
            valor_nuevo=exportado_at,
            origen="usuario",
            usuario_id=usuario_id,
            batch_id=str(uuid.uuid4()),
        )
    except Exception:
        # La exportación ya está hecha y marcada: no se deshace por un fallo de auditoría.
        logger.exception("No se pudo auditar la exportación de la OC %s", orden_compra_id)

    return ResultadoExportacion(
        archivo=nombre,
        exportado_at=exportado_at,
        exportado_por=UUID(usuario_id),
        filas=len(filas),
    )

