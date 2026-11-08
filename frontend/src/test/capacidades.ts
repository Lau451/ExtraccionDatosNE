import type { Capacidad } from '@/features/auth/capacidades'
import type { Rol } from '@/features/auth/AuthContext'

/** Solo para tests: copia de services/shared/permisos.py `MATRIZ`, para que los
 * tests sigan describiendo qué ve cada rol aunque el frontend solo reciba la
 * lista de capacidades. tests/arquitectura/test_capacidades_frontend.py falla
 * si diverge de la matriz. */
const MATRIZ_ESPEJO: Record<Capacidad, readonly Rol[]> = {
  'pcp.leer': ['superadmin', 'admin', 'gerencia', 'compras'],
  'pcp.escribir': ['admin', 'gerencia', 'compras'],
  'terceros.leer': ['superadmin', 'admin', 'gerencia', 'lider_comercial', 'comercial', 'compras'],
  'terceros.escribir': ['admin', 'gerencia', 'lider_comercial'],
  'terceros.contactos.leer': ['superadmin', 'admin', 'gerencia', 'lider_comercial', 'comercial', 'compras'],
  'terceros.contactos.escribir': ['admin', 'gerencia', 'lider_comercial'],
  'terceros.direcciones.leer': ['superadmin', 'admin', 'gerencia', 'lider_comercial', 'comercial', 'compras'],
  'terceros.direcciones.escribir': ['admin', 'gerencia', 'lider_comercial'],
  'terceros.catalogos.leer': ['superadmin', 'admin', 'gerencia', 'lider_comercial', 'comercial', 'compras'],
  'terceros.catalogos.escribir': ['admin', 'gerencia', 'lider_comercial'],
  'productos.leer': ['superadmin', 'admin', 'gerencia', 'lider_comercial', 'comercial', 'compras'],
  'productos.escribir': ['admin', 'gerencia', 'compras'],
  'productos.categorias.escribir': ['admin', 'gerencia'],
  'productos.costos.leer': ['superadmin', 'admin', 'gerencia', 'lider_comercial', 'compras'],
  'integracion_progress.leer': ['superadmin', 'admin', 'gerencia', 'lider_comercial', 'comercial', 'compras'],
  'presupuestos.importar_legacy': ['admin'],
  'extraccion.extraer': ['admin', 'gerencia', 'lider_comercial', 'comercial'],
  'auditoria.leer': ['superadmin', 'admin', 'gerencia', 'lider_comercial', 'comercial', 'compras'],
  'automatizaciones.gestionar': ['admin', 'gerencia'],
  'clientes.leer': ['superadmin', 'admin', 'gerencia', 'lider_comercial', 'comercial', 'compras'],
  'clientes.escribir': ['admin', 'gerencia', 'lider_comercial', 'comercial'],
  'comparativas.leer': ['superadmin', 'admin', 'gerencia', 'lider_comercial', 'comercial', 'compras'],
  'comparativas.asignar': ['admin', 'gerencia', 'lider_comercial', 'comercial'],
  'compras.leer': ['superadmin', 'admin', 'gerencia', 'lider_comercial', 'comercial', 'compras'],
  'compras.oc': ['admin', 'gerencia', 'lider_comercial', 'comercial'],
  'compras.entregas': ['admin', 'gerencia', 'lider_comercial', 'comercial'],
  'compras.vs_cotizado': ['superadmin', 'admin', 'gerencia', 'compras'],
  'compromisos.leer': ['superadmin', 'admin', 'gerencia', 'lider_comercial', 'comercial', 'compras'],
  'droguerias.gestionar': ['superadmin'],
  'eventos.leer': ['superadmin', 'admin', 'gerencia', 'lider_comercial', 'comercial', 'compras'],
  'eventos.escribir': ['admin', 'gerencia', 'lider_comercial', 'comercial', 'compras'],
  'eventos.eliminar': ['admin', 'gerencia'],
  'extraccion.listar': ['admin', 'gerencia', 'lider_comercial', 'comercial'],
  'extraccion.validar': ['admin', 'gerencia', 'lider_comercial', 'comercial'],
  'imports.importar': ['admin', 'gerencia', 'compras'],
  'matching.usar': ['superadmin', 'admin', 'gerencia', 'lider_comercial', 'comercial'],
  'oc_entregas.planificar': ['admin', 'gerencia', 'lider_comercial', 'comercial'],
  'oc_export.exportar': ['admin', 'gerencia', 'lider_comercial', 'comercial'],
  'oc_presupuesto.matching': ['admin', 'gerencia', 'lider_comercial', 'comercial'],
  'oc_resumen.leer': ['superadmin', 'admin', 'gerencia', 'lider_comercial', 'comercial', 'compras'],
  'presupuestos.leer': ['superadmin', 'admin', 'gerencia', 'lider_comercial', 'comercial'],
  'presupuestos.aprobar': ['superadmin', 'admin', 'gerencia', 'lider_comercial'],
  'presupuestos.ajustar': ['superadmin', 'admin', 'gerencia', 'lider_comercial', 'comercial'],
  'presupuestos.presentar': ['superadmin', 'admin', 'gerencia', 'lider_comercial', 'comercial'],
  'presupuestos.ver_costo': ['superadmin', 'admin', 'gerencia'],
  'pricing.generar_presupuesto': ['superadmin', 'admin', 'gerencia', 'lider_comercial', 'comercial'],
  'pricing.precios_especiales': ['superadmin', 'admin', 'gerencia', 'compras'],
  'procesos_comerciales.leer': ['superadmin', 'admin', 'gerencia', 'lider_comercial', 'comercial', 'compras'],
  'procesos_comerciales.escribir': ['admin', 'gerencia', 'lider_comercial', 'comercial'],
  'usuarios.gestionar': ['superadmin', 'admin', 'gerencia'],
  'compromisos.ver_pantalla': ['admin', 'gerencia', 'lider_comercial', 'comercial', 'compras'],
  'oc_resumen.acciones': ['admin', 'gerencia', 'lider_comercial', 'comercial'],
}

export function capacidadesDeRol(rol: string | null | undefined): Capacidad[] {
  return (Object.keys(MATRIZ_ESPEJO) as Capacidad[]).filter((cap) => MATRIZ_ESPEJO[cap].includes(rol as Rol))
}

/** Los campos de `useAuth()` que dependen de las capacidades, para un rol. */
export function authDeRol(rol: string | null | undefined) {
  const capacidades = capacidadesDeRol(rol)
  return { capacidades, puede: (cap: Capacidad) => capacidades.includes(cap) }
}

/** Argumentos de `beforeLoad` para un usuario con sesión y ese rol (null =
 * perfil todavía sin resolver). */
export function navegacionDeRol(rol: string | null, href = '/') {
  return {
    context: { auth: { isAuthenticated: true, perfil: rol ? { rol } : null, capacidades: capacidadesDeRol(rol) } },
    location: { href },
  } as never
}

/** Destino del redirect que tira un guard, o undefined si deja pasar. */
export function destinoRedirect(fn: () => void): string | undefined {
  try {
    fn()
  } catch (error) {
    return (error as { options: { to: string } }).options.to
  }
  return undefined
}
