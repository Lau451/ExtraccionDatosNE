# Casos de uso — Procesos Comerciales

Los 2 endpoints montados en `services/presupuestacion/main.py:49`
(`app.include_router(procesos_comerciales_router, tags=["procesos_comerciales"])`), sin
prefijo adicional.

Roles: `_ROLES_ESCRITURA = ("admin", "gerencia", "lider_comercial", "comercial")`,
`_ROLES_LECTURA = ("superadmin", "admin", "gerencia", "lider_comercial", "comercial",
"compras")` (`router.py:18-19`).

## `GET /procesos-comerciales`

- **Quién puede llamarlo**: los 6 roles de `_ROLES_LECTURA` — incluye `superadmin` y
  `compras`, que no tienen permiso de escritura en este módulo (`router.py:19`, `:25`).
- **Función**: `listar_procesos_comerciales_endpoint`, con `activos: bool = True`
  como query param.
- **Cliente Supabase**: `user_client` (con RLS) — ver [`flujo.md`](./flujo.md) Flujo 3.
- **Archivo**: `router.py:22-30`.

## `POST /procesos-comerciales`

- **Quién puede llamarlo**: `_ROLES_ESCRITURA` (`router.py:18`, `:36`) — no incluye
  `superadmin` ni `compras`.
- **Función**: `crear_proceso_comercial_endpoint`. Aplica RN-PROCESOS-001 (guarda de
  campos de seguimiento si `clase="cotizacion"`) y RN-PROCESOS-003 (auditoría).
- **Cliente Supabase**: `service_client` (sin RLS, vía
  `crear_proceso_comercial_para_endpoint`).
- **Archivo**: `router.py:33-40`.

## Consumidores de la tabla (con evidencia)

Ningún módulo de `presupuestacion/` **importa** `procesos_comerciales/` salvo
`main.py` (confirmado por grep en esta sesión). Fuera de ese Python, 5 módulos más 1
servicio externo leen o escriben directo sobre la tabla `procesos_comerciales`:

| Consumidor | Operación | Archivo:línea | Columnas / detalle |
|---|---|---|---|
| `matching/repository.py` | SELECT por `id` | `:14-22` | `id, drogueria_id, cliente_id`. |
| `extraccion/repository.py` (dentro de `presupuestacion/`) | SELECT por `id` | `:13-21` | `id, drogueria_id, cliente_id, clase`. |
| `pricing/repository.py` | SELECT por `id` | `:135-143` | `id, drogueria_id, cliente_id, clase`. |
| `pricing/router.py` | SELECT por `id`, inline | `:22-28` | `id, drogueria_id`, con `user_client`, sin pasar por el repository. |
| `compras/repository.py` | SELECT por `id` | `:6-14` | `id, drogueria_id, cliente_id`. |
| `compras/router.py` | SELECT por `id`, inline | `:50-56` | `id, drogueria_id`, con `user_client`, sin pasar por el repository. |
| `presupuestos/repository.py` | SELECT por `id` + **único UPDATE** | `:18-26` (SELECT), `:68-71` (UPDATE) | SELECT trae `id, drogueria_id, clase, estado`; UPDATE fuerza `estado="presentado"` desde `presupuestos/service.py:239-241` — ver [`estados.md`](./estados.md). |
| `services/extraccion/procesos_comerciales_client.py` (cross-servicio) | SELECT (validación + resolución de nombres) | `:30-77` (`validar_proceso_comercial_id`), `:80-114` (`listar_nombres_procesos_comerciales`) | `service_role` (bypasea RLS); filtro `drogueria_id` obligatorio en cada query, según el propio docstring del módulo (`:13-15`). |

**No se los incluye como consumidores de tabla** (verificado por grep en esta sesión,
para no sobre-reportar):

- `comparativas/`: no consulta `procesos_comerciales` directamente — usa una vista
  propia (`v_renglones_ganados`) para su lógica.
- `eventos/`: filtra su propia tabla de eventos por FK, sin consultar
  `procesos_comerciales` directamente.
- `automatizaciones/`: solo mapea el nombre de una columna, sin query propia contra
  `procesos_comerciales`.

Ver [`arquitectura.md`](./arquitectura.md) para el diagrama completo de acoplamiento y
[`base_de_datos.md`](./base_de_datos.md) para la tabla de CRUD real.
