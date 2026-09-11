import { supabase } from '@/lib/supabase'
import { ApiError, presupuestacionFetch } from './presupuestacion'

const PRESUPUESTACION_BASE_URL = import.meta.env.VITE_PRESUPUESTACION_API_URL ?? 'http://localhost:8001'

export type EstadoPcp = 'nueva' | 'en_gestion' | 'esperando_respuesta' | 'cerrada'
export type OrigenPcp = 'manual' | 'regla' | 'import_legado'
export type OrigenRenglon = 'manual' | 'regla' | 'import_legado'

export interface Pcp {
  id: string
  drogueria_id: string
  presupuesto_id: string
  proceso_comercial_id: string
  estado: EstadoPcp
  fecha_entrega_solicitada: string | null
  solicitante_id: string | null
  sector_id: string | null
  origen: OrigenPcp | null
  regla_pcp_id: string | null
  notas: string | null
  cerrada_at: string | null
  cerrada_por: string | null
}

export interface PresupuestoElegible {
  id: string
  nombre: string
}

export interface PcpCreatePayload {
  presupuesto_id: string
  fecha_entrega_solicitada?: string
  solicitante_id?: string
  sector_id?: string
  origen?: OrigenPcp
  notas?: string
}

export interface FiltrosPcp {
  estado?: EstadoPcp
  fecha_desde?: string
  fecha_hasta?: string
}

export interface ProductoProveedor {
  id: string
  drogueria_id: string
  producto_id: string
  proveedor_id: string
  codigo_proveedor: string | null
  preferido: boolean
  activo: boolean
  notas: string | null
}

export interface ProductoProveedorCreatePayload {
  proveedor_id: string
  codigo_proveedor?: string
  preferido?: boolean
  notas?: string
}

export interface PcpRenglon {
  id: string
  drogueria_id: string
  pcp_id: string
  item_proceso_id: string
  producto_id: string | null
  cantidad: number | null
  precio_referencia: number | null
  origen: OrigenRenglon
  regla_pcp_id: string | null
  estado: 'pendiente' | 'resuelto' | 'descartado'
}

export interface PcpRenglonCreatePayload {
  item_proceso_id: string
  origen?: OrigenRenglon
  regla_pcp_id?: string
}

export interface ProductoRenglon {
  id: string
  drogueria_id: string
  codigo_interno: string
  nombre: string
  categoria_id: string | null
  clasificacion: string | null
  droga: string | null
  presentacion: string | null
  forma_farmaceutica: string | null
  laboratorio: string | null
  codigo_anmat: string | null
  activo: boolean
}

export interface RenglonDetalle {
  renglon: PcpRenglon
  producto: ProductoRenglon | null
  proveedores_catalogados: ProductoProveedor[]
}

export type ResultadoNegociacionTipo = 'precio_obtenido' | 'no_cotiza'

export interface ResultadoNegociacion {
  id: string
  drogueria_id: string
  pcp_renglon_id: string
  proveedor_id: string
  resultado: string
  seleccionado: boolean
  precio_proveedor_id: string | null
  precio_unitario: number | null
  cantidad_minima: number | null
  cantidad_maxima: number | null
  mantenimiento_hasta: string | null
  condicion_pago_id: string | null
  forma_pago_id: string | null
  motivo: string | null
  registrado_por: string | null
}

export interface RegistrarResultadoPayload {
  resultado: ResultadoNegociacionTipo
  precio_unitario?: number
  cantidad_minima?: number
  cantidad_maxima?: number
  mantenimiento_hasta?: string
  condicion_pago_id?: string
  forma_pago_id?: string
  notas?: string
  motivo?: string
}

function pathListado(filtros?: FiltrosPcp): string {
  const parametros = new URLSearchParams()
  if (filtros?.estado) parametros.set('estado', filtros.estado)
  if (filtros?.fecha_desde) parametros.set('fecha_desde', filtros.fecha_desde)
  if (filtros?.fecha_hasta) parametros.set('fecha_hasta', filtros.fecha_hasta)
  const query = parametros.toString()
  return query ? `/pcp?${query}` : '/pcp'
}

export function listarPcp(filtros?: FiltrosPcp): Promise<Pcp[]> {
  return presupuestacionFetch<Pcp[]>(pathListado(filtros))
}

export function listarPresupuestosElegibles(): Promise<PresupuestoElegible[]> {
  return presupuestacionFetch<PresupuestoElegible[]>('/presupuestos?elegibles_para_pcp=true')
}

export function crearPcp(payload: PcpCreatePayload): Promise<Pcp> {
  return presupuestacionFetch<Pcp>('/pcp', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export function obtenerPcp(pcpId: string): Promise<Pcp> {
  return presupuestacionFetch<Pcp>(`/pcp/${pcpId}`)
}

export function cambiarEstadoPcp(pcpId: string, estado: EstadoPcp): Promise<Pcp> {
  return presupuestacionFetch<Pcp>(`/pcp/${pcpId}/estado`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ estado }),
  })
}

export function cerrarPcp(pcpId: string): Promise<Pcp> {
  return presupuestacionFetch<Pcp>(`/pcp/${pcpId}/cerrar`, { method: 'POST' })
}

export function listarProveedoresProducto(productoId: string): Promise<ProductoProveedor[]> {
  return presupuestacionFetch<ProductoProveedor[]>(`/pcp/catalogo/productos/${productoId}/proveedores`)
}

export function agregarProveedorProducto(
  productoId: string,
  payload: ProductoProveedorCreatePayload,
): Promise<ProductoProveedor> {
  return presupuestacionFetch<ProductoProveedor>(`/pcp/catalogo/productos/${productoId}/proveedores`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export function listarRenglones(pcpId: string): Promise<PcpRenglon[]> {
  return presupuestacionFetch<PcpRenglon[]>(`/pcp/${pcpId}/renglones`)
}

function normalizarErrorValidacion(error: unknown): never {
  if (error instanceof ApiError && error.status === 422 && Array.isArray(error.message)) {
    const mensajes = error.message
      .filter((detalle): detalle is { loc?: unknown, msg?: unknown } => typeof detalle === 'object' && detalle !== null)
      .map(({ loc, msg }) => {
        const campo = Array.isArray(loc)
          ? loc.filter((parte) => parte !== 'body').join('.')
          : ''
        return campo && typeof msg === 'string' ? `${campo}: ${msg}` : msg
      })
      .filter((mensaje): mensaje is string => typeof mensaje === 'string')

    if (mensajes.length > 0) throw new ApiError(mensajes.join('; '), error.status)
  }

  throw error
}

export async function crearRenglon(
  pcpId: string,
  payload: PcpRenglonCreatePayload,
): Promise<PcpRenglon> {
  const body: PcpRenglonCreatePayload = { item_proceso_id: payload.item_proceso_id }
  if (payload.origen !== undefined) body.origen = payload.origen
  if (payload.regla_pcp_id !== undefined) body.regla_pcp_id = payload.regla_pcp_id

  try {
    return await presupuestacionFetch<PcpRenglon>(`/pcp/${pcpId}/renglones`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
  } catch (error) {
    return normalizarErrorValidacion(error)
  }
}

export function obtenerDetalleRenglon(pcpId: string, renglonId: string): Promise<RenglonDetalle> {
  return presupuestacionFetch<RenglonDetalle>(`/pcp/${pcpId}/renglones/${renglonId}`)
}

export async function seleccionarProveedores(
  pcpId: string,
  renglonId: string,
  proveedorIds: string[],
): Promise<ResultadoNegociacion[]> {
  try {
    return await presupuestacionFetch<ResultadoNegociacion[]>(`/pcp/${pcpId}/renglones/${renglonId}/proveedores`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ proveedor_ids: proveedorIds }),
    })
  } catch (error) {
    return normalizarErrorValidacion(error)
  }
}

export function listarRenglonesSeleccionados(pcpId: string): Promise<string[]> {
  return presupuestacionFetch<string[]>(`/pcp/${pcpId}/seleccion`)
}

export interface SeleccionAgrupable {
  pcp_renglon_id: string
  proveedor_id: string
}

/** Distinto de `listarRenglonesSeleccionados` (que colapsa a un id de
 * renglón para el badge "Negociado"): devuelve el par renglón×proveedor
 * completo para TODO el PCP, sin colapsar, así `PcpDetalle` puede armar el
 * `selecciones` de `agruparConsultas` a nivel de PCP en vez de un único
 * renglón (Corrective Rerun -- Consultas grouping scope). */
export function listarSeleccionesAgrupables(pcpId: string): Promise<SeleccionAgrupable[]> {
  return presupuestacionFetch<SeleccionAgrupable[]>(`/pcp/${pcpId}/selecciones-agrupables`)
}

function pathResultado(pcpId: string, renglonId: string, proveedorId: string): string {
  return `/pcp/${pcpId}/renglones/${renglonId}/proveedores/${proveedorId}/resultado`
}

/** Nunca atrapa un 404: el llamador decide qué significa "sin resultado
 * aún" (design.md D4, `ComparacionProveedoresTable`'s `useQueries` fan-out
 * trata `ApiError.status === 404` como vacío, no como error). */
export function obtenerResultado(
  pcpId: string,
  renglonId: string,
  proveedorId: string,
): Promise<ResultadoNegociacion> {
  return presupuestacionFetch<ResultadoNegociacion>(pathResultado(pcpId, renglonId, proveedorId))
}

export async function registrarResultado(
  pcpId: string,
  renglonId: string,
  proveedorId: string,
  payload: RegistrarResultadoPayload,
): Promise<ResultadoNegociacion> {
  const body: RegistrarResultadoPayload = { resultado: payload.resultado }
  if (payload.precio_unitario !== undefined) body.precio_unitario = payload.precio_unitario
  if (payload.cantidad_minima !== undefined) body.cantidad_minima = payload.cantidad_minima
  if (payload.cantidad_maxima !== undefined) body.cantidad_maxima = payload.cantidad_maxima
  if (payload.mantenimiento_hasta !== undefined) body.mantenimiento_hasta = payload.mantenimiento_hasta
  if (payload.condicion_pago_id !== undefined) body.condicion_pago_id = payload.condicion_pago_id
  if (payload.forma_pago_id !== undefined) body.forma_pago_id = payload.forma_pago_id
  if (payload.notas !== undefined) body.notas = payload.notas
  if (payload.motivo !== undefined) body.motivo = payload.motivo

  try {
    return await presupuestacionFetch<ResultadoNegociacion>(pathResultado(pcpId, renglonId, proveedorId), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
  } catch (error) {
    return normalizarErrorValidacion(error)
  }
}

export function actualizarSeleccion(
  pcpId: string,
  renglonId: string,
  proveedorId: string,
  seleccionado: boolean,
): Promise<ResultadoNegociacion> {
  return presupuestacionFetch<ResultadoNegociacion>(
    `/pcp/${pcpId}/renglones/${renglonId}/proveedores/${proveedorId}/seleccion`,
    {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ seleccionado }),
    },
  )
}

export type EstadoConsulta = 'borrador' | 'enviada' | 'respondida' | 'cancelada'

export interface Consulta {
  id: string
  drogueria_id: string
  proveedor_id: string
  contacto_id: string | null
  estado: EstadoConsulta
  canal: string | null
  fecha_envio: string | null
  fecha_respuesta_esperada: string | null
  documento_path: string | null
}

export interface SeleccionParaAgrupar {
  pcp_renglon_id: string
  proveedor_id: string
  cantidad_consultada?: number
}

export interface AgruparConsultaPayload {
  selecciones: SeleccionParaAgrupar[]
  contacto_id?: string
  fecha_respuesta_esperada?: string
  canal?: string
}

/** El backend agrupa las selecciones por `proveedor_id` internamente y crea
 * una consulta por cada proveedor distinto presente (D6/`consultas/service.py`
 * `agrupar_renglones`), así que una sola llamada puede devolver varias. */
export function agruparConsultas(payload: AgruparConsultaPayload): Promise<Consulta[]> {
  const body: AgruparConsultaPayload = { selecciones: payload.selecciones }
  if (payload.contacto_id !== undefined) body.contacto_id = payload.contacto_id
  if (payload.fecha_respuesta_esperada !== undefined) body.fecha_respuesta_esperada = payload.fecha_respuesta_esperada
  if (payload.canal !== undefined) body.canal = payload.canal

  return presupuestacionFetch<Consulta[]>('/pcp/consultas', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

export function obtenerConsulta(consultaId: string): Promise<Consulta> {
  return presupuestacionFetch<Consulta>(`/pcp/consultas/${consultaId}`)
}

export function enviarConsulta(consultaId: string): Promise<Consulta> {
  return presupuestacionFetch<Consulta>(`/pcp/consultas/${consultaId}/enviar`, { method: 'POST' })
}

export interface SugerenciaAgrupacion {
  producto_id: string
  cantidad_agregada: number
  pcp_ids: string[]
  renglon_ids: string[]
}

export interface SugerenciaPrecioReciente {
  precio_proveedor_id: string
  proveedor: string
  mantenimiento_hasta: string
  dias_restantes: number
  precio_unitario: number
  cantidad_minima: number | null
  cantidad_maxima: number | null
}

export function obtenerSugerenciaAgrupacion(renglonId: string): Promise<SugerenciaAgrupacion | null> {
  return presupuestacionFetch<SugerenciaAgrupacion | null>(`/pcp/sugerencias/renglones/${renglonId}/agrupacion`)
}

export function listarSugerenciasPreciosRecientes(renglonId: string): Promise<SugerenciaPrecioReciente[]> {
  return presupuestacionFetch<SugerenciaPrecioReciente[]>(`/pcp/sugerencias/renglones/${renglonId}/precios-recientes`)
}

export type ProcesoComercialLegacy = '1' | '2'

/** Una fila del export legado (13 columnas, D8/`services/pcp/imports/models.py`
 * `FilaImportPcpLegacy`). Solo los 6 campos de renglón/cliente/PCP son
 * obligatorios; el resto de la cabecera es opcional y se repite por fila
 * que comparte `numero_pcp` del lado del backend. */
export interface FilaImportPcpLegacy {
  codigo_cliente: string
  razon_social_cliente: string
  numero_pcp: string
  numero_presupuesto?: string
  proceso_comercial?: ProcesoComercialLegacy
  importe_total?: number
  fecha_generacion?: string
  fecha_respuesta_esperada?: string
  renglon: number
  codigo_producto?: string
  descripcion_producto: string
  cantidad_producto: number
  precio_producto?: number
}

export interface ImportPcpLegacyResultado {
  codigo_legacy: string
  pcp_id: string
  accion: 'creado' | 'actualizado'
  renglones_procesados: number
}

export function importarPcpLegacy(filas: FilaImportPcpLegacy[]): Promise<ImportPcpLegacyResultado[]> {
  return presupuestacionFetch<ImportPcpLegacyResultado[]>('/pcp/imports/legacy', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ filas }),
  })
}

/** No puede reusar `presupuestacionFetch`: esa función siempre llama
 * `response.json()`, lo que rompería contra un cuerpo PDF binario
 * (design.md, `lib/api/pcp.ts` Contract). Duplica el fetch con header de
 * autorización y devuelve el blob directamente. */
export async function descargarPdfConsulta(consultaId: string): Promise<Blob> {
  const {
    data: { session },
  } = await supabase.auth.getSession()

  const response = await fetch(`${PRESUPUESTACION_BASE_URL}/pcp/consultas/${consultaId}/pdf`, {
    headers: {
      ...(session ? { Authorization: `Bearer ${session.access_token}` } : {}),
    },
  })

  if (!response.ok) {
    throw new ApiError(`Error ${response.status} al descargar el PDF de la consulta`, response.status)
  }

  return response.blob()
}
