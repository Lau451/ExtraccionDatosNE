import { presupuestacionFetch } from './presupuestacion'

export type TipoCliente = 'hospital' | 'obra_social' | 'municipio' | 'provincia' | 'nacional' | 'otro'
export type TipoProveedor = 'laboratorio' | 'drogueria' | 'distribuidor' | 'cooperativa' | 'otro'
export type UsoDireccion = 'facturacion' | 'entrega' | 'documentacion' | 'otra'

export interface Tercero {
  id: string
  drogueria_id: string
  codigo_interno: string | null
  razon_social: string
  nombre_fantasia: string | null
  cuit: string | null
  email: string | null
  telefono: string | null
  sitio_web: string | null
  notas: string | null
  activo: boolean
  /** Solo viene poblado en el listado (`GET /terceros`) — el detalle
   * (`GET /terceros/{id}`) no lo incluye, ver prompt de la tarea. */
  tiene_rol_cliente?: boolean
  tiene_rol_proveedor?: boolean
}

export interface TerceroCreatePayload {
  codigo_interno?: string
  razon_social: string
  nombre_fantasia?: string
  cuit?: string
  email?: string
  telefono?: string
  sitio_web?: string
  notas?: string
}

export interface TerceroUpdatePayload {
  codigo_interno?: string
  razon_social?: string
  nombre_fantasia?: string
  cuit?: string
  email?: string
  telefono?: string
  sitio_web?: string
  notas?: string
  activo?: boolean
}

export interface ClienteRol {
  id: string
  drogueria_id: string
  tipo: TipoCliente
  condicion_pago_id: string | null
  forma_pago_id: string | null
  activo: boolean
}

export interface ClienteRolCreatePayload {
  tipo?: TipoCliente
  condicion_pago_id?: string
  forma_pago_id?: string
}

export interface ClienteRolUpdatePayload {
  tipo?: TipoCliente
  condicion_pago_id?: string
  forma_pago_id?: string
  activo?: boolean
}

export interface ProveedorRol {
  id: string
  drogueria_id: string
  tipo: TipoProveedor
  es_competidor: boolean
  es_proveedor_compra: boolean
  condicion_pago_id: string | null
  forma_pago_id: string | null
  activo: boolean
}

export interface ProveedorRolCreatePayload {
  tipo?: TipoProveedor
  es_competidor?: boolean
  es_proveedor_compra?: boolean
  condicion_pago_id?: string
  forma_pago_id?: string
}

export interface ProveedorRolUpdatePayload {
  tipo?: TipoProveedor
  es_competidor?: boolean
  es_proveedor_compra?: boolean
  condicion_pago_id?: string
  forma_pago_id?: string
  activo?: boolean
}

export interface TerceroDireccion {
  id: string
  tercero_id: string
  drogueria_id: string
  etiqueta: string | null
  calle: string
  numero: string | null
  piso_depto: string | null
  ciudad: string | null
  provincia: string | null
  codigo_postal: string | null
  pais: string
  observaciones: string | null
  activo: boolean
}

export interface TerceroDireccionCreatePayload {
  etiqueta?: string
  calle: string
  numero?: string
  piso_depto?: string
  ciudad?: string
  provincia?: string
  codigo_postal?: string
  pais?: string
  observaciones?: string
}

export interface TerceroDireccionUpdatePayload {
  etiqueta?: string
  calle?: string
  numero?: string
  piso_depto?: string
  ciudad?: string
  provincia?: string
  codigo_postal?: string
  pais?: string
  observaciones?: string
  activo?: boolean
}

export interface DireccionUso {
  id: string
  direccion_id: string
  tercero_id: string
  drogueria_id: string
  uso: UsoDireccion
  es_principal: boolean
}

export interface DireccionUsoCreatePayload {
  uso: UsoDireccion
  es_principal?: boolean
}

export interface TerceroContacto {
  id: string
  tercero_id: string
  drogueria_id: string
  nombre: string
  apellido: string | null
  sector_id: string | null
  cargo: string | null
  email: string | null
  telefono: string | null
  celular: string | null
  es_principal: boolean
  notas: string | null
  activo: boolean
}

export interface TerceroContactoCreatePayload {
  nombre: string
  apellido?: string
  sector_id?: string
  cargo?: string
  email?: string
  telefono?: string
  celular?: string
  es_principal?: boolean
  notas?: string
}

export interface TerceroContactoUpdatePayload {
  nombre?: string
  apellido?: string
  sector_id?: string
  cargo?: string
  email?: string
  telefono?: string
  celular?: string
  es_principal?: boolean
  notas?: string
  activo?: boolean
}

// Identidad de terceros

export function listarTerceros(): Promise<Tercero[]> {
  return presupuestacionFetch<Tercero[]>('/terceros')
}

export function crearTercero(payload: TerceroCreatePayload): Promise<Tercero> {
  return presupuestacionFetch<Tercero>('/terceros', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export function obtenerTercero(terceroId: string): Promise<Tercero> {
  return presupuestacionFetch<Tercero>(`/terceros/${terceroId}`)
}

export function actualizarTercero(
  terceroId: string,
  payload: TerceroUpdatePayload,
): Promise<Tercero> {
  return presupuestacionFetch<Tercero>(`/terceros/${terceroId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

// Rol cliente

export function crearRolCliente(
  terceroId: string,
  payload: ClienteRolCreatePayload,
): Promise<ClienteRol> {
  return presupuestacionFetch<ClienteRol>(`/terceros/${terceroId}/clientes`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

/** 404 si el tercero no tiene rol cliente asignado — el caller debe capturar
 * `ApiError` con `status === 404` para mostrar el estado vacío. */
export function obtenerRolCliente(terceroId: string): Promise<ClienteRol> {
  return presupuestacionFetch<ClienteRol>(`/terceros/${terceroId}/clientes`)
}

export function actualizarRolCliente(
  terceroId: string,
  payload: ClienteRolUpdatePayload,
): Promise<ClienteRol> {
  return presupuestacionFetch<ClienteRol>(`/terceros/${terceroId}/clientes`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

// Rol proveedor

export function crearRolProveedor(
  terceroId: string,
  payload: ProveedorRolCreatePayload,
): Promise<ProveedorRol> {
  return presupuestacionFetch<ProveedorRol>(`/terceros/${terceroId}/proveedores`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

/** 404 si el tercero no tiene rol proveedor asignado — mismo criterio que
 * `obtenerRolCliente`. */
export function obtenerRolProveedor(terceroId: string): Promise<ProveedorRol> {
  return presupuestacionFetch<ProveedorRol>(`/terceros/${terceroId}/proveedores`)
}

export function actualizarRolProveedor(
  terceroId: string,
  payload: ProveedorRolUpdatePayload,
): Promise<ProveedorRol> {
  return presupuestacionFetch<ProveedorRol>(`/terceros/${terceroId}/proveedores`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

// Direcciones

export function listarDirecciones(terceroId: string): Promise<TerceroDireccion[]> {
  return presupuestacionFetch<TerceroDireccion[]>(`/terceros/${terceroId}/direcciones`)
}

export function crearDireccion(
  terceroId: string,
  payload: TerceroDireccionCreatePayload,
): Promise<TerceroDireccion> {
  return presupuestacionFetch<TerceroDireccion>(`/terceros/${terceroId}/direcciones`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export function obtenerDireccion(
  terceroId: string,
  direccionId: string,
): Promise<TerceroDireccion> {
  return presupuestacionFetch<TerceroDireccion>(`/terceros/${terceroId}/direcciones/${direccionId}`)
}

export function actualizarDireccion(
  terceroId: string,
  direccionId: string,
  payload: TerceroDireccionUpdatePayload,
): Promise<TerceroDireccion> {
  return presupuestacionFetch<TerceroDireccion>(`/terceros/${terceroId}/direcciones/${direccionId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

/** DELETE físico — a diferencia de contactos, ver prompt de la tarea. */
export function eliminarDireccion(terceroId: string, direccionId: string): Promise<void> {
  return presupuestacionFetch<void>(`/terceros/${terceroId}/direcciones/${direccionId}`, {
    method: 'DELETE',
  })
}

export function crearUsoDireccion(
  terceroId: string,
  direccionId: string,
  payload: DireccionUsoCreatePayload,
): Promise<DireccionUso> {
  return presupuestacionFetch<DireccionUso>(
    `/terceros/${terceroId}/direcciones/${direccionId}/usos`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    },
  )
}

export function listarUsosDireccion(
  terceroId: string,
  direccionId: string,
): Promise<DireccionUso[]> {
  return presupuestacionFetch<DireccionUso[]>(`/terceros/${terceroId}/direcciones/${direccionId}/usos`)
}

export function eliminarUsoDireccion(
  terceroId: string,
  direccionId: string,
  uso: UsoDireccion,
): Promise<void> {
  return presupuestacionFetch<void>(
    `/terceros/${terceroId}/direcciones/${direccionId}/usos/${uso}`,
    { method: 'DELETE' },
  )
}

// Contactos

export function listarContactos(terceroId: string): Promise<TerceroContacto[]> {
  return presupuestacionFetch<TerceroContacto[]>(`/terceros/${terceroId}/contactos`)
}

export function crearContacto(
  terceroId: string,
  payload: TerceroContactoCreatePayload,
): Promise<TerceroContacto> {
  return presupuestacionFetch<TerceroContacto>(`/terceros/${terceroId}/contactos`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export function obtenerContacto(
  terceroId: string,
  contactoId: string,
): Promise<TerceroContacto> {
  return presupuestacionFetch<TerceroContacto>(`/terceros/${terceroId}/contactos/${contactoId}`)
}

/** No existe DELETE de contactos — la "baja" es un PATCH `activo: false`,
 * ver prompt de la tarea. */
export function actualizarContacto(
  terceroId: string,
  contactoId: string,
  payload: TerceroContactoUpdatePayload,
): Promise<TerceroContacto> {
  return presupuestacionFetch<TerceroContacto>(`/terceros/${terceroId}/contactos/${contactoId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}
