# Arquitectura — Droguerías

## Dependencias hacia Core

Droguerías no importa de ningún otro módulo de negocio de `presupuestacion/`
(confirmado por inspección de imports de los 4 archivos del módulo); depende
exclusivamente de Core.

| Import | Origen | Uso |
|---|---|---|
| `UsuarioPerfil`, `get_current_user`, `require_roles` | `core/auth.py` | Perfil del solicitante en los 2 `GET` (`get_current_user`) y autorización `superadmin` en los 3 `POST`/`PATCH`/`DELETE` (`require_roles("superadmin")`) — `router.py:4`. |
| `get_user_client` | `core/database.py` | Cliente con RLS, inyectado en los 2 `GET` (`router.py:5`). |
| `get_service_client` | `core/database.py` | Cliente sin RLS, resuelto internamente por los 3 wrappers `*_para_endpoint` de `service.py` (`service.py:6`). |
| `ConflictError`, `NotFoundError` | `core/exceptions.py` | Levantadas por `service.py` (`service.py:7`). |
| `NotFoundError` | `core/exceptions.py` | Levantada por `router.py` en `obtener_drogueria_endpoint` (`router.py:6`, `:35`). |

Ver [`../core/`](../core/) para la documentación de estas piezas — no se repite acá.

## Por qué los `GET` no pasan por `service.py`

A diferencia de Clientes (que sí concentra la lógica de lectura en `service.py`), los 2
endpoints `GET` de este módulo consultan la tabla `droguerias` **directo**, con
`user_client`, sin invocar ninguna función de `service.py` ni de `repository.py`:

- `GET /droguerias` (`router.py:17-24`): `user_client.table("droguerias").select("*").order("nombre").execute().data`.
- `GET /droguerias/{id}` (`router.py:27-36`): mismo patrón con `.eq("id", drogueria_id)`,
  levantando `NotFoundError` inline si no hay fila (`router.py:34-35`).

`repository.py:obtener_drogueria` (`repository.py:6-8`) existe pero **solo lo usa
`service.py`**, con `service_client` (sin RLS), como chequeo de existencia previo a
`UPDATE`/`DELETE` (`service.py:19`, `:28`) — nunca para responder un `GET`. El
resultado es una lectura con dos implementaciones distintas de la misma query
(`SELECT ... FROM droguerias WHERE id = ?`), una con RLS (router, expuesta por HTTP) y
otra sin RLS (service, interna) — mismo patrón de duplicación ya señalado para
Clientes, aunque aquí no hay revalidación de tenant cruzado (la tabla es la raíz del
tenant, no hay un `drogueria_id` de otra tabla contra el cual comparar). Ver
[`pendientes.md`](./pendientes.md) P3.

```
GET /droguerias, GET /droguerias/{id}
        │
  Depends(get_current_user)   ← cualquier rol autenticado, sin require_roles
        │
  Depends(get_user_client)    ← CON RLS (droguerias_sel)
        │
  query directa en router.py, sin pasar por service.py ni repository.py
        │
  RLS droguerias_sel: es_superadmin() OR id = get_drogueria_id()
  (docs/schema/rls_final.sql:101)
        │
        ▼
  superadmin ve todas las filas; cualquier otro rol solo la propia
```

```
POST/PATCH/DELETE /droguerias[/{id}]
        │
  Depends(require_roles("superadmin"))   ← única puerta de autorización
        │
  *_para_endpoint (service.py)
        │
  get_service_client() (SIN RLS)
        │
  [PATCH/DELETE] repo.obtener_drogueria → NotFoundError si no existe
  (service.py:19-21, :28-30)
        │
        ▼
  repository.py (INSERT/UPDATE/DELETE con service_client)
```

## Rol de esta tabla como raíz del multi-tenant

`droguerias` es la tabla de la que cuelga el aislamiento multi-tenant de todo
`presupuestacion/`: 36 tablas del schema tienen una columna `drogueria_id` que la
referencia (conteo verificado en esta sesión con un `awk` sobre los bloques
`CREATE TABLE` de `docs/schema/extractor_final.sql`, buscando `drogueria_id` dentro de
cada bloque). Este módulo no lee ni escribe ninguna de esas 36 tablas: solo gestiona la
fila de `droguerias` en sí. El puente entre "quién soy" y "de qué droguería soy" lo
resuelve `core/auth.py:39` (`SELECT id, drogueria_id, rol, activo FROM usuarios ...`),
fuera de este módulo — ver [`../core/`](../core/).

`droguerias.plan_id` (columna agregada por la migración `0007_apellido_y_planes.sql`,
ver [`../planes/`](../planes/)) es el único acoplamiento a nivel de esquema entre este
módulo y Planes; no hay import de Python entre ambos.
