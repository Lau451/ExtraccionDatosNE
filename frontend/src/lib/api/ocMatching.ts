import { presupuestacionFetch } from './presupuestacion'

/** Espejo literal de `services/presupuestacion/oc_presupuesto/models.py::EstadoVinculo`
 * (design.md D4). Se DERIVA en el backend de `(presupuesto_item_id, vinculo_descartado)`,
 * no se persiste como columna propia. */
export type EstadoVinculo = 'pendiente' | 'confirmado' | 'sin_presupuesto'

/** Espejo literal de `oc_presupuesto/models.py::OrigenVinculo` (design.md D4). */
export type OrigenVinculo = 'precio_exacto' | 'manual'

/** Espejo literal de `oc_presupuesto/models.py::CandidatoPresupuesto` (design.md D2). */
export interface CandidatoPresupuesto {
  presupuesto_id: string
  proceso_comercial_id: string
  nombre_proceso: string
  // None cuando el presupuesto no vino del import legado (cargado a mano) o
  // cuando presupuesto_legacy_map no tiene fila para él (D2.1 / C1).
  numero_presupuesto: string | null
  estado: string
  generado_at: string
  cantidad_items: number
  // Puntaje del ranking (D2): cuántos renglones de ESTA OC coinciden exacto
  // en precio contra algún renglón de ESTE presupuesto.
  renglones_oc_con_coincidencia: number
  renglones_oc_totales: number
}

/** Espejo literal de `oc_presupuesto/models.py::PresupuestosCandidatosOut` (design.md D2/D13). */
export interface PresupuestosCandidatosOut {
  orden_compra_id: string
  cliente_id: string
  razon_social_cliente: string
  // Total de presupuestos del cliente, coincidan o no. Permite distinguir
  // "no tiene presupuestos" de "tiene 12 y ninguno coincide" (D2).
  presupuestos_del_cliente: number
  candidatos: CandidatoPresupuesto[] // top 5, puntaje > 0, ya ordenados
  presupuesto_sugerido_id: string | null // = candidatos[0] si hay; sugerido != elegido
  advertencias: string[]
}

/** Espejo literal de `oc_presupuesto/models.py::RenglonPresupuesto` (design.md C5).
 * Columna izquierda de la pantalla de matching: junta `presupuesto_items` +
 * `items_proceso`. */
export interface RenglonPresupuesto {
  presupuesto_item_id: string
  item_proceso_id: string
  numero_renglon: number
  descripcion: string
  cantidad_ofertada: number | null
  precio_unitario: number
  // COALESCE(presupuesto_items.producto_id, items_proceso.producto_id) -- lo
  // que se heredaría al confirmar. null es normal y no bloquea nada (D6).
  producto_id: string | null
  // Aviso N:1 (D5). Alcance: toda la droguería, no solo esta OC.
  renglones_oc_vinculados: number
  renglones_oc_vinculados_otras_oc: number
  cantidad_vinculada: number
}

/** Espejo literal de `oc_presupuesto/models.py::CandidatoVinculo` (design.md D7). */
export interface CandidatoVinculo {
  presupuesto_item_id: string
  // fuzz.WRatio 0-100 sobre normalizar_descripcion(...). null cuando hay un
  // solo candidato: no hay nada que desempatar (D7). NUNCA filtra: ordena.
  similitud: number | null
}

/** Espejo literal de `oc_presupuesto/models.py::RenglonOrdenCompra` (design.md D4).
 * Columna derecha de la pantalla de matching. `estado` se DERIVA en el backend,
 * no está en la base. */
export interface RenglonOrdenCompra {
  oc_item_id: string
  numero_renglon: number
  descripcion: string
  cantidad: number
  precio_unitario: number
  producto_id: string | null
  estado: EstadoVinculo
  presupuesto_item_id: string | null
  vinculo_origen: OrigenVinculo | null
  // Solo cuando estado === 'pendiente'. Vacío = ningún renglón del presupuesto
  // comparte el precio; el renglón queda pendiente y NO bloquea al resto.
  candidatos: CandidatoVinculo[]
}

/** Espejo literal de `oc_presupuesto/models.py::MatchingOut` (design.md D13). */
export interface MatchingOut {
  orden_compra_id: string
  numero_oc: string
  cliente_id: string
  // El presupuesto efectivamente usado, resuelto por el servidor cuando el
  // query param no vino (D8). null solo si el cliente no tiene ninguno.
  presupuesto_id: string | null
  renglones_presupuesto: RenglonPresupuesto[]
  renglones_oc: RenglonOrdenCompra[]
  advertencias: string[]
}

/** GET /ordenes-compra/{id}/presupuestos-candidatos (design.md D2, D13). */
export function obtenerPresupuestosCandidatos(
  ordenCompraId: string,
): Promise<PresupuestosCandidatosOut> {
  return presupuestacionFetch<PresupuestosCandidatosOut>(
    `/ordenes-compra/${ordenCompraId}/presupuestos-candidatos`,
  )
}

/** GET /ordenes-compra/{id}/matching?presupuesto_id= -- `presupuestoId` es
 * opcional (D13): si falta, el servidor lo resuelve (D8) y lo devuelve en la
 * respuesta. */
export function obtenerMatching(
  ordenCompraId: string,
  presupuestoId?: string,
): Promise<MatchingOut> {
  const query = new URLSearchParams()
  if (presupuestoId !== undefined) query.set('presupuesto_id', presupuestoId)
  const qs = query.toString()
  return presupuestacionFetch<MatchingOut>(
    `/ordenes-compra/${ordenCompraId}/matching${qs ? `?${qs}` : ''}`,
  )
}

/** POST /ordenes-compra/{id}/items/{ocItemId}/vinculo (design.md D13). Confirmar
 * sobre un renglón ya confirmado reemplaza el vínculo, sin error (idempotencia). */
export function confirmarVinculo(
  ordenCompraId: string,
  ocItemId: string,
  presupuestoItemId: string,
): Promise<MatchingOut> {
  return presupuestacionFetch<MatchingOut>(
    `/ordenes-compra/${ordenCompraId}/items/${ocItemId}/vinculo`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ presupuesto_item_id: presupuestoItemId }),
    },
  )
}

/** DELETE /ordenes-compra/{id}/items/{ocItemId}/vinculo (design.md D9). Vuelve
 * el renglón a `pendiente`, sirva para deshacer un `confirmado` o un
 * `sin_presupuesto`. */
export function deshacerVinculo(ordenCompraId: string, ocItemId: string): Promise<MatchingOut> {
  return presupuestacionFetch<MatchingOut>(
    `/ordenes-compra/${ordenCompraId}/items/${ocItemId}/vinculo`,
    { method: 'DELETE' },
  )
}

/** POST /ordenes-compra/{id}/items/{ocItemId}/descartar (design.md D4). Marca
 * `vinculo_descartado=true`: el humano afirma que este renglón no está en el
 * presupuesto elegido -- distinto de `pendiente` ("todavía no lo miré"). */
export function descartarRenglon(ordenCompraId: string, ocItemId: string): Promise<MatchingOut> {
  return presupuestacionFetch<MatchingOut>(
    `/ordenes-compra/${ordenCompraId}/items/${ocItemId}/descartar`,
    { method: 'POST' },
  )
}
