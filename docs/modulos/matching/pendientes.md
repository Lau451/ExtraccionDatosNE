# Pendientes — Matching

Auditoría técnica P1 (bloqueante/riesgo alto) / P2 (riesgo medio, corregir pronto) /
P3 (mejora, sin urgencia).

## P1 — `_generar_candidatos` trae TODOS los productos activos a memoria y corre fuzzy matching en Python, sin paginar ni limitar

`_generar_candidatos` (`service.py:17-36`) llama a `repo.listar_productos_activos`
(`repository.py:40-49`):

```python
def listar_productos_activos(client: Client, *, drogueria_id: str) -> list[dict[str, Any]]:
    resultado = (
        client.table("productos")
        .select("id, nombre")
        .eq("drogueria_id", drogueria_id)
        .eq("activo", True)
        .is_("deleted_at", None)
        .execute()
    )
    return resultado.data
```

Sin `.limit(...)`, sin `.range(...)`, sin ningún filtro adicional (por categoría, por
texto, por prefijo) que reduzca el conjunto antes de traerlo a memoria del proceso
Python. El único filtro es `drogueria_id + activo=True + deleted_at IS NULL` — es
decir, **el catálogo completo activo de una droguería**, en una sola llamada.

Después, `rapidfuzz.process.extract(descripcion_normalizada, choices,
scorer=fuzz.WRatio, limit=5)` (`service.py:25-27`) itera ese diccionario completo en
el proceso Python del backend, calculando `WRatio` contra cada nombre normalizado.
Esto ocurre **una vez por cada renglón** que se procesa: `procesar_matching_item` se
llama en un `for` por cada `item_proceso` creado en `_materializar_licitacion`
(`extraccion/service.py:88-91`) — una licitación de N renglones sin alias dispara N
`SELECT`es completos de `productos` y N pasadas de fuzzy sobre todo el catálogo.

**Qué tan grave es, matizado**:

- **No hay ningún límite implícito en el código.** No se encontró paginación,
  `LIMIT` de SQL, cache entre llamadas del mismo request, ni un índice de texto
  (`pg_trgm`, `tsvector`) que reduzca el trabajo antes de traer las filas. Cada
  llamada a `procesar_matching_item` repite el `SELECT` completo, aunque el conjunto
  de productos no haya cambiado entre renglones del mismo proceso comercial —
  `_generar_candidatos` no cachea `productos` a nivel de la corrida completa de
  `_materializar_licitacion`, cada renglón dispara su propio `SELECT`.
- **El costo es lineal en el tamaño del catálogo activo**, no en el tamaño de la
  respuesta (top-5). Con un catálogo de cientos de productos esto es transferencia de
  red + trabajo en Python asumible; con miles o decenas de miles (un catálogo
  farmacéutico real de una droguería puede tener ese orden de magnitud, ver
  `docs/modulos/catalogo/` para el volumen esperado — no verificado con datos reales
  en esta sesión) el costo por renglón crece proporcionalmente, y N renglones lo
  multiplican otra vez.
- **Sí existe un atajo real que reduce la frecuencia del problema**: el camino de
  alias (RN-MATCHING-001) evita el fuzzy por completo para cualquier cliente que ya
  tenga vocabulario aprendido — en un flujo de trabajo maduro (mismos clientes
  reenviando pliegos con descripciones similares), la proporción de renglones que
  efectivamente llegan al `SELECT` completo de `productos` debería bajar con el
  tiempo. Esto mitiga la frecuencia, no el costo por ocurrencia cuando sí ocurre.
- **No se encontró ningún índice funcional o de texto** sobre `productos.nombre` en
  el schema (`docs/schema/extractor_final.sql`) pensado para acelerar búsquedas por
  similitud (ej. `pg_trgm` + `GIN`) — el fuzzy matching es 100% client-side en
  Python, no delega ningún prefiltrado a Postgres.

**Recomendación** [RECOMENDACIÓN]: evaluar prefiltrado en base de datos antes de
traer candidatos a Python — por ejemplo, un índice `pg_trgm` sobre
`productos.nombre` con un operador de similitud (`%`, `similarity()`) para acotar el
`SELECT` a un conjunto ya pre-ordenado o al menos reducido antes de aplicar
`rapidfuzz`, o cachear `listar_productos_activos` a nivel de la corrida completa de
`_materializar_licitacion` (un solo `SELECT` por proceso comercial, no uno por
renglón) como mejora incremental de menor esfuerzo que no requiere cambios de schema.

## P2 — `proveedor_producto_alias` sin ningún código propio

Confirmado por lectura completa de `matching/repository.py` y `matching/service.py`
en esta sesión: ninguna función lee ni escribe `proveedor_producto_alias`, pese a que
la tabla existe en el schema con las mismas columnas que `cliente_producto_alias`
(`docs/schema/extractor_final.sql:956-973`). El propio código lo reconoce
explícitamente (`repository.py:65-68`):

```python
# proveedor_producto_alias (espejo por proveedor de cliente_producto_alias, §2 del spec)
# no tiene ningún código propio todavía -- ni lectura ni escritura. Scope futuro, igual
# que orden_compra/compras vs. comparativas en su momento: no bloquea el cierre de esta
# ronda porque nada del pipeline actual depende de esa tabla.
```

Y `services/presupuestacion/ROADMAP.md:43-49` documenta el mismo hallazgo, agregando
que fue confirmado explícitamente durante una auditoría de seguridad previa: "No
bloquea el matching cliente→producto que sí está implementado; el matching
proveedor→producto nunca se pidió construir en esta ronda."

**Impacto**: el matching proveedor→producto (útil para `comparativas/`, donde
distintos proveedores nombran el mismo insumo de formas distintas, según el
comentario de la propia tabla) no tiene ningún soporte de código — ni un
`repository.py` propio, ni integración con `comparativas/`. No se auditó en esta
sesión si `comparativas/` tiene su propia lógica de matching de proveedor
independiente (fuera del alcance de este módulo) — si la tiene, sería una
implementación paralela no relacionada con esta tabla; si no la tiene, el matching de
oferta↔producto en comparativas se resuelve hoy exclusivamente por
`numero_renglon` (ver `../extraccion_validacion/reglas.md` RN-EXTRACCIONVALIDACION-009),
no por nombre de producto.

**No es una omisión accidental**: el comentario en el código y en `ROADMAP.md` son
explícitos en que esto quedó fuera de alcance deliberadamente, con precedente
comparable (`orden_compra` sin materialización en `extraccion/`, ver
`../extraccion_validacion/decisiones.md` D-EXTRACCIONVALIDACION-003).

## P2 — Riesgo de escalabilidad sin mitigación de código (ver P1) combinado con ausencia de rate limiting o cola

No se encontró en este módulo, ni en `extraccion/service.py` (su único caller),
ningún mecanismo de cola, procesamiento asíncrono o batching que amortigüe el costo
descrito en P1 cuando se valida una licitación con muchos renglones de una sola vez.
`_materializar_licitacion` procesa el `for` de matching de forma síncrona, dentro del
mismo request HTTP que crea los `items_proceso` (`extraccion/service.py:86-91`) — un
pliego de licitación con cientos de renglones sin alias previo mantendría el request
HTTP abierto por la suma de cientos de `SELECT`+fuzzy secuenciales. No se midió
tiempo real de respuesta en esta sesión (fuera de alcance de una auditoría de
código).

## P3 — `MetodoMatching` declara 4 valores; el código solo produce `"fuzzy"`

Ver RN-MATCHING-004 y D-MATCHING-003. `"exact"`, `"embedding"` y `"manual"` son
valores permitidos por el tipo y por el `CHECK` de schema (`ck_mc_metodo`) sin
ninguna función que los asigne. No es un bug — es superficie de tipo más amplia que
la implementación actual, probablemente pensada para una evolución futura no
confirmada en el código.

## P3 — `marcar_candidato_elegido` no verifica que la fila exista (RN-MATCHING-006)

`repo.marcar_candidato_elegido` (`repository.py:97-100`) es un `UPDATE` condicional
sin `rowcount` ni verificación posterior. Si `confirmar_matching` se llama con un
`producto_id` que nunca apareció entre los candidatos generados (matching manual
directo desde el catálogo, sin pasar por sugerencia fuzzy), el `UPDATE` es un no-op
silencioso — comportamiento correcto en la práctica (no hay nada que marcar como
elegido si no hubo candidatos), pero no hay ningún test en
`tests/matching/test_service.py` que ejercite explícitamente ese camino (todos los
tests de confirmación que verifican `matching_candidatos` siembran una fila de
candidato de antemano). Ver [`api.md`](./api.md).

## P3 — `marcar_sin_match` no limpia `alias_id` (RN-MATCHING-007)

Un renglón que pasa de `automatico`/`confirmado` (con `alias_id` seteado) a
`sin_match` conserva el `alias_id` viejo en la fila de `items_proceso`, aunque
`producto_id` quede `NULL`. No se encontró ningún consumidor de `items_proceso.alias_id`
fuera de este módulo en esta sesión que dependa de que ese campo sea coherente con
`estado_matching`, por lo que el impacto funcional confirmado es bajo — se deja
como hallazgo de consistencia de datos, no de comportamiento observable roto.

## P3 — Validación de tenant duplicada entre routers (mismo patrón ya señalado en otros módulos)

`_validar_item_de_la_drogueria` (`router.py:22-37`) reimplementa, con nombre de
función idéntico al de `presupuestos/router.py:42`, el mismo patrón de chequeo
manual de `drogueria_id` que existe también en `clientes/service.py`,
`compras/router.py` y `comparativas/router.py` (ver [`arquitectura.md`](./arquitectura.md)
para el detalle completo de call sites). No hay una función compartida en `core/`
para esto — cada módulo la reescribe. Riesgo: si la regla de negocio de pertenencia
de tenant cambiara (por ejemplo, permitir acceso cross-droguería a un rol nuevo), 
habría que tocar N implementaciones independientes de forma consistente.

## P3 — Ningún test cubre `router.py` directamente

Los 11 tests de `tests/matching/test_service.py` llaman a `procesar_matching_item`,
`confirmar_matching` y `marcar_sin_match` (el service) directamente con
`service_client`, nunca a través de un endpoint HTTP. No hay evidencia en esta
sesión de un test que ejercite `router.py:22-69` — `_validar_item_de_la_drogueria`,
el chequeo de roles, o `GET /matching/pendientes` contra la vista real vía FastAPI
`TestClient`. El comportamiento del router está documentado por lectura de código
(ver [`casos_de_uso.md`](./casos_de_uso.md)), no verificado por test automatizado
dentro de este módulo. Mismo patrón que
`../extraccion_validacion/pendientes.md` P3 documenta para su propio router.
