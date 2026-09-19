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
}

export interface FilasExtraccionOut {
  extraction_id: string
  document_type: DocumentType
  row_count: number
  filas_leidas: number
  editable: boolean
  columnas: string[]
  filas: Record<string, string>[]
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

export interface ValidarExtraccionPayload {
  proceso_comercial_id?: string | null
  // undefined/null -> materializa desde el CSV en disco (comportamiento retrocompatible, D2)
  filas?: FilaLicitacionIn[] | FilaComparativaIn[] | null
}

export interface ResultadoValidarExtraccion {
  extraction_id: string
  document_type: DocumentType
  proceso_comercial_id: string
  filas_creadas: number
  comparativa_id: string | null
  reemplazo_version_anterior: boolean
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
