# Módulo Carga de documentos — `frontend/src/features/carga-documentos/` + Shell/Navegación

Último módulo del plan de documentación de `docs/modulos/`. Mismo criterio que
[`../frontend_login/`](../frontend_login/README.md): el módulo no es dueño de ninguna tabla de
Supabase (no tiene `base_de_datos.md` propio) ni tiene una máquina de estados real (no tiene
`estados.md`) — el único estado de UI relevante (`tipo`, `archivo`, `clienteId`, `isDragging` en
`FormCard.tsx`) es estado de formulario ordinario, sin transiciones que ameriten diagrama.

Este documento incluye también el **Shell/Navegación (`features/shell/Sidebar.tsx`)** como una
sección dentro de este módulo, no como módulo aparte, según el alcance definido para esta sesión.

## Qué es

"Carga de documentos" es, hoy, **la única pantalla funcional del MVP además de Login** —
confirmado contra `frontend/PROGRESS.md:9-16`: de las 8 pantallas del MVP, solo "Login" (#1) y
"Procesos comerciales" (#4) están marcadas "✅ Hecho"; "Carga de documentos" (#2) está "🔶 En
progreso"; las 5 restantes (#3, #5-8) están "⬜ Pendiente". "Procesos comerciales" (#4) no tiene
pantalla propia en `frontend/src/features/` — expone su UI únicamente a través del componente
`NuevaLiciCotiDialog.tsx` de este módulo, que hoy está huérfano (ver más abajo).

El usuario sube un documento (licitación/directa, comparativa; orden de compra visible pero
deshabilitada) para que `services/extraccion` lo procese con Gemini, elige opcionalmente un
cliente (afecta el prompt de extracción), y ve una lista de las últimas cargas ("Cargas
recientes").

**Estado real vs. declarado — CONFIRMADO**: `frontend/PROGRESS.md:10` sigue marcando esta pantalla
"🔶 En progreso", con change **activo** (no archivado) en
[`openspec/changes/carga-documentos/`](../../../openspec/changes/carga-documentos/) — confirmado
en esta sesión: el directorio existe fuera de `openspec/changes/archive/`.
`openspec/changes/carga-documentos/tasks.md:76-81` deja explícitamente sin marcar (`[ ]`) la tarea
"Subir un archivo real end-to-end y confirmar que aparece en 'Cargas recientes'", con la nota de
que no fue testeable con las herramientas de browser automation disponibles en esa sesión (no
permiten adjuntar un archivo por path del filesystem a un `<input type="file">`). Las tareas de
archivado (`tasks.md:87-89`: actualizar `PROGRESS.md` a "✅ Hecho" y mover el change a
`archive/`) también siguen sin marcar.

## Qué NO hace

- **No completa el flujo de "nueva licitación/cotización".** El componente
  `NuevaLiciCotiDialog.tsx` existe, está completo y funcional en aislamiento (formulario + mutación
  contra `POST /procesos-comerciales`), pero **no tiene ningún caller**: un grep de
  `NuevaLiciCotiDialog` sobre todo `frontend/src/` en esta sesión solo encuentra su propia
  definición (`NuevaLiciCotiDialog.tsx:18`) — ningún otro archivo lo importa. Fue sacado
  deliberadamente de esta pantalla (ver [`decisiones.md`](./decisiones.md) D-CARGADOCUMENTOS-001) y
  queda a la espera de que lo reutilice la pantalla "Validar extracción" (`openspec/changes/
  validar-extraccion/`), que todavía no tiene código real — solo un stub de `proposal.md`, sin
  `spec.md` ni `tasks.md` (confirmado leyendo `validar-extraccion/proposal.md:3`: "Estado: sin
  empezar"). Por eso esa pantalla no está cubierta en `docs/modulos/`.
- **No captura vinculación a un `proceso_comercial` en el formulario de carga.** Fue una decisión
  explícita revertida en el mismo change — ver
  [`decisiones.md`](./decisiones.md) D-CARGADOCUMENTOS-002.
- **No tiene `base_de_datos.md` propio** — el módulo no escribe directamente en Supabase; todo pasa
  por HTTP contra `services/extraccion` (y, solo a través del modal huérfano, contra
  `services/presupuestacion`).
- **No tiene `estados.md`** — ver arriba.
- **No hay tests de frontend.** Confirmado en esta sesión: `frontend/package.json` no tiene script
  `test` ni dependencia de `vitest`; no se encontró ningún archivo `*.test.ts(x)`/`*.spec.ts(x)` en
  `frontend/src`. Este hallazgo ya está documentado como P1 transversal en
  [`../frontend_login/pendientes.md`](../frontend_login/pendientes.md) P1(1) — sigue aplicando sin
  cambios a este módulo, no se repite el análisis acá. Ver [`pendientes.md`](./pendientes.md) P1(1)
  de este módulo, que solo enlaza.

## Mapa rápido de archivos

| Archivo | Qué hace |
|---|---|
| `frontend/src/features/carga-documentos/CargaDocumentos.tsx` | Página contenedora: monta `FormCard` + `RecentCard`. Ruteada en `/` vía `routes/_authenticated.index.tsx`. |
| `frontend/src/features/carga-documentos/components/FormCard.tsx` | Formulario completo: toggle de tipo de documento, drag&drop de archivo, selector de cliente, submit multipart. |
| `frontend/src/features/carga-documentos/components/RecentCard.tsx` | Lista de las últimas 3 cargas, con badge de estado. |
| `frontend/src/features/carga-documentos/components/NuevaLiciCotiDialog.tsx` | Modal "+ Nueva" licitación/cotización — **huérfano, sin caller**. Consume `services/presupuestacion`. |
| `frontend/src/features/shell/Sidebar.tsx` | Navegación lateral de todas las rutas protegidas — ver sección dedicada abajo. |
| `frontend/src/lib/api/client.ts` | `extraccionFetch` + `ApiError` — wrapper de fetch contra `services/extraccion`. |
| `frontend/src/lib/api/extraccion.ts` | Funciones y tipos para `/api/clientes`, `/api/documentos`, `/procesar`. |
| `frontend/src/lib/api/procesosComerciales.ts` | Funciones y tipos para `/procesos-comerciales` (`services/presupuestacion`), consumidas solo por el modal huérfano. |
| `frontend/src/lib/api/presupuestacion.ts` | `presupuestacionFetch` + `ApiError` (segunda implementación) — wrapper de fetch contra `services/presupuestacion`, con inyección de JWT. |

## Shell / Navegación — `Sidebar.tsx`

`Sidebar.tsx` se monta en `routes/_authenticated.tsx` (fuera del alcance de archivos de esta
documentación, ya cubierto en [`../frontend_login/`](../frontend_login/README.md)) y envuelve todas
las rutas protegidas.

**Sidebar desalineado con las 8 pantallas del MVP — CONFIRMADO**: `NAV_ITEMS`
(`Sidebar.tsx:12-19`) declara 6 ítems — "Carga de documentos" (única habilitada, apunta a `/`),
"Licitaciones", "Calendario", "Historial", "Presupuestos", "Comparativas" (las 5 restantes con
`disabled: true`) — que **no corresponden** a los nombres de las 8 pantallas de
`frontend/PROGRESS.md:8-16` ("Login", "Carga de documentos", "Validar extracción", "Procesos
comerciales", "Matching", "Presupuestos", "Comparativas", "Compras"): no hay ítem para "Procesos
comerciales", "Validar extracción", "Matching" ni "Compras", y sí hay dos ítems ("Licitaciones",
"Calendario") que no figuran como pantallas propias del MVP en `PROGRESS.md`.

El propio código lo reconoce como placeholder — cita textual exacta, `Sidebar.tsx:10-11`:

```typescript
// Placeholder: los 6 items y sus rutas finales vienen del mockup Figma
// (SEjXiBEMxprppdgmlNHKO8), todavía sin validar por screenshot en esta sesión.
```

Ver detalle de riesgo en [`pendientes.md`](./pendientes.md) P2.

## Dependencias

- **`services/extraccion`** (ya documentado en [`../extraccion_api/`](../extraccion_api/)) — vía
  `extraccionFetch` (`lib/api/client.ts`): `GET /api/clientes`, `POST /procesar` (multipart),
  `GET /api/documentos?tipo=`. Ver contrato completo de cada endpoint en
  [`../extraccion_api/api.md`](../extraccion_api/api.md) y
  [`../extraccion_api/casos_de_uso.md`](../extraccion_api/casos_de_uso.md). Detalle de qué
  componente llama a qué endpoint en [`casos_de_uso.md`](./casos_de_uso.md) de este módulo.
- **`services/presupuestacion`** (ya documentado en
  [`../procesos_comerciales/`](../procesos_comerciales/)) — **indirectamente**, únicamente a través
  del componente huérfano `NuevaLiciCotiDialog.tsx`, vía `presupuestacionFetch`
  (`lib/api/presupuestacion.ts`) → `POST /procesos-comerciales`. Como el componente no tiene
  caller, esta dependencia no se ejercita en runtime hoy — ver
  [`../procesos_comerciales/api.md`](../procesos_comerciales/api.md) para el contrato del endpoint
  y [`reglas.md`](./reglas.md) para la regla de negocio del backend que el propio componente conoce
  vía comentario.
- **`features/auth` (`AuthContext`)** — `Sidebar.tsx` consume `useAuth()` para `perfil` y
  `signOut()` (`Sidebar.tsx:22`, `:25-28`); ya documentado en
  [`../frontend_login/`](../frontend_login/README.md).

## Documentos del módulo

- [`arquitectura.md`](./arquitectura.md) — relación entre `CargaDocumentos`/`FormCard`/
  `RecentCard`/`NuevaLiciCotiDialog`, el patrón de fetch (`extraccionFetch`/`presupuestacionFetch`),
  el `ApiError` duplicado, por qué el modal quedó huérfano.
- [`reglas.md`](./reglas.md) — reglas reales del módulo (RN-CARGADOCUMENTOS-NNN).
- [`flujo.md`](./flujo.md) — flujo de carga de documento end-to-end y flujo roto del modal "+
  Nueva".
- [`casos_de_uso.md`](./casos_de_uso.md) — qué endpoint consume cada componente, con enlace a la
  doc de backend correspondiente.
- [`api.md`](./api.md) — props/hooks/funciones exportadas de cada componente y de `lib/api/`.
- [`decisiones.md`](./decisiones.md) — decisiones de diseño (D-CARGADOCUMENTOS-NNN).
- [`pendientes.md`](./pendientes.md) — auditoría P1/P2/P3.
