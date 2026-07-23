# Casos de uso — Eventos

Los 11 endpoints montados en `services/presupuestacion/main.py:15`, `:53`
(`app.include_router(eventos_router, tags=["eventos"])`), sin prefijo adicional.

Roles: `_ROLES_LECTURA = ("superadmin", "admin", "gerencia", "lider_comercial",
"comercial", "compras")`, `_ROLES_ESCRITURA = ("admin", "gerencia", "lider_comercial",
"comercial", "compras")` (`router.py:32-33`).

## `eventos`

| Método | Path | Roles | Función | Archivo:línea |
|---|---|---|---|---|
| GET | `/eventos` | `_ROLES_LECTURA`, `estado`/`proceso_comercial_id`/`responsable_id` como filtros opcionales de query | `listar_eventos_endpoint` | `router.py:36-50` |
| POST | `/eventos` | `_ROLES_ESCRITURA` | `crear_evento_endpoint` — aplica RN-EVENTOS-001 | `router.py:53-57` |
| GET | `/eventos/{evento_id}` | `_ROLES_LECTURA` | `obtener_evento_endpoint` | `router.py:60-66` |
| PATCH | `/eventos/{evento_id}` | `_ROLES_ESCRITURA` | `actualizar_evento_endpoint` — solo campos enviados, `estado` limitado a `"cancelado"` (RN-EVENTOS-007) | `router.py:69-75` |
| POST | `/eventos/{evento_id}/completar` | `_ROLES_ESCRITURA` | `completar_evento_endpoint` — aplica RN-EVENTOS-002 (desbloqueo en cascada) | `router.py:78-84` |
| DELETE | `/eventos/{evento_id}` | `require_roles("admin", "gerencia")` — **más restrictivo que `_ROLES_ESCRITURA`**, excluye `lider_comercial`, `comercial` y `compras` | `eliminar_evento_endpoint`, soft delete, `204` sin body | `router.py:87-91` |
| GET | `/eventos/{evento_id}/bloqueo` | `_ROLES_LECTURA` | `obtener_bloqueo_endpoint`, expone `v_eventos_bloqueo` (`puede_avanzar`) | `router.py:94-100` |
| GET | `/calendario` | `_ROLES_LECTURA`, `desde`/`hasta` como filtros de query (`YYYY-MM-DD`, sin validación de formato en el endpoint) | `calendario_endpoint`, expone `v_calendario` | `router.py:103-110` |

## `eventos_recurrentes`

| Método | Path | Roles | Función | Archivo:línea |
|---|---|---|---|---|
| GET | `/eventos-recurrentes` | `_ROLES_LECTURA`, `activa` como filtro opcional | `listar_eventos_recurrentes_endpoint` | `router.py:113-119` |
| POST | `/eventos-recurrentes` | `_ROLES_ESCRITURA` | `crear_evento_recurrente_endpoint` — valida `RRULE` (RN-EVENTOS-003) | `router.py:122-128` |
| PATCH | `/eventos-recurrentes/{evento_recurrente_id}` | `_ROLES_ESCRITURA` | `actualizar_evento_recurrente_endpoint` | `router.py:131-142` |

**No existe** `DELETE /eventos-recurrentes/{id}` ni `GET /eventos-recurrentes/{id}`
(por id individual) — confirmado leyendo `router.py` completo (142 líneas, 11
endpoints exactos).

## Cliente Supabase por endpoint

Todos los endpoints de **escritura** (`POST`/`PATCH`/`DELETE`) resuelven
`get_service_client()` internamente a través de un wrapper `*_para_endpoint`
(`service.py:214-233`, `:296-313`) — el router no inyecta ningún cliente en esos casos.
Todos los endpoints de **lectura** (`GET`) inyectan `user_client` con
`Depends(get_user_client)` (`router.py:5`, `:42`, `:64`, `:98`, `:108`, `:117`). Mismo
patrón que D-PROCESOS-001 en el módulo Procesos Comerciales — ver
[`decisiones.md`](./decisiones.md).

## Consumidor cruzado (con evidencia)

`services/presupuestacion/automatizaciones/service.py:14-15` (`import EventoCreate` /
`import crear_evento`) es el **único** módulo de negocio de `presupuestacion/` que
importa código Python de `eventos/` — confirmado por `Grep` de
`from services.presupuestacion.eventos` en todo el repositorio en esta sesión, sin otras
coincidencias fuera de `eventos/` y `tests/eventos/` mismos.

El call site (`automatizaciones/service.py:99-110`, dentro de
`_ejecutar_accion`) arma un `EventoCreate` a partir de
`parametros_accion` de una `regla_automatizacion` más la FK de la entidad que disparó la
regla, y llama a `crear_evento(..., origen="automatico")` — el único punto de todo el
repositorio que usa ese valor de `origen` explícitamente. `automatizaciones/` no está
documentado todavía; se documentará completo como el próximo módulo de esta serie. Ver
[`README.md`](./README.md) y [`arquitectura.md`](./arquitectura.md) para el detalle.

No se encontró ningún otro consumidor — ni HTML/template legacy, ni otro backend, ni
`services/extraccion/` — que importe o consulte `eventos`/`eventos_recurrentes`.
