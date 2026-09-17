import { presupuestacionFetch } from './presupuestacion'

export type Clasificacion =
  | 'medicamento'
  | 'descartable'
  | 'solucion'
  | 'nutricion'
  | 'equipamiento'
  | 'reactivo'
  | 'cosmetico'
  | 'otro'

export interface Producto {
  id: string
  drogueria_id: string
  codigo_interno: string
  nombre: string
  categoria_id: string | null
  clasificacion: Clasificacion | null
  droga: string | null
  presentacion: string | null
  forma_farmaceutica: string | null
  marca_id: string | null
  envase_id: string | null
  alicuota_iva: number | null
  codigo_anmat: string | null
  activo: boolean
}

export interface ProductoCreatePayload {
  codigo_interno: string
  nombre: string
  categoria_id?: string
  clasificacion?: Clasificacion
  droga?: string
  presentacion?: string
  forma_farmaceutica?: string
  marca_id?: string
  envase_id?: string
  alicuota_iva?: number
  codigo_anmat?: string
}

export interface ProductoUpdatePayload {
  codigo_interno?: string
  nombre?: string
  categoria_id?: string
  clasificacion?: Clasificacion
  droga?: string
  presentacion?: string
  forma_farmaceutica?: string
  marca_id?: string
  envase_id?: string
  alicuota_iva?: number
  codigo_anmat?: string
  activo?: boolean
}

export interface Categoria {
  id: string
  drogueria_id: string
  nombre: string
  descripcion: string | null
  activa: boolean
}

export interface CategoriaCreatePayload {
  nombre: string
  descripcion?: string
}

export interface CategoriaUpdatePayload {
  nombre?: string
  descripcion?: string
  activa?: boolean
}

export interface Marca {
  id: string
  drogueria_id: string
  nombre: string
  activa: boolean
}

export interface MarcaCreatePayload {
  nombre: string
}

export interface MarcaUpdatePayload {
  nombre?: string
  activa?: boolean
}

export interface Envase {
  id: string
  drogueria_id: string
  nombre: string
  activa: boolean
}

export interface EnvaseCreatePayload {
  nombre: string
}

export interface EnvaseUpdatePayload {
  nombre?: string
  activa?: boolean
}

export interface Caracteristica {
  id: string
  drogueria_id: string
  nombre: string
  activa: boolean
}

export interface CaracteristicaCreatePayload {
  nombre: string
}

export interface CaracteristicaUpdatePayload {
  nombre?: string
  activa?: boolean
}

export interface ProductoCaracteristica {
  id: string
  producto_id: string
  caracteristica_id: string
}

export interface Costo {
  id: string
  producto_id: string
  costo_unitario: number
  fecha_desde: string
  fecha_hasta: string | null
  origen: string
}

export interface CostoCreatePayload {
  costo_unitario: number
  fecha_desde: string
}

export interface Stock {
  id: string
  producto_id: string
  deposito: string | null
  cantidad_disponible: number
  cantidad_comprometida: number
}

export interface StockAjustePayload {
  deposito?: string
  cantidad_disponible: number
}

export interface ListarProductosParams {
  q?: string
  categoriaId?: string
  clasificacion?: Clasificacion
  page?: number
  pageSize?: number
}

export interface ProductosPagina {
  items: Producto[]
  total: number
}

export function listarProductos(params: ListarProductosParams = {}): Promise<ProductosPagina> {
  const query = new URLSearchParams()
  if (params.q) query.set('q', params.q)
  if (params.categoriaId) query.set('categoria_id', params.categoriaId)
  if (params.clasificacion) query.set('clasificacion', params.clasificacion)
  query.set('page', String(params.page ?? 1))
  query.set('page_size', String(params.pageSize ?? 50))
  return presupuestacionFetch<ProductosPagina>(`/productos?${query.toString()}`)
}

export function crearProducto(payload: ProductoCreatePayload): Promise<Producto> {
  return presupuestacionFetch<Producto>('/productos', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export function obtenerProducto(productoId: string): Promise<Producto> {
  return presupuestacionFetch<Producto>(`/productos/${productoId}`)
}

export function actualizarProducto(
  productoId: string,
  payload: ProductoUpdatePayload,
): Promise<Producto> {
  return presupuestacionFetch<Producto>(`/productos/${productoId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export function eliminarProducto(productoId: string): Promise<void> {
  return presupuestacionFetch<void>(`/productos/${productoId}`, { method: 'DELETE' })
}

export function listarCategorias(): Promise<Categoria[]> {
  return presupuestacionFetch<Categoria[]>('/categorias')
}

export function crearCategoria(payload: CategoriaCreatePayload): Promise<Categoria> {
  return presupuestacionFetch<Categoria>('/categorias', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export function actualizarCategoria(
  categoriaId: string,
  payload: CategoriaUpdatePayload,
): Promise<Categoria> {
  return presupuestacionFetch<Categoria>(`/categorias/${categoriaId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export function listarMarcas(): Promise<Marca[]> {
  return presupuestacionFetch<Marca[]>('/marcas')
}

export function crearMarca(payload: MarcaCreatePayload): Promise<Marca> {
  return presupuestacionFetch<Marca>('/marcas', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export function actualizarMarca(marcaId: string, payload: MarcaUpdatePayload): Promise<Marca> {
  return presupuestacionFetch<Marca>(`/marcas/${marcaId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export function listarEnvases(): Promise<Envase[]> {
  return presupuestacionFetch<Envase[]>('/envases')
}

export function crearEnvase(payload: EnvaseCreatePayload): Promise<Envase> {
  return presupuestacionFetch<Envase>('/envases', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export function actualizarEnvase(envaseId: string, payload: EnvaseUpdatePayload): Promise<Envase> {
  return presupuestacionFetch<Envase>(`/envases/${envaseId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export function listarCaracteristicas(): Promise<Caracteristica[]> {
  return presupuestacionFetch<Caracteristica[]>('/caracteristicas')
}

export function crearCaracteristica(payload: CaracteristicaCreatePayload): Promise<Caracteristica> {
  return presupuestacionFetch<Caracteristica>('/caracteristicas', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export function actualizarCaracteristica(
  caracteristicaId: string,
  payload: CaracteristicaUpdatePayload,
): Promise<Caracteristica> {
  return presupuestacionFetch<Caracteristica>(`/caracteristicas/${caracteristicaId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export function listarCaracteristicasProducto(productoId: string): Promise<ProductoCaracteristica[]> {
  return presupuestacionFetch<ProductoCaracteristica[]>(`/productos/${productoId}/caracteristicas`)
}

export function asignarCaracteristicaProducto(
  productoId: string,
  caracteristicaId: string,
): Promise<ProductoCaracteristica> {
  return presupuestacionFetch<ProductoCaracteristica>(`/productos/${productoId}/caracteristicas`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ caracteristica_id: caracteristicaId }),
  })
}

export function quitarCaracteristicaProducto(productoId: string, caracteristicaId: string): Promise<void> {
  return presupuestacionFetch<void>(`/productos/${productoId}/caracteristicas/${caracteristicaId}`, {
    method: 'DELETE',
  })
}

export function listarCostos(productoId: string): Promise<Costo[]> {
  return presupuestacionFetch<Costo[]>(`/productos/${productoId}/costos`)
}

export function crearCosto(productoId: string, payload: CostoCreatePayload): Promise<Costo> {
  return presupuestacionFetch<Costo>(`/productos/${productoId}/costos`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export function listarStock(productoId: string): Promise<Stock[]> {
  return presupuestacionFetch<Stock[]>(`/productos/${productoId}/stock`)
}

export function ajustarStock(productoId: string, payload: StockAjustePayload): Promise<Stock> {
  return presupuestacionFetch<Stock>(`/productos/${productoId}/stock`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}
