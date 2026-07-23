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

**Ningún frontend lo consume todavía.** No se encontró en esta sesión ningún cliente
HTTP dentro del repositorio que llame a este endpoint (no hay tests de router, solo
de `service.py` directamente — ver [`api.md`](./api.md)). Confirmado también por
`openspec/changes/validar-extraccion/proposal.md:1-6`: la pantalla #3 del MVP del
frontend ("Validar extracción") es, a la fecha de esta documentación, un **stub sin
empezar** ("Estado: sin empezar... no hay `spec.md` ni `tasks.md` todavía",
`proposal.md:3`) — el backend de este módulo existe y está probado por integración,
pero no tiene consumidor de UI todavía. Ver también `frontend/PROGRESS.md:11`
("⬜ Pendiente").

El flujo previsto (según el scope heredado documentado en ese stub,
`proposal.md:20-46`) es: subida de archivo (`POST /procesar` en
`services/extraccion/`) → vinculación opcional a un proceso comercial (mecanismo
todavía sin definir entre este endpoint y `PATCH /api/extraction-results/{id}` de
`services/extraccion/routers/extraction_results.py`, `proposal.md:41-46`) → esta
pantalla, que dispararía `POST /extracciones/{id}/validar`. Nada de esto está
confirmado en código — es intención de producto documentada, no comportamiento
verificado.
