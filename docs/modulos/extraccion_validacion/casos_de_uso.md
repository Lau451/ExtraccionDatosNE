# Casos de uso — Extracción-Validación

## `POST /extracciones/{extraction_id}/validar`

Único endpoint del módulo (`router.py:15-40`). Montado sin prefijo adicional en
`services/presupuestacion/main.py:45` (tag `"extraccion"`).

- **Roles habilitados**: `admin`, `gerencia`, `lider_comercial`, `comercial`
  (`_ROLES_VALIDAR`, `router.py:12`, vía `require_roles(*_ROLES_VALIDAR)` de
  `core.auth`, `router.py:19`).
- **Path param**: `extraction_id: str` — el `id` de la fila de `extraction_results`
  a validar.
- **Body**: `ValidarExtraccionRequest` (`models.py:8-9`) — un único campo opcional
  `proceso_comercial_id: str | None`.
- **Response**: `ResultadoValidarExtraccion` (`models.py:12-18`):

  | Campo | Descripción |
  |---|---|
  | `extraction_id` | Eco del `id` procesado. |
  | `document_type` | El tipo de documento de la extracción validada. |
  | `proceso_comercial_id` | El resuelto (existente o recién vinculado). |
  | `filas_creadas` | Cantidad de `items_proceso` (licitación/cotización) u `ofertas_items` (comparativa) insertadas. |
  | `comparativa_id` | `None` salvo `document_type == "comparativa"`. |
  | `reemplazo_version_anterior` | `True` si se reemplazó una comparativa vigente previa; siempre `False` para licitación/cotización. |

### Secuencia interna (`router.py:16-40`)

1. `SELECT id, drogueria_id FROM extraction_results WHERE id = extraction_id` con
   `user_client` (RLS-aware, `router.py:22-28`).
2. Si no hay resultado → `NotFoundError("No se encontró la extracción")`
   (`router.py:29-30`).
3. Si `usuario.rol != "superadmin"` y la droguería de la extracción no coincide con
   la del usuario → `ForbiddenError("La extracción no pertenece a tu droguería")`
   (`router.py:32-34`).
4. Delega en `validar_extraccion_para_endpoint` (`router.py:36-40`), que abre su
   propio cliente `service_role` y ejecuta todo el caso de uso descrito en
   [`flujo.md`](./flujo.md).

### Errores posibles (vía `core.exceptions`, mapeados a HTTP por `STATUS_MAP`)

| Excepción | HTTP | Origen |
|---|---|---|
| `NotFoundError` | 404 | Extracción inexistente (`router.py:29-30`); proceso comercial indicado inexistente (`service.py:46-47`); extracción inexistente re-chequeada dentro del service (`service.py:251-253`). |
| `ForbiddenError` | 403 | Extracción de otra droguería, usuario no `superadmin` (`router.py:32-34`). |
| `ConflictError` | 409 | Extracción ya validada (`service.py:254-255`); `proceso_comercial_id` indicado difiere del ya vinculado (`service.py:35-37`). |
| `ValidationError` | 422 | Sin `proceso_comercial_id` y la extracción no tiene uno vinculado (`service.py:41-43`); proceso comercial de otra droguería (`service.py:49-51`); `document_type` sin materialización implementada (`service.py:286-289`). |

## Quién consume este endpoint

**Corrección post-`validar-extraccion` (reemplaza el texto anterior de esta sección,
que describía un stub sin frontend):** el change `validar-extraccion` implementó
`frontend/src/features/validar-extraccion/` como consumidor real de este endpoint —
`ValidarExtraccionDetalle.tsx` llama `POST /extracciones/{id}/validar` vía
`frontend/src/lib/api/extracciones.ts:validarExtraccion`. Ver
[`../../../openspec/changes/validar-extraccion/`](../../../openspec/changes/validar-extraccion/)
para el spec/design completos.

**No hay ninguna relación entre este endpoint y `PATCH /api/extraction-results/{id}`**
(`services/extraccion/routers/extraction_results.py`) — ni funcional ni de código. El
texto anterior de esta sección especulaba con un "mecanismo todavía sin definir" entre
ambos; quedó resuelto (y esa relación descartada) al construir el flujo real:
`ValidarExtraccionDetalle` resuelve `proceso_comercial_id` directamente contra
`services/presupuestacion/procesos_comerciales/` (vía
`ProcesoComercialSelector.tsx`/`NuevaLiciCotiDialog.tsx`, reusando
`crearProcesoComercial`/`listarProcesosComerciales`) y lo manda en el body de
`POST .../validar` — el `PATCH` de `services/extraccion` nunca se invoca desde este
flujo. Además, ese `PATCH` está **deprecado y confirmado roto** contra el schema real
(`extraction_results` no tiene columna `licitacion_id`) — ver
[`extraccion_api/api.md`](../extraccion_api/api.md) y
[`extraccion_api/pendientes.md`](../extraccion_api/pendientes.md), por lo que tampoco
sería viable adoptarlo como mecanismo de vinculación aunque se hubiera querido.
