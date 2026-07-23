# API pública — Carga de documentos

Firmas verificadas contra el código real en esta sesión.

## `features/carga-documentos/CargaDocumentos.tsx`

```typescript
export function CargaDocumentos(): JSX.Element
// CargaDocumentos.tsx:4-16
// Sin props. Monta <FormCard /> + <RecentCard /> dentro de un contenedor con título fijo.
// Ruteado en "/" vía routes/_authenticated.index.tsx (fuera del alcance de archivos,
// confirmado por grep: import { CargaDocumentos } from '@/features/carga-documentos/CargaDocumentos').
```

## `features/carga-documentos/components/FormCard.tsx`

```typescript
type TipoDocumento = 'licitaciones' | 'comparativas' | 'ordenes'
// re-exportado desde lib/api/extraccion.ts, no redeclarado acá

const TIPO_OPTIONS: { value: TipoDocumento; label: string; disabled?: boolean }[]
// FormCard.tsx:6-10 (no exportado, constante de módulo)

const ACCEPT_POR_TIPO: Record<TipoDocumento, string>
// FormCard.tsx:12-16 (no exportado, constante de módulo)

export function FormCard(): JSX.Element
// FormCard.tsx:18-149
// Sin props. Estado interno: tipo, archivo, clienteId, isDragging (useState);
// fileInputRef (useRef<HTMLInputElement>); queryClient (useQueryClient).
// Queries/mutations internas (no expuestas):
//   clientesQuery = useQuery({ queryKey: ['clientes'], queryFn: listarClientes })       (:26)
//   mutation = useMutation({ mutationFn: () => procesarDocumento(...), onSuccess })     (:28-38)
// handleFile(file: File | null): void — setArchivo + mutation.reset()                  (:40-43)
```

## `features/carga-documentos/components/RecentCard.tsx`

```typescript
const STATUS_STYLES: Record<string, string>
// RecentCard.tsx:5-9 (no exportado, constante de módulo)
// Claves: 'completado', 'procesando', 'error' — ver pendientes.md sobre el mismatch
// con los valores reales que escribe el backend.

export function RecentCard(): JSX.Element
// RecentCard.tsx:11-49
// Sin props. useQuery({ queryKey: ['documentos-recientes'], queryFn: () => listarDocumentosRecientes() }) (:12-15)
// Renderiza data?.documentos.slice(0, 3) (:17).
```

## `features/carga-documentos/components/NuevaLiciCotiDialog.tsx`

**Sin caller en `frontend/src/` — ver [`README.md`](./README.md) y [`flujo.md`](./flujo.md).**

```typescript
interface Props {
  clase: Clase                                  // 'cotizacion' | 'licitacion' (procesosComerciales.ts:3)
  onCreated: (proceso: ProcesoComercialResumen) => void
}
// NuevaLiciCotiDialog.tsx:11-16 (no exportado — tipo interno del módulo)
// Comentario de la prop `clase` (:12-13): "Controlada desde FormCard — el selector de clase
// vive en el flujo principal, no en este modal (ver openspec/changes/carga-documentos/spec.md)."

export function NuevaLiciCotiDialog({ clase, onCreated }: Props): JSX.Element
// NuevaLiciCotiDialog.tsx:18-129
// Estado interno: open, nombre, apertura, modalidad (useState); queryClient (useQueryClient).
// mutation = useMutation({ mutationFn: () => crearProcesoComercial(...), onSuccess })  (:27-44)
//   — arma el payload omitiendo apertura/modalidad si clase !== 'licitacion'
//     (comentario explícito sobre ck_proc_cotizacion_sin_seguimiento, :31-33 — ver reglas.md).
// onCreated se invoca con el ProcesoComercialResumen devuelto por el backend tras crear (:39).
```

## `features/shell/Sidebar.tsx`

```typescript
interface NavItem {
  label: string
  to: string
  disabled?: boolean
}
// Sidebar.tsx:4-8 (no exportado)

const NAV_ITEMS: NavItem[]
// Sidebar.tsx:12-19 (no exportado, constante de módulo)
// 6 items: "Carga de documentos" (habilitado, to: '/'), "Licitaciones", "Calendario",
// "Historial", "Presupuestos", "Comparativas" (los 5 restantes con disabled: true).
// Comentario explícito de placeholder (:10-11) — ver README.md.

export function Sidebar(): JSX.Element
// Sidebar.tsx:21-65
// Sin props. Consume useAuth() → { perfil, signOut } (:22, ya documentado en
// ../frontend_login/api.md). handleLogout(): Promise<void> — signOut() + navigate({ to: '/login' }) (:25-28).
```

## `lib/api/client.ts`

```typescript
const EXTRACCION_BASE_URL: string
// client.ts:1 — import.meta.env.VITE_EXTRACCION_API_URL ?? 'http://localhost:8000'

export class ApiError extends Error {
  constructor(message: string, public status: number)
}
// client.ts:3-11 — implementación independiente de la de presupuestacion.ts (ver arquitectura.md).

export async function extraccionFetch<T>(path: string, init?: RequestInit): Promise<T>
// client.ts:17-34
// Agrega Accept: application/json. Parsea el body como JSON (null si falla el parseo, :26).
// Si !response.ok: throw new ApiError(body?.error ?? `Error ${status} al llamar ${path}`, status) (:28-31).
// No inyecta Authorization — services/extraccion no lo exige (ver ../extraccion_api/).
```

## `lib/api/extraccion.ts`

```typescript
export type TipoDocumento = 'licitaciones' | 'comparativas' | 'ordenes'
// extraccion.ts:3

export interface Cliente { id: string; nombre: string }
// extraccion.ts:5-8

export interface DocumentoReciente {
  id: string
  source_filename: string
  document_type: 'licitacion' | 'comparativa'
  row_count: number
  status: string
  created_at: string
  proceso_comercial: { id: string; nombre: string } | null
}
// extraccion.ts:10-18

export interface ProcesarPayload {
  archivo: File
  tipo: TipoDocumento
  licitacionId?: string   // nunca lo envía FormCard.tsx — ver flujo.md
  clienteId?: string
}
// extraccion.ts:20-25

export interface ProcesarResultado { ok: boolean; tipo: string; error?: string }
// extraccion.ts:27-31

export function listarClientes(): Promise<Cliente[]>
// extraccion.ts:33-35 — GET /api/clientes

export function listarDocumentosRecientes(tipo = ''): Promise<{ documentos: DocumentoReciente[] }>
// extraccion.ts:37-40 — GET /api/documentos[?tipo=...]. FormCard/RecentCard siempre lo llaman
// sin argumento (RecentCard.tsx:14), así que `tipo` nunca se usa en este módulo hoy.

export function procesarDocumento(payload: ProcesarPayload): Promise<ProcesarResultado>
// extraccion.ts:42-58 — POST /procesar (multipart/form-data)
```

## `lib/api/procesosComerciales.ts`

Consumido únicamente por `NuevaLiciCotiDialog.tsx` (sin caller — ver arriba).

```typescript
export type Clase = 'cotizacion' | 'licitacion'
export type Modalidad = 'mail' | 'pliego'
// procesosComerciales.ts:3-4 — mismos literales que procesos_comerciales/models.py del backend
// (ver ../procesos_comerciales/api.md), redeclarados de forma independiente (mismo patrón que
// D-LOGIN-002 en ../frontend_login/decisiones.md).

export interface ProcesoComercialResumen { id: string; nombre: string; clase: Clase; estado: string }
// procesosComerciales.ts:6-11

export interface ProcesoComercialCreatePayload {
  nombre: string
  clase: Clase
  cliente_id?: string
  apertura?: string
  modalidad?: Modalidad
}
// procesosComerciales.ts:13-19 — nota: no incluye vencimiento/tipo_gestion/comparativa_pedida/
// categoria_id/monto_estimado/notas, que sí existen en ProcesoComercialCreate del backend
// (ver ../procesos_comerciales/api.md) — este payload es un subconjunto mínimo.

export function listarProcesosComerciales(): Promise<ProcesoComercialResumen[]>
// procesosComerciales.ts:21-23 — GET /procesos-comerciales. Sin caller en este módulo
// (NuevaLiciCotiDialog.tsx no lo usa — solo invalida la query con esa key tras crear, :38).

export function crearProcesoComercial(payload: ProcesoComercialCreatePayload): Promise<ProcesoComercialResumen>
// procesosComerciales.ts:25-33 — POST /procesos-comerciales
```

## `lib/api/presupuestacion.ts`

```typescript
const PRESUPUESTACION_BASE_URL: string
// presupuestacion.ts:3 — import.meta.env.VITE_PRESUPUESTACION_API_URL ?? 'http://localhost:8001'

export class ApiError extends Error {
  constructor(message: string, public status: number)
}
// presupuestacion.ts:5-13 — segunda implementación independiente, ver arquitectura.md.

export async function presupuestacionFetch<T>(path: string, init?: RequestInit): Promise<T>
// presupuestacion.ts:19-41
// Resuelve supabase.auth.getSession() en cada llamada (:20-22); agrega
// Authorization: Bearer <access_token> solo si hay sesión (:28). Si !response.ok:
// throw new ApiError(body?.detail ?? `Error ${status} al llamar ${path}`, status) (:36-37).
```
