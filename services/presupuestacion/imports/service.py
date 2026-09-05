from datetime import timedelta
from decimal import Decimal

from supabase import Client

from services.presupuestacion.core.config import get_settings
from services.presupuestacion.core.database import get_service_client
from services.presupuestacion.core.exceptions import ValidationError
from services.presupuestacion.imports import repository as repo
from services.presupuestacion.imports.models import (
    ImportClienteRow,
    ImportCostoRow,
    ImportProductoRow,
    ImportProveedorRow,
    ImportStockRow,
)

DEPOSITO_SENTINEL = "unico"


def _usuario_sistema_id() -> str:
    return get_settings().usuario_sistema_id


# -- productos ---------------------------------------------------------------

def importar_productos(
    client: Client, *, drogueria_id: str, productos: list[ImportProductoRow], usuario_id: str
) -> dict:
    if not productos:
        raise ValidationError("La lista de productos no puede estar vacía")

    codigos = [p.codigo_interno for p in productos]
    existentes = repo.codigos_existentes_productos(client, drogueria_id=drogueria_id, codigos=codigos)

    nuevos_filas = []
    actualizados_filas = []
    for p in productos:
        base = {
            "drogueria_id": drogueria_id,
            "codigo_interno": p.codigo_interno,
            "nombre": p.nombre,
            "categoria_id": p.categoria_id,
            "clasificacion": p.clasificacion,
            "droga": p.droga,
            "presentacion": p.presentacion,
            "forma_farmaceutica": p.forma_farmaceutica,
            "laboratorio": p.laboratorio,
            "codigo_anmat": p.codigo_anmat,
            "datos_sistema": p.datos_sistema,
            "activo": True,
            "updated_by": usuario_id,
        }
        if p.codigo_interno in existentes:
            actualizados_filas.append(base)
        else:
            nuevos_filas.append({**base, "created_by": usuario_id})

    repo.insertar_productos(client, nuevos_filas)
    repo.actualizar_productos_existentes(client, actualizados_filas)

    activos = repo.codigos_activos_productos(client, drogueria_id=drogueria_id)
    faltantes = activos - set(codigos)
    if faltantes:
        repo.desactivar_productos(
            client, drogueria_id=drogueria_id, codigos=list(faltantes), usuario_id=usuario_id
        )

    return {
        "creados": len(nuevos_filas),
        "actualizados": len(actualizados_filas),
        "desactivados": len(faltantes),
    }


def importar_productos_para_endpoint(*, drogueria_id: str, productos: list[ImportProductoRow]) -> dict:
    return importar_productos(
        get_service_client(),
        drogueria_id=drogueria_id,
        productos=productos,
        usuario_id=_usuario_sistema_id(),
    )


# -- costos --------------------------------------------------------------------

def importar_costos(
    client: Client, *, drogueria_id: str, costos: list[ImportCostoRow], usuario_id: str
) -> dict:
    if not costos:
        raise ValidationError("La lista de costos no puede estar vacía")

    codigos = [c.codigo_interno for c in costos]
    mapa_productos = repo.mapear_productos_por_codigo(client, drogueria_id=drogueria_id, codigos=codigos)
    no_encontrados = [c for c in codigos if c not in mapa_productos]
    filas_validas = [c for c in costos if c.codigo_interno in mapa_productos]

    producto_ids = [mapa_productos[c.codigo_interno] for c in filas_validas]
    vigentes = repo.costos_vigentes_por_producto(client, producto_ids=producto_ids)

    nuevos = actualizados = sin_cambios = 0
    for fila in filas_validas:
        producto_id = mapa_productos[fila.codigo_interno]
        vigente = vigentes.get(producto_id)

        if vigente is None:
            repo.crear_costo(
                client,
                {
                    "producto_id": producto_id,
                    "drogueria_id": drogueria_id,
                    "costo_unitario": str(fila.costo_unitario),
                    "fecha_desde": fila.fecha_desde.isoformat(),
                    "fecha_hasta": None,
                    "origen": "import_sistema",
                },
            )
            nuevos += 1
        elif Decimal(str(vigente["costo_unitario"])) != fila.costo_unitario:
            fecha_cierre = fila.fecha_desde - timedelta(days=1)
            repo.cerrar_costo_vigente(
                client, costo_id=vigente["id"], fecha_hasta=fecha_cierre.isoformat()
            )
            repo.crear_costo(
                client,
                {
                    "producto_id": producto_id,
                    "drogueria_id": drogueria_id,
                    "costo_unitario": str(fila.costo_unitario),
                    "fecha_desde": fila.fecha_desde.isoformat(),
                    "fecha_hasta": None,
                    "origen": "import_sistema",
                },
            )
            actualizados += 1
        else:
            sin_cambios += 1

    return {
        "nuevos": nuevos,
        "actualizados": actualizados,
        "sin_cambios": sin_cambios,
        "no_encontrados": no_encontrados,
    }


def importar_costos_para_endpoint(*, drogueria_id: str, costos: list[ImportCostoRow]) -> dict:
    return importar_costos(
        get_service_client(), drogueria_id=drogueria_id, costos=costos, usuario_id=_usuario_sistema_id()
    )


# -- stock -----------------------------------------------------------------------

def importar_stock(
    client: Client, *, drogueria_id: str, stock: list[ImportStockRow], usuario_id: str
) -> dict:
    if not stock:
        raise ValidationError("La lista de stock no puede estar vacía")

    codigos = [s.codigo_interno for s in stock]
    mapa_productos = repo.mapear_productos_por_codigo(client, drogueria_id=drogueria_id, codigos=codigos)
    no_encontrados = [c for c in codigos if c not in mapa_productos]

    filas = [
        {
            "producto_id": mapa_productos[s.codigo_interno],
            "drogueria_id": drogueria_id,
            "deposito": s.deposito if s.deposito else DEPOSITO_SENTINEL,
            "cantidad_disponible": str(s.cantidad_disponible),
        }
        for s in stock
        if s.codigo_interno in mapa_productos
    ]
    repo.upsert_stock(client, filas)

    return {"upserted": len(filas), "no_encontrados": no_encontrados}


def importar_stock_para_endpoint(*, drogueria_id: str, stock: list[ImportStockRow]) -> dict:
    return importar_stock(
        get_service_client(), drogueria_id=drogueria_id, stock=stock, usuario_id=_usuario_sistema_id()
    )


# -- terceros legacy (proveedores + clientes, PR5/Fase 9) ------------------------
#
# Un RPC por lote (`upsert_terceros_legacy`, design.md sección 7) en lugar de
# insert/upsert directos contra `clientes`/`proveedores`: la identidad vive en
# `terceros` y la idempotencia se ancla en `terceros_legacy_map`, no en
# `codigo_interno` (design.md D1). `desactivar_*` queda deliberadamente fuera
# del RPC y opera sobre `terceros_legacy_map` para resolver los códigos
# ausentes, desactivando solo la fila de ROL — nunca el `tercero` completo,
# porque una empresa que desaparece del CSV de clientes puede seguir activa
# como proveedor.

SISTEMA_ORIGEN_LEGACY = "legacy"


def _importar_terceros_legacy(
    client: Client,
    *,
    drogueria_id: str,
    entidad_legacy: str,
    p_filas: list[dict],
    codigos_presentes: list[str],
    usuario_id: str,
) -> dict:
    filas_resultado = repo.upsert_terceros_legacy(
        client,
        drogueria_id=drogueria_id,
        sistema_origen=SISTEMA_ORIGEN_LEGACY,
        entidad_legacy=entidad_legacy,
        filas=p_filas,
        usuario_id=usuario_id,
    )
    creados = sum(1 for fila in filas_resultado if fila["accion"] == "creado")
    actualizados = len(filas_resultado) - creados

    activos_previos = repo.codigos_legacy_activos(
        client,
        drogueria_id=drogueria_id,
        sistema_origen=SISTEMA_ORIGEN_LEGACY,
        entidad_legacy=entidad_legacy,
    )
    codigos_presentes_set = set(codigos_presentes)
    faltantes = [cod for cod in activos_previos if cod not in codigos_presentes_set]
    if faltantes:
        repo.desactivar_rol_por_tercero_ids(
            client,
            entidad_legacy=entidad_legacy,
            tercero_ids=[activos_previos[cod] for cod in faltantes],
            usuario_id=usuario_id,
        )

    return {"creados": creados, "actualizados": actualizados, "desactivados": len(faltantes)}


# -- proveedores -------------------------------------------------------------------

def importar_proveedores(
    client: Client, *, drogueria_id: str, proveedores: list[ImportProveedorRow], usuario_id: str
) -> dict:
    if not proveedores:
        raise ValidationError("La lista de proveedores no puede estar vacía")

    p_filas = [
        {
            "codigo_legacy": p.codigo_interno,
            "razon_social": p.razon_social,
            "cuit": p.cuit,
            "tipo": p.tipo,
            "es_competidor": p.es_competidor,
            "es_proveedor_compra": p.es_proveedor_compra,
        }
        for p in proveedores
    ]
    return _importar_terceros_legacy(
        client,
        drogueria_id=drogueria_id,
        entidad_legacy="proveedor",
        p_filas=p_filas,
        codigos_presentes=[p.codigo_interno for p in proveedores],
        usuario_id=usuario_id,
    )


def importar_proveedores_para_endpoint(
    *, drogueria_id: str, proveedores: list[ImportProveedorRow]
) -> dict:
    return importar_proveedores(
        get_service_client(),
        drogueria_id=drogueria_id,
        proveedores=proveedores,
        usuario_id=_usuario_sistema_id(),
    )


# -- clientes ------------------------------------------------------------------------

def importar_clientes(
    client: Client, *, drogueria_id: str, clientes: list[ImportClienteRow], usuario_id: str
) -> dict:
    if not clientes:
        raise ValidationError("La lista de clientes no puede estar vacía")

    p_filas = [
        {
            "codigo_legacy": c.codigo_interno,
            "razon_social": c.razon_social,
            "cuit": c.cuit,
            "tipo": c.tipo,
        }
        for c in clientes
    ]
    return _importar_terceros_legacy(
        client,
        drogueria_id=drogueria_id,
        entidad_legacy="cliente",
        p_filas=p_filas,
        codigos_presentes=[c.codigo_interno for c in clientes],
        usuario_id=usuario_id,
    )


def importar_clientes_para_endpoint(*, drogueria_id: str, clientes: list[ImportClienteRow]) -> dict:
    return importar_clientes(
        get_service_client(),
        drogueria_id=drogueria_id,
        clientes=clientes,
        usuario_id=_usuario_sistema_id(),
    )
