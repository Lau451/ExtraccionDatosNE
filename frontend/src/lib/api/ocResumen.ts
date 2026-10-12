import type { EntregaPlanOut, ExportacionOut } from './ocEntregas'
import { presupuestacionFetch } from './presupuestacion'

export type EstadoVinculo = 'pendiente' | 'confirmado' | 'sin_presupuesto'

/** Espejo literal de `oc_resumen/models.py::ClienteResumen`. */
export interface ClienteResumen {
  razon_social: string
  cuit: string | null
}

/** Espejo literal de `oc_resumen/models.py::ProductoResumen`. */
export interface ProductoResumen {
  codigo_interno: string | null
  nombre: string
}

/** Espejo literal de `oc_resumen/models.py::RenglonResumen` (ya parseado). */
export interface RenglonResumen {
  oc_item_id: string
  numero_renglon: number
  numero_renglon_documento: string | null
  descripcion: string
  producto: ProductoResumen | null
  cantidad: number
  precio_unitario: number | null
  monto_total: number | null
  estado_vinculo: EstadoVinculo
}

/** Espejo literal de `oc_resumen/models.py::OcResumenOut` (ya parseado). */
export interface OcResumenOut {
  orden_compra_id: string
  numero_oc: string
  cliente: ClienteResumen | null
  fecha_emision: string | null
  fecha_entrega_estimada: string | null
  direccion_entrega: string | null
  notas: string | null
  estado: string
  version_numero: number | null
  // null en algunas OC (p.ej. TEST 986): la pantalla suma los renglones.
  monto_total: number | null
  exportacion: ExportacionOut | null
  renglones: RenglonResumen[]
  entregas: EntregaPlanOut[]
}

// Pydantic v2 serializa `Decimal` como STRING (ver `ocEntregas.ts`): estos
// `*Crudo` son la forma real de la respuesta y se parsean en el borde.

interface RenglonResumenCrudo extends Omit<RenglonResumen, 'cantidad' | 'precio_unitario' | 'monto_total'> {
  cantidad: string
  precio_unitario: string | null
  monto_total: string | null
}

interface EntregaPlanOutCrudo extends Omit<EntregaPlanOut, 'items'> {
  items: { oc_item_id: string; cantidad_planificada: string }[]
}

interface OcResumenOutCrudo extends Omit<OcResumenOut, 'monto_total' | 'renglones' | 'entregas'> {
  monto_total: string | null
  renglones: RenglonResumenCrudo[]
  entregas: EntregaPlanOutCrudo[]
}

function numeroONull(valor: string | null): number | null {
  return valor === null ? null : Number(valor)
}

/** GET /ordenes-compra/{id}/resumen: vista de solo lectura de la OC. */
export async function obtenerOcResumen(ordenCompraId: string): Promise<OcResumenOut> {
  const cruda = await presupuestacionFetch<OcResumenOutCrudo>(`/ordenes-compra/${ordenCompraId}/resumen`)
  return {
    ...cruda,
    monto_total: numeroONull(cruda.monto_total),
    renglones: cruda.renglones.map((renglon) => ({
      ...renglon,
      cantidad: Number(renglon.cantidad),
      precio_unitario: numeroONull(renglon.precio_unitario),
      monto_total: numeroONull(renglon.monto_total),
    })),
    entregas: cruda.entregas.map((entrega) => ({
      ...entrega,
      items: entrega.items.map((item) => ({
        oc_item_id: item.oc_item_id,
        cantidad_planificada: Number(item.cantidad_planificada),
      })),
    })),
  }
}
