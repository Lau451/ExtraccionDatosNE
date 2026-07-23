# Decisiones de diseño — Extracción-Validación

## D-EXTRACCIONVALIDACION-001 — `es_drogueria_propia` no se auto-detecta desde el texto de "proveedor"

**Decisión**: toda oferta creada al materializar una comparativa se inserta con
`es_drogueria_propia = False` fijo, sin intentar inferirlo del texto de
`fila["proveedor"]`.

**Motivo** (comentario textual, `service.py:198-200`):

> "es_drogueria_propia NO se auto-detecta: el texto de 'proveedor' no trae ningún
> marcador confiable y un falso positivo dispara compras sobre una premisa falsa
> (ver v_renglones_ganados). Queda para un PATCH manual, fuera de este alcance."

**Por qué importa un falso positivo**: la vista `v_renglones_ganados`
(`docs/schema/extractor_final.sql:1576-1595`) filtra
`WHERE oi.es_drogueria_propia = TRUE AND (oi.adjudicada OR oi.adjudicacion_estimada)`
para listar "renglones ganados por la droguería" — el insumo de decisiones de
compra. Si este módulo marcara `es_drogueria_propia = True` por error (ej. un
proveedor con nombre parecido al de la droguería propia), esa fila aparecería como
"ganada" en un proceso donde en realidad ganó otro proveedor, disparando trabajo de
compras sobre una premisa falsa.

**Alternativa descartada**: heurística de texto (match parcial/fuzzy contra el
nombre de la droguería). Descartada explícitamente por el comentario del código —
"no trae ningún marcador confiable" — priorizando falsos negativos (requiere marcado
manual posterior) sobre falsos positivos (dispara compras erróneas). Consistente con
el criterio ya usado en matching (`_UMBRAL_SUGERIDO` en `matching/service.py:13`
exige confirmación humana por debajo de cierto umbral, en vez de autoconfirmar).

**Estado**: sin PATCH manual implementado en este módulo ni en ningún otro auditado
en esta sesión — ver [`pendientes.md`](./pendientes.md).

## D-EXTRACCIONVALIDACION-002 — Workaround: reusar `marca` del CSV como `descripcion` de la oferta

**Decisión**: `ofertas_items.descripcion` se llena con el valor de la columna
`marca` del CSV de comparativa, en vez de dejarse vacía.

**Motivo** (comentario textual, `service.py:216-218`):

> "No hay columna 'marca' en ofertas_items ni 'descripcion' en el CSV de
> comparativa: reusamos marca como descripcion (mejor que perderla)."

Es decir: la comparativa extraída por IA trae una columna `marca` (ej. "ELEA") pero
el schema de `ofertas_items` no tiene una columna `marca` dedicada — solo
`descripcion`. En vez de descartar ese dato (que sí tiene valor informativo para el
usuario que revisa la comparativa), se lo reasigna al campo más cercano disponible.

**Trade-off aceptado**: el nombre de la columna (`descripcion`) ya no describe con
precisión su contenido real (una marca comercial, no una descripción de producto).
Cualquier consumidor futuro de `ofertas_items.descripcion` en el contexto de
comparativas debe saber que en la práctica contiene la marca ofertada, no una
descripción libre. Confirmado por test:
`test_validar_comparativa_calcula_posicion_precio_y_adjudicacion_estimada`
(`tests/extraccion/test_service.py:242-243`,
`assert por_proveedor["Proveedor C"]["descripcion"] == "OTRA"` — "OTRA" es el valor
de `marca` en el fixture, no una descripción).

**Alternativa no tomada**: agregar una columna `marca` real a `ofertas_items` (cambio
de schema). No hay evidencia en el código ni en `docs/schema/` de que se haya
evaluado o descartado formalmente — Motivo pendiente de definición funcional.

## D-EXTRACCIONVALIDACION-003 — `orden_compra` queda fuera de alcance de este caso de uso

**Decisión**: `validar_extraccion` no implementa materialización para
`document_type == "orden_compra"`, aunque el tipo está declarado en
`DocumentType` (`models.py:5`) y `ordenes_compra` es una tabla real del schema
(`docs/schema/extractor_final.sql:607-630`, con columnas propias de versionado
`es_vigente`/`reemplaza_id`/`motivo_version` — mismo patrón que `comparativas`).

**Motivo**: no documentado explícitamente en el código (el comentario/mensaje de
`service.py:286-289` describe el síntoma — "todavía no tiene materialización
implementada" — no la razón de negocio de por qué se dejó para después). Pendiente
de definición funcional; hipótesis razonable no confirmada: la materialización de
`comparativa` e `items_proceso` cubre los flujos de licitación/cotización y
comparativa de precios, mientras que "orden de compra" probablemente representa un
paso posterior del pipeline (post-adjudicación) que todavía no se construyó — el
propio schema de `ordenes_compra` incluye `numero_oc`, `fecha_emision`,
`cantidad_entregas`, campos que no tienen equivalente en el CSV de comparativa/
licitación consumido hoy por este módulo.

**Evidencia de que es una omisión reconocida, no un olvido**: el `else` de
`validar_extraccion` (`service.py:286-289`) levanta un error de dominio explícito
(`ValidationError`) con mensaje descriptivo, en vez de fallar silenciosamente o con
un `KeyError`/excepción no controlada — señal de que el caso se previó y se decidió
excluir deliberadamente del alcance actual. Confirmado por test:
`test_validar_orden_compra_no_implementado`
(`tests/extraccion/test_service.py:172-189`).
