import { presupuestacionFetch } from './presupuestacion'

export type Clasificacion =
  | 'medicamento'
  | 'descartable'
  | 'insumo'
  | 'equipamiento'
  | 'perfumeria'
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
  laboratorio: string | null
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
  laboratorio?: string
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
  laboratorio?: string
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

export function listarProductos(): Promise<Producto[]> {
  return presupuestacionFetch<Producto[]>('/productos')
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
