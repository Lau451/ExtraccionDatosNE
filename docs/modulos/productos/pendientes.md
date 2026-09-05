# Pendientes — Auditoría técnica de Productos

> **Actualización (refactor `catalogo/` → `services/productos/`)**: el módulo se
> movió a `services/productos/` (top-level) y el wrapper de compatibilidad de
> `proveedores` se **eliminó por completo**. Los ítems de abajo que mencionan
> `proveedor(es)` (P3(1) sobre roles hardcodeados en `DELETE`, P3(3) sobre
> reactivación sin guarda) describen código que ya no existe en este módulo y no
> fueron purgados en este refactor.

Clasificación P1 (ausencia de una capacidad esperada) / P2 (deuda técnica relevante)
/ P3 (menor), verificada contra el código y los tests reales en esta sesión.

## P1 — Ausencia de auditoría y acoplamiento negocio→soporte

1. **Ninguna mutación de este módulo queda registrada en `historial_cambios`.**
   Confirmado por grep exhaustivo en esta sesión: 0 referencias a `core.audit`,
   `registrar_cambio`, `registrar_cambios` o `registrar_evento_ciclo_vida` en los 4
   archivos fuente (`models.py`, `repository.py`, `service.py`, `router.py`).
   [IMPLEMENTADO] el hecho. Esto significa que el alta y la baja de productos y
   proveedores, la edición de categorías, el versionado de costos y el ajuste manual
   de stock no dejan ningún rastro auditable — mismo patrón ya documentado para
   [`../clientes/`](../clientes/) y [`../usuarios/`](../usuarios/). Particularmente
   relevante para `costos_productos`: un cambio de precio queda trazado solo en la
   fila cerrada del historial de costo (que sí preserva el valor anterior por
   diseño, RN-PRODUCTOS-006), pero no hay registro de **quién** hizo el cambio más
   allá de lo que ya guarda la propia tabla — no hay un evento explícito con
   `usuario_id` para esta acción, a diferencia de lo que hace `historial_cambios`
   para otros módulos. Ver `docs/modulos/core/` para el mecanismo de auditoría
   (`core/audit.py`) que este módulo no consume.

2. **Acoplamiento unidireccional negocio→soporte vía `DEPOSITO_SENTINEL`.**
   `repository.py:6` importa una constante de `services/presupuestacion/imports/service.py`
   — el único módulo de negocio o soporte no-Core que Productos importa. [IMPLEMENTADO].
   Si `imports/service.py` cambia el valor, renombra o elimina `DEPOSITO_SENTINEL`,
   `productos/repository.py` falla en tiempo de import, con un mensaje de error que no
   apunta a ningún problema evidente en `productos/` — ver D-PRODUCTOS-004 en
   [`decisiones.md`](./decisiones.md).

## P2 — Deuda técnica relevante

1. **Acoplamiento de tabla con 5 módulos, sin código compartido, con un caso de
   regla de negocio duplicada.** `matching/`, `comparativas/`, `pricing/`,
   `core/stock.py` e `imports/` leen o escriben directo las 5 tablas de este módulo
   — más consumidores por tabla que cualquier otro módulo documentado hasta ahora en
   este proyecto (ver [`../clientes/arquitectura.md`](../clientes/arquitectura.md)
   para el caso comparable, más chico, de `clientes`). [IMPLEMENTADO]. El caso más
   grave, verificado en esta sesión: `imports/service.py:87-138`
   (`importar_costos`) reimplementa **el mismo algoritmo** de versionado de costo
   que `productos.service.crear_costo` (cerrar vigente + insertar nuevo, sin cambios
   si el valor es igual) de forma completamente independiente, con la única
   diferencia de `origen="import_sistema"` en vez de `"manual"`. Si la regla de
   negocio cambiara (por ejemplo, el criterio de cierre de `fecha_hasta`), habría
   que modificar dos archivos sin relación de código de forma consistente, sin que
   exista un punto único de verdad. Ejemplo adicional, menos grave: el upsert masivo
   de `imports/repository.py:37-39` (`actualizar_productos_existentes`) no pasa por
   ninguna validación de `productos.service` (no aplica `exclude_unset`, no valida
   `categoria_id`, etc.).

2. **Riesgo de condición de carrera en `stock_productos` entre `productos.ajustar_stock`
   y `core/stock.py`.** Verificado en esta sesión (no estaba en el descubrimiento
   previo con este nivel de detalle): `core/stock.py` no solo mantiene
   `cantidad_comprometida`, también descuenta `cantidad_disponible`
   (`_descontar_disponible_hasta`, `core/stock.py:242-270`, invocada desde
   `entregar_stock_producto` al confirmar una entrega de OC) usando optimistic
   locking (`WHERE cantidad_disponible = valor_leído`). `productos.ajustar_stock` en
   cambio hace un `upsert` sobre la misma columna sin ninguna comparación de valor
   esperado (`repository.py:185-191`). [IMPLEMENTADO] el hecho de que ambos
   escritores existen y tocan la misma columna con técnicas distintas. Lo que no se
   pudo confirmar en esta sesión es si el `upsert` de PostgREST/Supabase, en la
   ventana entre que `core/stock.py` lee y escribe, puede efectivamente pisar ese
   valor de forma silenciosa (depende del comportamiento exacto de `upsert` con
   `on_conflict` frente a un `UPDATE` concurrente en la misma fila, algo que no es
   verificable solo con el código Python de este repositorio) — hipótesis razonable,
   no un bug reproducido. Ver D-PRODUCTOS-003 en [`decisiones.md`](./decisiones.md).

3. **Falta de endpoint `DELETE` para categorías.** [IMPLEMENTADO] la ausencia
   (RN-PRODUCTOS-004). Posiblemente intencional para evitar productos huérfanos
   (D-PRODUCTOS-005), pero sin ningún comentario en el código que lo confirme —
   queda como hipótesis, no como motivo verificado.

## P3 — Menor

1. **`DELETE /productos/{id}` y `DELETE /proveedores/{id}` usan una tupla
   hardcodeada en vez de una constante nombrada.** `router.py:94` y `:173` usan
   `require_roles("admin", "gerencia")` directo, en vez de una constante como
   `_ROLES_ELIMINACION_CATALOGO` — a diferencia de los otros 10 endpoints del mismo
   archivo, que sí usan una de las 4 constantes definidas en `router.py:43-46`.
   [IMPLEMENTADO]. Efecto funcional real, no solo estilo: el rol `compras`, que sí
   puede crear y editar productos y proveedores vía `_ROLES_ESCRITURA_CATALOGO`
   (`router.py:44`), **no** puede eliminarlos — una asimetría de permisos que hoy
   solo es visible leyendo dos literales de tupla en vez de un nombre autoexplicativo
   como en [`../clientes/`](../clientes/) (`_ROLES_ELIMINACION`,
   [`../clientes/casos_de_uso.md`](../clientes/casos_de_uso.md)).

2. **Duplicación mecánica de 12 pares función pura / `_para_endpoint`.** Verificado
   por grep en esta sesión: 12 funciones `_para_endpoint`, cada una una línea de
   código que resuelve `get_service_client()` y delega — sin lógica nueva. Ver
   D-PRODUCTOS-001 en [`decisiones.md`](./decisiones.md). [IMPLEMENTADO]. Este conteo
   corrige el "8 pares" del descubrimiento previo del módulo.

3. **`ProductoUpdate`/`ProveedorUpdate` permiten reactivar (`activo=True`) sin
   ninguna guarda.** Ni `actualizar_producto` (`service.py:58-64`) ni
   `actualizar_proveedor` (`service.py:156-162`) distinguen "reactivar un registro
   soft-deleted" de "editar un campo cualquiera" — ambos casos pasan por el mismo
   `exclude_unset=True` sin ninguna regla adicional. [IMPLEMENTADO]. No se pudo
   confirmar si esto es intencional (permitir "deshacer" una baja) o un descuido —
   pendiente de definición funcional. No se encontró un test dedicado a este
   escenario en `tests/productos/test_service.py`.

No se detectó código muerto: las 12 funciones puras y las 12 `_para_endpoint` tienen
al menos un call site en `router.py` o son ejercitadas directo por
`tests/productos/test_service.py` (confirmado leyendo ambos archivos completos en
esta sesión).
