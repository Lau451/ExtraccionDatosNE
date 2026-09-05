# Módulo Productos — `services/productos/`

> **Actualización (refactor `services/presupuestacion/catalogo/` → `services/productos/`)**:
> este módulo fue extraído de `services/presupuestacion/` a un paquete top-level
> `services/productos/`, sibling de `services/terceros/`. En el mismo refactor se
> **eliminó por completo** el wrapper de compatibilidad de `proveedores`
> (`crear_proveedor`/`listar_proveedores`/`obtener_proveedor`/`actualizar_proveedor`/
> `eliminar_proveedor`, endpoints `/proveedores*`) — no se movió, se borró, porque no
> tenía callers externos y la identidad + rol proveedor ya vive íntegramente en
> `services/terceros/` (ver [`../terceros/`](../terceros/)). El resto de este
> documento describe el estado **anterior** a esa eliminación en las secciones que
> todavía mencionan `proveedores`/`Proveedor*` — no se reescribió línea por línea como
> parte de este refactor puntual.

## Qué es

Productos gestiona el maestro de productos y categorías de una droguería, más el
costo histórico de cada producto y el stock disponible por depósito. Es el módulo
dueño de las 4 tablas `productos`, `categorias`, `costos_productos` y
`stock_productos` (`proveedores` es propiedad de `services/terceros/` desde el
refactor de la nota de arriba).

El módulo tiene 5 archivos (`models.py`, `repository.py`, `service.py`, `router.py`,
`__init__.py`) y 12 endpoints, sin máquina de estados propia. El conteo de líneas de
la tabla original de esta sección quedó desactualizado tras quitar el código de
`proveedores` y no fue recalculado en este refactor.

## Qué NO hace

- **No ejecuta auditoría.** Confirmado por grep en esta sesión: 0 referencias a
  `core.audit`, `registrar_cambio`, `registrar_cambios` o
  `registrar_evento_ciclo_vida` en los 4 archivos fuente. Ninguna mutación (alta/baja
  de producto o proveedor, edición de categoría, versionado de costo, ajuste de stock)
  queda registrada en `historial_cambios` — mismo hallazgo que en
  [`../clientes/`](../clientes/) y [`../usuarios/`](../usuarios/). Ver
  [`../core/`](../core/) para el mecanismo de auditoría que otros módulos sí usan, y
  [`pendientes.md`](./pendientes.md) P1.
- **No compromete stock.** `ajustar_stock` solo escribe `cantidad_disponible`; la
  columna `cantidad_comprometida` de `stock_productos` la mantiene exclusivamente el
  motor de compromiso de `core/stock.py` — comentario explícito en el código, ver
  RN-PRODUCTOS-010 en [`reglas.md`](./reglas.md). Para el detalle de ese motor
  (optimistic locking, liberar/comprometer/descontar), ver [`../core/`](../core/).
- **No gestiona la baja de categorías.** `categorias` no tiene soft-delete ni
  operación de borrado en `repository.py`, y `router.py` no expone
  `DELETE /categorias/{id}` — confirmado por grep en esta sesión. Ver
  RN-PRODUCTOS-004 en [`reglas.md`](./reglas.md) y D-PRODUCTOS-005 en
  [`decisiones.md`](./decisiones.md).
- **No tiene `estados.md`.** No hay una máquina de estados: los campos `activo`
  (productos, proveedores) y `activa` (categorías) son booleanos de negocio sin
  transiciones reguladas por este módulo — se pueden reactivar manualmente vía
  `PATCH` sin ninguna guarda. La vigencia de un costo se resuelve con
  `fecha_hasta IS NULL`, no con un enum de estados. Mismo criterio de omisión ya
  aplicado en Core, Usuarios y Clientes.

## Mapa rápido de archivos

| Archivo | Qué hace |
|---|---|
| `productos/__init__.py` | Vacío. |
| `productos/models.py` | 1 `Literal` (`Clasificacion`) y modelos Pydantic `Create`/`Update`/`Out` para Producto, Categoria, Costo y Stock. Ya no define `TipoProveedor` ni `Proveedor*` — eliminados con el wrapper de compatibilidad. |
| `productos/repository.py` | Acceso a datos puro sobre las 4 tablas, recibe siempre un `Client` inyectado. Único archivo del módulo con un import cruzado hacia otro paquete de negocio: `DEPOSITO_SENTINEL` de `services/presupuestacion/imports/service.py`. |
| `productos/service.py` | Reglas de negocio (tenant isolation, actualización parcial, versionado de costo, ajuste de stock) más 9 pares de wrappers `*_para_endpoint` que fijan `get_service_client()` (3 de producto, 2 de categoría, 2 de costo, 2 de stock — ya no hay 3 pares de proveedor). |
| `productos/router.py` | 12 endpoints HTTP (`/productos*`, `/categorias*`), con roles en 4 constantes (`_ROLES_LECTURA_CATALOGO`, `_ROLES_ESCRITURA_CATALOGO`, `_ROLES_ESCRITURA_CATEGORIAS`, `_ROLES_LECTURA_COSTOS` — nombres de constante sin renombrar en este refactor) más una excepción hardcodeada para el `DELETE` de producto. Ya no expone `/proveedores*` (5 endpoints eliminados). |

## Quién lo consume

Montado en `services/presupuestacion/main.py`
(`app.include_router(productos_router, tags=["productos"])`), sin prefijo adicional.
Ningún módulo de `presupuestacion/` **importa** código de `services.productos` salvo
`main.py` (verificado por grep al cerrar este refactor).

Sin embargo, es un módulo con acoplamiento a nivel de tabla ya documentado en este
proyecto: `matching/`, `pricing/`, `core/stock.py` e `imports/` leen o escriben
directo sobre `productos`/`costos_productos`/`stock_productos` sin pasar por este
código (`comparativas/repository.py` leía `proveedores` directo, pero esa tabla ya no
es de este módulo — ver [`../terceros/`](../terceros/)). Ver
[`arquitectura.md`](./arquitectura.md) para el detalle completo con evidencia de
línea, incluyendo un caso más grave que el documentado en
[`../clientes/arquitectura.md`](../clientes/arquitectura.md): la misma regla de
negocio de versionado de costo (RN-PRODUCTOS-006) está reimplementada de forma
independiente en `imports/service.py`.

## Documentos del módulo

- [`arquitectura.md`](./arquitectura.md) — dependencias hacia Core, el acoplamiento
  hacia `imports/service.py` (`DEPOSITO_SENTINEL`), y el diagrama del acoplamiento de
  tabla con los 5 módulos consumidores.
- [`base_de_datos.md`](./base_de_datos.md) — las 5 tablas, columnas, CRUD y quién más
  las toca.
- [`reglas.md`](./reglas.md) — reglas de negocio (RN-PRODUCTOS-NNN).
- [`flujo.md`](./flujo.md) — los 6 flujos principales paso a paso.
- [`casos_de_uso.md`](./casos_de_uso.md) — los 12 endpoints y quién puede invocarlos.
- [`api.md`](./api.md) — API pública de cada archivo.
- [`decisiones.md`](./decisiones.md) — decisiones de diseño (D-PRODUCTOS-NNN).
- [`pendientes.md`](./pendientes.md) — auditoría técnica P1/P2/P3.

Para `UsuarioPerfil`, `require_roles`, `service_client`/`user_client`, las excepciones
de dominio y el mecanismo de auditoría que este módulo NO usa, ver
[`../core/`](../core/) — no se repite esa documentación acá. Para un caso más chico
del mismo patrón de acoplamiento de tabla, ver
[`../clientes/arquitectura.md`](../clientes/arquitectura.md).
