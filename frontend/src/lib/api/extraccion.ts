import { extraccionFetch } from './client'

export type TipoDocumento = 'licitaciones' | 'comparativas' | 'ordenes'

export interface Cliente {
  id: string
  nombre: string
}

export interface DocumentoReciente {
  id: string
  source_filename: string
  document_type: 'licitacion' | 'comparativa'
  client_id: string
  row_count: number
  status: string
  created_at: string
  licitacion: { id: string; nombre: string } | null
}

export interface ProcesarPayload {
  archivo: File
  tipo: TipoDocumento
  licitacionId?: string
  clienteId?: string
}

export interface ProcesarResultado {
  ok: boolean
  tipo: string
  error?: string
}

export type TipoLicitacion = 'descartables' | 'medicamentos' | 'soluciones' | 'panales' | 'formulas'

export interface LicitacionActiva {
  id: string
  nombre: string
  tipo: TipoLicitacion
}

export interface LicitacionCreatePayload {
  nombre: string
  tipo: TipoLicitacion
  apertura: string
}

export function listarClientes(): Promise<Cliente[]> {
  return extraccionFetch<Cliente[]>('/api/clientes')
}

export function listarLicitacionesActivas(): Promise<LicitacionActiva[]> {
  return extraccionFetch<LicitacionActiva[]>('/api/licitaciones/activas')
}

export function crearLicitacion(payload: LicitacionCreatePayload): Promise<LicitacionActiva> {
  return extraccionFetch<LicitacionActiva>('/api/licitaciones', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export function listarDocumentosRecientes(tipo = ''): Promise<{ documentos: DocumentoReciente[] }> {
  const query = tipo ? `?tipo=${encodeURIComponent(tipo)}` : ''
  return extraccionFetch(`/api/documentos${query}`)
}

export function procesarDocumento({
  archivo,
  tipo,
  licitacionId,
  clienteId,
}: ProcesarPayload): Promise<ProcesarResultado> {
  const formData = new FormData()
  formData.append('archivo', archivo)
  formData.append('tipo', tipo)
  if (licitacionId) formData.append('licitacion_id', licitacionId)
  if (clienteId) formData.append('cliente_id', clienteId)

  return extraccionFetch('/procesar', {
    method: 'POST',
    body: formData,
  })
}
