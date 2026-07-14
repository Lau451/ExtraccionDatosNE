import csv
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from supabase import Client

from services.presupuestacion.core.database import get_service_client
from services.presupuestacion.core.exceptions import ConflictError, NotFoundError, ValidationError
from services.presupuestacion.core.texto import normalizar_descripcion
from services.presupuestacion.extraccion import repository as repo
from services.presupuestacion.extraccion.models import ResultadoValidarExtraccion
from services.presupuestacion.matching.service import procesar_matching_item

# document_type que materializan en items_proceso (mismo robot de extracción para ambos
# hoy — la distinción cotizacion/licitacion vive en procesos_comerciales.clase, no acá).
_TIPOS_ITEMS_PROCESO = {"licitacion", "cotizacion"}

_ROLES_NOTIFICACION_REEMPLAZO = ("admin", "gerencia", "lider_comercial")


def _leer_filas_csv(csv_disk_path: str) -> list[dict[str, str]]:
    with open(csv_disk_path, encoding="utf-8", newline="") as archivo:
        return list(csv.DictReader(archivo, delimiter=";"))


def _resolver_proceso_comercial_id(
    client: Client, *, extraction: dict[str, Any], proceso_comercial_id: str | None
) -> str:
    existente = extraction.get("proceso_comercial_id")
    if existente is not None:
        if proceso_comercial_id is not None and proceso_comercial_id != existente:
            raise ConflictError(
                "Esta extracción ya está vinculada a otro proceso_comercial_id"
            )
        return existente

    if proceso_comercial_id is None:
        raise ValidationError(
            "Esta extracción no tiene proceso_comercial_id — indicalo para poder validarla"
        )

    proceso = repo.buscar_proceso_comercial(client, proceso_comercial_id=proceso_comercial_id)
    if proceso is None:
        raise NotFoundError("No se encontró el proceso comercial indicado")
    if proceso["drogueria_id"] != extraction["drogueria_id"]:
        raise ValidationError(
            "El proceso comercial indicado no pertenece a la misma droguería que la extracción"
        )

    repo.actualizar_extraction_result(
        client,
        extraction_id=extraction["id"],
        campos={"proceso_comercial_id": proceso_comercial_id},
    )
    return proceso_comercial_id


def _materializar_licitacion(
    client: Client,
    *,
    extraction: dict[str, Any],
    proceso_comercial_id: str,
    drogueria_id: str,
    cliente_id: str | None,
) -> int:
    filas_csv = _leer_filas_csv(extraction["csv_disk_path"])

    filas_items = []
    for fila in filas_csv:
        descripcion = fila["descripcion"].strip()
        filas_items.append(
            {
                "proceso_comercial_id": proceso_comercial_id,
                "drogueria_id": drogueria_id,
                "extraction_id": extraction["id"],
                "numero_renglon": int(fila["item"].strip()),
                "descripcion": descripcion,
                "descripcion_normalizada": normalizar_descripcion(descripcion),
                "cantidad": fila["cantidad"].strip(),
            }
        )

    items_creados = repo.insertar_items_proceso(client, filas_items)

    for item in items_creados:
        procesar_matching_item(
            client, item=item, drogueria_id=drogueria_id, cliente_id=cliente_id
        )

    return len(items_creados)


def _computar_posiciones(filas: list[dict[str, Any]]) -> list[tuple[str, int, bool]]:
    """Agrupa por renglon_id, ordena por precio_unitario ascendente y asigna
    posicion_precio (1 = más barato) + adjudicacion_estimada=TRUE al ganador de cada
    renglón (§5)."""
    por_renglon: dict[str, list[dict[str, Any]]] = {}
    for fila in filas:
        por_renglon.setdefault(fila["renglon_id"], []).append(fila)

    actualizaciones: list[tuple[str, int, bool]] = []
    for filas_del_renglon in por_renglon.values():
        ordenadas = sorted(filas_del_renglon, key=lambda f: Decimal(str(f["precio_unitario"])))
        for posicion, fila in enumerate(ordenadas, start=1):
            actualizaciones.append((fila["id"], posicion, posicion == 1))
    return actualizaciones


def _notificar_reemplazo_comparativa(
    client: Client, *, drogueria_id: str, proceso_comercial_id: str, comparativa_id: str
) -> None:
    destinatarios = repo.listar_usuarios_por_rol(
        client, drogueria_id=drogueria_id, roles=_ROLES_NOTIFICACION_REEMPLAZO
    )
    for usuario in destinatarios:
        repo.crear_notificacion(
            client,
            fila={
                "drogueria_id": drogueria_id,
                "destinatario_id": usuario["id"],
                "tipo": "comparativa_disponible",
                "titulo": "Comparativa reemplazada por una nueva extracción",
                "mensaje": (
                    "Se validó una nueva extracción que reemplazó la comparativa vigente "
                    "de este proceso."
                ),
                "origen": "sistema",
                "proceso_comercial_id": proceso_comercial_id,
                "comparativa_id": comparativa_id,
            },
        )


def _materializar_comparativa(
    client: Client,
    *,
    extraction: dict[str, Any],
    proceso_comercial_id: str,
    drogueria_id: str,
) -> tuple[str, int, bool]:
    filas_csv = _leer_filas_csv(extraction["csv_disk_path"])

    items_por_renglon = {
        item["numero_renglon"]: item["id"]
        for item in repo.listar_items_proceso_por_proceso(
            client, proceso_comercial_id=proceso_comercial_id
        )
    }

    vigente_previa = repo.buscar_comparativa_vigente(client, proceso_comercial_id=proceso_comercial_id)
    reemplazo = vigente_previa is not None

    proveedores = {f["proveedor"].strip() for f in filas_csv if f.get("proveedor")}
    renglones = {f["renglon"].strip() for f in filas_csv if f.get("renglon")}

    fila_comparativa: dict[str, Any] = {
        "proceso_comercial_id": proceso_comercial_id,
        "drogueria_id": drogueria_id,
        "extraction_id": extraction["id"],
        "cantidad_proveedores": len(proveedores),
        "items_analizados": len(renglones),
    }
    if reemplazo:
        fila_comparativa["version_numero"] = vigente_previa["version_numero"] + 1
        fila_comparativa["reemplaza_id"] = vigente_previa["id"]
        fila_comparativa["motivo_version"] = "nueva extracción validada"

    comparativa = repo.crear_comparativa(client, fila_comparativa)

    if reemplazo:
        repo.invalidar_comparativa(client, comparativa_id=vigente_previa["id"])

    # es_drogueria_propia NO se auto-detecta: el texto de "proveedor" no trae ningún
    # marcador confiable y un falso positivo dispara compras sobre una premisa falsa
    # (ver v_renglones_ganados). Queda para un PATCH manual, fuera de este alcance.
    filas_ofertas = []
    for fila in filas_csv:
        renglon_texto = fila["renglon"].strip()
        try:
            item_proceso_id = items_por_renglon.get(int(renglon_texto))
        except ValueError:
            item_proceso_id = None

        filas_ofertas.append(
            {
                "comparativa_id": comparativa["id"],
                "drogueria_id": drogueria_id,
                "item_proceso_id": item_proceso_id,
                "renglon_id": renglon_texto,
                "proveedor": fila["proveedor"].strip(),
                # No hay columna "marca" en ofertas_items ni "descripcion" en el CSV de
                # comparativa: reusamos marca como descripcion (mejor que perderla).
                "descripcion": (fila.get("marca") or "").strip() or None,
                "precio_unitario": fila["precio"].strip().replace(",", "."),
                "es_drogueria_propia": False,
            }
        )

    ofertas_creadas = repo.insertar_ofertas_items(client, filas_ofertas)

    for oferta_id, posicion, es_ganadora in _computar_posiciones(ofertas_creadas):
        repo.actualizar_oferta_item(
            client,
            oferta_item_id=oferta_id,
            campos={"posicion_precio": posicion, "adjudicacion_estimada": es_ganadora},
        )

    if reemplazo:
        _notificar_reemplazo_comparativa(
            client,
            drogueria_id=drogueria_id,
            proceso_comercial_id=proceso_comercial_id,
            comparativa_id=comparativa["id"],
        )

    return comparativa["id"], len(ofertas_creadas), reemplazo


def validar_extraccion(
    client: Client,
    *,
    extraction_id: str,
    usuario_id: str,
    proceso_comercial_id: str | None,
) -> ResultadoValidarExtraccion:
    extraction = repo.buscar_extraction_result(client, extraction_id=extraction_id)
    if extraction is None:
        raise NotFoundError("No se encontró la extracción")
    if extraction["validado"]:
        raise ConflictError("Esta extracción ya fue validada")

    proceso_comercial_id_resuelto = _resolver_proceso_comercial_id(
        client, extraction=extraction, proceso_comercial_id=proceso_comercial_id
    )
    proceso = repo.buscar_proceso_comercial(
        client, proceso_comercial_id=proceso_comercial_id_resuelto
    )
    if proceso is None:
        raise NotFoundError("No se encontró el proceso comercial")

    document_type = extraction["document_type"]
    comparativa_id: str | None = None
    reemplazo = False

    if document_type in _TIPOS_ITEMS_PROCESO:
        filas_creadas = _materializar_licitacion(
            client,
            extraction=extraction,
            proceso_comercial_id=proceso_comercial_id_resuelto,
            drogueria_id=extraction["drogueria_id"],
            cliente_id=proceso["cliente_id"],
        )
    elif document_type == "comparativa":
        comparativa_id, filas_creadas, reemplazo = _materializar_comparativa(
            client,
            extraction=extraction,
            proceso_comercial_id=proceso_comercial_id_resuelto,
            drogueria_id=extraction["drogueria_id"],
        )
    else:
        raise ValidationError(
            f"document_type='{document_type}' todavía no tiene materialización implementada"
        )

    ahora = datetime.now(timezone.utc).isoformat()
    repo.actualizar_extraction_result(
        client,
        extraction_id=extraction_id,
        campos={"validado": True, "validado_por": usuario_id, "validado_at": ahora},
    )

    return ResultadoValidarExtraccion(
        extraction_id=extraction_id,
        document_type=document_type,
        proceso_comercial_id=proceso_comercial_id_resuelto,
        filas_creadas=filas_creadas,
        comparativa_id=comparativa_id,
        reemplazo_version_anterior=reemplazo,
    )


def validar_extraccion_para_endpoint(
    *, extraction_id: str, usuario_id: str, proceso_comercial_id: str | None
) -> ResultadoValidarExtraccion:
    """Corre con service_role: materializar toca items_proceso/comparativas/ofertas_items/
    notificaciones y dispara matching — mismo criterio que pricing/matching/presupuestos,
    el router nunca importa el service client directamente."""
    return validar_extraccion(
        get_service_client(),
        extraction_id=extraction_id,
        usuario_id=usuario_id,
        proceso_comercial_id=proceso_comercial_id,
    )
