# Mapa de módulos — actual → objetivo

Qué módulo del código actual pasa a cuál módulo objetivo, qué funcionalidades
quedan juntas y qué desvíos hay que corregir en el camino. Los principios
(P1–P10) y decisiones (D-ARQ-NNN) se definen en [`README.md`](./README.md).

## Resumen

| Módulo objetivo | Capa | Viene de (hoy) | Estado |
|-----------------|------|----------------|--------|
| `plataforma` | Plataforma | `services/shared/` (ya contiene `auth`, `database`, `config`, `exceptions`, `auth_jwt`) + lo que queda de `presupuestacion/core` (`audit`, `texto`) + `auth`, `usuarios`, `droguerias`, `planes`, `auditoria`, `eventos`, `notificaciones` | **[IMPLEMENTADO]** en parte: `presupuestacion/core/{auth,database,config,exceptions}.py` ya son shims de reexport hacia `services/shared/` |
| `productos` | Maestros | `services/productos/` + `stock` (`presupuestacion/core/stock.py`) + import de catálogo (`presupuestacion/imports`) | **[IMPLEMENTADO]** como módulo top-level, sin fachada `api.py` |
| `terceros` | Maestros | `services/terceros/` + configuración por cliente (`presupuestacion/clientes`: formato de documentos y observaciones) | **[IMPLEMENTADO]** con fachada y test de dependencias |
| `comercial` | Negocio | `procesos_comerciales`, `matching`, `pricing`, `presupuestos`, `comparativas`, `extraccion` (materialización) | **[RECOMENDACIÓN]** — hoy son subcarpetas de `presupuestacion/` |
| `compras` (PCP) | Negocio | `services/pcp/` + `presupuestacion/compras` | **[IMPLEMENTADO]** como módulo top-level con fachada |
| `ordenes_compra` | Negocio | `oc_presupuesto`, `oc_entregas`, `oc_resumen`, `compromisos` | **[RECOMENDACIÓN]** — hoy cuatro carpetas sueltas |
| `integracion_progress` | Integración | `oc_export`, la parte Progress de `pcp/imports`, `progress_docs_dir` | **[RECOMENDACIÓN]** — ver [`integracion-progress.md`](./integracion-progress.md) |
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
| Todo lo que toca Progress | **Sale a `integracion_progress`** (D-ARQ-004) | Hoy está repartido entre `oc_export`, `pcp/imports` y `shared/config.py:35-37`, sin un dueño. |
| Extracción IA | **Sigue como proceso aparte** | Dependencias pesadas y consumo de memoria distinto (P8). |

## Desvíos conocidos a corregir

Cada desvío se corrige cuando el módulo se toque por otro motivo o cuando bloquee algo (P10).

| ID | Desvío | Evidencia | Principio |
|----|--------|-----------|-----------|
| X-ARQ-001 | Un dato maestro depende de un módulo de negocio. | `services/productos/router.py:4-5` y `services/productos/service.py:7-8` importan `services.presupuestacion.core` (el shim, en vez de `services.shared`); `services/productos/repository.py:6` importa una constante de `services.presupuestacion.imports`. | P3 |
| X-ARQ-002 | `pcp` llama a internos de otros módulos sin pasar por su fachada. | `services/pcp/negociacion/service.py:34-35` importa `presupuestacion.notificaciones.service` y `presupuestacion.pricing.service`. | P2 |
| X-ARQ-003 | La tabla `procesos_comerciales` la escriben varios módulos además de su dueño. | `services/pcp/imports/repository.py:66,187`, `services/presupuestacion/extraccion/repository.py:53`, `services/extraccion/procesos_comerciales_client.py:63,99`. | P1 |
| X-ARQ-004 | Lógica de versionado de costos duplicada entre `imports` y `productos`. | Documentado en [`../modulos/imports/`](../modulos/imports/README.md). | P1 |
| X-ARQ-005 | Roles escritos como tuplas en el código de cada módulo. | `services/pcp/roles.py:15-20`; `services/terceros/identidad/router.py:37-38`. | P7 |
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
- Cada módulo tiene un `tests/<modulo>/test_dependencias.py` que lo verifica.
