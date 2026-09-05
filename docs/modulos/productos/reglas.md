# Reglas — Catálogo

Todas las reglas fueron verificadas contra el código real (`service.py`, `router.py`)
y sus tests (`tests/catalogo/test_service.py`) en esta sesión.

### RN-CATALOGO-001 — Un producto o proveedor solo es consultable/modificable si pertenece a la droguería del solicitante

- **Descripción**: `obtener_producto` y `obtener_proveedor` (service) buscan la fila
  por `id` y validan que su `drogueria_id` coincida con el del solicitante; si no
  coincide (o no existe), ambos casos se tratan igual: `NotFoundError`, sin
  distinguir uno del otro.
- **Condición**: `producto is None or producto["drogueria_id"] != drogueria_id`
  (análogo para proveedor).
- **Resultado**: `NotFoundError("No se encontró el producto")` /
  `NotFoundError("No se encontró el proveedor")`.
- **Prioridad**: Alta.
- **Archivo**: `services/presupuestacion/catalogo/service.py:51-55` (producto),
  `:149-153` (proveedor).
- **Observaciones**: [IMPLEMENTADO]. `obtener_producto` es reutilizada como primer
  paso por `actualizar_producto` (`service.py:61`) y `eliminar_producto`
  (`service.py:68`); `obtener_proveedor` de igual forma por `actualizar_proveedor`
  (`service.py:159`) y `eliminar_proveedor` (`service.py:166`). Verificada para
  producto en `tests/catalogo/test_service.py:87-97`
  (`test_obtener_producto_de_otra_drogueria_lanza_not_found`). No se encontró un test
  equivalente explícito para proveedor en este archivo — la implementación es
  idéntica en código, pero su cobertura de test queda sin confirmar en esta sesión.

### RN-CATALOGO-002 — Las actualizaciones de producto, categoría y proveedor son parciales

- **Descripción**: solo se pisan los campos enviados explícitamente en el body; los
  campos no incluidos en el `PATCH` no se tocan.
- **Condición**: cualquier llamada a `actualizar_producto`, `actualizar_categoria` o
  `actualizar_proveedor`.
- **Resultado**: `body.model_dump(exclude_unset=True)` — `service.py:62` (producto,
  con `updated_by` agregado después en `:63`), `service.py:106` (categoría, sin
  campo `updated_by`), `service.py:160` (proveedor, con `updated_by` en `:161`).
- **Prioridad**: Alta.
- **Archivo**: `services/presupuestacion/catalogo/service.py:62`, `:106`, `:160`.
- **Observaciones**: [IMPLEMENTADO]. Verificada en
  `tests/catalogo/test_service.py:100-120`
  (`test_actualizar_producto_solo_pisa_campos_enviados`, confirma que `nombre` no se
  pierde al actualizar solo `laboratorio`), `tests/catalogo/test_service.py:147-161`
  (`test_crear_y_actualizar_categoria`, confirma que `nombre` no se pierde al
  actualizar solo `activa`) y `tests/catalogo/test_service.py:177-210`
  (`test_crear_listar_actualizar_y_eliminar_proveedor`, confirma que `razon_social` no
  se pierde al actualizar solo `plazo_pago_dias`, líneas 192-200).

### RN-CATALOGO-003 — La baja de producto y proveedor es siempre soft-delete

- **Descripción**: no existe una vía en este módulo para borrar físicamente una fila
  de `productos` o `proveedores`. `DELETE` marca `deleted_at`, `deleted_by` y fuerza
  `activo=False`.
- **Condición**: cualquier llamada exitosa a `eliminar_producto`/`eliminar_proveedor`.
- **Resultado**: `repo.soft_delete_producto(...)` / `repo.soft_delete_proveedor(...)`
  — `UPDATE`, nunca `DELETE`.
- **Prioridad**: Alta.
- **Archivo**: `services/presupuestacion/catalogo/repository.py:46-53` (producto),
  `:114-121` (proveedor); invocadas desde `service.py:69` y `:167`.
- **Observaciones**: [IMPLEMENTADO]. Verificada en
  `tests/catalogo/test_service.py:123-140`
  (`test_eliminar_producto_soft_delete`, confirma que `obtener_producto` deja de
  encontrarlo tras el borrado) y `tests/catalogo/test_service.py:177-210`
  (`test_crear_listar_actualizar_y_eliminar_proveedor`, líneas 205-210, mismo patrón
  para proveedor).

### RN-CATALOGO-004 — Categorías no tienen baja: ni soft-delete ni endpoint `DELETE`

- **Descripción**: `repository.py` no define ninguna función de borrado (ni físico ni
  lógico) para `categorias`; `router.py` no expone `DELETE /categorias/{id}` — la
  única forma de "desactivar" una categoría es `PATCH .../categorias/{id}` con
  `activa=False`, un booleano sin ninguna transición regulada.
- **Condición**: N/A — ausencia de capacidad, no un flujo condicional.
- **Resultado**: no aplica.
- **Prioridad**: Media.
- **Archivo**: `services/presupuestacion/catalogo/repository.py` (búsqueda de
  funciones de borrado sobre `categorias`, sin resultados); confirmado por grep en
  esta sesión sobre `router.py` que los únicos verbos para `/categorias` son `GET`,
  `POST` y `PATCH` (`router.py:103`, `:112`, `:120`).
- **Observaciones**: [IMPLEMENTADO] la ausencia. Ver D-CATALOGO-005 en
  [`decisiones.md`](./decisiones.md).

### RN-CATALOGO-005 — Un costo nuevo con el mismo valor que el vigente no genera fila nueva

- **Descripción**: si el `costo_unitario` recibido es igual al del costo vigente,
  `crear_costo` devuelve el vigente sin escribir nada — idempotencia por valor.
- **Condición**: `vigente is not None and Decimal(str(vigente["costo_unitario"])) ==
  body.costo_unitario`.
- **Resultado**: `return vigente` — sin `insert` ni `update`.
- **Prioridad**: Alta.
- **Archivo**: `services/presupuestacion/catalogo/service.py:201-202`.
- **Observaciones**: [IMPLEMENTADO]. Verificada en
  `tests/catalogo/test_service.py:245-256`
  (`test_crear_costo_manual_no_duplica_si_es_igual`, llama `crear_costo` dos veces con
  el mismo body y confirma `len(historial) == 1`).

### RN-CATALOGO-006 — Un costo con valor distinto versiona: cierra el vigente e inserta uno nuevo

- **Descripción**: si el `costo_unitario` recibido difiere del vigente, se cierra la
  fila vigente con `fecha_hasta = fecha_desde_nueva - 1 día` y se inserta una fila
  nueva con `fecha_hasta=None`.
- **Condición**: `vigente is not None` (tras descartar el caso de valor igual de
  RN-CATALOGO-005).
- **Resultado**: `repo.cerrar_costo_vigente(client, costo_id=vigente["id"],
  fecha_hasta=fecha_cierre.isoformat())` seguido de `repo.crear_costo(...)` con
  `fecha_hasta=None`.
- **Prioridad**: Alta.
- **Archivo**: `services/presupuestacion/catalogo/service.py:204-218`.
- **Observaciones**: [IMPLEMENTADO]. Verificada en
  `tests/catalogo/test_service.py:217-242`
  (`test_crear_costo_manual_versiona_igual_que_import`, confirma que el historial
  queda con 2 filas, que la vigente tiene el costo nuevo y que la cerrada tiene
  `fecha_hasta == fecha_desde_nueva - 1 día`). El nombre del test refleja que
  `imports/service.py` reimplementa el mismo algoritmo — ver
  [`arquitectura.md`](./arquitectura.md).

### RN-CATALOGO-007 — El origen de un costo creado por este módulo es siempre `"manual"`

- **Descripción**: `crear_costo` hardcodea `origen="manual"` en toda fila que inserta,
  sin exponer el campo en `CostoCreate` (`models.py:109-111`, sin campo `origen`).
- **Condición**: cualquier llamada exitosa a `crear_costo` que efectivamente inserte
  (RN-CATALOGO-006, o primera alta sin vigente previo).
- **Resultado**: `"origen": "manual"`.
- **Prioridad**: Media.
- **Archivo**: `services/presupuestacion/catalogo/service.py:216`.
- **Observaciones**: [IMPLEMENTADO]. Contrasta con `imports/service.py:115`, `:132`,
  que usa `"import_sistema"` para la misma tabla con el mismo algoritmo — ver
  [`arquitectura.md`](./arquitectura.md). Verificada indirectamente en
  `tests/catalogo/test_service.py:236`
  (`assert resultado["origen"] == "manual"`).

### RN-CATALOGO-008 — El ajuste de stock es un upsert idempotente por depósito

- **Descripción**: `ajustar_stock` no distingue alta de edición: siempre hace un
  `upsert` sobre `stock_productos` con clave `UNIQUE(producto_id, deposito)` — dos
  ajustes al mismo depósito actualizan la misma fila en vez de crear una nueva.
- **Condición**: cualquier llamada a `ajustar_stock`.
- **Resultado**: `repo.upsert_stock(client, fila)` con
  `on_conflict="producto_id,deposito"`.
- **Prioridad**: Alta.
- **Archivo**: `services/presupuestacion/catalogo/repository.py:185-191`.
- **Observaciones**: [IMPLEMENTADO]. Verificada en
  `tests/catalogo/test_service.py:281-297`
  (`test_ajustar_stock_sin_deposito_es_idempotente`, dos ajustes consecutivos sin
  depósito explícito dejan una sola fila con `deposito == "unico"`).

### RN-CATALOGO-009 — Sin depósito especificado, se usa el sentinel `"unico"`

- **Descripción**: si `StockAjuste.deposito` es `None` o cadena vacía, se sustituye
  por la constante `DEPOSITO_SENTINEL`, definida fuera de este módulo.
- **Condición**: `body.deposito` es falsy.
- **Resultado**: `deposito = repo.DEPOSITO_SENTINEL` (valor `"unico"`, definido en
  `services/presupuestacion/imports/service.py:18`).
- **Prioridad**: Media.
- **Archivo**: `services/presupuestacion/catalogo/service.py:247`;
  `services/presupuestacion/catalogo/repository.py:173` (mismo patrón para
  `buscar_stock_por_deposito`).
- **Observaciones**: [IMPLEMENTADO]. Ver D-CATALOGO-004 en
  [`decisiones.md`](./decisiones.md) sobre el acoplamiento que implica reusar una
  constante de otro paquete de negocio. Verificada indirectamente en
  `tests/catalogo/test_service.py:281-297` (el resultado queda con
  `deposito == "unico"`, línea 298).

### RN-CATALOGO-010 — El ajuste manual de stock nunca modifica `cantidad_comprometida`

- **Descripción**: `ajustar_stock` arma la fila del upsert únicamente con
  `cantidad_disponible`; `cantidad_comprometida` no aparece en absoluto en el dict que
  este módulo escribe. El código lo documenta con un comentario explícito.
- **Condición**: cualquier llamada a `ajustar_stock`.
- **Resultado**: cita textual verificada, `service.py:239-240`:

  > "Ajuste manual de cantidad_disponible. NO toca cantidad_comprometida — esa la
  > mantiene únicamente el motor de compromiso de stock (core/stock.py)."

- **Prioridad**: Alta.
- **Archivo**: `services/presupuestacion/catalogo/service.py:236-250` (comentario en
  `:239-240`, dict del upsert en `:244-249`, sin la clave `cantidad_comprometida`).
- **Observaciones**: [IMPLEMENTADO]. Verificada en
  `tests/catalogo/test_service.py:263-278`
  (`test_ajustar_stock_no_toca_comprometida`, siembra `comprometida="4"` y confirma
  que sigue en `4` tras un ajuste de `cantidad_disponible` a `50`). Ver
  [`arquitectura.md`](./arquitectura.md) para el detalle de que `core/stock.py`
  **también** escribe `cantidad_disponible` en otro flujo (entrega de OC), lo que
  matiza la separación "cada módulo su columna" que sugiere el comentario.
