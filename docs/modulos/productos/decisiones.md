# Decisiones de diseño — Productos

Numeración D-PRODUCTOS-NNN, verificada contra el código en esta sesión.

> **Actualización (refactor `catalogo/` → `services/productos/`)**: el módulo se
> extrajo de `services/presupuestacion/catalogo/` a un paquete top-level
> `services/productos/`, sibling de `services/terceros/`. En el mismo refactor se
> **eliminó por completo** el wrapper de compatibilidad de `proveedores` descrito en
> la nota siguiente (no se movió a `services/productos/`): `crear_proveedor`,
> `listar_proveedores`, `obtener_proveedor`, `actualizar_proveedor`,
> `eliminar_proveedor`, `ProveedorCreate`/`Update`/`Out` y los endpoints
> `/proveedores*` ya no existen en este módulo. Confirmado sin callers externos antes
> de borrar. La nota de la Fase 8/10 de abajo queda como registro histórico de por qué
> el wrapper existió.

> **Actualización (change `terceros-modelo`, Fase 8/10)**: `productos/` dejó de ser
> dueño de la identidad de `proveedores` (D2/D5, ver
> [`../terceros/decisiones.md`](../terceros/decisiones.md)). `repository.py` eliminó
> por completo la sección de proveedores; `service.py` mantiene un wrapper de
> compatibilidad (`crear_proveedor`/`listar_proveedores`/`obtener_proveedor`/
> `actualizar_proveedor`/`eliminar_proveedor`, mismos endpoints `/proveedores`) que
> internamente orquesta `services.terceros.api` — decisión explícita tomada en esa
> sesión en vez de repuntar a los llamadores directamente a la fachada, porque el grep
> de esa sesión confirmó que ningún otro módulo importa `productos.service`/
> `productos.repository` para proveedores (blast radius cero). `eliminar_proveedor`
> desactiva solo el rol (D1/D4), no borra al tercero — mismo patrón que
> `eliminar_cliente` (ver [`../clientes/decisiones.md`](../clientes/decisiones.md)
> D-CLIENTES-006). `ProveedorCreate`/`Update`/`Out` cambiaron
> `plazo_pago_dias`/`condiciones_pago` (texto libre) por `condicion_pago_id`/
> `forma_pago_id` (FK a `services.terceros.catalogos`).

### D-PRODUCTOS-001 — Función pura + wrapper `_para_endpoint` en 12 pares

- **Decisión**: cada operación de escritura y cada lectura que depende de un
  `producto_id` tiene dos versiones: una función "pura" que recibe `client: Client`
  explícito, y un wrapper `*_para_endpoint` sin ese parámetro, que resuelve
  `get_service_client()` internamente y delega en la pura. Confirmado por grep en
  esta sesión: 12 funciones `_para_endpoint` en `service.py` (3 de producto, 2 de
  categoría, 3 de proveedor, 2 de costo, 2 de stock) — corrige el conteo de "8
  pares" del descubrimiento previo del módulo.
- **Motivo**: pendiente de definición funcional. No hay comentario en el código que
  explique por qué se separan ambas capas; el patrón es idéntico al que ya
  documentan [`../clientes/decisiones.md`](../clientes/decisiones.md) D-CLIENTES-001
  y [`../usuarios/decisiones.md`](../usuarios/decisiones.md) para sus propios
  módulos, con la misma ausencia de justificación explícita.
- **Ventajas**: las funciones puras son testeables sin pasar por FastAPI ni por la
  resolución del token JWT — de hecho, `tests/productos/test_service.py` importa y
  llama únicamente a las versiones puras (`crear_producto`, `actualizar_producto`,
  etc., líneas 17-35), nunca a los wrappers `_para_endpoint`.
- **Desventajas**: duplica la superficie pública de `service.py` (24 funciones para
  cubrir 12 operaciones lógicas) sin agregar lógica nueva en el wrapper más allá de
  resolver el cliente — ver [`pendientes.md`](./pendientes.md) P3.

### D-PRODUCTOS-002 — Versionado de costo por cierre + alta, en vez de `UPDATE` del `costo_unitario`

- **Decisión**: cuando cambia el costo de un producto, `crear_costo` no actualiza la
  fila vigente: la cierra (`fecha_hasta`) y crea una fila nueva
  (`service.py:204-218`).
- **Motivo**: pendiente de definición funcional — no hay comentario explícito en el
  código. Inferido de la estructura de la tabla (`fecha_desde`/`fecha_hasta` como
  rango de vigencia) y de que `pricing/repository.py:57`
  (`buscar_costo_estandar_vigente`) y otros consumidores dependen de poder filtrar
  por `fecha_hasta IS NULL`.
- **Ventajas**: permite reconstruir qué costo estaba vigente en cualquier fecha
  pasada, sin perder el histórico — capacidad que un `UPDATE` in-place destruiría.
- **Desventajas**: las dos escrituras (`cerrar_costo_vigente` + `crear_costo`,
  `service.py:206` y `:208-218`) no están envueltas en una transacción explícita a
  nivel de aplicación — si el proceso falla entre ambas, la tabla queda con **dos**
  filas vigentes (`fecha_hasta IS NULL`) para el mismo producto, violando la
  invariante que asume `costo_vigente` (`repository.py:137-146`, que usa `.limit(1)`
  y devolvería una de las dos de forma no determinística). No se pudo confirmar en
  esta sesión si existe una constraint de base de datos que lo prevenga.

### D-PRODUCTOS-003 — Separación explícita entre ajuste manual de stock (Productos) y compromiso automático (`core/stock.py`)

- **Decisión**: `ajustar_stock` escribe únicamente `cantidad_disponible`;
  `cantidad_comprometida` es responsabilidad exclusiva de `core/stock.py`.
- **Motivo**: cita textual verificada del docstring, `service.py:239-240`:

  > "Ajuste manual de cantidad_disponible. NO toca cantidad_comprometida — esa la
  > mantiene únicamente el motor de compromiso de stock (core/stock.py)."

- **Ventajas**: responsabilidades claras sobre `cantidad_comprometida` — un solo
  escritor, con optimistic locking, evita que un ajuste manual pise una promesa de
  stock ya comprometida a un cliente.
- **Desventajas**: la separación no es tan limpia como sugiere el comentario.
  Verificado en esta sesión: `core/stock.py` **también** escribe
  `cantidad_disponible` — `_descontar_disponible_hasta`
  (`core/stock.py:242-270`), invocada desde `entregar_stock_producto`
  (`core/stock.py:273-325`) al confirmar una entrega de orden de compra. Esa función
  usa optimistic locking (`WHERE cantidad_disponible = valor_leído`,
  `core/stock.py:44-54`); `productos.ajustar_stock` en cambio hace un `upsert` sin
  ninguna comparación de valor esperado (`repository.py:185-191`). Dos módulos
  escriben la misma columna con dos técnicas distintas, y solo una de ellas se
  protege contra escrituras concurrentes — riesgo de que un ajuste manual
  sobrescriba silenciosamente un descuento de entrega que ocurrió en el medio, o
  viceversa. Es una hipótesis razonable a partir de la lectura del código, no un bug
  reproducido en esta sesión — ver [`pendientes.md`](./pendientes.md) P2.

### D-PRODUCTOS-004 — Reutilizar `DEPOSITO_SENTINEL` de `imports/service.py` en vez de definirlo en Productos

- **Decisión**: `repository.py:6` importa la constante `DEPOSITO_SENTINEL = "unico"`
  desde `services.presupuestacion.imports.service` (definida en
  `imports/service.py:18`) en vez de declarar su propia constante.
- **Motivo**: pendiente de definición funcional — no hay comentario en el código que
  explique por qué el valor vive en `imports/` en vez de en `productos/`, siendo que
  ambos módulos lo consumen.
- **Ventajas**: valor consistente entre la carga masiva de stock
  (`imports/repository.py:89-91`) y el ajuste manual de este módulo — un mismo
  producto sin depósito específico cae siempre en la misma fila de
  `stock_productos`, sin importar qué flujo lo escribió.
- **Desventajas**: acoplamiento negocio→soporte en la dirección menos intuitiva —
  `productos/` (que documentalmente aparenta ser el módulo "dueño" de `productos` y
  `stock_productos`) depende de un módulo de carga masiva para una constante de
  dominio propio. Si `imports/service.py` renombra o elimina
  `DEPOSITO_SENTINEL`, `productos/repository.py` se rompe en tiempo de import, sin
  que el nombre del módulo lo sugiera.

### D-PRODUCTOS-005 — Categorías sin soft-delete ni endpoint de eliminación

- **Decisión**: `repository.py` no define ninguna función de borrado para
  `categorias`; `router.py` no expone `DELETE /categorias/{id}`.
- **Motivo**: pendiente de definición funcional — no hay comentario en el código.
- **Ventajas**: evita productos huérfanos por categoría borrada — como
  `productos.categoria_id` no tiene `ON DELETE` documentado en este código y no hay
  forma de eliminar una categoría por esta API, no puede darse el caso de un
  producto apuntando a una categoría inexistente por esta vía.
- **Desventajas**: no hay forma de archivar una categoría creada por error salvo
  reutilizar `activa=False` (RN-PRODUCTOS-004) — que, a diferencia de
  `productos.activo`, sí es filtrable en `listar_categorias`
  (`repository.py:64-65`), por lo que al menos tiene efecto funcional real, a
  diferencia del caso ya documentado de `cliente_contactos.activo` en
  [`../clientes/pendientes.md`](../clientes/pendientes.md) P3(2).
