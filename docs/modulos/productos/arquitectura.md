# Arquitectura — Productos

> **Actualización (refactor `catalogo/` → `services/productos/`)**: el módulo se
> movió a `services/productos/` (top-level, sibling de `services/terceros/`). La
> sección "`comparativas/repository.py` — lectura de `proveedores`" de abajo describe
> un acoplamiento que ya no involucra a este módulo: `proveedores` es propiedad de
> `services/terceros/` desde antes de este refactor, y el wrapper de compatibilidad
> que este módulo mantenía sobre esa tabla se eliminó por completo (no se movió). El
> resto de esta página no fue reescrito línea por línea en este refactor.

## Dependencias hacia Core

Productos no importa de ningún otro módulo de negocio de `presupuestacion/` para su
lógica de dominio (roles, excepciones, clientes de Supabase); depende de Core para
eso. La única excepción es un import cruzado puntual hacia `imports/service.py`, ver
más abajo.

| Import | Origen | Uso |
|---|---|---|
| `UsuarioPerfil`, `require_roles` | `core/auth.py` | Perfil del solicitante y autorización por rol en los 12 endpoints (`router.py:38`). |
| `get_user_client` | `core/database.py` | Cliente con RLS, inyectado en los 6 endpoints `GET` de listados/detalle (`router.py:39`). |
| `get_service_client` | `core/database.py` | Cliente sin RLS, resuelto internamente por los 8 pares de wrappers `*_para_endpoint` de `service.py` (`service.py:18`). |
| `NotFoundError` | `core/exceptions.py` | Única excepción de dominio levantada por este módulo, en las 4 validaciones de pertenencia de `service.py` (`service.py:19`). |

Ver [`../core/`](../core/) para la documentación de estas piezas — no se repite acá.

## El único import cruzado: `DEPOSITO_SENTINEL` de `imports/service.py`

`repository.py:6` importa `DEPOSITO_SENTINEL` de
`services.presupuestacion.imports.service` — el único import de este módulo hacia
otro paquete de negocio o de soporte que no es `core/`:

```python
from services.presupuestacion.imports.service import DEPOSITO_SENTINEL
```

`DEPOSITO_SENTINEL = "unico"` está definido en `imports/service.py:18`. Productos lo
usa en dos puntos, ambos para resolver a qué depósito pertenece una fila de
`stock_productos` cuando no se especifica uno explícito:

- `repository.py:173` (`buscar_stock_por_deposito`): `valor = deposito if deposito
  else DEPOSITO_SENTINEL`.
- `service.py:247` (`ajustar_stock`): `"deposito": body.deposito if body.deposito
  else repo.DEPOSITO_SENTINEL` — accedido vía el módulo `repo` reexportado, no
  reimportado directo.

Ver RN-PRODUCTOS-009 en [`reglas.md`](./reglas.md) y D-PRODUCTOS-004 en
[`decisiones.md`](./decisiones.md) sobre el riesgo de este acoplamiento
negocio→soporte: si `imports/service.py` cambia el valor o el nombre de la constante,
o el módulo se elimina, `productos/repository.py` se rompe en tiempo de import.

## Separación de responsabilidad sobre `stock_productos` con `core/stock.py`

`stock_productos` tiene dos columnas de cantidad —`cantidad_disponible` y
`cantidad_comprometida`— y dos escritores independientes:

- **Productos** (`ajustar_stock`, `service.py:236-250`) escribe únicamente
  `cantidad_disponible`, vía `upsert_stock` (`repository.py:185-191`), con un
  comentario explícito en el código (cita textual verificada en RN-PRODUCTOS-010,
  [`reglas.md`](./reglas.md)) de que `cantidad_comprometida` es responsabilidad
  exclusiva de `core/stock.py`.
- **`core/stock.py`** mantiene `cantidad_comprometida` mediante
  `comprometer_stock_producto`/`liberar_compromisos` (optimistic locking vía
  `actualizar_comprometida_si_no_cambio`, `core/stock.py:31-41`), consumido por
  `compras/` y `presupuestos/` (ver [`../core/casos_de_uso.md`](../core/casos_de_uso.md)).

**Corrección relevante al descubrimiento previo de este módulo**: `core/stock.py`
**también** escribe `cantidad_disponible`, no solo `cantidad_comprometida`. La función
`_descontar_disponible_hasta` (`core/stock.py:242-270`), invocada desde
`entregar_stock_producto` (`core/stock.py:273-325`, al confirmar la entrega de una
orden de compra), descuenta `cantidad_disponible` con la misma técnica de optimistic
locking (`actualizar_disponible_si_no_cambio`, `core/stock.py:44-54`) que usa para
`cantidad_comprometida`. Es decir: la separación de responsabilidad no es "Productos
escribe disponible, Core escribe comprometida" en términos absolutos, sino "Productos
es el único escritor **manual/administrativo** de disponible; Core también la
descuenta como efecto de una entrega, con locking optimista".

Esto vuelve concreto —no solo teórico— el riesgo señalado en D-PRODUCTOS-003
([`decisiones.md`](./decisiones.md)): `productos.ajustar_stock` hace un `upsert` sin
ninguna comparación de valor esperado (`repository.py:185-191`), mientras que
`core/stock.py` sí usa `WHERE cantidad_disponible = valor_leído` antes de escribir
(`core/stock.py:47-54`). Si un ajuste manual de Productos y una entrega de OC caen
sobre la misma fila de `stock_productos` en una ventana de tiempo corta, el `upsert`
de Productos puede pisar el valor que `core/stock.py` acaba de descontar, porque
Productos no relee ni compara nada antes de escribir — el guard de optimistic locking
solo protege al escritor de Core, no a ambos.

## Acoplamiento a nivel de tabla (fuera de este código Python)

Cinco módulos de `presupuestacion/` leen o escriben directo sobre las 5 tablas de
Productos, sin pasar por `productos/repository.py` ni por `productos/service.py`. Es el
mismo patrón que documenta [`../clientes/arquitectura.md`](../clientes/arquitectura.md)
para `clientes`, pero con más consumidores y, en un caso, con la misma regla de
negocio reimplementada dos veces.

### `matching/repository.py` — lectura de `productos`

`matching/repository.py:40-49` (`listar_productos_activos`) hace
`SELECT id, nombre FROM productos WHERE drogueria_id=? AND activo=True AND
deleted_at IS NULL`, en paralelo a `productos.repository.listar_productos`. Documentado
en detalle, con el riesgo de escalabilidad de traer todo el catálogo a memoria para
fuzzy matching, en [`../matching/arquitectura.md`](../matching/arquitectura.md) y
[`../matching/pendientes.md`](../matching/pendientes.md).

### `comparativas/repository.py` — lectura de `proveedores`

`comparativas/repository.py:15` (`buscar_proveedor`) hace
`SELECT id, drogueria_id FROM proveedores WHERE id=?`, en paralelo a
`productos.repository.obtener_proveedor`.

### `pricing/repository.py` — lectura de `costos_productos`, `stock_productos` y `productos`

- `pricing/repository.py:57` (`buscar_costo_estandar_vigente`):
  `SELECT * FROM costos_productos WHERE producto_id=? AND fecha_hasta IS NULL` — la
  misma condición de vigencia que usa `productos.repository.costo_vigente`
  (`repository.py:137-146`), reimplementada de forma independiente.
- `pricing/repository.py:114` (`buscar_stock_libre`): lee
  `cantidad_disponible, cantidad_comprometida` de `stock_productos` y calcula
  `disponible - comprometida` en Python.
- `pricing/repository.py:126` (`buscar_producto`): `SELECT id, categoria_id,
  drogueria_id FROM productos WHERE id=?`.

### `core/stock.py` — motor de compromiso sobre `stock_productos`

Ya documentado en [`../core/`](../core/) como módulo propio; ver la sección anterior
de esta página para el detalle de qué columnas toca y cómo interactúa con
`productos.ajustar_stock`. Puntos de acceso a la tabla: `core/stock.py:17`
(`listar_stock_por_producto`), `:27` (`buscar_fila_stock`), `:35`
(`actualizar_comprometida_si_no_cambio`), `:48` (`actualizar_disponible_si_no_cambio`).

### `imports/repository.py` — CRUD masivo directo sobre las 5 tablas

`imports/repository.py` implementa cuatro bloques hermanos con CRUD directo por
carga masiva, sin relación de código con `productos/repository.py`:

- `-- productos --` (líneas 5-61): incluye un **upsert masivo**
  (`actualizar_productos_existentes`, `repository.py:37-39`) con
  `on_conflict="drogueria_id,codigo_interno"`, que no pasa por ninguna validación de
  `productos.service` (ni `exclude_unset`, ni resolución de `categoria_id`, etc.).
- `-- costos --` (líneas 64-84).
- `-- stock --` (líneas 87-91).
- `-- proveedores --` (líneas 94-138).

### `imports/service.py` — la misma regla de versionado de costo, reimplementada

Este es el hallazgo más relevante de acoplamiento verificado en esta sesión, no
presente en el descubrimiento previo con este nivel de detalle:
`imports/service.py:87-138` (`importar_costos`) reimplementa **exactamente el mismo
algoritmo** que `productos.service.crear_costo` (`service.py:195-218`,
RN-PRODUCTOS-005/006) — cerrar el costo vigente con `fecha_hasta = fecha_desde - 1
día` e insertar uno nuevo, sin escribir nada si el valor no cambió — con una sola
diferencia de dato: `origen="import_sistema"` (`imports/service.py:115`, `:132`) en
vez de `origen="manual"` (`service.py:216`, RN-PRODUCTOS-007). Las dos
implementaciones no comparten ninguna función: si la regla de negocio cambiara (por
ejemplo, el criterio de cierre de fecha), habría que modificar ambos archivos de
forma consistente sin que exista un punto único de verdad — ver
[`pendientes.md`](./pendientes.md) P2.

```
                 productos / categorias / proveedores /
                 costos_productos / stock_productos
                            │
     ┌──────────┬───────────┼───────────┬──────────────┬─────────────┐
     │          │           │           │              │             │
productos/   matching/  comparativas/ pricing/     core/stock.py  imports/
(dueño)     (lee       (lee          (lee          (compromete/  (CRUD masivo +
            productos) proveedores)  costos,       descuenta      versionado de
                                     stock,        comprometida/  costo duplicado)
                                     productos)    disponible)
```

Ningún módulo de este diagrama importa código Python de otro para acceder a estas
tablas — cada uno construye sus propias queries Supabase. Ver
[`casos_de_uso.md`](./casos_de_uso.md) para el detalle de consumidores con evidencia
completa.
