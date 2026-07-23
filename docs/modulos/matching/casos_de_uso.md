# Casos de uso — Matching

Los 3 endpoints están montados sin prefijo adicional en
`services/presupuestacion/main.py:19,43`
(`app.include_router(matching_router, tags=["matching"])`).

## `POST /items/{item_id}/confirmar-matching`

`confirmar_matching_endpoint` (`router.py:40-50`).

- **Roles habilitados**: `superadmin`, `admin`, `gerencia`, `lider_comercial`,
  `comercial` (`_ROLES_MATCHING`, `router.py:19`).
- **Path param**: `item_id: str` — el `id` de la fila de `items_proceso`.
- **Body**: `ConfirmarMatchingRequest` (`models.py:26-27`) — un único campo
  `producto_id: str`.
- **Secuencia**: valida pertenencia de droguería (`router.py:47`,
  RN-MATCHING-009), delega en `confirmar_matching_para_endpoint` (`service_role`) —
  ver Flujo 2 en [`flujo.md`](./flujo.md).
- **Response**: `ResultadoMatchingItem` con `estado_matching="confirmado"`.

## `POST /items/{item_id}/sin-match`

`sin_match_endpoint` (`router.py:53-60`).

- **Roles habilitados**: los mismos `_ROLES_MATCHING`.
- **Path param**: `item_id: str`.
- **Sin body.**
- **Secuencia**: valida pertenencia de droguería (`router.py:59`), delega en
  `marcar_sin_match_para_endpoint` — ver Flujo 3 en [`flujo.md`](./flujo.md).
- **Response**: `ResultadoMatchingItem` con `estado_matching="sin_match"`.

## `GET /matching/pendientes`

`listar_pendientes_endpoint` (`router.py:63-69`).

- **Roles habilitados**: los mismos `_ROLES_MATCHING`.
- **Sin path param, sin body.**
- **Secuencia**: `SELECT * FROM v_matching_pendiente` directo con `user_client`
  (`router.py:68`, RLS-aware) — **no invoca `service.py`** (RN-MATCHING-010). El
  filtrado por tenant lo hace la política RLS de las tablas subyacentes de la vista
  (`items_proceso`, `procesos_comerciales`, `clientes`), no un chequeo explícito de
  `drogueria_id` en este endpoint.
- **Response**: `list[ItemMatchingPendiente]` (`models.py:30-41`) — columnas
  expuestas por la vista: `item_proceso_id`, `proceso_comercial_id`, `proceso`
  (nombre), `clase`, `cliente_id`, `cliente` (nombre), `numero_renglon`,
  `descripcion`, `estado_matching`, `confianza_matching`, `candidatos` (conteo).
  Definición de la vista: `docs/schema/extractor_final.sql:1534-1552` — filtra
  `estado_matching IN ('pendiente', 'sugerido')` y `proc.estado IN ('abierto',
  'presupuestado')`, ordenada por `proc.vencimiento NULLS FIRST, numero_renglon`.

## Errores posibles (vía `core.exceptions`, mapeados a HTTP por `STATUS_MAP`)

| Excepción | HTTP | Origen |
|---|---|---|
| `NotFoundError` | 404 | Renglón inexistente en el chequeo del router (`router.py:33`); renglón inexistente re-chequeado dentro del service, en `confirmar_matching` (`service.py:148-149`) y `marcar_sin_match` (`service.py:195-196`). |
| `ForbiddenError` | 403 | Renglón de otra droguería, usuario no `superadmin` (`router.py:36-37`). |

No se encontró en el código de este módulo ningún `ConflictError` ni
`ValidationError` — a diferencia de `extraccion/`, no hay guardas de "ya procesado"
ni validaciones de formato de entrada más allá de las que impone Pydantic sobre
`ConfirmarMatchingRequest`.

## Quién consume `procesar_matching_item` (sin HTTP)

`procesar_matching_item` no tiene endpoint propio. Su único consumidor de código en
todo `services/presupuestacion/` es `extraccion/service.py:15,88-91`
(`_materializar_licitacion`), confirmado por grep cruzado en esta sesión — ver
[`arquitectura.md`](./arquitectura.md) y
[`../extraccion_validacion/arquitectura.md`](../extraccion_validacion/arquitectura.md#dependencia-hacia-matching)
para el mismo hallazgo documentado desde el lado del módulo consumidor.

## Quién consume los 3 endpoints HTTP

**Ningún frontend los consume todavía.** Grep de `"confirmar-matching"`, `"sin-match"`
y `"matching/pendientes"` sobre `frontend/` en esta sesión no tuvo resultados — el
directorio `frontend/` existe (`frontend/PROGRESS.md`, `frontend/README.md`) pero no
se encontró ningún llamador HTTP de estos 3 endpoints dentro del repositorio. Igual
que documenta [`../extraccion_validacion/casos_de_uso.md`](../extraccion_validacion/casos_de_uso.md)
para `POST /extracciones/{id}/validar`: el backend existe y está probado por
integración (`tests/matching/test_service.py`, 11 tests sobre `service.py`
directamente), pero no tiene consumidor de UI confirmado en esta sesión. No se
verificó `router.py` con ningún test dentro de `tests/matching/` — ver
[`pendientes.md`](./pendientes.md).
