# Fix: paginación real de `GET /terceros` + filtro de rol inclusivo

## Objetivo

Corregir dos bugs preexistentes en el listado de terceros, encontrados durante el
diseño del change `orden-compra` (no introducidos por él, documentados aparte en
memoria del proyecto).

## Problema / evidencia (verificado leyendo el código real)

`services/terceros/identidad/repository.py::listar_terceros` (línea 31-67): trae
**todas** las filas que matchean el filtro en un loop de páginas de 1000
(`_TAMANO_PAGINA`) hasta agotar el resultado, y devuelve la lista completa.
`services/terceros/identidad/service.py::listar_terceros_paginado` (línea 84-107)
llama a esa función y **recién ahí** recorta con `filas[inicio:inicio+page_size]` en
Python. Con 5541 terceros y una búsqueda `q` amplia o vacía, esto sigue trayendo
miles de filas por página pedida — la paginación no es real a nivel de base.

`_coincide_filtro_rol` (línea 72-81, `service.py`): `filtro_rol == "clientes"` exige
`tiene_cliente AND NOT tiene_proveedor` — **excluyente**. Un tercero que es cliente
y proveedor a la vez queda invisible en cualquier búsqueda filtrada por rol cliente
(o proveedor). El filtro `"ambos"` ya existe aparte para el caso `tiene_cliente AND
tiene_proveedor`, así que la exclusividad de `"clientes"`/`"proveedores"` no cumple
ningún propósito que `"ambos"` no cubra ya — es un bug, no una decisión de producto.

## Alcance

### 1. Filtro de rol — hacerlo inclusivo

`_coincide_filtro_rol`: `"clientes"` → `tiene_cliente` (sin el `and not
tiene_proveedor`); `"proveedores"` → `tiene_proveedor` (sin el `and not
tiene_cliente`). `"ambos"` no cambia (sigue siendo la intersección). Esto es
coherente con cómo ya lo pidió D3.2 de `orden-compra`: `rol='todos'` + filtro
`tiene_rol_cliente` en el cliente — la corrección de acá hace que además
`rol='clientes'` directamente sirva, sin necesitar ese workaround.

### 2. Paginación real cuando `filtro_rol == "todos"`

Cuando no hay filtro de rol (el caso común — es lo que usa `orden-compra`'s
`ClienteBuscador`), el filtro de rol no bloquea empujar `page`/`page_size`
directo a PostgREST. Implementar un camino que:
- Use `.select("*, clientes(id), proveedores(id)", count="exact")` +
  `.range(offset, offset+page_size-1)` en la query real contra `terceros`, en vez
  de acumular todo y recortar en Python.
- Devuelva `total` desde el `count` que PostgREST ya calcula en la misma
  respuesta (`response.count`), no `len(filas)` sobre una lista completa.

### 3. Paginación cuando `filtro_rol != "todos"`

Investigar primero (no asumir el comentario existente en el código, que dice "no
es expresable... supabase-py no ofrece" un filtro de "no existe" sobre un embed):
¿la versión de `postgrest-py`/`supabase-py` que usa este proyecto soporta filtrar
por ausencia/presencia de un embed relacionado (ej. algo tipo `.not_.is_("clientes",
"null")` o equivalente vía `!inner` combinado con negación)? Si existe una forma
real de expresarlo, usarla para lograr paginación 100% server-side también en este
caso. **Si de verdad no es expresable** con las herramientas disponibles (confirmar,
no asumir), mantener el comportamiento actual (traer todo lo que matchea `q`,
filtrar por rol en Python, paginar en memoria) para este caso puntual — documentarlo
explícitamente como limitación conocida y remanente, con un comentario claro de por
qué (para que quede trazable, no repetir el mismo hallazgo en el futuro).

## Verificación

- `pytest tests/terceros -q -m "not integration"` (0 regresiones).
- `pytest tests/terceros -m integration -q` contra el proyecto de test
  (`grnamollopxdlstcpxhc`) — confirmar en vivo: (a) un tercero con ambos roles
  aparece filtrando por `rol=clientes` y por `rol=proveedores`; (b) con
  `rol=todos`, pedir `page=1&page_size=50` hace UNA sola query con `range`/`count`
  a PostgREST, no un loop de acumulación (se puede verificar contando las llamadas
  mockeadas, o revisando que el repository ya no usa el loop `while True` para este
  camino).
- Full `pytest tests/ -q -m "not integration"` para confirmar 0 regresiones fuera
  de `terceros` (especialmente `services/presupuestacion/clientes/` y el
  `ClienteBuscador` de `orden-compra`, que consumen este mismo endpoint).

## Contexto de tooling

- Strict TDD Mode activo. Test runner: `pytest tests/` (venv, `asyncio_mode=auto`).
- Proyecto de test Supabase: `grnamollopxdlstcpxhc`.
- No agregar línea de atribución de IA a ningún commit.
- Commit directo en `dev`, sin branch/PR nuevo — no pushear, el orquestador revisa
  y pushea.

## Tareas

- [x] 1 [RED] Test que confirma que un tercero con `tiene_cliente=true` y
  `tiene_proveedor=true` aparece en el resultado filtrando `rol='clientes'` (hoy no
  aparece — RED contra el código actual).
  Evidencia: agregadas `test_filtro_rol_clientes_incluye_los_que_tambien_son_proveedores`
  y `test_filtro_rol_proveedores_incluye_los_que_tambien_son_clientes` en
  `tests/terceros/identidad/test_service_listar_paginado.py` (reemplazando el test
  viejo que afirmaba la exclusividad, que era literalmente el bug). Comando:
  `pytest tests/terceros/identidad/test_service_listar_paginado.py -q -m "not integration"`
  → RED confirmado: `2 failed, 7 passed` (`assert 1 == 2` en ambos, exactamente el
  comportamiento excluyente viejo).
- [x] 2 [GREEN] Aplicar el fix de la sección 1 (`_coincide_filtro_rol`).
  Evidencia: `services/terceros/identidad/service.py` — quitado el `and not
  tiene_proveedor`/`and not tiene_cliente`. Comando:
  `pytest tests/terceros -q -m "not integration"` → `16 passed, 48 deselected`.
- [x] 3 [RED] Test que confirma que `listar_terceros_paginado(..., filtro_rol='todos',
  page=1, page_size=50)` con más de 50 terceros disponibles NO trae más de 50 filas
  desde el repository (mock de `client.table(...).range(...)` — afirmar que se llamó
  con el `range` correcto y que no hubo loop de acumulación).
  Evidencia: extendido el fake de `tests/terceros/identidad/test_repository.py` con
  `count="exact"`, soporte de embeds `!inner` y un contador `client.llamadas_table`;
  agregados 7 tests nuevos para `repo.listar_terceros_paginado` (que todavía no
  existía). Comando: `pytest tests/terceros/identidad/test_repository.py -q -m "not
  integration"` → RED confirmado: `7 failed, 6 passed`
  (`AttributeError: module 'services.terceros.identidad.repository' has no attribute
  'listar_terceros_paginado'`).
- [x] 4 [GREEN] Aplicar el fix de la sección 2 (paginación real para `rol=todos`).
  Evidencia: `repo.listar_terceros_paginado` nueva en
  `services/terceros/identidad/repository.py` — una sola query con
  `.select(..., count="exact")` + `.range(inicio, inicio+page_size-1)`, sin loop.
  `service.listar_terceros_paginado` pasó a ser un wrapper fino que delega ahí.
- [x] 5 Investigar la sección 3 (filtro de rol + paginación server-side) — documentar
  el hallazgo (soportado o no) y aplicar el fix si es viable, o dejar el
  comportamiento actual con el comentario explicativo si no lo es.
  **Hallazgo: SÍ es viable, y se aplicó en el mismo cambio de la tarea 4.** El
  comentario original decía que hacía falta "un filtro de no-existe sobre un embed"
  que `supabase-py` no ofrece — cierto en su momento, pero esa necesidad era
  consecuencia directa del bug de la sección 1 (la semántica excluyente "cliente Y
  NO proveedor" es un anti-join, que efectivamente no es expresable simple). Al
  sacar el "AND NOT" en la tarea 2, el filtro de rol pasó a ser un chequeo de
  *presencia* puro (¿tiene al menos una fila relacionada?), y **eso sí lo expresa
  un embed `!inner` de PostgREST** (`clientes!inner(id)` fuerza INNER JOIN — solo
  matchean filas con al menos un relacionado), sin necesitar ningún método nuevo de
  la librería: `!inner` es sintaxis PostgREST cruda dentro del string de
  `.select()`, soportada por cualquier versión de postgrest-py (confirmado leyendo
  el código fuente instalado, postgrest-py 2.30.0, en
  `venv/Lib/site-packages/postgrest/_sync/request_builder.py` — `select()` acepta
  `count` y pasa las columnas tal cual). `repo.listar_terceros_paginado` arma el
  embed condicionalmente: `clientes!inner(id)` cuando `filtro_rol` es `"clientes"`
  o `"ambos"`, `proveedores!inner(id)` cuando es `"proveedores"` o `"ambos"`, y
  embed plano (LEFT) para `"todos"`. Un solo query, un solo `.range()`, para
  cualquier valor de `filtro_rol` — sin fallback en Python.
  Confirmado en vivo contra Postgres real (no solo contra el fake):
  `test_listar_terceros_paginado_filtro_rol_es_inclusivo_contra_postgres_real` en
  `tests/terceros/identidad/test_service.py` (`@pytest.mark.integration`) — un
  tercero con ambos roles aparece filtrando por `clientes`, `proveedores` y
  `ambos` contra el proyecto de test real. Comando:
  `pytest tests/terceros/identidad/test_service.py -m integration -q` →
  `24 passed`.
  **Desviación respecto al plan del task file:** como el mismo mecanismo
  (`!inner` condicional) resuelve tanto la sección 2 como la sección 3, no hubo
  un "fix separado" para la tarea 5 — quedó implementado junto con la tarea 4 en
  una sola función. `_coincide_filtro_rol` quedó sin ningún llamador (su
  comportamiento correcto ahora vive en la query SQL, no en Python) y se borró
  como parte de la tarea 6 (limpieza de código muerto) en vez de mantenerse sin uso.
- [x] 6 [REFACTOR] Correr la verificación completa (arriba) y confirmar 0
  regresiones.
  Evidencia:
  - `pytest tests/terceros -q -m "not integration"` → `19 passed, 49 deselected`.
  - `pytest tests/terceros -m integration -q` (contra `grnamollopxdlstcpxhc`) →
    `48 passed` (incluye el nuevo test de rol inclusivo en vivo).
  - `pytest tests/terceros/identidad/test_service.py -m integration -q` → `24
    passed` (confirmación aislada del test nuevo).
  - `pytest tests/ -q -m "not integration"` (suite completa) → `384 passed, 450
    deselected` — 0 regresiones, incluye `services/presupuestacion/clientes/` y
    `tests/extraccion/` (consumidores de `ClienteBuscador`/búsqueda de terceros
    del feature `orden-compra`).
  - Cleanup: eliminada `_coincide_filtro_rol` de `service.py` (sin llamadores tras
    el fix server-side); reescrito
    `tests/terceros/identidad/test_service_listar_paginado.py` para probar el
    wrapper fino real (reenvío de parámetros + `_con_flags_de_rol`) en vez de la
    paginación/filtrado en Python que ya no existe ahí.
