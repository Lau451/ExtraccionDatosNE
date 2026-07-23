# Arquitectura — Carga de documentos

## Piezas y relación entre ellas

```
                    routes/_authenticated.index.tsx
                    (ruta "/", fuera del alcance de archivos)
                                  │
                                  ▼
                        CargaDocumentos.tsx
                    (contenedor, sin estado propio)
                                  │
                    ┌─────────────┴─────────────┐
                    │                            │
              FormCard.tsx                 RecentCard.tsx
        (toggle tipo, dropzone,          (lista últimas 3
         cliente, submit)                 cargas, polling
                    │                      manual vía cache
                    │                      de react-query)
                    ▼
          services/extraccion
    (GET /api/clientes, POST /procesar,
       GET /api/documentos?tipo=)


        NuevaLiciCotiDialog.tsx  ◄── SIN CALLER (ver abajo)
        (recibe `clase`/`onCreated` por props,
         nunca se monta en ningún árbol real)
                    │
                    ▼
          services/presupuestacion
        (POST /procesos-comerciales)
```

- **`CargaDocumentos.tsx`** (`CargaDocumentos.tsx:4-16`) es puramente estructural: monta
  `<FormCard />` y `<RecentCard />` dentro de un contenedor con título fijo. No tiene estado, no
  hace fetch, no pasa props a sus hijos.
- **`FormCard.tsx`** concentra prácticamente toda la lógica del módulo (ver más abajo, "mezcla de
  responsabilidades").
- **`RecentCard.tsx`** es de solo lectura: un `useQuery` sobre `['documentos-recientes']`
  (`RecentCard.tsx:12-15`) que `FormCard.tsx` invalida tras un submit exitoso
  (`FormCard.tsx:33-34`, `queryClient.invalidateQueries({ queryKey: ['documentos-recientes'] })`) —
  es el único acoplamiento entre ambos componentes, y es indirecto (vía la cache compartida de
  `@tanstack/react-query`, no vía props ni contexto).
- **`NuevaLiciCotiDialog.tsx`** no tiene ninguna relación de árbol con los tres componentes
  anteriores: no es importado por `CargaDocumentos.tsx`, `FormCard.tsx` ni `RecentCard.tsx` — un
  grep de `NuevaLiciCotiDialog` sobre todo `frontend/src/` en esta sesión confirma que su único
  aparición es su propia definición (`NuevaLiciCotiDialog.tsx:18`). Se documenta acá porque vive en
  el mismo directorio (`components/`) y porque el proposal del change lo trata como parte de este
  módulo — ver más abajo "Por qué el modal está huérfano".

## El patrón de fetch: dos wrappers, dos `ApiError`

Este módulo usa **dos wrappers de fetch independientes**, uno por backend, cada uno con su propia
clase `ApiError`:

```typescript
// lib/api/client.ts:3-11 — usado por FormCard.tsx y RecentCard.tsx (vía extraccion.ts)
export class ApiError extends Error {
  constructor(message: string, public status: number) {
    super(message)
    this.name = 'ApiError'
  }
}

// lib/api/presupuestacion.ts:5-13 — usado por NuevaLiciCotiDialog.tsx (vía procesosComerciales.ts)
export class ApiError extends Error {
  constructor(message: string, public status: number) {
    super(message)
    this.name = 'ApiError'
  }
}
```

Las dos clases son **estructuralmente idénticas** (mismo cuerpo, campo por campo) pero son dos
símbolos TypeScript distintos, sin herencia ni tipo compartido entre ambas — `instanceof ApiError`
en un archivo que importe la de `client.ts` no reconocería una instancia lanzada por
`presupuestacion.ts`, y viceversa. Ver [`decisiones.md`](./decisiones.md) D-CARGADOCUMENTOS-003
para el porqué (hasta donde el código lo documenta).

Los dos wrappers difieren en más que el nombre de la clase:

| | `extraccionFetch` (`client.ts:17-34`) | `presupuestacionFetch` (`presupuestacion.ts:19-41`) |
|---|---|---|
| Base URL | `VITE_EXTRACCION_API_URL` ?? `http://localhost:8000` (`client.ts:1`) | `VITE_PRESUPUESTACION_API_URL` ?? `http://localhost:8001` (`presupuestacion.ts:3`) |
| Inyección de JWT | No — `services/extraccion` no exige auth en la mayoría de sus endpoints (ver [`../extraccion_api/casos_de_uso.md`](../extraccion_api/casos_de_uso.md) "Resumen de auth por endpoint") | Sí — `supabase.auth.getSession()` en cada llamada, header `Authorization: Bearer <access_token>` si hay sesión (`presupuestacion.ts:20-28`) |
| Header `Accept` | `application/json` siempre — necesario para que `/procesar` devuelva JSON en vez del HTML legacy (comentario explícito, `client.ts:13-16`) | `application/json` siempre (`presupuestacion.ts:27`) |
| Extracción del mensaje de error | `body?.error` (`client.ts:29`) — formato propio de `services/extraccion` | `body?.detail` (`presupuestacion.ts:36`) — formato default de FastAPI (`HTTPException.detail`) |
| Parseo de body en error de red/timeout | `response.json().catch(() => null)` (`client.ts:26`) — si el `fetch()` en sí rechaza (red caída), la excepción original de `fetch` se propaga sin envolver en `ApiError` | Igual patrón (`presupuestacion.ts:33`) |

Ambos wrappers comparten la misma limitación de manejo de errores de red — ver
[`pendientes.md`](./pendientes.md) P2.

## Por qué el modal está huérfano

Evidencia, en orden cronológico según `openspec/changes/carga-documentos/proposal.md`:

1. Se descubrió que `comparativas.proceso_comercial_id` y `ordenes_compra.proceso_comercial_id`
   son `UUID NOT NULL` en el schema (`proposal.md:19`, citando
   `docs/schema/extractor_final.sql:561`, `:609`).
2. Una primera implementación intentó capturar esa vinculación en esta misma pantalla, con un
   componente `VinculacionSelector.tsx` de dos variantes y `NuevaLiciCotiDialog.tsx` recibiendo
   `clase` como estado propio (`proposal.md:20-23`, `tasks.md:52-57`).
3. Se revisó la decisión el mismo día: `proceso_comercial_id` es una decisión de negocio pura, sin
   impacto en la calidad de extracción — a diferencia de `Cliente`, que sí inyecta instrucciones al
   prompt de Gemini (`proposal.md:34-36`). Se decidió que la pantalla correcta para resolver la
   vinculación es "Validar extracción" (pantalla #3 del MVP), no esta.
4. Consecuencia en código: `VinculacionSelector.tsx` se borró por completo. `NuevaLiciCotiDialog.tsx`
   **no se borró** — cita textual, `proposal.md:45-50`:

   > "`NuevaLiciCotiDialog.tsx` (parte del change ya archivado
   > [`archive/procesos-comerciales`](../../../openspec/changes/archive/procesos-comerciales/))
   > queda SIN ningún caller en el árbol actual — no se borra, porque la próxima pantalla
   > (`validar-extraccion`) va a necesitar la misma capacidad de 'crear/vincular proceso comercial'
   > y es razonable reutilizarlo o adaptarlo ahí en vez de reescribirlo desde cero."

5. Su firma se ajustó para ese futuro reuso: pasó a recibir `clase` como prop controlada en vez de
   gestionar su propio estado de clase (`tasks.md:55-57`, `NuevaLiciCotiDialog.tsx:14`,
   comentario: "Controlada desde FormCard — el selector de clase vive en el flujo principal, no en
   este modal").
6. `openspec/changes/validar-extraccion/proposal.md:28-31` confirma la intención de reuso desde el
   lado de la pantalla destino, pero sin comprometerse a la forma final: "Evaluar si se reubica a
   `features/validar-extraccion/` tal cual, o se adapta." Esa pantalla no tiene `spec.md` ni
   `tasks.md` todavía — solo el stub de `proposal.md` (`validar-extraccion/proposal.md:3`, "Estado:
   sin empezar").

Ver el análisis de riesgo de este código sin caller en [`pendientes.md`](./pendientes.md) P2 y la
decisión formal en [`decisiones.md`](./decisiones.md) D-CARGADOCUMENTOS-001.

## `FormCard.tsx` mezcla responsabilidades

Confirmado leyendo el archivo completo (`FormCard.tsx:1-149`): un único componente concentra
cuatro responsabilidades distintas, sin separación en hooks ni módulos:

1. **Estado de UI puro**: `isDragging` (`:22`) y los handlers `onDragOver`/`onDragLeave`/`onDrop`
   del dropzone (`:82-91`).
2. **Fetch de datos de referencia**: `clientesQuery` vía `useQuery(['clientes'], listarClientes)`
   (`:26`).
3. **Mutación de subida**: `mutation` vía `useMutation` (`:28-38`), incluida la invalidación manual
   de la query de `RecentCard` (`:33-34`) y el reseteo del `<input type="file">` por ref (`:35-36`,
   necesario porque el navegador no permite limpiar el valor de un input de archivo por estado de
   React).
4. **Reglas de negocio del tipo de documento**: `TIPO_OPTIONS` (`:6-10`, qué tipos existen y cuál
   está deshabilitado) y `ACCEPT_POR_TIPO` (`:12-16`, qué extensiones acepta cada tipo) están
   definidos como constantes a nivel de módulo dentro del mismo archivo que el componente que las
   consume, sin extraerlas a `lib/` ni a un archivo de configuración separado.

No hay separación entre "contenedor" (fetch/mutación) y "presentación" (JSX puro) — todo vive en el
mismo componente y el mismo archivo. Ver [`pendientes.md`](./pendientes.md) P2 para el riesgo
asociado.

## Relación con el Shell (`Sidebar.tsx`)

`Sidebar.tsx` no importa nada de `features/carga-documentos/` ni de `lib/api/extraccion.ts` /
`lib/api/procesosComerciales.ts` — su único acoplamiento con este módulo es de **navegación**: el
ítem habilitado `{ label: 'Carga de documentos', to: '/' }` (`Sidebar.tsx:13`) apunta a la ruta
donde se monta `CargaDocumentos` (`routes/_authenticated.index.tsx:2,5`, confirmado por grep en
esta sesión: `import { CargaDocumentos } from '@/features/carga-documentos/CargaDocumentos'` y
`component: CargaDocumentos`). El resto de la relación de `Sidebar.tsx` (con `AuthContext`, JWT,
logout) ya está cubierto en [`../frontend_login/arquitectura.md`](../frontend_login/arquitectura.md)
y no se repite acá — ver la sección "Shell / Navegación" de [`README.md`](./README.md) para el
detalle de desalineación con las 8 pantallas del MVP.
