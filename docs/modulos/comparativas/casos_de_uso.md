# Casos de uso — Comparativas

Los 3 endpoints se montan sin prefijo propio en
`services/presupuestacion/main.py:11,46` (tag `"comparativas"`).

## `GET /procesos/{proceso_id}/renglones-ganados`

`router.py:21-27`.

- **Roles habilitados**: `superadmin`, `admin`, `gerencia`, `lider_comercial`,
  `comercial`, `compras` (`_ROLES_LECTURA`, `router.py:18`).
- **Path param**: `proceso_id: str` — el `proceso_comercial_id` a consultar.
- **Response**: `list[RenglonGanado]` (`models.py:10-21`) — ver
  [`base_de_datos.md`](./base_de_datos.md) para el detalle de cada campo.
- **Errores posibles**: ninguno propio — `ForbiddenError` (403) si el rol no está en
  `_ROLES_LECTURA` (manejado por `require_roles`, `core.auth`). Una lista vacía (200
  OK, `[]`) si el proceso no tiene renglones ganados o no existe — el endpoint no
  valida que `proceso_id` corresponda a un proceso comercial real.

## `GET /proveedores/sin-matchear`

`router.py:30-35`.

- **Roles habilitados**: mismos 6 que el endpoint anterior (`_ROLES_LECTURA`).
- **Sin path params ni query params.**
- **Response**: `list[OfertaSinMatchear]` (`models.py:24-28`).
- **Errores posibles**: solo `ForbiddenError` (403) por rol.

## `POST /ofertas/{oferta_id}/asignar-proveedor`

`router.py:38-59`.

- **Roles habilitados**: `admin`, `gerencia`, `lider_comercial`, `comercial`
  (`_ROLES_ASIGNAR`, `router.py:17`) — **no** incluye `superadmin` ni `compras` (ver
  RN-COMPARATIVAS-003).
- **Path param**: `oferta_id: str` — el `id` de la fila de `ofertas_items` a
  actualizar.
- **Body**: `AsignarProveedorRequest` (`models.py:6-7`) — un único campo
  `proveedor_id: str`.
- **Response**: `dict` (la fila completa de `ofertas_items` tras el `UPDATE`, sin
  `response_model` declarado en el decorador — a diferencia de los 2 `GET`, este
  endpoint no tipa su salida con un modelo Pydantic explícito).
- **Errores posibles** (vía `core.exceptions`, mapeados a HTTP por `STATUS_MAP`):

| Excepción | HTTP | Origen |
|---|---|---|
| `NotFoundError` | 404 | Oferta inexistente bajo RLS (`router.py:52-53`); oferta inexistente re-chequeada con `service_client` (`service.py:14-15`); proveedor inexistente (`service.py:18-19`). |
| `ForbiddenError` | 403 | Oferta de otra droguería, usuario no `superadmin` (`router.py:56-57`); rol fuera de `_ROLES_ASIGNAR` (`require_roles`). |
| `ValidationError` | 422 | Proveedor de otra droguería que la oferta (`service.py:20-21`, RN-COMPARATIVAS-001). |

### Secuencia interna

Ver [`flujo.md`](./flujo.md) Flujo 3 para el detalle paso a paso con líneas exactas.

## Quién consume estos endpoints

**Ningún frontend los consume todavía.** `Grep` de `renglones-ganados`,
`sin-matchear` y `asignar-proveedor` en todo el repositorio solo encontró
`router.py` — ningún cliente HTTP los invoca. `frontend/PROGRESS.md:15` confirma la
pantalla correspondiente:

| # | Pantalla | Estado |
|---|---|---|
| 7 | Comparativas | ⬜ Pendiente |

No hay `Glob` de `frontend/**/*comparativ*` que devuelva resultados — la pantalla no
tiene ni siquiera un stub de componente todavía, a diferencia de otros módulos
(ej. `extraccion_validacion`, que sí tiene un `openspec/changes/validar-extraccion/`
con `proposal.md` describiendo el flujo previsto). `Grep` de "comparativa" en
`openspec/` sí encuentra `openspec/changes/parser-router-comparatives-refactor/`, pero
ese change es sobre el pipeline de extracción IA del backend legacy
(`services/extraccion/robot_comparativas.py` — ver el aviso de "no confundir" al
inicio de [`README.md`](./README.md)), no sobre este módulo ni sus endpoints. No se
encontró ningún artefacto de planificación (openspec o similar) específico de este
módulo en esta sesión.
