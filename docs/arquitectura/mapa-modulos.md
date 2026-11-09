# Mapa de módulos — actual → objetivo

Qué módulo del código actual pasa a cuál módulo objetivo, qué funcionalidades
quedan juntas y qué desvíos hay que corregir en el camino. Los principios
(P1–P10) y decisiones (D-ARQ-NNN) se definen en [`README.md`](./README.md).

## Resumen

| Módulo objetivo | Capa | Viene de (hoy) | Estado |
|-----------------|------|----------------|--------|
| `plataforma` | Plataforma | `services/shared/` (ya contiene `auth`, `database`, `config`, `exceptions`, `auth_jwt`) + lo que queda de `presupuestacion/core` (`audit`, `texto`) + `auth`, `usuarios`, `droguerias`, `planes`, `auditoria`, `eventos`, `notificaciones` | **[IMPLEMENTADO]** en parte: `presupuestacion/core/{auth,database,config,exceptions}.py` ya son shims de reexport hacia `services/shared/` |
| `productos` | Maestros | `services/productos/` + `stock` (`presupuestacion/core/stock.py`) + import de catálogo (`presupuestacion/imports`) | **[IMPLEMENTADO]** como módulo top-level, sin fachada `api.py`; ya no depende de `presupuestacion` |
| `terceros` | Maestros | `services/terceros/` + configuración por cliente (`presupuestacion/clientes`: formato de documentos y observaciones) | **[IMPLEMENTADO]** con fachada y test de dependencias |
| `comercial` | Negocio | `procesos_comerciales`, `matching`, `pricing`, `presupuestos`, `comparativas`, `extraccion` (materialización) | **[RECOMENDACIÓN]** — hoy son subcarpetas de `presupuestacion/` |
| `compras` (PCP) | Negocio | `services/pcp/` + `presupuestacion/compras` | **[IMPLEMENTADO]** como módulo top-level con fachada |
| `ordenes_compra` | Negocio | `oc_presupuesto`, `oc_entregas`, `oc_resumen`, `compromisos` | **[RECOMENDACIÓN]** — hoy cuatro carpetas sueltas |
| `integracion_progress` | Integración | `oc_export` (escritura), la recepción del archivo de presupuestos de Progress, `progress_docs_dir` | **[IMPLEMENTADO]** etapa 1: fachada, registro, recepción manual y automática — ver [`integracion-progress.md`](./integracion-progress.md) |
| `extraccion_ia` | Capacidades | `services/extraccion/` (proceso aparte) | **[IMPLEMENTADO]** como unidad desplegable propia |
| `automatizaciones` / agentes | Capacidades | `presupuestacion/automatizaciones` | **[IMPLEMENTADO]** sin disparador real en producción |

## Lo que ya está bien encaminado

**[IMPLEMENTADO]** El patrón objetivo ya existe en tres módulos y es la referencia para el resto:

- `services/terceros/api.py` y `services/pcp/api.py` son fachadas que solo reexportan modelos y servicios. Lo que está fuera del módulo consume la fachada, no los internos.
- `tests/terceros/test_dependencias.py` y `tests/pcp/test_dependencias.py` verifican con `ast` la dirección de las dependencias. Este es el mecanismo que se generaliza para hacer cumplir P2 y P3.
- `services/extraccion` y `services/presupuestacion` son unidades desplegables separadas por su perfil de ejecución (`docker-compose.yml`), lo que cumple D-ARQ-002.
- La técnica de migración sin ruptura ya está probada: se mueve la implementación a su nuevo lugar y el archivo viejo queda como reexportación, para no romper los imports existentes (`services/presupuestacion/core/auth.py:1-8`, `services/presupuestacion/core/exceptions.py:1-5`). Se repite para cada movimiento de este mapa.

## Qué queda junto y por qué

| Grupo | Decisión | Motivo |
|-------|----------|--------|
| Procesos, matching, pricing, presupuestos, comparativas | **Un solo módulo `comercial`** (D-ARQ-006) | Comparten el ciclo de vida del proceso comercial y se escriben entre sí: `pricing` crea presupuestos y `presupuestos` cambia el estado del proceso. |
| Órdenes de compra, entregas, resumen, compromisos | **Un solo módulo `ordenes_compra`** | Es el mismo dominio (la OC del cliente y su cumplimiento) repartido en cuatro carpetas `oc_*`. |
| Productos y stock | **Un solo módulo `productos`** | El stock es un atributo operativo del producto. Hoy está en `core/stock.py`, que es plataforma, y lo consumen `presupuestos` y `compras`. |
| PCP y compras | **Un solo módulo `compras`** | Mismo dominio de abastecimiento. |

## Qué se separa y por qué

| Pieza | Decisión | Motivo |
|-------|----------|--------|
| Núcleo común | **Sale de `presupuestacion/` a `plataforma`** (D-ARQ-003) | Es la base de todos los módulos, pero vive dentro de uno de negocio. |
| Todo lo que toca Progress | **Sale a `integracion_progress`** (D-ARQ-004) | Hecho en la etapa 1: antes estaba repartido entre `oc_export`, `pcp/imports` y un parser del frontend. |
| Extracción IA | **Sigue como proceso aparte** | Dependencias pesadas y consumo de memoria distinto (P8). |

## Desvíos conocidos a corregir

Cada desvío se corrige cuando el módulo se toque por otro motivo o cuando bloquee algo (P10).

| ID | Desvío | Evidencia | Principio |
|----|--------|-----------|-----------|
| X-ARQ-001 | ~~Un dato maestro depende de un módulo de negocio.~~ **Resuelto:** `productos` importa de `services.shared` y `DEPOSITO_SENTINEL` vive en `services/productos/domain.py`. Lo protege `tests/arquitectura/test_capas.py`. | Antes: `services/productos/{router,service}.py` importaban el shim `services.presupuestacion.core`; `services/productos/repository.py:6` importaba `services.presupuestacion.imports`. | P3 |
| X-ARQ-002 | ~~`pcp` llama a internos de otros módulos sin pasar por su fachada.~~ **Resuelto en la etapa 4** (`odd/tasks/pcp-fachadas.md`): `services/pcp/**` importa solo fachadas `api.py` (`notificaciones`, `pricing`, `presupuestos`, `procesos_comerciales`, `productos`, `terceros`) y ya no nombra las tablas comerciales: las lee por `presupuestos/api.py` (`buscar_presupuesto`, `buscar_mapa_legacy_presupuesto`) y `procesos_comerciales/api.py` (`buscar_item_proceso`, `buscar_item_proceso_por_renglon`). Lo protegen `tests/pcp/test_dependencias.py` y `tests/arquitectura/test_duenos_tablas.py::test_pcp_does_not_access_comercial_tables`. | Antes: `services/pcp/negociacion/service.py:34-35` importaba `presupuestacion.notificaciones.service` y `presupuestacion.pricing.service`; cuatro servicios de `pcp` importaban `productos.service`; y seis repositorios de `pcp` leían `presupuestos`, `items_proceso` y `presupuesto_legacy_map` directo (seguimiento de la etapa 2). | P2 |
| X-ARQ-003 | ~~Las tablas comerciales (`procesos_comerciales`, `items_proceso`, `presupuestos`, `presupuesto_items`, `presupuesto_legacy_map`) las escribe `pcp` además de su dueño.~~ **Resuelto en la etapa 2** (`odd/tasks/procesos-comerciales-dueno.md`): el import legado de presupuestos vive en `services/presupuestacion/presupuestos/` detrás de `presupuestos/api.py`, y crea el proceso a través de `procesos_comerciales.service`. Lo protege `tests/arquitectura/test_duenos_tablas.py`. Las escrituras de `presupuestos`, `matching` y `presupuestacion/extraccion` son internas de `comercial` (D-ARQ-006); `services/extraccion/procesos_comerciales_client.py` solo lee. | Antes: `services/pcp/imports/repository.py` creaba y borraba procesos, presupuestos, ítems y el mapa legacy. Queda pendiente que `pcp` lea esas tablas por la fachada en lugar de directo. | P1 |
| X-ARQ-004 | ~~Lógica de versionado de costos duplicada entre `imports` y `productos`.~~ **Resuelto en la etapa 3** (`odd/tasks/costos-un-dueno.md`): la regla vive solo en `services/productos/service.py` y la importación de Progress la llama por `services/productos/api.py` (`versionar_costos`). Lo protege `tests/arquitectura/test_duenos_tablas.py`. | Antes: `services/presupuestacion/imports/{service,repository}.py` tenía su propia copia del algoritmo y escribía `costos_productos`. La etapa 7 ([`maestros-progress.md`](./maestros-progress.md)) dejó a `imports` como único escritor de las columnas de Progress en `productos`, `stock_productos` y `terceros`; sigue escribiéndolas directo porque es la puerta de entrada de Progress. | P1 |
| X-ARQ-005 | ~~Roles escritos como tuplas en el código de cada módulo.~~ **Resuelto en la etapa 5** (`odd/tasks/roles-capacidades.md`): cada acción es una capacidad de `services/shared/permisos.py` y los endpoints la piden con `require_capacidad`; el frontend usa `puede()` y `requireCapacidad()` con la lista de `GET /auth/capacidades`. Lo protegen `tests/arquitectura/test_permisos_centralizados.py` y `tests/arquitectura/test_capacidades_frontend.py`. | Antes: 48 tuplas y 6 `require_roles(...)` en 27 archivos del backend (por ejemplo `services/pcp/roles.py`) y 10 `roles.ts` en el frontend. Quedan fuera de la matriz la jerarquía de usuarios (`usuarios/service.py`), los destinatarios de notificaciones y las listas de roles de las políticas RLS. | P7 |
| X-ARQ-006 | `presupuestacion/main.py` monta 25 routers de dominios distintos. | `services/presupuestacion/main.py:52-76`. | P2, P10 |

## Reglas de dependencia objetivo

```
capacidades  ──►  negocio  ──►  maestros  ──►  plataforma
     │              │              │
     └──────────────┴──────────────┴──►  integracion_progress  ──►  plataforma
```

- Un módulo puede importar la fachada (`api.py`) de un módulo de su misma capa o de una capa inferior, nunca la de una capa superior.
- `plataforma` no importa ningún otro módulo.
- `integracion_progress` no escribe tablas ajenas: entrega datos a la fachada del dueño.
- `tests/arquitectura/test_capas.py` hace cumplir las reglas entre capas: `services/shared` no importa ningún otro módulo, y `productos` y `terceros` no importan módulos de negocio (`presupuestacion`, `pcp`). **[IMPLEMENTADO]**
- Las reglas propias de cada módulo van en su `tests/<modulo>/test_dependencias.py` (hoy existen para `terceros` y `pcp`).
