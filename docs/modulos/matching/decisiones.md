# Decisiones de diseño — Matching

## D-MATCHING-001 — Alias del cliente antes que fuzzy matching, sin excepción

**Decisión**: si existe un alias vigente para el cliente y la descripción
normalizada del renglón, se usa siempre, sin correr el fuzzy matching ni comparar
scores con él.

**Motivo**: no documentado explícitamente en un comentario de código dentro de
`matching/`. Pendiente de definición funcional en cuanto al "por qué" formal, pero
consistente con el propósito declarado de la tabla en el propio schema
(`docs/schema/extractor_final.sql:271`): "Cuando un humano confirma que 'IBUPROFENO
600MG X30' del Hospital X es el producto MED-483, queda acá. La próxima vez que ese
cliente use esa descripción, el matching es automático. El sistema aprende el
vocabulario de cada cliente." Un alias representa una confirmación humana previa
exacta para ese cliente — una decisión ya tomada por una persona, con más certeza que
cualquier score heurístico de similitud de texto contra el catálogo general.

**Trade-off aceptado**: si el catálogo cambia (el producto del alias se descontinúa,
por ejemplo) el alias sigue resolviendo matching automático hacia ese `producto_id`
sin ninguna revalidación contra el estado actual de `productos` — `procesar_matching_item`
no verifica `productos.activo` ni `deleted_at` del producto del alias, solo lo hace
para el pool de candidatos fuzzy (`repo.listar_productos_activos`,
`repository.py:40-49`). Ver [`pendientes.md`](./pendientes.md).

## D-MATCHING-002 — Umbral de sugerencia fijo en 70, sin parametrizar

**Decisión**: `_UMBRAL_SUGERIDO = Decimal("70")` (`service.py:13`) es una constante
de módulo, no configurable por droguería, por cliente ni por tipo de producto.

**Motivo**: no documentado explícitamente en el código — no hay comentario que
explique por qué 70 y no otro valor. Motivo pendiente de definición funcional. El
valor de 70 sobre una escala 0-100 de `rapidfuzz.fuzz.WRatio` es un punto medio-alto
típico de heurísticas de similitud de texto en la literatura de la librería, pero no
hay evidencia en este repositorio de un análisis o benchmark documentado que lo
respalde para este dominio (nombres de productos farmacéuticos/insumos médicos).

**Alternativa no tomada**: umbral configurable por `drogueria_id` (como sí ocurre con
otras reglas de negocio en `reglas_pricing`, ver `../presupuestos/`). No hay
evidencia en el código ni en el schema de que se haya evaluado formalmente.

## D-MATCHING-003 — Solo se implementa `metodo="fuzzy"`, pese a declarar 4 métodos posibles

**Decisión**: `MetodoMatching` (`models.py:7`) declara `"exact" | "fuzzy" |
"embedding" | "manual"`, y el `CHECK` de schema (`ck_mc_metodo`,
`docs/schema/extractor_final.sql:459`) los permite los 4 — pero el código de
`matching/` solo genera candidatos con `metodo="fuzzy"` (`service.py:32`).

**Motivo**: no documentado explícitamente. Es una lectura razonable —no confirmada
en código ni comentarios— que el tipo se diseñó pensando en una evolución futura del
matching (por ejemplo, un método `"exact"` para coincidencia literal de texto antes
de gastar el costo de un fuzzy, o `"embedding"` para similitud semántica vía modelo
de lenguaje) que todavía no se construyó. El valor `"manual"` en particular sugiere
que se contempló registrar en `matching_candidatos` un candidato agregado por un
humano (distinto de simplemente marcar `elegido=True` sobre uno fuzzy) — tampoco
implementado: `confirmar_matching` nunca inserta una fila nueva en
`matching_candidatos`, solo actualiza `elegido` sobre filas preexistentes
(RN-MATCHING-006).

**Estado**: sin implementación de los 3 métodos restantes en este módulo — ver
[`pendientes.md`](./pendientes.md).

## D-MATCHING-004 — Top-5 candidatos, no top-3 ni top-10

**Decisión**: `_TOP_K = 5` (`service.py:14`).

**Motivo**: no documentado explícitamente en el código. Motivo pendiente de
definición funcional — es un valor de compromiso típico entre dar suficientes
opciones al humano que confirma manualmente (cuando el mejor candidato no supera el
umbral) sin saturar la UI de opciones, pero no hay evidencia de que se haya evaluado
formalmente contra otros valores.

## D-MATCHING-005 — `confirmar_matching` no valida que el `producto_id` exista ni esté activo

**Decisión**: `confirmar_matching` (`service.py:144-190`) recibe `producto_id: str`
del body (`ConfirmarMatchingRequest`, `models.py:26-27`) y lo escribe directo en
`items_proceso.producto_id` y, si corresponde, en un alias nuevo — sin ningún
`SELECT` previo contra `productos` para confirmar que ese `id` existe, está activo, o
pertenece a la misma droguería del renglón.

**Motivo**: no documentado explícitamente. Confirmado por lectura completa de
`confirmar_matching` y de `matching/repository.py` en esta sesión: ninguna función
de este módulo hace `SELECT ... FROM productos WHERE id = producto_id`. Sí existe una
`FOREIGN KEY` de base de datos sobre `items_proceso.producto_id`
(`fk_ip_prod`, `docs/schema/extractor_final.sql:1092`, `REFERENCES productos (id)`,
sin `ON DELETE`) y otra equivalente sobre `matching_candidatos.producto_id`
(`fk_mc_prod`, `extractor_final.sql:1095`) — ambas fallarían en tiempo de `UPDATE`/
`INSERT` si el `producto_id` no existe **en absoluto**, pero ninguna de las dos
protege contra un `producto_id` real que pertenezca a **otra** droguería o que esté
inactivo/borrado lógicamente (`productos.activo=False` o `deleted_at` seteado) — esas
dos condiciones solo se filtran en `listar_productos_activos`
(`repository.py:40-49`), que no interviene en el camino de confirmación manual. Ver
[`pendientes.md`](./pendientes.md).
