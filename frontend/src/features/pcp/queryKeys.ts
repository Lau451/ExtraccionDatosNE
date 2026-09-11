import type { EstadoPcp } from '@/lib/api/pcp'

export interface FiltrosPcp {
  estado?: EstadoPcp
  fecha_desde?: string
  fecha_hasta?: string
}

const PCP_LISTAS = ['pcp'] as const

export const pcpQueryKeys = {
  listas: () => PCP_LISTAS,
  lista: (filtros?: FiltrosPcp) => (filtros ? [...PCP_LISTAS, filtros] : PCP_LISTAS),
  detalle: (pcpId: string) => ['pcp', pcpId] as const,
  seleccion: (pcpId: string) => ['pcp', pcpId, 'seleccion'] as const,
  seleccionesAgrupables: (pcpId: string) => ['pcp', pcpId, 'selecciones-agrupables'] as const,
  renglones: (pcpId: string) => ['pcp', pcpId, 'renglones'] as const,
  renglon: (pcpId: string, renglonId: string) => ['pcp', pcpId, 'renglones', renglonId] as const,
  /** Lectura batched -- reemplaza el fan-out de N claves por-proveedor
   * (una por proveedor) que ComparacionProveedoresTable/RegistrarResultadoDialog
   * usaban antes. */
  resultadosRenglon: (pcpId: string, renglonId: string) =>
    ['pcp', pcpId, 'renglones', renglonId, 'resultados'] as const,
  agrupacion: (renglonId: string) => ['pcp', 'sugerencias', renglonId, 'agrupacion'] as const,
  preciosRecientes: (renglonId: string) =>
    ['pcp', 'sugerencias', renglonId, 'precios-recientes'] as const,
  proveedoresProducto: (productoId: string) =>
    ['pcp', 'catalogo', 'productos', productoId, 'proveedores'] as const,
  consulta: (consultaId: string) => ['pcp', 'consultas', consultaId] as const,
}
