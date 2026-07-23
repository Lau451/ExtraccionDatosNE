# Base de datos — Planes

Planes es el módulo dueño de la tabla `planes`, creada por
`supabase/migrations/0007_apellido_y_planes.sql:28-46`.

## `planes`

| Columna | Qué hace este módulo |
|---|---|
| `id` | PK, `gen_random_uuid()` por default (migración, línea 29). |
| `nombre` | NOT NULL. Solo lectura desde este módulo — usada para ordenar el listado (`router.py:18`). |
| `max_usuarios`, `max_documentos_mes`, `almacenamiento_mb` | INT, nullable = "sin límite" (comentario de la migración, línea 33). Expuestas en `PlanOut` pero sin ningún código en el repositorio que las lea para aplicar un límite — ver [`pendientes.md`](./pendientes.md) P1. |
| `funcionalidades` | JSONB, NOT NULL, default `{}`. Sin esquema fijo (comentario de la migración, línea 39). Expuesta en `PlanOut.funcionalidades: dict` (`models.py:10`) tal cual, sin tipado interno. |
| `activo` | BOOLEAN, NOT NULL, default `TRUE`. Único campo que sí tiene efecto funcional en este módulo: `GET /planes` filtra `.eq("activo", True)` (`router.py:18`) — un plan con `activo=false` deja de aparecer en el catálogo. |
| `created_at`, `updated_at` | Gestionadas por Postgres; `updated_at` tiene un trigger dedicado (`trg_planes_updated_at`, migración líneas 48-51). No leídas ni escritas por código Python de este módulo. |

**CRUD**: Solo Read desde este módulo (`router.py:11-18`, `SELECT * WHERE activo=True
ORDER BY nombre`). No hay Create/Update/Delete en `presupuestacion/planes/` — ver
[`decisiones.md`](./decisiones.md).

## RLS (`docs/schema/rls_final.sql:111-113` y migración `0007`, líneas 74-93)

| Policy | Operación | Condición |
|---|---|---|
| `planes_sel` | SELECT | `auth.role() = 'authenticated'` — cualquier usuario autenticado, sin distinción de rol ni de droguería (es un catálogo global, no tiene `drogueria_id`). |
| `planes_ins` | INSERT | `es_superadmin()` únicamente. |
| `planes_upd` | UPDATE | `es_superadmin()` únicamente. |
| `planes_del` | DELETE | `es_superadmin()` únicamente. |

Las 3 policies de escritura (`planes_ins`/`upd`/`del`) ya están definidas en la base de
datos y listas para un futuro CRUD administrado por `superadmin`, pero **hoy no las
usa ningún código de `presupuestacion/`** — no existe ningún endpoint en `router.py`
que haga `INSERT`/`UPDATE`/`DELETE` sobre `planes`. La carga de planes se hace por SQL
directo contra la base, fuera de la API. Ver [`pendientes.md`](./pendientes.md) P1.

`GRANT SELECT ON planes TO authenticated` y
`GRANT SELECT, INSERT, UPDATE, DELETE ON planes TO service_role` (migración, líneas
99-100) — necesarios porque, según el comentario de la propia migración, "Supabase no
auto-expone tablas nuevas al Data API".

## Relación con `droguerias`

`droguerias.plan_id` (columna agregada por la misma migración, nullable, `FOREIGN KEY
REFERENCES planes(id)`) es el único vínculo de esta tabla con el resto del schema. Se
gestiona enteramente desde [`../droguerias/`](../droguerias/) — este módulo no lee ni
escribe `droguerias` en ningún punto.
