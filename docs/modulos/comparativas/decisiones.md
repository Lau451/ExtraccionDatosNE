# Decisiones de diseño — Comparativas

## D-COMPARATIVAS-001 — El módulo es una fachada delgada porque no es dueño de ninguna tabla

**Decisión**: `comparativas/` no tiene `INSERT` propio sobre `comparativas` ni
`ofertas_items` (las tablas que su nombre sugiere que gobierna), ni caso de uso de
creación. Su única escritura es un `UPDATE` de una sola columna
(`ofertas_items.proveedor_id`) sobre filas que otro módulo ya creó.

**Motivo**: no hay un comentario textual explícito en el código que declare esta
intención de diseño (a diferencia de otras decisiones documentadas en este proyecto,
como D-EXTRACCIONVALIDACION-001). Es una inferencia respaldada por evidencia
estructural fuerte:

1. `_materializar_comparativa` (`extraccion/service.py:137-241`) es el único punto de
   `INSERT` sobre `comparativas`/`ofertas_items` en todo el repositorio auditado —
   confirmado por `Grep` de `.table("comparativas")` y `.table("ofertas_items")` con
   `.insert(` fuera de `extraccion/repository.py`.
2. El nombre del módulo (`comparativas/`) coincide con el nombre de la tabla
   (`comparativas`), lo que podría sugerir que es su dueño — pero el schema
   (`docs/schema/extractor_final.sql:579`) documenta la tabla como "Entidad de
   NEGOCIO: se crea al validar la extracción", es decir, ligada al caso de uso de
   `extraccion/`, no a este módulo.
3. Las 2 únicas fuentes de datos de este módulo son vistas (`v_renglones_ganados`,
   `v_ofertas_sin_matchear`), un patrón típico de un módulo de "solo lectura curada"
   sobre datos que otro módulo posee.

**Alternativa descartada**: fusionar este módulo dentro de `extraccion/` (que ya
gobierna `comparativas`/`ofertas_items`) o dentro de `compras/` (que consume
`es_drogueria_propia` para adjudicar). No hay evidencia en el código de que esta
fusión se haya evaluado — Motivo pendiente de definición funcional. Separarlo en un
módulo propio tiene sentido si se lo mira como "la vista de negocio de comparativas
para el usuario comercial que revisa y corrige matching", distinta de "el pipeline
técnico que materializa una extracción" (`extraccion/`) — pero esa distinción no está
declarada explícitamente en ningún comentario o documento del repositorio.

## D-COMPARATIVAS-002 — Tampoco acá se auto-detecta `es_drogueria_propia`, y el gap es más amplio que en `extraccion_validacion/`

**Decisión**: ningún archivo de este módulo lee, calcula o escribe
`ofertas_items.es_drogueria_propia`.

**Motivo**: mismo motivo de negocio documentado del lado de `extraccion_validacion/`
(D-EXTRACCIONVALIDACION-001) — el texto libre de `ofertas_items.proveedor` no trae un
marcador confiable para inferir si una oferta es de la propia droguería, y un falso
positivo dispararía `v_renglones_ganados`/`compras` sobre una premisa falsa. No hay un
comentario textual propio de este módulo que lo confirme explícitamente (a diferencia
de `extraccion/service.py:198-200`), porque este módulo simplemente **no tiene código
que intente resolverlo en ningún sentido** — ni automático ni manual.

**Por qué el gap es más amplio acá**: `compras/service.py:127-129` da por sentado que
existe "el PATCH manual de asignación" que eventualmente setea
`es_drogueria_propia = True`. Este módulo es el candidato natural para ser ese PATCH
(es el único caso de escritura sobre `ofertas_items` fuera de `extraccion/`), y su
nombre de función (`asignar_proveedor`) sugiere exactamente esa operación. Sin
embargo, `asignar_proveedor` (`service.py:23-25`) solo escribe `proveedor_id` — nunca
`es_drogueria_propia`. Es decir: incluso si un usuario asigna manualmente el
"proveedor real" de una oferta y ese proveedor resulta ser la propia droguería (un
`proveedores` con `drogueria_id` igual al de la oferta es técnicamente posible si la
propia droguería está cargada como su propio proveedor en el catálogo — no verificado
en esta sesión si eso ocurre en la práctica), `es_drogueria_propia` sigue en `False`.

**Alternativa no tomada, y con evidencia de que sería técnicamente viable**: que
`asignar_proveedor` derive `es_drogueria_propia` a partir de columnas que sí existen en
`proveedores` — `es_competidor` (`BOOLEAN NOT NULL DEFAULT TRUE`,
`extractor_final.sql:137`) y `tipo` (`CHECK ... IN ('laboratorio', 'drogueria',
'distribuidor', 'cooperativa', 'otro')`, `extractor_final.sql:136,146-147`, con
`'drogueria'` como valor explícito del enum). A diferencia del texto libre de
`ofertas_items.proveedor` (el motivo real por el que `extraccion/` no auto-detecta,
D-EXTRACCIONVALIDACION-001), acá el usuario ya identificó un `proveedor_id` real —
`es_competidor`/`tipo` de ese proveedor concreto sí son datos confiables, no una
heurística de texto. `Grep` de `es_competidor`/`tipo.*drogueria` confirma que ninguno
de los dos se lee en `comparativas/`, `extraccion/` ni `compras/service.py` para
derivar `es_drogueria_propia` — solo se usan en `catalogo/` (alta/edición de
proveedores) e `imports/` (carga masiva). No hay evidencia de que se haya evaluado y
descartado esta derivación — Motivo pendiente de definición funcional. Ver
[`pendientes.md`](./pendientes.md) para el impacto operativo concreto.

## D-COMPARATIVAS-003 — La validación de tenant en `asignar_proveedor` es de integridad de datos, no de autorización

**Decisión**: `service.py:20-21` compara `proveedor["drogueria_id"]` contra
`oferta["drogueria_id"]` (RN-COMPARATIVAS-001) — no compara contra la droguería del
usuario que hace la petición (eso ya lo resolvió el router, RN-COMPARATIVAS-002, con
`user_client` antes de delegar).

**Motivo**: son dos preguntas distintas. RN-COMPARATIVAS-002 responde "¿puede este
usuario tocar esta oferta?" (autorización). RN-COMPARATIVAS-001 responde "¿el
proveedor que el usuario eligió es coherente con la droguería dueña de la oferta?"
(integridad). Sin esta segunda validación, un usuario autorizado a tocar una oferta
de su propia droguería podría, por error o por un `proveedor_id` mal copiado,
vincularla a un proveedor de una droguería distinta — un dato inconsistente que
ninguna política RLS impediría (RLS filtra filas por `drogueria_id` de la fila que se
edita, no valida coherencia entre columnas de tablas relacionadas). No es una
duplicación del chequeo del router: son dos comparaciones con distinto propósito que
comparten forma sintáctica (`A.drogueria_id != B.drogueria_id`) — ver
[`reglas.md`](./reglas.md) RN-COMPARATIVAS-002, nota final.
