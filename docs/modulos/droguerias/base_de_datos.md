# Base de datos — Droguerías

Droguerías es el módulo dueño de la tabla `droguerias`.

## `droguerias`

| Columna | Qué hace este módulo |
|---|---|
| `id` | PK. Generada por Postgres al insertar. |
| `nombre` | NOT NULL. Escrita al crear (`service.py:13`, vía `body.model_dump()`), actualizable parcialmente. Usada para ordenar el listado del router (`router.py:24`). |
| `razon_social` | NOT NULL. Escrita al crear, actualizable parcialmente. |
| `cuit` | NOT NULL. Validada en formato `NN-NNNNNNNN-N` por `_validar_formato_cuit` (`models.py:8-11`), aplicada tanto en `DrogueriaCreate` (obligatoria, `models.py:24`) como en `DrogueriaUpdate` (opcional, valida solo si se envía, `models.py:39-44`). Es validación de **formato**, no de dígito verificador — ver [`reglas.md`](./reglas.md) RN-DROGUERIAS-001. |
| `ciudad`, `provincia` | NOT NULL. Escritas al crear, actualizables parcialmente. |
| `codigo_postal` | Nullable. Escrita al crear, actualizable parcialmente. |
| `contacto_email`, `contacto_telefono` | NOT NULL. Escritas al crear, actualizables parcialmente. |
| `activa` | BOOLEAN. Solo en `DrogueriaUpdate`/`DrogueriaOut` (`models.py:36`, `:57`) — no en `DrogueriaCreate`, por lo que su valor inicial depende del `DEFAULT` de la columna en la base (no verificable desde este módulo). Escribible vía `PATCH`, pero **ningún query de este módulo la usa como filtro** — ver [`pendientes.md`](./pendientes.md) P2. |
| `plan_id` | Nullable, FK a `planes` (agregada por `supabase/migrations/0007_apellido_y_planes.sql:56-57`). Solo en `DrogueriaUpdate`/`DrogueriaOut` (`models.py:37`, `:58`) — no en `DrogueriaCreate`; una droguería nace sin plan asignado y se le asigna después vía `PATCH`. Ver [`../planes/`](../planes/). |

No hay columnas `created_by`/`updated_by`/`deleted_at`/`deleted_by` en este módulo (a
diferencia de `clientes`) — ni `models.py` ni `service.py` las mencionan.

**CRUD**: Create (`repository.py:11-12`), Read (`obtener_drogueria`,
`repository.py:6-8`, usada solo internamente por `service.py`; los `GET` HTTP
consultan la tabla directo desde `router.py`, ver [`arquitectura.md`](./arquitectura.md)),
Update (`repository.py:15-16`), **hard**-Delete (`repository.py:19-20` —
`DELETE FROM droguerias WHERE id = ?`, sin `deleted_at`).

## RLS (`docs/schema/rls_final.sql:101-104`)

A diferencia de Clientes, para este módulo sí se encontró el archivo de políticas RLS
en el repositorio (`docs/schema/rls_final.sql`), verificado en esta sesión:

| Policy | Operación | Condición |
|---|---|---|
| `droguerias_sel` | SELECT | `es_superadmin() OR id = get_drogueria_id()` — superadmin ve todas, cualquier otro rol solo la propia. |
| `droguerias_ins` | INSERT | `es_superadmin()` únicamente. |
| `droguerias_upd` | UPDATE | `es_superadmin() OR (get_rol() = 'admin' AND id = get_drogueria_id())` — **más permisiva que este módulo**: la policy dejaría a un `admin` editar la propia droguería, pero `router.py:46-52` restringe `PATCH /droguerias/{id}` a `require_roles("superadmin")` únicamente, y además el `UPDATE` real corre con `service_client` (sin RLS), por lo que esta policy no tiene ningún efecto práctico hoy sobre este endpoint. Ver [`decisiones.md`](./decisiones.md) D-DROGUERIAS-003. |
| `droguerias_del` | DELETE | `es_superadmin()` únicamente. |

Como los 3 endpoints de escritura de este módulo (`POST`, `PATCH`, `DELETE`) corren
con `service_client` (sin RLS) tras pasar `require_roles("superadmin")`, estas policies
no son la barrera efectiva de autorización para este módulo — lo es `require_roles`.
Sí lo son para `droguerias_sel`, porque los `GET` usan `user_client` directo.
