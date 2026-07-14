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


# -- proveedores -------------------------------------------------------------------

def importar_proveedores(
    client: Client, *, drogueria_id: str, proveedores: list[ImportProveedorRow], usuario_id: str
) -> dict:
    if not proveedores:
        raise ValidationError("La lista de proveedores no puede estar vacía")

    con_codigo = [p for p in proveedores if p.codigo_interno]
    sin_codigo = [p for p in proveedores if not p.codigo_interno]

    codigos = [p.codigo_interno for p in con_codigo]
    existentes = repo.codigos_existentes_proveedores(client, drogueria_id=drogueria_id, codigos=codigos)

    def _base(p: ImportProveedorRow) -> dict:
        return {
            "drogueria_id": drogueria_id,
            "codigo_interno": p.codigo_interno,
            "razon_social": p.razon_social,
            "nombre_comercial": p.nombre_comercial,
            "cuit": p.cuit,
            "tipo": p.tipo or "otro",
            "es_competidor": p.es_competidor if p.es_competidor is not None else True,
            "es_proveedor_compra": p.es_proveedor_compra if p.es_proveedor_compra is not None else False,
            "plazo_pago_dias": p.plazo_pago_dias,
            "condiciones_pago": p.condiciones_pago,
            "activo": True,
            "updated_by": usuario_id,
        }

    nuevos_filas = []
    actualizados_filas = []
    for p in con_codigo:
        base = _base(p)
        if p.codigo_interno in existentes:
            actualizados_filas.append(base)
        else:
            nuevos_filas.append({**base, "created_by": usuario_id})

    for p in sin_codigo:
        nuevos_filas.append({**_base(p), "created_by": usuario_id})

    repo.insertar_proveedores(client, nuevos_filas)
    repo.actualizar_proveedores_existentes(client, actualizados_filas)

    activos = repo.codigos_activos_proveedores(client, drogueria_id=drogueria_id)
    faltantes = activos - set(codigos)
    if faltantes:
        repo.desactivar_proveedores(
            client, drogueria_id=drogueria_id, codigos=list(faltantes), usuario_id=usuario_id
        )

    return {
        "creados": len(nuevos_filas),
        "actualizados": len(actualizados_filas),
        "desactivados": len(faltantes),
        "sin_codigo_interno": len(sin_codigo),
    }


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

    codigos = [c.codigo_interno for c in clientes]
    existentes = repo.mapear_clientes_por_codigo(client, drogueria_id=drogueria_id, codigos=codigos)

    nuevos_filas = []
    actualizados = 0
    for c in clientes:
        campos_opcionales = {
            k: v
            for k, v in {
                "direccion": c.direccion,
                "ciudad": c.ciudad,
                "provincia": c.provincia,
                "codigo_postal": c.codigo_postal,
                "plazo_pago_dias": c.plazo_pago_dias,
                "condiciones_pago": c.condiciones_pago,
            }.items()
            if v is not None
        }

        if c.codigo_interno in existentes:
            campos = dict(campos_opcionales)
            if c.nombre is not None:
                campos["nombre"] = c.nombre
            if c.tipo is not None:
                campos["tipo"] = c.tipo
            campos["updated_by"] = usuario_id
            repo.actualizar_cliente(client, cliente_id=existentes[c.codigo_interno], campos=campos)
            actualizados += 1
        else:
            if c.nombre is None or c.tipo is None:
                raise ValidationError(
                    f"El cliente nuevo '{c.codigo_interno}' requiere nombre y tipo"
                )
            nuevos_filas.append(
                {
                    "drogueria_id": drogueria_id,
                    "codigo_interno": c.codigo_interno,
                    "nombre": c.nombre,
                    "tipo": c.tipo,
                    **campos_opcionales,
                    "activo": True,
                    "created_by": usuario_id,
                    "updated_by": usuario_id,
                }
            )

    repo.insertar_clientes(client, nuevos_filas)

    activos = repo.codigos_activos_clientes(client, drogueria_id=drogueria_id)
    faltantes = activos - set(codigos)
    if faltantes:
        repo.desactivar_clientes(
            client, drogueria_id=drogueria_id, codigos=list(faltantes), usuario_id=usuario_id
        )

    return {
        "creados": len(nuevos_filas),
        "actualizados": actualizados,
        "desactivados": len(faltantes),
    }


def importar_clientes_para_endpoint(*, drogueria_id: str, clientes: list[ImportClienteRow]) -> dict:
    return importar_clientes(
        get_service_client(),
        drogueria_id=drogueria_id,
        clientes=clientes,
        usuario_id=_usuario_sistema_id(),
    )
