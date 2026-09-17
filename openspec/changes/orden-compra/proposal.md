# Propuesta: Orden de compra

## Intent

Las órdenes de compra de clientes (PDF/imagen/Excel/HTML) fallan hoy con un 422 en
`services/extraccion/main.py:163`, aunque la UI de carga ya ofrece la opción
(`templates/index.html:146`). El personal las vuelve a tipear a mano en Progress v8 (sin API, solo
CSV). Este cambio es el paso 1 de digitalizar ese traspaso: extraer una OC, validarla, anclarla a un
cliente, dividirla en entregas, exportar una nota de pedido CSV para Progress e importar el CSV de
retorno de Progress para seguir lo entregado frente a lo pendiente.

## Scope

### En alcance

- `orden_compra` como tercera clasificación real (se elimina el 422; extractor Gemini dedicado).
- Materialización en las tablas ya existentes `ordenes_compra` / `oc_items`.
- Anclaje al cliente por `codigo_interno` en lugar de `proceso_comercial`.
- División en entregas — campo manual obligatorio cuando el documento no la declara; distribución
  pareja de la cantidad de cada línea cuando solo se indica la cantidad de entregas.
- Exportación saliente de nota de pedido en CSV.
- Importación entrante del CSV de retorno de Progress, que actualiza `cantidad_entregada` /
  `cantidad_rechazada` y dispara el descuento de stock.
- Esquema: `proceso_comercial_id` pasa a nullable + CHECK
  `proceso_comercial_id IS NOT NULL OR cliente_id IS NOT NULL`.
- Esquema: `uq_oc` global se reemplaza por dos índices únicos parciales, uno por ruta de anclaje.
- Frontend: búsqueda por `codigo_interno` + editor de entregas, separado de `ProcesoComercialSelector`.

### Fuera de alcance

- Flujos de presupuesto y comparativa — no se tocan.
- Integración directa con Progress vía ODBC/OpenEdge — trabajo futuro.
- Formatos exactos de columnas CSV, en ambas direcciones — decisión de la fase de diseño.
- Versionado/reemplazo de `ordenes_compra` (las columnas existen, el código nunca se implementó).
- Construir la ingesta de `codigo_interno` — `services/presupuestacion/imports/` ya lo puebla.
- Reserva de stock al confirmar la OC — decidido explícitamente que no existe.

## Capabilities

### Nuevas capacidades

- `orden-compra-extraccion`: clasificar y extraer documentos OC hacia `extraction_results`.
- `orden-compra-validacion`: confirmar una extracción de OC hacia `ordenes_compra`/`oc_items`, con
  anclaje al cliente y división en entregas.
- `nota-pedido-export`: CSV saliente consumible por Progress.
- `entregas-import`: CSV entrante de retorno de Progress que actualiza cantidades entregadas/rechazadas
  y descuenta stock.

### Capacidades modificadas

- Ninguna. `openspec/specs/` está vacío. `validar-extraccion` sigue sin archivar y su no-objetivo
  documentado (D-EXTRACCIONVALIDACION-003, "orden_compra rechazado") queda superado aquí — reconciliar
  al momento de archivar.

## Approach

Se reutiliza el dominio ya preprovisionado `services/presupuestacion/compras/` (`ordenes_compra`,
`oc_items`, `entregas_oc`, `entregas_oc_items`) en lugar de crear tablas paralelas: tres fuentes
independientes (ROADMAP, comentario del esquema y `decisiones.md`) muestran que fue construido para
exactamente este caso, y ya arrastra las columnas sin uso `extraction_id` / `cantidad_entregas`.
`crear_orden_compra` **no** se modifica; la ruta de extracción obtiene su propio
`_materializar_orden_compra()` que asigna `cliente_id` directamente.

Decisiones resueltas que ordenan el diseño:

- **Momento del descuento de stock**: el stock se descuenta únicamente al importar el CSV de retorno
  de Progress, reutilizando sin cambios el mecanismo existente `crear_entrega` →
  `entregar_stock_producto` de `services/presupuestacion/compras/service.py`. Confirmar la OC no
  reserva ni descuenta nada: Progress es la fuente de verdad sobre lo efectivamente entregado.
- **`oc_items.precio_unitario`**: se mantiene `NOT NULL` tal como está, sin cambio de esquema. Las
  órdenes de compra de clientes siempre traen precio unitario por línea; si la extracción no lo
  detecta, el usuario lo carga manualmente antes de confirmar.
- **Alcance de unicidad de `numero_oc`**: la restricción actual
  `CONSTRAINT uq_oc UNIQUE (numero_oc, version_numero)` (`docs/schema/extractor_final.sql:646`) es
  global y se elimina. Dos clientes distintos pueden numerar sus órdenes igual (por ejemplo, ambos
  envían "OC-001") y la restricción global produciría un `ConflictError` falso entre clientes sin
  relación. Como `cliente_id` es nullable y Postgres trata cada `NULL` como distinto, un único
  `UNIQUE (drogueria_id, cliente_id, numero_oc, version_numero)` dejaría sin unicidad efectiva a las
  OC ancladas solo por `proceso_comercial_id`. El reemplazo son **dos índices únicos parciales**, uno
  por ruta de anclaje:

  ```sql
  -- Ruta 1: OC anclada a un cliente
  CREATE UNIQUE INDEX uq_oc_por_cliente
    ON ordenes_compra (drogueria_id, cliente_id, numero_oc, version_numero)
    WHERE cliente_id IS NOT NULL;

  -- Ruta 2: OC anclada solo vía proceso_comercial_id
  CREATE UNIQUE INDEX uq_oc_por_proceso
    ON ordenes_compra (drogueria_id, proceso_comercial_id, numero_oc, version_numero)
    WHERE cliente_id IS NULL;
  ```

  Se descarta `UNIQUE ... NULLS NOT DISTINCT` porque no se pudo confirmar la versión de Postgres del
  proyecto; los índices parciales no dependen de la versión. El CHECK de anclaje
  (`proceso_comercial_id IS NOT NULL OR cliente_id IS NOT NULL`) garantiza que dentro de
  `uq_oc_por_proceso` la columna `proceso_comercial_id` nunca es `NULL`, así que ninguna de las dos
  rutas queda sin cubrir. `uq_oc_id_drog UNIQUE (id, drogueria_id)` no se toca, y ninguna FK depende
  de `uq_oc` (todas referencian `id` o `(id, drogueria_id)`), por lo que eliminarlo es seguro.

## Affected Areas

| Área | Impacto | Descripción |
|---|---|---|
| `services/extraccion/main.py` | Modificado | Quitar el 422 de `tipo=="ordenes"`; clasificación en tres vías |
| `services/extraccion/robot_orden_compra.py` | Nuevo | Prompt Gemini + esquema CSV incluyendo entregas |
| `services/extraccion/persistent_output.py` | Modificado | Agregar a `_DOC_TYPES_SOPORTADOS` |
| `services/presupuestacion/extraccion/models.py` | Modificado | Forma de fila OC, `codigo_interno`, entregas |
| `services/presupuestacion/extraccion/service.py` | Modificado | `_materializar_orden_compra()`; `_TIPOS_CON_LECTURA_DE_FILAS` |
| `services/presupuestacion/clientes/` | Modificado | `buscar_cliente_por_codigo_interno()` (no existe) |
| `services/presupuestacion/compras/` | Modificado | Nuevos puntos de entrada export/import; `crear_entrega` se reutiliza sin cambios |
| `docs/schema/extractor_final.sql` | Modificado | FK nullable + CHECK de anclaje + baja de `uq_oc` y alta de los índices parciales `uq_oc_por_cliente` / `uq_oc_por_proceso` |
| `docs/modulos/compras/README.md` | Modificado | La dirección es hacia el cliente, no hacia el proveedor |
| `frontend/src/features/validar-extraccion/` | Modificado | Selector específico de OC + editor de entregas |
| `tests/extraccion/test_service.py:172-189` | Modificado | `test_validar_orden_compra_no_implementado` se invierte |

## Risks

| Riesgo | Probabilidad | Mitigación |
|---|---|---|
| ~~`clientes.codigo_interno` no tiene restricción de unicidad~~ — **Resuelto**: verificado contra la base real, ya existe `uq_cli_codigo UNIQUE (drogueria_id, codigo_interno)`. No requiere cambio de esquema | N/A | N/A |
| El nuevo prompt de Gemini regresiona sobre documentos reales | Media | Fixtures golden bajo `tests/fixtures/`; costo de API sin cambios (una llamada por documento) |
| Extracción sin `precio_unitario` bloquea la confirmación | Media | Carga manual obligatoria en el editor de validación antes de confirmar |
| La creación de los índices parciales falla si ya existen filas que colisionan bajo el nuevo alcance | Baja | Verificar duplicados antes de aplicar; ambos alcances nuevos son estrictamente más permisivos que el `uq_oc` global actual |

## Rollback Plan

Backend y frontend son aditivos: revertir el commit restaura el 422 y el `ValidationError`, y ningún
flujo existente lee las columnas nuevas. Los cambios de esquema son el único retroceso no trivial:

1. Revertir datos antes que esquema. Volver a poner `NOT NULL` en `proceso_comercial_id` exige borrar
   o rellenar previamente las filas de OC originadas en extracción.
2. Eliminar los índices `uq_oc_por_cliente` y `uq_oc_por_proceso` y restaurar
   `CONSTRAINT uq_oc UNIQUE (numero_oc, version_numero)`. Solo es posible si no quedan filas que
   colisionen bajo el alcance global; verificar duplicados y resolverlos antes de recrear la
   restricción.

## Dependencies

- `services/presupuestacion/imports/` debe haber poblado `clientes.codigo_interno` para los clientes
  objetivo; un código sin poblar deja la OC imposible de anclar.

## Success Criteria

- [ ] Un documento OC cargado por la UI existente llega a validación en lugar de un 422.
- [ ] Una OC validada produce una fila en `ordenes_compra` anclada a un cliente por `codigo_interno`,
      con `extraction_id` y `cantidad_entregas` poblados.
- [ ] La división en entregas produce filas de `entregas_oc` que suman la cantidad completa de cada línea.
- [ ] Dos clientes distintos pueden registrar el mismo `numero_oc` sin conflicto.
- [ ] Confirmar una OC no altera el stock; el stock se mueve solo al importar el CSV de retorno.
- [ ] Una OC confirmada exporta un CSV que Progress importa sin edición manual.
- [ ] Un CSV de retorno de Progress actualiza entregado/pendiente por línea y por entrega.

## Open Questions (diferidas a spec/design)

1. Distribución del resto cuando la cantidad de una línea no se divide de forma pareja entre entregas.
2. Cumplimiento parcial de una entrega por parte de Progress — semántica y `estado` resultante.
~~3. Si `codigo_interno` recibe una restricción de unicidad en este cambio.~~ **Resuelto**: ya existe
   `uq_cli_codigo UNIQUE (drogueria_id, codigo_interno)` en la base real, verificado directamente.
4. Formatos exactos de columnas CSV, en ambas direcciones.
5. Si las líneas de OC requieren `producto_id` al validar, o alcanza el texto libre (el
   `precio_unitario` ya está resuelto: obligatorio, manual si falta).
6. Qué roles pueden validar/confirmar una OC (probablemente el patrón `_ROLES_ESCRITURA` — confirmar).

**Nota de verificación**: `docs/schema/extractor_final.sql` está desactualizado para la tabla
`clientes` (no lista `codigo_interno`, `deleted_at`, `deleted_by`, `created_by`, `updated_by`, que sí
existen en la base real). Se verificó `ordenes_compra`, `oc_items` y `entregas_oc_items` directamente
contra la base viva y coinciden con el snapshot — solo `clientes` estaba desactualizado.
