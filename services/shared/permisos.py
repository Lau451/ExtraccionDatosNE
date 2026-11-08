"""Matriz única rol → capacidad (etapa 5, X-ARQ-005;
odd/tasks/roles-capacidades.md S1-S2).

Cada módulo pregunta por una capacidad con nombre (`require_capacidad("pcp.escribir")`)
en lugar de escribir su propia tupla de roles. La matriz vive en código por ahora
(L3): cambiar un permiso es un cambio revisable en un PR. Pasarla a una tabla
`rol_capacidades` es una etapa posterior y solo cambia de dónde se lee.

Una capacidad por acción (S2): dos capacidades con los mismos roles hoy siguen
separadas porque mañana pueden divergir. Las políticas RLS de
docs/schema/rls_final.sql mantienen sus propias listas (S8).
"""

from types import MappingProxyType
from typing import Mapping

_TODOS = frozenset({"superadmin", "admin", "gerencia", "lider_comercial", "comercial", "compras"})
_COMERCIAL = frozenset({"admin", "gerencia", "lider_comercial", "comercial"})
_TERCEROS_ESCRITURA = frozenset({"admin", "gerencia", "lider_comercial"})


class CapacidadDesconocidaError(KeyError):
    """Una capacidad que no está en la matriz es un error de programación, no un deny."""


MATRIZ: Mapping[str, frozenset[str]] = MappingProxyType(
    {
        # pcp
        "pcp.leer": frozenset({"superadmin", "admin", "gerencia", "compras"}),
        "pcp.escribir": frozenset({"admin", "gerencia", "compras"}),
        # terceros
        "terceros.leer": _TODOS,
        "terceros.escribir": _TERCEROS_ESCRITURA,
        "terceros.contactos.leer": _TODOS,
        "terceros.contactos.escribir": _TERCEROS_ESCRITURA,
        "terceros.direcciones.leer": _TODOS,
        "terceros.direcciones.escribir": _TERCEROS_ESCRITURA,
        "terceros.catalogos.leer": _TODOS,
        "terceros.catalogos.escribir": _TERCEROS_ESCRITURA,
        # productos
        "productos.leer": _TODOS,
        "productos.escribir": frozenset({"admin", "gerencia", "compras"}),
        "productos.categorias.escribir": frozenset({"admin", "gerencia"}),
        "productos.costos.leer": frozenset({"superadmin", "admin", "gerencia", "lider_comercial", "compras"}),
        # integracion_progress
        "integracion_progress.leer": _TODOS,
        "presupuestos.importar_legacy": frozenset({"admin"}),
        # extraccion (servicio de extracción con IA)
        "extraccion.extraer": _COMERCIAL,
        # presupuestacion
        "auditoria.leer": _TODOS,
        "automatizaciones.gestionar": frozenset({"admin", "gerencia"}),
        "clientes.leer": _TODOS,
        "clientes.escribir": _COMERCIAL,
        "comparativas.leer": _TODOS,
        "comparativas.asignar": _COMERCIAL,
        "compras.leer": _TODOS,
        "compras.oc": _COMERCIAL,
        "compras.entregas": _COMERCIAL,
        "compras.vs_cotizado": frozenset({"superadmin", "admin", "gerencia", "compras"}),
        "compromisos.leer": _TODOS,
        "droguerias.gestionar": frozenset({"superadmin"}),
        "eventos.leer": _TODOS,
        "eventos.escribir": frozenset({"admin", "gerencia", "lider_comercial", "comercial", "compras"}),
        "eventos.eliminar": frozenset({"admin", "gerencia"}),
        "extraccion.listar": _COMERCIAL,
        "extraccion.validar": _COMERCIAL,
        "imports.importar": frozenset({"admin", "gerencia", "compras"}),
        "matching.usar": frozenset({"superadmin", "admin", "gerencia", "lider_comercial", "comercial"}),
        "oc_entregas.planificar": _COMERCIAL,
        "oc_export.exportar": _COMERCIAL,
        "oc_presupuesto.matching": _COMERCIAL,
        "oc_resumen.leer": _TODOS,
        "presupuestos.leer": frozenset({"superadmin", "admin", "gerencia", "lider_comercial", "comercial"}),
        "presupuestos.aprobar": frozenset({"superadmin", "admin", "gerencia", "lider_comercial"}),
        "presupuestos.ajustar": frozenset({"superadmin", "admin", "gerencia", "lider_comercial", "comercial"}),
        "presupuestos.presentar": frozenset({"superadmin", "admin", "gerencia", "lider_comercial", "comercial"}),
        "presupuestos.ver_costo": frozenset({"superadmin", "admin", "gerencia"}),
        "pricing.generar_presupuesto": frozenset({"superadmin", "admin", "gerencia", "lider_comercial", "comercial"}),
        "pricing.precios_especiales": frozenset({"superadmin", "admin", "gerencia", "compras"}),
        "procesos_comerciales.leer": _TODOS,
        "procesos_comerciales.escribir": _COMERCIAL,
        "usuarios.gestionar": frozenset({"superadmin", "admin", "gerencia"}),
        # Solo pantallas del frontend: difieren de la capacidad de su API.
        "compromisos.ver_pantalla": frozenset({"admin", "gerencia", "lider_comercial", "comercial", "compras"}),
        "oc_resumen.acciones": _COMERCIAL,
    }
)


def roles_con(capacidad: str) -> frozenset[str]:
    try:
        return MATRIZ[capacidad]
    except KeyError:
        raise CapacidadDesconocidaError(capacidad) from None


def tiene_capacidad(rol: str, capacidad: str) -> bool:
    return rol in roles_con(capacidad)


def capacidades_de(rol: str) -> list[str]:
    return sorted(cap for cap, roles in MATRIZ.items() if rol in roles)
