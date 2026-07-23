# Reglas — Imports

Todas las reglas fueron verificadas contra el código real (`service.py`,
`repository.py`, `router.py`) y sus tests (`tests/imports/test_service.py`) en esta
sesión.

### RN-IMPORTS-001 — Productos: reconciliación completa por lote, lo no presente se desactiva

- **Descripción**: tras insertar/actualizar el lote, se recalcula el conjunto de
  códigos activos en base de datos y se desactiva todo lo que no vino en el lote
  actual.
- **Condición**: `faltantes = activos - set(codigos_del_lote)`, con `activos =
  repo.codigos_activos_productos(...)` (filtra `activo=True AND deleted_at IS NULL`).
- **Resultado**: `repo.desactivar_productos(..., codigos=list(faltantes), ...)` →
  `UPDATE activo=False, updated_by=usuario_id` (sin tocar `deleted_at`).
- **Prioridad**: Alta.
- **Archivo**: `services/presupuestacion/imports/service.py:62-67`;
  `imports/repository.py:20-29` (`codigos_activos_productos`), `:42-46`
  (`desactivar_productos`).
- **Observaciones**: [IMPLEMENTADO]. Verificada en
  `tests/imports/test_service.py:96-127`
  (`test_importar_productos_desactiva_los_que_no_vienen`). Cada llamada a
  `importar_productos` es una reconciliación **total** contra el estado actual de la
  droguería, no un upsert incremental — un lote parcial (por ejemplo, por un error de
  paginación en el sistema origen) desactivaría productos que en realidad siguen
  existiendo. Ver D-IMPORTS-001 en [`decisiones.md`](./decisiones.md).

### RN-IMPORTS-002 — Proveedores: mismo patrón de reconciliación, acotado a los que tienen `codigo_interno`

- **Descripción**: igual que RN-IMPORTS-001, pero el conjunto `activos` excluye
  explícitamente proveedores sin `codigo_interno`.
- **Condición**: `repo.codigos_activos_proveedores` agrega
  `.not_.is_("codigo_interno", None)` al filtro de `activo=True AND deleted_at IS NULL`.
- **Resultado**: `faltantes = activos - set(codigos)` solo puede contener proveedores
  que sí tenían `codigo_interno`; un proveedor sin código nunca puede ser desactivado
  por este flujo.
- **Prioridad**: Media.
- **Archivo**: `services/presupuestacion/imports/repository.py:111-121`
  (`codigos_activos_proveedores`); `imports/service.py:231-236`.
- **Observaciones**: [IMPLEMENTADO]. Verificada en
  `tests/imports/test_service.py:452-484`
  (`test_importar_proveedores_desactiva_los_que_no_vienen`, usa dos proveedores **con**
  código). No hay un test que confirme explícitamente que un proveedor sin código nunca
  se desactiva — se infiere directo del filtro SQL. Ver RN-IMPORTS-008.

### RN-IMPORTS-003 — Clientes: mismo patrón de reconciliación por `codigo_interno`

- **Descripción**: igual que RN-IMPORTS-001, sobre `clientes`.
- **Condición**: `faltantes = activos - set(codigos)`, con `activos =
  repo.codigos_activos_clientes(...)` (filtra `activo=True AND deleted_at IS NULL AND
  codigo_interno IS NOT NULL`).
- **Resultado**: `repo.desactivar_clientes(..., codigos=list(faltantes), ...)` →
  `UPDATE activo=False, updated_by=usuario_id`.
- **Prioridad**: Alta.
- **Archivo**: `services/presupuestacion/imports/service.py:313-318`;
  `imports/repository.py:158-168` (`codigos_activos_clientes`), `:181-185`
  (`desactivar_clientes`).
- **Observaciones**: [IMPLEMENTADO]. Verificada en
  `tests/imports/test_service.py:567-599`
  (`test_importar_clientes_desactiva_los_que_no_vienen`). Ver RN-IMPORTS-007 para el
  matiz de que esta desactivación **no es reversible por un import posterior**.

### RN-IMPORTS-004 — Costos: sin concepto de "faltante"; un costo no incluido en el lote sigue vigente

- **Descripción**: a diferencia de productos/proveedores/clientes, `importar_costos`
  nunca calcula qué productos con costo vigente **no** vinieron en el lote actual. Solo
  procesa las filas que sí llegaron.
- **Condición**: N/A — ausencia de capacidad, no un flujo condicional.
- **Resultado**: un costo vigente de un producto que deja de reportarse en importaciones
  sucesivas permanece vigente indefinidamente, sin ningún mecanismo de este módulo que
  lo marque como desactualizado.
- **Prioridad**: Media.
- **Archivo**: `services/presupuestacion/imports/service.py:87-144` (lectura completa
  de la función: no hay ninguna llamada a una función `activos_*`/`desactivar_*` para
  costos, ni en este archivo ni en `repository.py`).
- **Observaciones**: [IMPLEMENTADO] la ausencia. Contradice la generalización de "5
  flujos de reconciliación con la misma lógica de nuevos/actualizados/desactivados" —
  ver [`arquitectura.md`](./arquitectura.md) para la tabla comparativa completa.

### RN-IMPORTS-005 — Stock: upsert puro, sin reconciliación de ningún tipo

- **Descripción**: `importar_stock` no lee qué filas de `stock_productos` existen
  actualmente para la droguería ni compara contra el lote — solo upsertea las filas que
  vienen, y reporta los códigos no encontrados en `productos`.
- **Condición**: N/A — ausencia de capacidad.
- **Resultado**: `repo.upsert_stock(client, filas)`, sin ningún paso posterior de
  desactivación o limpieza.
- **Prioridad**: Media.
- **Archivo**: `services/presupuestacion/imports/service.py:155-183` (lectura completa:
  no hay lectura de "filas activas" antes ni después del upsert).
- **Observaciones**: [IMPLEMENTADO] la ausencia. Es el flujo más alejado del patrón de
  "reconciliación completa por lote" que sí tienen productos/proveedores/clientes: acá
  ni siquiera existe el concepto de fila "no presente en el lote" — cada `deposito` de
  cada producto conserva indefinidamente el último valor que recibió, sea cual sea la
  antigüedad de esa importación. Ver [`arquitectura.md`](./arquitectura.md).

### RN-IMPORTS-006 — Depósito sin especificar usa el sentinel `DEPOSITO_SENTINEL`

- **Descripción**: si `ImportStockRow.deposito` es `None` o cadena vacía, se sustituye
  por `DEPOSITO_SENTINEL` antes del upsert.
- **Condición**: `s.deposito` es falsy.
- **Resultado**: `"deposito": s.deposito if s.deposito else DEPOSITO_SENTINEL` (valor
  `"unico"`).
- **Prioridad**: Alta.
- **Archivo**: `services/presupuestacion/imports/service.py:18` (definición), `:169`
  (uso).
- **Observaciones**: [IMPLEMENTADO]. Verificada en
  `tests/imports/test_service.py:317-344`
  (`test_importar_stock_sin_deposito_usa_sentinel_y_es_idempotente`), con un comentario
  de test explícito sobre por qué existe: un `upsert` nativo con `deposito=NULL` crea
  una fila nueva cada vez porque Postgres no dedupea `NULL` en un `UNIQUE`; el sentinel
  normaliza el valor antes de upsertear para evitar duplicados. Reusada por
  `catalogo/repository.py` — ver [`arquitectura.md`](./arquitectura.md) y
  D-IMPORTS-004 en [`decisiones.md`](./decisiones.md).

### RN-IMPORTS-007 — Un cliente desactivado por reconciliación no se reactiva automáticamente en un import posterior

- **Descripción**: la rama de actualización de `importar_clientes` nunca incluye la
  clave `"activo"` en el dict que envía a `repo.actualizar_cliente` — a diferencia de
  productos y proveedores, cuyo dict base sí fuerza `"activo": True` en cada
  actualización.
- **Condición**: un cliente con `activo=False` (desactivado por una importación
  anterior, RN-IMPORTS-003) reaparece con el mismo `codigo_interno` en un lote
  posterior.
- **Resultado**: `repo.actualizar_cliente` actualiza `nombre`/`tipo`/campos opcionales
  y `updated_by`, pero el cliente permanece `activo=False`.
- **Prioridad**: Media.
- **Archivo**: `services/presupuestacion/imports/service.py:284-291` (rama de
  actualización, sin clave `"activo"`), contrastar con `:39-53` (productos, `"activo":
  True` en la línea 51 del dict `base` compartido por alta y actualización) y
  `:200-214` (proveedores, `"activo": True` en la línea 212 del dict `_base`).
- **Observaciones**: [IMPLEMENTADO]. No se encontró un test en
  `tests/imports/test_service.py` que ejercite este escenario (desactivar un cliente y
  luego reimportarlo con el mismo código) — el comportamiento se confirmó por lectura
  directa del código, no por evidencia de test. No se pudo determinar si es
  intencional o un descuido — pendiente de definición funcional. Ver
  [`pendientes.md`](./pendientes.md) P2.

### RN-IMPORTS-008 — Un proveedor sin `codigo_interno` siempre se inserta como nuevo, nunca se actualiza ni se desactiva

- **Descripción**: `importar_proveedores` separa el lote en `con_codigo`/`sin_codigo`
  al principio; toda fila `sin_codigo` va directo a `nuevos_filas`, sin pasar por la
  comparación contra `existentes`.
- **Condición**: `p.codigo_interno` es `None` o cadena vacía.
- **Resultado**: `nuevos_filas.append({**_base(p), "created_by": usuario_id})` para
  cada fila `sin_codigo`, sin deduplicar contra proveedores ya insertados en
  importaciones anteriores.
- **Prioridad**: Media.
- **Archivo**: `services/presupuestacion/imports/service.py:194-195`, `:225-226`.
- **Observaciones**: [IMPLEMENTADO]. Verificada en
  `tests/imports/test_service.py:424-449`
  (`test_importar_proveedores_sin_codigo_interno_siempre_inserta_nuevo`, confirma
  explícitamente que dos filas sin código crean dos proveedores nuevos, no uno).
  Reimportar el mismo archivo de origen dos veces duplica cada proveedor sin código
  interno — riesgo funcional real si el sistema origen no siempre provee ese campo. Ver
  [`pendientes.md`](./pendientes.md) P2.

### RN-IMPORTS-009 — Un costo nuevo con el mismo valor que el vigente no genera fila nueva

- **Descripción**: si `costo_unitario` recibido es igual al del costo vigente del
  producto, no se escribe nada — mismo criterio de idempotencia que
  `catalogo.crear_costo` (RN-CATALOGO-005).
- **Condición**: `vigente is not None and Decimal(str(vigente["costo_unitario"])) ==
  fila.costo_unitario`.
- **Resultado**: `sin_cambios += 1`, sin `insert` ni `update`.
- **Prioridad**: Alta.
- **Archivo**: `services/presupuestacion/imports/service.py:136-137`.
- **Observaciones**: [IMPLEMENTADO]. Verificada en
  `tests/imports/test_service.py:224-253`
  (`test_importar_costos_no_toca_si_es_igual`, dos importaciones consecutivas con el
  mismo valor dejan una sola fila en `costos_productos`). Ver
  [`arquitectura.md`](./arquitectura.md) para la duplicación de este algoritmo con
  Catálogo.

### RN-IMPORTS-010 — Un costo con valor distinto versiona: cierra el vigente e inserta uno nuevo

- **Descripción**: mismo algoritmo que RN-CATALOGO-006 (`catalogo.crear_costo`),
  reimplementado de forma independiente: cierra la fila vigente con `fecha_hasta =
  fecha_desde_nueva - 1 día` e inserta una fila nueva con `fecha_hasta=None` y
  `origen="import_sistema"`.
- **Condición**: `vigente is not None` y el valor difiere (tras descartar
  RN-IMPORTS-009).
- **Resultado**: `repo.cerrar_costo_vigente(...)` seguido de `repo.crear_costo(...)`.
- **Prioridad**: Alta.
- **Archivo**: `services/presupuestacion/imports/service.py:119-134`.
- **Observaciones**: [IMPLEMENTADO]. Verificada en
  `tests/imports/test_service.py:178-221`
  (`test_importar_costos_actualiza_si_difiere`, confirma 2 filas tras la segunda
  importación, la cerrada con `fecha_hasta == fecha_desde_nueva - 1 día`, la nueva con
  `fecha_hasta IS NULL`). Ver D-IMPORTS-003 en [`decisiones.md`](./decisiones.md) sobre
  por qué no se reusa `catalogo.service.crear_costo` directamente.

### RN-IMPORTS-011 — Las actualizaciones nunca pisan `created_by`, solo `updated_by`

- **Descripción**: en productos y proveedores, el dict `base`/`_base` usado tanto para
  alta como para actualización incluye `updated_by` siempre, pero `created_by` **solo**
  se agrega en la rama de alta (`{**base, "created_by": usuario_id}`).
- **Condición**: cualquier fila en la rama de actualización (código ya existente).
- **Resultado**: `repo.actualizar_productos_existentes`/`actualizar_proveedores_existentes`
  hacen `upsert` con `on_conflict="drogueria_id,codigo_interno"` sobre un dict que no
  incluye `created_by` — Postgres conserva el valor existente de esa columna al no
  incluirla en el `SET` del upsert.
- **Prioridad**: Media.
- **Archivo**: `services/presupuestacion/imports/service.py:39-57` (productos),
  `:200-223` (proveedores).
- **Observaciones**: [IMPLEMENTADO]. Verificada en
  `tests/imports/test_service.py:62-93`
  (`test_importar_productos_actualiza_sin_pisar_created_by`, con dos usuarios técnicos
  distintos — `seed_usuario_sistema` y `seed_usuario_sistema_2` — confirma que
  `created_by` queda con el primero y `updated_by` con el segundo). No se encontró un
  test equivalente explícito para proveedores en este archivo — la implementación es
  idéntica en código, cobertura de test no confirmada para ese caso puntual.

### RN-IMPORTS-012 — Una lista vacía de filas lanza `ValidationError` en las 5 funciones

- **Descripción**: las 5 funciones públicas de `service.py` validan primero que la
  lista recibida no esté vacía, antes de cualquier otra lógica.
- **Condición**: `not productos` / `not costos` / `not stock` / `not proveedores` / `not
  clientes`.
- **Resultado**: `raise ValidationError("La lista de X no puede estar vacía")`.
- **Prioridad**: Media.
- **Archivo**: `services/presupuestacion/imports/service.py:30-31`, `:90-91`,
  `:158-159`, `:191-192`, `:262-263`.
- **Observaciones**: [IMPLEMENTADO]. Verificada para productos en
  `tests/imports/test_service.py:130-135`
  (`test_importar_productos_lista_vacia_lanza_validation_error`). No se encontró un
  test equivalente explícito para las otras 4 entidades en este archivo — la
  implementación es idéntica en código (misma condición, mismo tipo de excepción),
  cobertura de test no confirmada para esos 4 casos puntuales.

### RN-IMPORTS-013 — Los 5 endpoints comparten un único tuple de roles, distinto del patrón `_ROLES_ESCRITURA` de Clientes/Eventos/Procesos Comerciales

- **Descripción**: `_ROLES_IMPORT = ("admin", "gerencia", "compras")` es el único tuple
  de roles del módulo, aplicado a los 5 endpoints por igual (sin distinción de lectura,
  ni roles ampliados para ninguna entidad en particular).
- **Condición**: N/A — configuración estática, no un flujo condicional.
- **Resultado**: coincide exactamente con `_ROLES_ESCRITURA_CATALOGO` de
  `catalogo/router.py:44`; difiere de `_ROLES_ESCRITURA` de `clientes/router.py:36`,
  `eventos/router.py:33` y `procesos_comerciales/router.py:18` (que incluyen
  `lider_comercial`/`comercial` pero no `compras`).
- **Prioridad**: Media.
- **Archivo**: `services/presupuestacion/imports/router.py:26`.
- **Observaciones**: [IMPLEMENTADO]. Confirmado por grep de los 4 patrones de roles
  (`_ROLES_ESCRITURA`, `_ROLES_IMPORT`, `_ROLES_LECTURA`, `_ROLES_ELIMINACION`) sobre
  todo `services/presupuestacion/` en esta sesión. Efecto funcional concreto: un
  usuario `lider_comercial` o `comercial` puede crear/editar un cliente directo vía
  `clientes/router.py` (RN-CLIENTES, roles `_ROLES_ESCRITURA` de ese módulo), pero no
  puede disparar `POST /imports/clientes`, que crea/actualiza/desactiva clientes en
  lote — la misma acción de negocio (mantener el maestro de clientes) queda con
  distintos requisitos de rol según la vía usada. Ver
  [`arquitectura.md`](./arquitectura.md).
