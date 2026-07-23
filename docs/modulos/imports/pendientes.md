# Pendientes — Auditoría técnica de Imports

Clasificación P1 (ausencia de una capacidad esperada) / P2 (deuda técnica relevante) /
P3 (menor), verificada contra el código y los tests reales en esta sesión.

## P1 — Ausencia de auditoría, atribución real y punto único de verdad

1. **Ninguna mutación de este módulo queda registrada en `historial_cambios`, y es el
   caso más grave del proyecto por volumen.** Confirmado por grep exhaustivo en esta
   sesión: 0 referencias a `core.audit`, `registrar_cambio`, `registrar_cambios` o
   `registrar_evento_ciclo_vida` en los 4 archivos fuente (`models.py`,
   `repository.py`, `service.py`, `router.py`). [IMPLEMENTADO] el hecho. Mismo patrón
   ya documentado para [`../catalogo/`](../catalogo/) y [`../clientes/`](../clientes/),
   pero acá el impacto es mayor: una sola llamada a `POST /imports/productos` puede
   crear, actualizar y **desactivar en lote** un número arbitrario de productos de una
   vez, sin dejar ningún rastro auditable de la operación como conjunto (no hay un
   evento "importación #N ejecutada, resultado: 40 creados, 120 actualizados, 8
   desactivados, por el usuario X, a las Y") — solo quedan los valores finales de
   `updated_by`/`created_by` en cada fila individual, y ese valor es **siempre el mismo
   UUID técnico fijo** (ver hallazgo 2). Ver `docs/modulos/core/` para el mecanismo de
   auditoría (`core/audit.py`) que este módulo no consume.

2. **`usuario_id` fijo (`usuario_sistema_id`) en vez del usuario real que dispara la
   importación.** `imports/service.py:21-22` (`_usuario_sistema_id`) resuelve
   `get_settings().usuario_sistema_id` — confirmado como un campo requerido de
   `Settings` en `core/config.py:15`, cargado desde `.env` — y los 5 wrappers
   `*_para_endpoint` lo usan siempre como `usuario_id`, **nunca** el `usuario.id` del
   `UsuarioPerfil` que `router.py` ya resuelve vía `require_roles` para autorizar la
   llamada. [IMPLEMENTADO]. Combinado con el hallazgo 1: no hay ninguna forma, ni en
   las tablas de destino ni en un log de auditoría, de saber qué cuenta humana concreta
   ejecutó una importación puntual que, por ejemplo, dejó sin stock vigente a un
   producto o desactivó un cliente. Ver D-IMPORTS-002 en
   [`decisiones.md`](./decisiones.md).

3. **Duplicación del algoritmo de versionado de costos con `catalogo.service.crear_costo`,
   sin punto único de verdad — el caso de duplicación más grave confirmado en el
   proyecto hasta ahora.** `imports/service.py:87-144` (`importar_costos`) reimplementa
   exactamente el mismo algoritmo que `catalogo/service.py:195-218` (`crear_costo`,
   RN-CATALOGO-005/006 en [`../catalogo/reglas.md`](../catalogo/reglas.md)): cerrar el
   costo vigente con `fecha_hasta = fecha_desde - 1 día` e insertar uno nuevo, sin
   escribir nada si el valor es igual. [IMPLEMENTADO]. Las dos implementaciones no
   comparten ninguna función ni test — si la regla de negocio cambiara, habría que
   modificar ambos archivos de forma consistente, sin ningún mecanismo que lo
   garantice. Confirmado con evidencia cruzada desde ambos lados: este documento y
   [`../catalogo/pendientes.md`](../catalogo/pendientes.md) P2(1). Ver D-IMPORTS-003 en
   [`decisiones.md`](./decisiones.md).

4. **Acoplamiento negocio→soporte invertido: `DEPOSITO_SENTINEL` vive en este módulo de
   soporte y `catalogo/` (negocio) depende de él.** `catalogo/repository.py:6` importa
   `DEPOSITO_SENTINEL` desde `imports/service.py:18`. [IMPLEMENTADO]. Si este archivo
   cambia o se elimina, `catalogo/repository.py` falla en tiempo de import con un error
   que no señala ningún problema evidente en `catalogo/`. Confirmado con evidencia
   cruzada: este documento y [`../catalogo/pendientes.md`](../catalogo/pendientes.md)
   P1(2). Ver D-IMPORTS-004 en [`decisiones.md`](./decisiones.md).

## P2 — Deuda técnica relevante

1. **Reconciliación completa por lote sin ningún umbral de seguridad.** Los 3 flujos
   que desactivan lo faltante (productos, proveedores, clientes) recalculan el
   conjunto completo de filas activas y desactivan todo lo que no vino en el lote
   actual, sin ninguna validación de que el lote sea razonablemente completo (por
   ejemplo, "no desactivar más del X% del total"). [IMPLEMENTADO]. Un lote truncado por
   un error del sistema origen (timeout, paginación mal implementada, archivo cortado)
   desactivaría silenciosamente todo lo que faltó, indistinguible de una baja real. Ver
   D-IMPORTS-001 en [`decisiones.md`](./decisiones.md).

2. **Asimetría no documentada: clientes no se reactivan al reaparecer, productos y
   proveedores sí.** Verificado por lectura línea por línea de las 3 ramas de
   actualización: `service.py:39-53` (productos) y `:200-214` (proveedores) fuerzan
   `"activo": True` en cada actualización; `service.py:284-291` (clientes) no incluye
   esa clave en absoluto. [IMPLEMENTADO]. Un cliente desactivado por una importación
   queda desactivado para siempre aunque el sistema origen vuelva a reportarlo — no se
   encontró un test que ejercite este escenario en `tests/imports/test_service.py`. No
   se pudo confirmar si es intencional. Ver RN-IMPORTS-007 en
   [`reglas.md`](./reglas.md) y D-IMPORTS-005 en [`decisiones.md`](./decisiones.md).

3. **Proveedores sin `codigo_interno` se duplican en reimportaciones.** Confirmado por
   test explícito en el propio módulo:
   `test_importar_proveedores_sin_codigo_interno_siempre_inserta_nuevo`
   (`tests/imports/test_service.py:424-449`) verifica que dos filas sin código crean
   dos proveedores nuevos — no hay ninguna forma de deduplicar por
   `razon_social`/`cuit`. [IMPLEMENTADO]. Si el sistema origen no siempre provee
   `codigo_interno` para todos sus proveedores, reimportar el mismo lote genera
   duplicados acumulativos en cada corrida. Ver RN-IMPORTS-008 en
   [`reglas.md`](./reglas.md).

4. **5 flujos con lógica de reconciliación no homogénea, sin documentación que explique
   la diferencia.** Contradice la premisa de "5 flujos con la misma lógica de
   nuevos/actualizados/desactivados": productos, proveedores y clientes desactivan lo
   faltante; costos versiona sin concepto de "faltante"; stock hace upsert puro sin
   ningún tipo de reconciliación. [IMPLEMENTADO], ver tabla comparativa completa en
   [`arquitectura.md`](./arquitectura.md). No hay comentario en el código que explique
   por qué costos y stock quedaron fuera del patrón de reconciliación — es consistente
   con la naturaleza de esos datos (un costo o un nivel de stock no "dejan de existir",
   solo dejan de actualizarse), pero esa interpretación no está confirmada en el código
   ni documentada explícitamente.

5. **CRUD paralelo y sin código compartido con `catalogo/` y `clientes/` para las
   mismas 5 tablas — deuda ya confirmada desde ambos lados.** `imports/repository.py`
   implementa su propio acceso a `productos`, `costos_productos`, `stock_productos`,
   `proveedores` y `clientes`, sin ninguna relación de código con
   `catalogo/repository.py` ni `clientes/repository.py`. [IMPLEMENTADO]. Ver
   [`../catalogo/pendientes.md`](../catalogo/pendientes.md) P2(1) y
   [`../clientes/arquitectura.md`](../clientes/arquitectura.md) para el mismo hallazgo
   documentado desde el otro lado. Un ejemplo concreto adicional confirmado en esta
   sesión: `imports.desactivar_productos`/`desactivar_proveedores` solo escriben
   `activo=False`, **sin tocar `deleted_at`** — mientras que
   `catalogo.soft_delete_producto`/`soft_delete_proveedor` escriben `activo=False` **y**
   `deleted_at`. Como `catalogo.obtener_producto` (`catalogo/repository.py:30-38`)
   filtra solo por `deleted_at IS NULL` (no por `activo`), un producto desactivado por
   este módulo sigue siendo plenamente visible y editable vía `GET`/`PATCH
   /productos/{id}` de Catálogo — dos semántica distintas de "baja" conviven sobre la
   misma columna `activo` según qué módulo la escribió.

## P3 — Menor

1. **Sin evidencia de ningún consumidor de los 5 endpoints en este repositorio.**
   Confirmado en esta sesión: no existe `scripts/` en el repo; un grep de `/imports` y
   de los 5 nombres de función del cliente HTTP del frontend
   (`frontend/src/lib/api/presupuestacion.ts`) no encontró ninguna coincidencia.
   [IMPLEMENTADO] la ausencia de evidencia. No se puede determinar si el flujo real es
   un sistema externo llamando directo por HTTP, un proceso manual, o una integración
   pendiente de construir — pendiente de definición funcional. Ver
   [`casos_de_uso.md`](./casos_de_uso.md).

2. **Roles de escritura (`_ROLES_IMPORT`) no incluyen `lider_comercial`/`comercial`,
   a diferencia del patrón de `clientes/router.py`.** `router.py:26` usa
   `("admin", "gerencia", "compras")` para los 5 endpoints, incluido
   `POST /imports/clientes` — un `lider_comercial`/`comercial` que sí puede
   crear/editar un cliente vía `clientes/router.py` no puede disparar una importación
   masiva de clientes. [IMPLEMENTADO]. No hay comentario que confirme si es
   intencional (compras/gerencia como únicos responsables de cargas masivas, sin
   importar la entidad) — coincide con el patrón de `catalogo/`, pero no con el de
   `clientes/`. Ver RN-IMPORTS-013 en [`reglas.md`](./reglas.md).

3. **`tests/imports/test_service.py` no cubre el escenario de RN-IMPORTS-007
   (reactivación de cliente).** [IMPLEMENTADO] la ausencia de test — confirmado por
   lectura completa de los 19 tests del archivo, ninguno reimporta un cliente
   previamente desactivado. Igual ausencia para el caso simétrico en `ValidationError`
   por lista vacía en costos/stock/proveedores/clientes (solo hay test explícito para
   productos, `tests/imports/test_service.py:130-135`) — la implementación es idéntica
   en código para las 5 entidades, pero la cobertura de test puntual no está
   confirmada para 4 de los 5 casos.

No se detectó código muerto: las 10 funciones de `service.py` (5 puras + 5
`*_para_endpoint`, sin contar `_usuario_sistema_id`) y las 20 de `repository.py` tienen
al menos un call site dentro del módulo, o son ejercitadas directo por
`tests/imports/test_service.py` (confirmado leyendo los 5 archivos fuente y el archivo
de test completos en esta sesión).
