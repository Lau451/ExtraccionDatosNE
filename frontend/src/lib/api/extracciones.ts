import { presupuestacionFetch } from './presupuestacion'

export type DocumentType = 'comparativa' | 'licitacion' | 'cotizacion' | 'orden_compra'

export interface ExtraccionResumen {
  id: string
  document_type: DocumentType
  source_filename: string
  row_count: number
  status: string
  validado: boolean
  proceso_comercial_id: string | null
  proceso_comercial_nombre: string | null
  created_at: string
  // D13/D13.1 (gap post-Phase 7, task 7.13) -- persistido, para que el
  // indicador de agrupación del listado sobreviva a un refetch/recarga sin
  // depender solo del estado en memoria del front (`gruposLocales`).
  grupo_id?: string | null
  // D11 (Phase 4 backend / Phase 6 espejo frontend, `orden-compra-matching-
  // presupuesto`) -- re-entrada a la pantalla de matching desde el listado.
  // El backend (`extraccion/models.py::ExtraccionResumen`) ya lo devuelve
  // desde Phase 4; este espejo TS quedó desactualizado hasta esta tarea
  // (6.2). Distinto de `ResultadoValidarExtraccion.orden_compra_id` (ese es
  // el de la respuesta de validar UNA extracción; este es el del LISTADO).
  // `null` para licitación/comparativa y para los miembros no-ancla de un
  // grupo multi-archivo (D13 del cambio padre).
  orden_compra_id: string | null
}

/** Espejo literal de `MiembroGrupo` (design.md § D13, Interfaces). */
export interface MiembroGrupo {
  extraction_id: string
  source_filename: string
}

export interface FilasExtraccionOut {
  extraction_id: string
  document_type: DocumentType
  row_count: number
  filas_leidas: number
  editable: boolean
  columnas: string[]
  filas: Record<string, string>[]
  // D13/D13.1 -- solo relevante para document_type='orden_compra'; grupo_id
  // null y miembros=[] para el resto de los tipos (retrocompatible). Sin
  // `modo_fusion_sugerido`: D13.1 elimina ese concepto por completo.
  grupo_id?: string | null
  miembros?: MiembroGrupo[]
  advertencias_cabecera?: string[]
  // NUEVO (T2, extraccion-duplicado-link) -- ¿ya fue validada esta extracción?
  // Si es así, la pantalla de validación muestra un aviso en vez de ofrecer una
  // segunda confirmación (el backend la rechaza igual). Opcional por
  // retrocompat con mocks/tests existentes que construyen este objeto a mano
  // sin esta clave (mismo criterio que grupo_id/miembros arriba).
  validado?: boolean
  // Solo no-null cuando validado=true Y hay una OC ya confirmada para esta
  // extracción -- resuelto por CUALQUIER miembro del grupo cuando corresponde
  // (mismo backend lookup que ExtraccionResumen.orden_compra_id, D11/D13.1).
  // Licitación/comparativa validadas: siempre null (nunca tienen OC).
  orden_compra_id?: string | null
}

/** Mismos nombres de columna que `services/presupuestacion/extraccion/models.py`
 * (`FilaLicitacionIn`/`FilaComparativaIn`) -- el override tiene exactamente la
 * misma forma que las filas del CSV (design.md §1). */
export interface FilaLicitacionIn {
  item: string
  descripcion: string
  cantidad: string
}

export interface FilaComparativaIn {
  renglon: string
  proveedor: string
  marca?: string | null
  precio: string
}

/** Espejo literal de `FilaOrdenCompraIn` (design.md § Interfaces).
 * `numero_renglon_documento` es SOLO referencia (C10/D13.1): `oc_items.numero_renglon`
 * lo asigna el backend por posición al confirmar, nunca este valor. */
export interface FilaOrdenCompraIn {
  numero_renglon_documento: string | null
  descripcion: string
  cantidad: string
  precio_unitario: string
  producto_id: string | null
}

/** Espejo literal de `EntregaPlanIn` (services/presupuestacion/extraccion/models.py).
 * Ajuste post-shipping (2026-09-21): ya NO viaja en `OrdenCompraOverride` -- la
 * división en entregas se sacó del flujo de confirmación de OC y se mueve a una
 * fase futura de matching contra presupuesto, todavía sin diseñar. Se conserva
 * esta interfaz sin usar (igual que su espejo Pydantic) porque esa fase futura
 * la va a reusar tal cual -- ver también `EntregasEditor.tsx`, que no la
 * importa (define su propio tipo local `EntregaPlanEditable`). */
export interface EntregaPlanIn {
  numero_entrega: number
  plazo_dias: number | null
  cantidades_por_posicion: Record<string, string> | null
}

/** Espejo literal de `OrdenCompraOverride` (design.md § Interfaces). Sin
 * `modo_fusion`: D13.1 elimina ese concepto por completo -- las filas del
 * grupo se concatenan siempre y el usuario reconcilia editando. Sin
 * `entregas` (ajuste post-shipping 2026-09-21, ver `EntregaPlanIn` arriba). */
export interface OrdenCompraOverride {
  numero_oc: string
  cliente_id: string
  razon_social_extraida: string | null
  fecha_emision: string | null
  direccion_entrega: string | null
  notas: string | null
  filas: FilaOrdenCompraIn[]
}

export interface ValidarExtraccionPayload {
  proceso_comercial_id?: string | null
  // undefined/null -> materializa desde el CSV en disco (comportamiento retrocompatible, D2)
  filas?: FilaLicitacionIn[] | FilaComparativaIn[] | null
  orden_compra?: OrdenCompraOverride | null
}

export interface ResultadoValidarExtraccion {
  extraction_id: string
  document_type: DocumentType
  // CAMBIO (D7): era `string` -- NULL en la ruta orden_compra
  // (proceso_comercial_id no aplica, D4).
  proceso_comercial_id: string | null
  filas_creadas: number
  comparativa_id: string | null
  reemplazo_version_anterior: boolean
  // Sincronización con services/presupuestacion/extraccion/models.py:94-107
  // (`ResultadoValidarExtraccion`). Los cuatro campos siguientes ya existen
  // en el backend desde 3b37fca3 (cambio padre `orden-compra`, C7 de
  // design.md de `orden-compra-matching-presupuesto`); este espejo quedó
  // desactualizado hasta ahora (D10, Phase 6). `orden_compra_id` es `null`
  // para licitación/comparativa; no nulo únicamente en la ruta orden_compra.
  orden_compra_id: string | null
  entregas_creadas: number
  renglones_sin_producto: number
  extracciones_validadas: number
}

/** Espejo literal de `services/presupuestacion/extraccion/models.py::OrigenCandidato`
 * (design.md § D3). */
export type OrigenCandidato = 'alias' | 'cuit' | 'cuit_compartido' | 'ninguno'

/** Espejo literal de `CandidatoCliente` (design.md § D3 / Interfaces). */
export interface CandidatoCliente {
  cliente_id: string
  razon_social: string
  cuit: string | null
  codigo_interno: string | null
  tipo: string
  activo: boolean
  cuit_no_exclusivo: boolean
}

/** Espejo literal de `CandidatoClienteOut` (design.md § D3 / Interfaces):
 * 1 elemento -> sugerencia única (alias, o CUIT exclusivo); N elementos ->
 * candidatos de un CUIT compartido (C6); 0 elementos -> el usuario busca a
 * mano (D3.2). */
export interface CandidatoClienteOut {
  origen: OrigenCandidato
  candidatos: CandidatoCliente[]
  cuit_extraido: string | null
  razon_social_extraida: string | null
  advertencias: string[]
}

export function obtenerClienteCandidato(extractionId: string): Promise<CandidatoClienteOut> {
  return presupuestacionFetch<CandidatoClienteOut>(`/extracciones/${extractionId}/cliente-candidato`)
}

export interface ListarExtraccionesParams {
  validado?: boolean
  limit?: number
  offset?: number
}

export function listarExtracciones(
  params: ListarExtraccionesParams = {},
): Promise<ExtraccionResumen[]> {
  const query = new URLSearchParams()
  if (params.validado !== undefined) query.set('validado', String(params.validado))
  if (params.limit !== undefined) query.set('limit', String(params.limit))
  if (params.offset !== undefined) query.set('offset', String(params.offset))
  const qs = query.toString()
  return presupuestacionFetch<ExtraccionResumen[]>(`/extracciones${qs ? `?${qs}` : ''}`)
}

export function obtenerFilasExtraccion(extractionId: string): Promise<FilasExtraccionOut> {
  return presupuestacionFetch<FilasExtraccionOut>(`/extracciones/${extractionId}/filas`)
}

export function validarExtraccion(
  extractionId: string,
  payload: ValidarExtraccionPayload,
): Promise<ResultadoValidarExtraccion> {
  return presupuestacionFetch<ResultadoValidarExtraccion>(`/extracciones/${extractionId}/validar`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

/** D13 § Agrupar después -- POST /extracciones/agrupar (router.py real,
 * Phase 4). Mismo body shape para agrupar y desagrupar
 * (AgruparExtraccionesRequest), sin modelo separado para la inversa. */
export function agruparExtracciones(extractionIds: string[]): Promise<{ grupo_id: string }> {
  return presupuestacionFetch<{ grupo_id: string }>('/extracciones/agrupar', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ extraction_ids: extractionIds }),
  })
}

/** POST /extracciones/desagrupar -- responde 204 sin cuerpo. */
export function desagruparExtracciones(extractionIds: string[]): Promise<void> {
  return presupuestacionFetch<void>('/extracciones/desagrupar', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ extraction_ids: extractionIds }),
  })
}
