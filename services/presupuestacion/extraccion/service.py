import csv
import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from supabase import Client

from services.presupuestacion.core.audit import registrar_cambio, registrar_evento_ciclo_vida
from services.presupuestacion.core.database import get_service_client
from services.presupuestacion.core.exceptions import (
    ConflictError,
    ExtraccionNoDisponibleError,
    NotFoundError,
    ValidationError,
)
from services.presupuestacion.core.texto import normalizar_descripcion
from services.presupuestacion.extraccion import repository as repo
from services.presupuestacion.extraccion.models import (
    MAX_FILAS_EDITABLES,
    ExtraccionResumen,
    FilasExtraccionOut,
    ResultadoValidarExtraccion,
)
from services.presupuestacion.matching.service import procesar_matching_item
from services.presupuestacion.notificaciones.service import crear_notificacion

logger = logging.getLogger(__name__)

# document_type que materializan en items_proceso (mismo robot de extracción para ambos
# hoy — la distinción cotizacion/licitacion vive en procesos_comerciales.clase, no acá).
_TIPOS_ITEMS_PROCESO = {"licitacion", "cotizacion"}

_ROLES_NOTIFICACION_REEMPLAZO = ("admin", "gerencia", "lider_comercial")

# document_type que tienen lectura de filas implementada para GET .../filas
# (§8.2 -- orden_compra queda deliberadamente afuera, no hay CSV materializable).
_TIPOS_CON_LECTURA_DE_FILAS = {"licitacion", "cotizacion", "comparativa"}


def _leer_filas_csv_con_columnas(
    csv_disk_path: str | None,
) -> tuple[list[str], list[dict[str, str]]]:
    """Origen único de lectura del CSV crudo -- columnas en el orden real del
    DictReader (§8.2) + filas. `_leer_filas_csv` es un atajo sobre esto para los
    callers que solo necesitan las filas (materialización)."""
    if not csv_disk_path:
        raise ExtraccionNoDisponibleError(
            "Esta extracción no tiene archivo de resultados asociado"
        )
    try:
        with open(csv_disk_path, encoding="utf-8", newline="") as archivo:
            reader = csv.DictReader(archivo, delimiter=";")
            filas = list(reader)
            columnas = list(reader.fieldnames or [])
    except OSError as exc:
        raise ExtraccionNoDisponibleError(
            "El archivo de la extracción no está disponible — "
            "puede que el volumen compartido no esté montado"
        ) from exc
    return columnas, filas


def _leer_filas_csv(csv_disk_path: str | None) -> list[dict[str, str]]:
    _, filas = _leer_filas_csv_con_columnas(csv_disk_path)
    return filas


def listar_extracciones(
    client: Client, *, validado: bool | None, limit: int, offset: int
) -> list[ExtraccionResumen]:
    filas = repo.listar_extracciones(client, validado=validado, limit=limit, offset=offset)
    resumenes = []
    for fila in filas:
        proceso_embed = fila.pop("procesos_comerciales", None) or {}
        resumenes.append(
            ExtraccionResumen(**fila, proceso_comercial_nombre=proceso_embed.get("nombre"))
        )
    return resumenes


def leer_filas_extraccion(extraction: dict[str, Any]) -> FilasExtraccionOut:
    document_type = extraction["document_type"]
    if document_type not in _TIPOS_CON_LECTURA_DE_FILAS:
        raise ValidationError(
            f"document_type='{document_type}' no tiene lectura de filas implementada"
        )

    columnas, filas_completas = _leer_filas_csv_con_columnas(extraction["csv_disk_path"])
    filas_leidas = len(filas_completas)
    editable = filas_leidas <= MAX_FILAS_EDITABLES

    return FilasExtraccionOut(
        extraction_id=extraction["id"],
        document_type=document_type,
        row_count=extraction["row_count"],
        filas_leidas=filas_leidas,
        editable=editable,
        columnas=columnas,
        # >500 filas: no se manda una lista gigante que la UI no va a renderizar
        # (§8.2) -- el frontend ya bloquea la edición antes de pedir esto, esto es
        # la red de seguridad del servidor.
        filas=filas_completas if editable else [],
    )


def _chequear_entero(errores: list[str], numero: int, campo: str, valor: str) -> None:
    try:
        entero = int((valor or "").strip())
    except (TypeError, ValueError):
        errores.append(f"fila {numero}: '{campo}' no es un número entero válido (\"{valor}\")")
        return
    if entero <= 0:
        errores.append(f"fila {numero}: '{campo}' debe ser mayor a cero (\"{valor}\")")


def _chequear_texto(errores: list[str], numero: int, campo: str, valor: str) -> None:
    if not (valor or "").strip():
        errores.append(f"fila {numero}: '{campo}' no puede estar vacío")


def _chequear_decimal(
    errores: list[str], numero: int, campo: str, valor: str, *, minimo: Decimal
) -> None:
    try:
        decimal_valor = Decimal((valor or "").strip().replace(",", "."))
    except (TypeError, InvalidOperation):
        errores.append(f"fila {numero}: '{campo}' no es un número válido (\"{valor}\")")
        return
    if decimal_valor < minimo:
        errores.append(f"fila {numero}: '{campo}' no puede ser negativo (\"{valor}\")")


def _validar_filas_override(
    filas: list[dict[str, str]] | None, *, document_type: str
) -> None:
    """Corre en `validar_extraccion()` ANTES del primer write (§3 -- si esto revienta,
    `_resolver_proceso_comercial_id` nunca corre y la extracción queda intacta)."""
    if filas is None:
        return
    if not filas:
        raise ValidationError("La lista de filas no puede estar vacía")
    if len(filas) > MAX_FILAS_EDITABLES:
        raise ValidationError(
            f"No se pueden editar más de {MAX_FILAS_EDITABLES} filas en una validación "
            f"(recibidas {len(filas)})"
        )

    es_comparativa = document_type == "comparativa"
    esperado = "comparativa" if es_comparativa else "licitación/cotización"
    if es_comparativa != ("renglon" in filas[0]):
        raise ValidationError(
            f"Las filas enviadas no corresponden a un documento de tipo {esperado}"
        )

    errores: list[str] = []
    for numero, fila in enumerate(filas, start=1):
        if es_comparativa:
            _chequear_entero(errores, numero, "renglon", fila["renglon"])
            _chequear_texto(errores, numero, "proveedor", fila["proveedor"])
            _chequear_decimal(errores, numero, "precio", fila["precio"], minimo=Decimal(0))
        else:
            _chequear_entero(errores, numero, "item", fila["item"])
            _chequear_texto(errores, numero, "descripcion", fila["descripcion"])
            _chequear_decimal(errores, numero, "cantidad", fila["cantidad"], minimo=Decimal(0))

    if errores:
        detalle = "; ".join(errores[:10])
        extra = f" (y {len(errores) - 10} más)" if len(errores) > 10 else ""
        raise ValidationError(f"Filas con datos inválidos — {detalle}{extra}")


def _filas_a_materializar(
    extraction: dict[str, Any], filas_override: list[dict[str, str]] | None
) -> list[dict[str, str]]:
    """Origen único de las filas. El CSV en disco nunca se reescribe (D2)."""
    if filas_override is not None:
        return filas_override
    return _leer_filas_csv(extraction["csv_disk_path"])


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
    filas_override: list[dict[str, str]] | None,
) -> int:
    filas_csv = _filas_a_materializar(extraction, filas_override)

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
    client: Client,
    *,
    drogueria_id: str,
    proceso_comercial_id: str,
    comparativa_id: str,
    extraction_id: str,
    actor_id: str,
) -> None:
    """D6 -- corre DESPUÉS del flip de `validado=TRUE` (ver call site en
    `validar_extraccion`), envuelta en try/except: un aviso no es una aprobación y
    no puede revertir ni bloquear una validación ya confirmada en la DB."""
    destinatarios = repo.listar_usuarios_por_rol(
        client,
        drogueria_id=drogueria_id,
        roles=_ROLES_NOTIFICACION_REEMPLAZO,
        excluir_id=actor_id,
    )
    for usuario in destinatarios:  # sin destinatarios -> no pasa nada, no es error
        crear_notificacion(  # notificaciones.service, NO el insert directo del repo local
            client,
            drogueria_id=drogueria_id,
            destinatario_id=usuario["id"],
            tipo="comparativa_disponible",
            titulo="Comparativa reemplazada por una nueva extracción",
            mensaje=(
                "Se validó una nueva extracción que reemplazó la comparativa vigente "
                "de este proceso. La versión anterior quedó invalidada."
            ),
            prioridad="alta",
            url_destino=f"/comparativas/{comparativa_id}",
            origen="sistema",
            relaciones={
                "proceso_comercial_id": proceso_comercial_id,
                "comparativa_id": comparativa_id,
            },
            metadata={
                "extraction_result_id": extraction_id,
                "motivo": "reemplazo_por_validacion",
            },
        )


def _materializar_comparativa(
    client: Client,
    *,
    extraction: dict[str, Any],
    proceso_comercial_id: str,
    drogueria_id: str,
    usuario_id: str,
    filas_override: list[dict[str, str]] | None,
) -> tuple[str, int, bool]:
    filas_csv = _filas_a_materializar(extraction, filas_override)

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
    registrar_evento_ciclo_vida(
        client,
        entidad="comparativa",
        entidad_id=comparativa["id"],
        drogueria_id=drogueria_id,
        tipo_cambio="creacion",
        origen="usuario",
        usuario_id=usuario_id,
    )

    if reemplazo:
        repo.invalidar_comparativa(client, comparativa_id=vigente_previa["id"])
        registrar_cambio(
            client,
            entidad="comparativa",
            entidad_id=vigente_previa["id"],
            drogueria_id=drogueria_id,
            campo="es_vigente",
            valor_anterior=True,
            valor_nuevo=False,
            origen="usuario",
            usuario_id=usuario_id,
            batch_id=str(uuid.uuid4()),
        )

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

    return comparativa["id"], len(ofertas_creadas), reemplazo


def validar_extraccion(
    client: Client,
    *,
    extraction_id: str,
    usuario_id: str,
    proceso_comercial_id: str | None,
    filas_override: list[dict[str, str]] | None = None,
) -> ResultadoValidarExtraccion:
    extraction = repo.buscar_extraction_result(client, extraction_id=extraction_id)
    if extraction is None:
        raise NotFoundError("No se encontró la extracción")
    if extraction["validado"]:
        raise ConflictError("Esta extracción ya fue validada")

    # §3 -- puro, sin tocar la DB, y ANTES del primer write (`_resolver_proceso_comercial_id`
    # abajo). Si `filas_override` trae datos inválidos, la extracción queda exactamente
    # como estaba: sin proceso_comercial_id, sin items_proceso/comparativas.
    _validar_filas_override(filas_override, document_type=extraction["document_type"])

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
            filas_override=filas_override,
        )
    elif document_type == "comparativa":
        comparativa_id, filas_creadas, reemplazo = _materializar_comparativa(
            client,
            extraction=extraction,
            proceso_comercial_id=proceso_comercial_id_resuelto,
            drogueria_id=extraction["drogueria_id"],
            usuario_id=usuario_id,
            filas_override=filas_override,
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

    # Fire-and-forget (D6): un aviso no es una aprobación. Nada de lo que pase acá
    # puede revertir ni bloquear una validación que YA está confirmada en la DB.
    if reemplazo and comparativa_id is not None:
        try:
            _notificar_reemplazo_comparativa(
                client,
                drogueria_id=extraction["drogueria_id"],
                proceso_comercial_id=proceso_comercial_id_resuelto,
                comparativa_id=comparativa_id,
                extraction_id=extraction_id,
                actor_id=usuario_id,
            )
        except Exception:  # noqa: BLE001 — deliberado, ver comentario de arriba
            logger.exception(
                "No se pudo notificar el reemplazo de comparativa "
                "(extraction_id=%s, comparativa_id=%s)",
                extraction_id,
                comparativa_id,
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
    *,
    extraction_id: str,
    usuario_id: str,
    proceso_comercial_id: str | None,
    filas_override: list[dict[str, str]] | None = None,
) -> ResultadoValidarExtraccion:
    """Corre con service_role: materializar toca items_proceso/comparativas/ofertas_items/
    notificaciones y dispara matching — mismo criterio que pricing/matching/presupuestos,
    el router nunca importa el service client directamente."""
    return validar_extraccion(
        get_service_client(),
        extraction_id=extraction_id,
        usuario_id=usuario_id,
        proceso_comercial_id=proceso_comercial_id,
        filas_override=filas_override,
    )
