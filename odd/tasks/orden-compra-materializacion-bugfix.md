# Fix: materialización de orden de compra — decimales con coma + atomicidad

## Objetivo

Corregir dos bugs encontrados probando en vivo (navegador + backend real) el cambio
`orden-compra` ya mergeado a `dev`, en `_materializar_orden_compra`
(`services/presupuestacion/extraccion/service.py`).

## Problema / evidencia

Confirmar una OC con `precio_unitario="890,75"` (coma decimal, formato que el extractor
Gemini produce normalmente, documento real subido) crashea con:

```
postgrest.exceptions.APIError: {'message': 'invalid input syntax for type numeric: "890,75"', 'code': '22P02', ...}
```

Traceback real: `router.py:149` → `service.py:1312` (`validar_extraccion_para_endpoint`) →
`service.py:1219` (`_validar_y_materializar_orden_compra`) → `service.py:861`
(`_materializar_orden_compra`) → `service.py:747` (`repo.insertar_oc_items`) →
`repository.py:280` (`client.table("oc_items").insert(...)`).

**Causa raíz (verificada leyendo el código, no asumida)**: `_a_decimal()`
(`service.py:607-611`) ya sabe convertir coma→punto y ya se usa para *validar*
`precio_unitario`/`cantidad` en `_validar_orden_compra_override` (línea 631). Pero
`_materializar_orden_compra` (línea 733-746) arma `filas_items` con
`fila.cantidad`/`fila.precio_unitario` **sin pasar por `_a_decimal()`** — manda el string
original (con coma si el documento la traía) directo al insert.

**Bug 2 — no atómico**: como `repo.crear_orden_compra` (línea 722) y
`repo.insertar_oc_items` (línea 747) son dos llamadas REST separadas, cuando la segunda
falla la primera ya quedó comprometida. Verificado en vivo: quedó una fila huérfana en
`ordenes_compra` (sin `oc_items`/`entregas_oc`) que además bloquearía un reintento futuro
vía `uq_oc_por_cliente` con un "conflicto" que no tiene nada que ver con la causa real. Se
limpió manualmente la fila de prueba (`DELETE FROM ordenes_compra WHERE id = 'b65c79b3-...'`)
contra el proyecto de test.

**Nota de alcance**: el mismo patrón no-atómico (insertar OC, después items, sin
transacción) ya existe en `compras/service.py::crear_orden_compra` (línea 74 y 97), no
introducido por este cambio. No se toca acá — fuera de alcance de este fix puntual.

## Tareas

- [x] 1 [RED] Test en `tests/extraccion/test_orden_compra.py` (o `test_service.py`, verificar
  convención real) que reproduce el bug: `FilaOrdenCompraIn.precio_unitario="890,75"` (o
  `cantidad` con coma) llega a `_materializar_orden_compra` y el valor insertado en
  `oc_items` (mock del repository, aserción sobre el payload real que se le pasa a
  `insertar_oc_items`) tiene que ser `"890.75"` (punto), no `"890,75"`. Confirmar RED antes
  del fix.
  - Agregado `test_precio_unitario_con_coma_se_convierte_a_punto_antes_del_insert` en
    `tests/extraccion/test_orden_compra.py`. RED confirmado:
    `AssertionError: assert '890,75' == '890.75'`.
- [x] 2 [GREEN] Aplicar `_a_decimal()` a `cantidad` y `precio_unitario` al construir
  `filas_items` en `_materializar_orden_compra` (línea ~742-743). Ambos campos ya pasaron
  por `_validar_orden_compra_override` antes de llegar acá, así que `_a_decimal()` nunca
  debería devolver `None` en este punto — pero agregar una aserción defensiva o comentario
  explicando por qué es seguro asumirlo (la validación previa ya lo garantiza).
  - Aplicado en `services/presupuestacion/extraccion/service.py` dentro del loop de
    `filas_items`: `_a_decimal(fila.cantidad)` / `_a_decimal(fila.precio_unitario)`, con
    `assert ... is not None` defensivo + comentario. Test del punto 1 en GREEN.
- [x] 3 [RED] Test que reproduce el bug 2: mockear `repo.insertar_oc_items` para que lance
  una excepción después de que `repo.crear_orden_compra` ya insertó, y afirmar que
  `_materializar_orden_compra` limpia (borra) la fila de `ordenes_compra` recién creada
  antes de re-lanzar la excepción — no debe quedar huérfana.
  - Agregado `test_falla_en_insertar_oc_items_borra_la_orden_compra_huerfana` en
    `tests/extraccion/test_orden_compra.py`. RED confirmado:
    `AttributeError: module ... repository has no attribute 'borrar_orden_compra'`.
- [x] 4 [GREEN] Envolver el `try/except` alrededor de los inserts posteriores a
  `crear_orden_compra` para que, ante cualquier excepción, borre la fila de
  `ordenes_compra` recién creada (compensación manual, no transacción real — la limitación
  de fondo de usar PostgREST sin RPC sigue existiendo, pero al menos no deja basura) y
  vuelva a lanzar la excepción original. Usar una función nueva en `repository.py`
  (`borrar_orden_compra` o similar) si no existe ya una utilizable.
  - No existía ninguna función de borrado reutilizable para `ordenes_compra` (ni en
    `extraccion/repository.py` ni en `compras/repository.py`). Se agregó
    `borrar_orden_compra(client, *, orden_compra_id)` en
    `services/presupuestacion/extraccion/repository.py` (simple `DELETE ... WHERE id=`).
    Se envolvió todo el bloque desde `filas_items = []` hasta el final del `for` de
    entregas en `_materializar_orden_compra` en un `try/except Exception: repo.
    borrar_orden_compra(...); raise`. Test del punto 3 en GREEN.
- [x] 5 [REFACTOR] Correr `pytest tests/extraccion -q -m "not integration"` completo (0
  regresiones) y `pytest tests/extraccion -m integration -q` contra el proyecto de test
  (confirmar en vivo que un `precio_unitario` con coma ya no crashea, y que una falla
  simulada en `oc_items` no deja fila huérfana).
  - `pytest tests/extraccion -q -m "not integration"` → 118 passed (116 baseline + 2
    nuevos), 37 deselected, 0 regresiones.
  - `pytest tests/ -q -m "not integration"` (repo completo) → 383 passed, 447 deselected,
    0 regresiones.
  - Agregados 2 tests de integración en vivo en `tests/extraccion/test_service.py`:
    `test_validar_orden_compra_precio_unitario_con_coma_no_crashea` (confirma inserción
    real con `precio_unitario`/`cantidad` con coma, sin mocks de repository) y
    `test_validar_orden_compra_falla_en_items_no_deja_orden_huerfana` (crea la OC real
    contra la DB de test, mockea solo `insertar_oc_items` para fallar, y verifica que NO
    queda fila huérfana en `ordenes_compra`). Ambos en GREEN contra
    `grnamollopxdlstcpxhc`.
  - `pytest tests/extraccion -m integration -q` completo (con los 2 tests nuevos) → **39
    passed, 118 deselected, 0 failures, 225.20s (0:03:45)** contra `grnamollopxdlstcpxhc`.
    Confirmado en vivo, sin mocks de repository en los nuevos tests (salvo el mock
    deliberado de `insertar_oc_items` en el test de huérfana, que simula la falla de red
    manteniendo el insert real de `crear_orden_compra`): el `precio_unitario`/`cantidad`
    con coma ya no crashea, y una falla simulada en `oc_items` no deja fila huérfana en
    `ordenes_compra`.

Los 5 pasos quedaron completos. Resumen de evidencia final:
- Unitarios `tests/extraccion -m "not integration"`: 118 passed (0 regresiones).
- Unitarios repo completo `tests/ -m "not integration"`: 383 passed (0 regresiones).
- Integración `tests/extraccion -m integration`: 39 passed (0 regresiones, incluye los 2
  tests nuevos que reproducen ambos bugs en vivo).

## Contexto de tooling

- Strict TDD Mode activo. Test runner: `pytest tests/` (venv, `asyncio_mode=auto`).
- Proyecto de test Supabase: `grnamollopxdlstcpxhc` (mismo `.env` del repo).
- No agregar línea de atribución de IA a ningún commit (regla de CLAUDE.md).
- No hace falta branch/PR nuevo a menos que el usuario lo pida — este fix es chico y puede
  ir directo a `dev` con un commit propio, mismo patrón que otros ajustes menores de esta
  sesión. Confirmar con el usuario antes de pushear si hace falta.
