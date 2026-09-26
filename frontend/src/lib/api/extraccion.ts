import { extraccionFetch } from './client'

export type TipoDocumento = 'licitaciones' | 'comparativas' | 'ordenes'

export interface Cliente {
  id: string
  nombre: string
}

// Espejo de `extraction_results.status` (migración 0028, carga-asincrona T1).
export type EstadoExtraccion = 'processing' | 'completed' | 'failed' | 'partial'

export interface DocumentoReciente {
  id: string
  source_filename: string
  document_type: 'licitacion' | 'comparativa' | 'orden_compra'
  row_count: number
  status: EstadoExtraccion
  // Mensaje en español para el usuario cuando status='failed' (mapeo de
  // excepciones existente en services/extraccion/main.py, ahora escrito acá
  // en vez de devuelto sincrónicamente -- carga-asincrona T1/T2).
  error_msg: string | null
  created_at: string
  proceso_comercial: { id: string; nombre: string } | null
}

export interface ProcesarPayload {
  archivo: File
  tipo: TipoDocumento
  licitacionId?: string
  clienteId?: string
  // D13 § Agrupar al subir -- UUID v4 generado por el frontend, compartido
  // por los N archivos de una misma OC repartida en varios documentos.
  grupoId?: string
}

export interface ProcesarResultado {
  ok: boolean
  tipo: string
  error?: string
  // 202 (carga-asincrona T1): id de la fila 'processing' recién creada, para
  // que el frontend pueda referenciarla (p.ej. el link a "Ver extracción
  // existente" en un 409 reusa el mismo campo del body de error).
  extraction_id?: string | null
}

export function listarClientes(): Promise<Cliente[]> {
  return extraccionFetch<Cliente[]>('/api/clientes')
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
  grupoId,
}: ProcesarPayload): Promise<ProcesarResultado> {
  const formData = new FormData()
  formData.append('archivo', archivo)
  formData.append('tipo', tipo)
  if (licitacionId) formData.append('licitacion_id', licitacionId)
  if (clienteId) formData.append('cliente_id', clienteId)
  if (grupoId) formData.append('grupo_id', grupoId)

  return extraccionFetch('/procesar', {
    method: 'POST',
    body: formData,
  })
}
