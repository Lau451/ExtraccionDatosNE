# Módulo Imports — `services/presupuestacion/imports/`

## Qué es

Imports es el módulo de ingesta masiva de maestros desde sistemas externos: recibe
lotes (arrays) de filas por HTTP, hace upsert por código interno y **desactiva por
lote** lo que no vino en la carga más reciente. Cubre 5 entidades — productos, costos,
stock, proveedores y clientes — sobre 5 tablas que **no son propias de este módulo**:
las 5 pertenecen a [`catalogo/`](../catalogo/) (`productos`, `costos_productos`,
`stock_productos`, `proveedores`) y a [`clientes/`](../clientes/) (`clientes`).

El módulo tiene 5 archivos, 704 líneas en total (`models.py` 111, `repository.py` 185,
`service.py` 333, `router.py` 75, `__init__.py` 0 — verificado leyendo cada archivo en
esta sesión), 5 endpoints `POST`, sin máquina de estados propia. Es el módulo con el
archivo de test más largo de todo el proyecto: `tests/imports/test_service.py`, 598
líneas, 19 tests de integración (confirmado por conteo en esta sesión).

Es el **último módulo de `services/presupuestacion/` en documentarse** en este
proyecto — todos los demás módulos de negocio ya están documentados en
`docs/modulos/`.

## Qué NO hace

- **No ejecuta auditoría.** Confirmado por grep exhaustivo en esta sesión: 0
  referencias a `core.audit`, `registrar_cambio`, `registrar_cambios` o
  `registrar_evento_ciclo_vida` en los 4 archivos fuente. Es el caso más grave de este
  patrón —ya documentado también para [`catalogo/`](../catalogo/) y
  [`clientes/`](../clientes/)— porque acá una sola llamada HTTP puede crear, actualizar
  y **desactivar en lote** decenas o cientos de filas de una vez, sin dejar ningún
  rastro de quién lo hizo más allá de un `usuario_id` **fijo** (ver
  [`arquitectura.md`](./arquitectura.md) y [`pendientes.md`](./pendientes.md) P1).
- **No pasa por las validaciones de negocio de `catalogo/` ni de `clientes/`.** Los
  upserts de `imports/repository.py` van directo contra las tablas, sin invocar
  `catalogo.service` ni `clientes.service` — no aplican `exclude_unset` con la misma
  semántica, no resuelven `categoria_id`, no corren las validaciones de pertenencia de
  esos módulos.
- **No tiene `estados.md`.** No hay una máquina de estados: el campo `activo` que
  manipulan 3 de los 5 flujos es un booleano de reconciliación por lote, no un enum con
  transiciones — mismo criterio de omisión ya aplicado en Core, Usuarios, Clientes y
  Catálogo. Nota adicional de este módulo: de los 5 flujos, solo 3 (productos,
  proveedores, clientes) desactivan algo; costos versiona por fecha y stock hace upsert
  puro sin ningún concepto de "desactivado" — ver [`arquitectura.md`](./arquitectura.md).

## El hallazgo cruzado más importante: código paralelo y duplicado con `catalogo/` y `clientes/`

Este módulo **no reutiliza ningún código** de `catalogo/repository.py`,
`catalogo/service.py`, `clientes/repository.py` ni `clientes/service.py` para tocar las
mismas 5 tablas. Construye sus propias queries Supabase de punta a punta. Dos
consecuencias verificadas en esta sesión, ya señaladas como hallazgo cruzado desde
ambos lados:

1. **`imports/repository.py:141-185`** implementa un bloque `-- clientes --` con CRUD
   directo sobre `clientes` (`mapear_clientes_por_codigo`, `codigos_activos_clientes`,
   `insertar_clientes`, `actualizar_cliente`, `desactivar_clientes`), en paralelo a
   `clientes/repository.py`. Es, con evidencia directa desde este lado, el origen real
   de `codigo_interno` en `clientes`: `clientes.service.crear_cliente` nunca escribe
   ese campo (confirmado en [`../clientes/pendientes.md`](../clientes/pendientes.md)
   P3(4)); `imports/service.py:301` (`importar_clientes`) sí lo hace en el `INSERT`.
   Ver [`arquitectura.md`](./arquitectura.md) y [`../clientes/arquitectura.md`](../clientes/arquitectura.md).
2. **`imports/service.py:87-144`** (`importar_costos`) reimplementa **el mismo
   algoritmo** de versionado de costo que `catalogo.service.crear_costo`
   (`catalogo/service.py:195-218`, RN-CATALOGO-005/006): cerrar el costo vigente con
   `fecha_hasta = fecha_desde - 1 día` e insertar uno nuevo, sin escribir nada si el
   valor no cambió. La única diferencia de dato es `origen="import_sistema"`
   (`imports/service.py:115`, `:132`) contra `origen="manual"`
   (`catalogo/service.py:216`). Las dos implementaciones no comparten ninguna función:
   ver [`arquitectura.md`](./arquitectura.md) y D-IMPORTS-003 en
   [`decisiones.md`](./decisiones.md).

Además, `catalogo/repository.py:6` importa `DEPOSITO_SENTINEL` **desde este módulo**
(`imports/service.py:18`) — el acoplamiento inverso: un módulo de soporte (Imports)
define una constante de dominio que un módulo de negocio (Catálogo) consume. Ver
[`arquitectura.md`](./arquitectura.md).

## Mapa rápido de archivos

| Archivo | Qué hace |
|---|---|
| `imports/__init__.py` | Vacío. |
| `imports/models.py` | 10 modelos Pydantic (`ImportXRow`, `ImportXRequest`, `ImportXResultado` por cada una de las 5 entidades) y 3 `Literal` reexportados de forma independiente de `catalogo/models.py` y `clientes/models.py` (`Clasificacion`, `TipoProveedor`, `TipoCliente`). |
| `imports/repository.py` | Acceso a datos puro sobre 5 tablas ajenas a este módulo, en 4 bloques (`-- productos --`, `-- costos --`, `-- stock --`, `-- proveedores --`, `-- clientes --`), recibe siempre un `Client` inyectado. |
| `imports/service.py` | Los 5 algoritmos de reconciliación, `DEPOSITO_SENTINEL`, la resolución de `usuario_sistema_id`, y 5 wrappers `*_para_endpoint`. |
| `imports/router.py` | 5 endpoints `POST`, todos con el mismo tuple de roles `_ROLES_IMPORT`. |

## Dependencias

Igual que el resto de los módulos de negocio, depende de Core para autenticación
(`UsuarioPerfil`, `require_roles`), acceso a datos (`get_service_client` — **nunca**
`get_user_client`, ningún endpoint de este módulo usa RLS) y `core/config.get_settings`
para resolver `usuario_sistema_id`. No importa nada de `catalogo/` ni de `clientes/` —
la relación de acoplamiento va **al revés**: es `catalogo/` quien importa de acá (ver
arriba). Ver [`../core/`](../core/) para esas piezas — no se repite acá.

## Quién lo consume

Montado en `services/presupuestacion/main.py:17,50`
(`app.include_router(imports_router, tags=["imports"])`), prefijo `/imports`. **No se
encontró ningún consumidor** de los 5 endpoints en este repositorio: no hay carpeta
`scripts/`, y un grep de `import` sobre `frontend/src/` no encontró ninguna llamada a
`/imports/productos`, `/imports/costos`, `/imports/stock`, `/imports/proveedores` ni
`/imports/clientes` (confirmado en esta sesión). Ver
[`casos_de_uso.md`](./casos_de_uso.md) para el detalle.

## Documentos del módulo

- [`arquitectura.md`](./arquitectura.md) — los 5 flujos de reconciliación, el
  acoplamiento inverso de `DEPOSITO_SENTINEL`, la duplicación del versionado de costos
  con evidencia de ambos lados.
- [`base_de_datos.md`](./base_de_datos.md) — las 5 tablas tocadas, columnas y patrón de
  reconciliación por lote de cada una.
- [`reglas.md`](./reglas.md) — reglas de negocio (RN-IMPORTS-NNN).
- [`flujo.md`](./flujo.md) — flujo de importación paso a paso para productos y costos.
- [`casos_de_uso.md`](./casos_de_uso.md) — los 5 endpoints, roles y consumidores (o su
  ausencia).
- [`api.md`](./api.md) — API pública de cada archivo.
- [`decisiones.md`](./decisiones.md) — decisiones de diseño (D-IMPORTS-NNN).
- [`pendientes.md`](./pendientes.md) — auditoría técnica P1/P2/P3, con foco en ausencia
  de auditoría, duplicación de lógica de negocio y el acoplamiento inverso.

Para `UsuarioPerfil`, `require_roles`, `service_client` y el mecanismo de auditoría que
este módulo NO usa, ver [`../core/`](../core/) — no se repite esa documentación acá.
