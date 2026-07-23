# Flujos — Imports

Los 5 flujos siguen el mismo esqueleto de router (rol → wrapper → función pura), pero
solo 2 se documentan paso a paso acá — productos (representa el patrón de
reconciliación completa, compartido con proveedores y clientes) y costos (el flujo con
la lógica de negocio más rica, y el que reimplementa el algoritmo de Catálogo). Ver
[`arquitectura.md`](./arquitectura.md) para la tabla comparativa de los 5.

## Flujo 1 — Importación de productos (`POST /imports/productos`)

Patrón: **mapear → comparar → insertar/actualizar/desactivar**.

1. El router exige `require_roles(*_ROLES_IMPORT)` — `("admin", "gerencia",
   "compras")` (`router.py:26`, `:32`).
2. `importar_productos_endpoint` llama a
   `importar_productos_para_endpoint(drogueria_id=usuario.drogueria_id,
   productos=body.productos)` (`router.py:34-36`).
3. `importar_productos_para_endpoint` resuelve `get_service_client()` y
   `_usuario_sistema_id()` (**no** `usuario.id`) y delega en `importar_productos`
   (`service.py:76-82`).
4. **Mapear**: `codigos_existentes_productos` trae el subconjunto de `codigo_interno`
   del lote que ya existe en la droguería (`service.py:34`, `repository.py:7-17`).
5. **Comparar**: por cada fila del lote, si su código está en `existentes` va a
   `actualizados_filas`, si no va a `nuevos_filas` con `created_by` agregado
   (`service.py:38-57`).
6. **Insertar/actualizar**: `repo.insertar_productos` hace `INSERT` en lote
   (`repository.py:32-34`); `repo.actualizar_productos_existentes` hace `upsert` con
   `on_conflict="drogueria_id,codigo_interno"` (`repository.py:37-39`) — dos llamadas
   HTTP a Supabase, no una transacción.
7. **Desactivar**: se recalcula `activos` (todo lo `activo=True AND deleted_at IS
   NULL` de la droguería, sin relación con el lote) y se resta el conjunto de códigos
   del lote actual; lo que sobra se desactiva en un tercer `UPDATE`
   (`service.py:62-67`, RN-IMPORTS-001).
8. El endpoint responde `ImportProductosResultado` con `{creados, actualizados,
   desactivados}` (`router.py:29`, `:37`).

Tres llamadas HTTP a Supabase por importación (`insert`, `upsert`, `update` de
desactivación), ninguna dentro de una transacción explícita a nivel de aplicación — si
el proceso falla entre el paso 6 y el 7, el lote queda con las filas nuevas/actualizadas
persistidas pero sin la desactivación de lo faltante.

## Flujo 2 — Importación de costos (`POST /imports/costos`)

Patrón: **mapear → comparar contra vigente → versionar (sin concepto de "faltante")**.
Es el único de los 5 flujos que reimplementa una regla de negocio ya existente en otro
módulo — ver [`arquitectura.md`](./arquitectura.md).

1. El router exige `require_roles(*_ROLES_IMPORT)` (`router.py:41-43`).
2. `importar_costos_endpoint` llama a
   `importar_costos_para_endpoint(drogueria_id=usuario.drogueria_id, costos=body.costos)`
   (`router.py:45`).
3. `importar_costos_para_endpoint` resuelve `get_service_client()` y
   `_usuario_sistema_id()`, delega en `importar_costos` (`service.py:147-150`).
4. **Mapear**: `mapear_productos_por_codigo` resuelve `codigo_interno → producto_id`
   para todo el lote (`service.py:94`, `repository.py:49-61`); los códigos sin match
   quedan en `no_encontrados` (`service.py:95`) y sus filas se excluyen del resto del
   procesamiento (`filas_validas`, `service.py:96`).
5. `costos_vigentes_por_producto` trae, para todos los `producto_id` válidos de una
   sola query, la fila con `fecha_hasta IS NULL` de cada uno (`service.py:99`,
   `repository.py:66-76`) — evita N+1 queries dentro del loop.
6. **Comparar contra vigente**, por cada fila válida (`service.py:102-137`):
   - Si no hay vigente (`vigente is None`): `repo.crear_costo` con `fecha_hasta=None`,
     `origen="import_sistema"` — `nuevos += 1` (RN-IMPORTS-004 caso alta).
   - Si el valor es igual al vigente: no se escribe nada — `sin_cambios += 1`
     (RN-IMPORTS-009).
   - Si el valor difiere: `repo.cerrar_costo_vigente` (cierra con `fecha_hasta =
     fecha_desde_nueva - 1 día`) seguido de `repo.crear_costo` (nueva fila vigente) —
     `actualizados += 1` (RN-IMPORTS-010, mismo algoritmo que
     `catalogo.crear_costo`).
7. **Sin desactivación**: no hay un paso 4 análogo al de productos — un producto cuyo
   costo dejó de reportarse simplemente no aparece en el lote y su costo vigente no se
   toca (RN-IMPORTS-004).
8. El endpoint responde `ImportCostosResultado` con `{nuevos, actualizados,
   sin_cambios, no_encontrados}` (`router.py:40`, `:46`).

Igual que en Flujo 1: el cierre del vigente y la inserción del nuevo (paso 6, caso
"versiona") son dos llamadas HTTP separadas sin transacción explícita — si el proceso
falla entre ambas, el producto queda temporalmente sin ningún costo vigente
(`fecha_hasta IS NULL`), a diferencia del riesgo simétrico ya documentado para
`catalogo.crear_costo` en [`../catalogo/decisiones.md`](../catalogo/decisiones.md)
D-CATALOGO-002 (dos vigentes en vez de cero).

## Los otros 3 flujos, en una línea

- **Stock** (`POST /imports/stock`): mapear código→`producto_id`, upsertear
  `cantidad_disponible` por `(producto_id, deposito)` normalizando depósito vacío con
  `DEPOSITO_SENTINEL`, sin paso de desactivación (RN-IMPORTS-005/006).
- **Proveedores** (`POST /imports/proveedores`): mismo esqueleto que productos, con la
  salvedad de que las filas sin `codigo_interno` se insertan siempre como nuevas y
  quedan fuera de la reconciliación (RN-IMPORTS-002/008).
- **Clientes** (`POST /imports/clientes`): mismo esqueleto que productos, con
  actualización parcial real (solo pisa campos presentes) y sin reactivar `activo` en
  la rama de actualización (RN-IMPORTS-003/007).
