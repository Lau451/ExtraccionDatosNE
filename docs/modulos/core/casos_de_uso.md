# Casos de uso — Consumidores de Core

Listado de quién usa cada pieza de Core y para qué, con al menos un call site real por
consumidor. Los conteos de archivos fueron verificados con búsqueda de texto sobre
`services/presupuestacion/` en esta sesión.

## `core/database.py` (`get_service_client` / `get_user_client`)

`get_service_client` se importa en 14 módulos de negocio/soporte de `presupuestacion/`
(todos `service.py`, ninguno `router.py` — ver RN-CORE-016): `automatizaciones`,
`catalogo`, `clientes`, `comparativas`, `compras`, `eventos`, `extraccion`, `imports`,
`matching`, `notificaciones`, `presupuestos`, `pricing`, `procesos_comerciales`,
`usuarios`. [IMPLEMENTADO]

`get_user_client` (directo o vía `core/auth.py`) es la vía de acceso a datos de
prácticamente todos los `router.py` de `presupuestacion/`, para que las consultas
respeten RLS por droguería. [IMPLEMENTADO]

- Evidencia: `services/presupuestacion/auditoria/router.py:6`, `:18` (uso directo de
  `get_user_client` sin pasar por `core/auth.py`, junto con `require_roles`).

## `core/exceptions.py`

Usado transversalmente: 26 archivos de `services/presupuestacion/` importan de
`core/exceptions.py`, incluyendo prácticamente todos los `service.py` y varios
`router.py` (`pricing/router.py`, `presupuestos/router.py`, `usuarios/router.py`,
`clientes/router.py`, `matching/router.py`, `extraccion/router.py`,
`compras/router.py`, `comparativas/router.py`) además del propio `main.py` (registro de
handlers). [IMPLEMENTADO]

- Evidencia: `services/presupuestacion/main.py:14`, `:32`
  (`register_exception_handlers(app)`).

## `core/audit.py`

Usado por 6 `service.py` de negocio para dejar rastro de cambios de estado/campo y
eventos de ciclo de vida: `procesos_comerciales`, `eventos`, `extraccion`,
`presupuestos`, `pricing`, `compras`. [IMPLEMENTADO]

- Evidencia:
  - `services/presupuestacion/procesos_comerciales/service.py:5`, `:60`
    (`registrar_evento_ciclo_vida` al dar de alta un proceso comercial).
  - `services/presupuestacion/eventos/service.py:8`, `:73`, `:128`, `:153`, `:170`,
    `:189`, `:342` (uso de las tres funciones de `core/audit.py`, el consumidor con más
    call sites).
  - `services/presupuestacion/presupuestos/service.py:8`, `:76`, `:116`, `:227`, `:242`
    (`registrar_cambio` en presentación, aprobación y otros cambios de estado — ver
    Flujo A).
  - `services/presupuestacion/compras/service.py:17`, `:99`, `:136`.
  - `services/presupuestacion/pricing/service.py:8`, `:264`, `:296`.
  - `services/presupuestacion/extraccion/service.py:9`, `:173`, `:185`.

## `core/auth.py` (`require_roles` / `get_current_user`)

`require_roles` se usa en 14 `router.py` de `presupuestacion/`:
`procesos_comerciales`, `pricing`, `presupuestos`, `auditoria`, `automatizaciones`,
`eventos`, `usuarios`, `catalogo`, `clientes`, `imports`, `matching`, `extraccion`,
`compras`, `comparativas`. [IMPLEMENTADO]

- Evidencia: `services/presupuestacion/auditoria/router.py:5`, `:17`
  (`require_roles(*_ROLES_LECTURA)`).

`get_current_user` se usa **directamente**, sin pasar por `require_roles` — es decir,
solo exigiendo autenticación válida, sin restricción de rol — en exactamente 2 routers:
`usuarios/router.py` y `notificaciones/router.py`. [IMPLEMENTADO]

- Evidencia: `services/presupuestacion/usuarios/router.py:4`, `:15`, `:24`;
  `services/presupuestacion/notificaciones/router.py:4`, `:24`, `:35`, `:42`, `:49`,
  `:59` (6 endpoints de este router usan `get_current_user` directo). Ninguno de los
  dos routers restringe por rol específico — cualquier usuario autenticado puede
  invocar estos endpoints (sujeto a lo que permita RLS sobre los datos). Ver
  `pendientes.md` P3(3).

## `core/stock.py`

Solo 2 consumidores dentro de `presupuestacion/`: `presupuestos/service.py` y
`compras/service.py`. [IMPLEMENTADO]

- Evidencia: `services/presupuestacion/presupuestos/service.py:206`
  (`stock.comprometer_stock_producto`, Flujo A);
  `services/presupuestacion/compras/service.py:273`
  (`stock.entregar_stock_producto`, Flujo D).

## `core/texto.py` (`normalizar_descripcion`)

Solo 2 consumidores: `extraccion/service.py` (de `presupuestacion/`) y
`matching/service.py`. [IMPLEMENTADO]

- Evidencia: `services/presupuestacion/extraccion/service.py:12`, `:81`
  (normaliza la descripción extraída de un documento antes de guardarla).
  `services/presupuestacion/matching/service.py:9`, `:24`, `:43`, `:159` (normaliza
  tanto la descripción del ítem a matchear como los nombres de productos candidatos,
  para comparación).

## `core/config.py` (`get_settings`)

Usado en `main.py` (para configurar CORS) y en `imports/service.py` (para resolver
`usuario_sistema_id`), además de internamente en `core/auth.py` y `core/database.py`.
[IMPLEMENTADO]

- Evidencia: `services/presupuestacion/main.py:13`, `:36`
  (`get_settings().cors_origins_list` como `allow_origins` del `CORSMiddleware`).
  `services/presupuestacion/imports/service.py:6`, `:22`
  (`get_settings().usuario_sistema_id`).

## `shared/auth_jwt.py`

Único código compartido entre los dos backends del monorepo: `services/extraccion/` y
`services/presupuestacion/`. [IMPLEMENTADO]

- Evidencia en `services/presupuestacion/`: `services/presupuestacion/core/auth.py:10`,
  `:26` (`verificar_token` dentro de `get_current_claims`, exigencia obligatoria de
  identidad — ver Flujo B).
- Evidencia en `services/extraccion/`: `services/extraccion/auth.py:18`, `:50`
  (`verificar_token` dentro de `get_usuario_id_actual`). A diferencia de
  `presupuestacion/`, en `extraccion/` la identificación es **opcional**: si no viene
  token, la request sigue funcionando de forma anónima
  (`services/extraccion/auth.py:1-11`, docstring del módulo); si viene un token
  inválido, sí se rechaza con 401 (`services/extraccion/auth.py:51-52`).
